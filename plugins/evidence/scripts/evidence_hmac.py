"""HMAC override token framework for the evidence plugin.

A "override token" is a signed grant that lets an evidence-discipline hook
bypass its block decision for a specific action. Tokens carry:

- `action`: the named action being bypassed (e.g., `submit_finding`, `network_call`)
- `nbf` / `exp`: not-before and expiration unix timestamps (TTL gate)
- `max_uses`: how many times the token can be redeemed before it's burned
- `nonce`: random per-token, makes each issuance unique

Tokens are HMAC-SHA256 signed with a key file (default `~/.claude/evidence-override-key`).
The key file MUST be readable only by the user (chmod 600). Default 4-hour
max TTL and 5-use max are enforced at issuance.

Single-use redemption persistence uses a sibling file
`<keypath>.redemptions.json` that tracks `{nonce: uses_remaining}`. Hooks
must call `redeem_token()` (which decrements + persists) rather than just
`verify_token()` if they want enforce-once semantics.

Designed so the override key never lives in a git-tracked location.
The default path under `~/.claude/` is *not* part of the marketplace repo.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_KEY_PATH = Path.home() / ".claude" / "evidence-override-key"
MAX_TTL_SECONDS = 4 * 60 * 60  # 4 hours
MAX_USES = 5


@dataclass
class TokenPayload:
    action: str
    nbf: int
    exp: int
    max_uses: int
    nonce: str


def _resolve_key_path(key_path: Path | None) -> Path:
    if key_path is not None:
        return key_path
    env = os.environ.get("EVIDENCE_OVERRIDE_KEY")
    return Path(env) if env else DEFAULT_KEY_PATH


def _read_key(key_path: Path) -> bytes:
    if not key_path.is_file():
        raise FileNotFoundError(
            f"Override key not found at {key_path}. "
            f"Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\" > {key_path}"
        )
    raw = key_path.read_bytes().strip()
    if len(raw) < 32:
        raise ValueError(f"Override key at {key_path} is too short (<32 bytes). Regenerate.")
    return raw


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding)


def issue_token(
    action: str,
    ttl_seconds: int = 3600,
    max_uses: int = 1,
    key_path: Path | None = None,
) -> str:
    """Issue an override token for `action` with the given TTL and use cap.

    Caps enforced at issuance:
      - ttl_seconds <= MAX_TTL_SECONDS (4 hours)
      - max_uses <= MAX_USES (5)

    Returns the token as a single base64url-encoded string with three
    dot-separated parts: `<payload>.<signature>` (compact JWT-like).
    """
    if ttl_seconds <= 0 or ttl_seconds > MAX_TTL_SECONDS:
        raise ValueError(f"ttl_seconds must be in (0, {MAX_TTL_SECONDS}]")
    if max_uses < 1 or max_uses > MAX_USES:
        raise ValueError(f"max_uses must be in [1, {MAX_USES}]")
    if not action or not action.replace("_", "").replace("-", "").isalnum():
        raise ValueError("action must be a non-empty identifier (alnum / _ / -)")

    key = _read_key(_resolve_key_path(key_path))
    now = int(time.time())
    payload = TokenPayload(
        action=action,
        nbf=now,
        exp=now + ttl_seconds,
        max_uses=max_uses,
        nonce=secrets.token_hex(8),
    )
    payload_json = json.dumps(payload.__dict__, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64url(payload_json)
    sig = hmac.new(key, payload_b64.encode("ascii"), hashlib.sha256).digest()
    return f"{payload_b64}.{_b64url(sig)}"


def verify_token(
    token: str,
    expected_action: str,
    key_path: Path | None = None,
    now: int | None = None,
) -> tuple[bool, str, TokenPayload | None]:
    """Validate a token's signature, TTL, and action match.

    Returns (valid, reason, payload). Does NOT decrement use count —
    call redeem_token() to consume a use.
    """
    try:
        payload_b64, sig_b64 = token.split(".", 1)
    except ValueError:
        return False, "malformed token (expected <payload>.<sig>)", None

    try:
        key = _read_key(_resolve_key_path(key_path))
    except (FileNotFoundError, ValueError) as e:
        return False, str(e), None

    expected_sig = hmac.new(key, payload_b64.encode("ascii"), hashlib.sha256).digest()
    try:
        actual_sig = _b64url_decode(sig_b64)
    except Exception:
        return False, "malformed signature", None
    if not hmac.compare_digest(expected_sig, actual_sig):
        return False, "signature mismatch (wrong key or tampered token)", None

    try:
        payload_json = _b64url_decode(payload_b64).decode("utf-8")
        data = json.loads(payload_json)
        payload = TokenPayload(
            action=data["action"], nbf=int(data["nbf"]), exp=int(data["exp"]),
            max_uses=int(data["max_uses"]), nonce=str(data["nonce"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as e:
        return False, f"malformed payload: {e}", None

    now = now if now is not None else int(time.time())
    if now < payload.nbf:
        return False, f"token not yet valid (nbf={payload.nbf}, now={now})", payload
    if now >= payload.exp:
        return False, f"token expired (exp={payload.exp}, now={now})", payload
    if payload.action != expected_action:
        return False, f"action mismatch (token={payload.action}, expected={expected_action})", payload

    return True, "valid", payload


def _redemptions_path(key_path: Path) -> Path:
    return key_path.with_name(key_path.name + ".redemptions.json")


def redeem_token(
    token: str,
    expected_action: str,
    key_path: Path | None = None,
    now: int | None = None,
) -> tuple[bool, str]:
    """Verify the token and consume one use atomically.

    Returns (ok, reason). Persists remaining uses in
    `<keypath>.redemptions.json`. Burns the entry when uses reach 0.

    Race-conditional: multiple processes redeeming the same nonce
    simultaneously could both succeed once. Acceptable for single-user
    workflows; if you need strict serialization, wrap in a file lock.
    """
    valid, reason, payload = verify_token(token, expected_action, key_path, now)
    if not valid or payload is None:
        return False, reason

    resolved_key = _resolve_key_path(key_path)
    redemptions_file = _redemptions_path(resolved_key)
    try:
        existing = json.loads(redemptions_file.read_text(encoding="utf-8")) if redemptions_file.is_file() else {}
    except (json.JSONDecodeError, OSError):
        existing = {}

    # Persist BOTH live and exhausted nonces. Popping on exhaustion would
    # let the same token redeem again next time (get() returns the default).
    remaining = existing.get(payload.nonce, payload.max_uses)
    if remaining <= 0:
        return False, f"token already exhausted (nonce={payload.nonce})"

    remaining -= 1
    existing[payload.nonce] = remaining

    try:
        redemptions_file.write_text(json.dumps(existing), encoding="utf-8")
    except OSError as e:
        return False, f"could not persist redemption: {e}"

    return True, f"redeemed (uses_remaining={remaining})"


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Issue or verify an evidence override token.")
    sub = p.add_subparsers(dest="cmd", required=True)

    issue = sub.add_parser("issue", help="Issue a new token.")
    issue.add_argument("action")
    issue.add_argument("--ttl", type=int, default=3600, help="TTL in seconds (max 14400)")
    issue.add_argument("--uses", type=int, default=1, help="Max redemptions (max 5)")
    issue.add_argument("--key", type=Path, default=None, help="Override key file path")

    verify = sub.add_parser("verify", help="Verify a token without redeeming.")
    verify.add_argument("action")
    verify.add_argument("token")
    verify.add_argument("--key", type=Path, default=None)

    redeem = sub.add_parser("redeem", help="Verify and consume one use.")
    redeem.add_argument("action")
    redeem.add_argument("token")
    redeem.add_argument("--key", type=Path, default=None)

    args = p.parse_args()
    if args.cmd == "issue":
        print(issue_token(args.action, args.ttl, args.uses, args.key))
    elif args.cmd == "verify":
        ok, reason, _ = verify_token(args.token, args.action, args.key)
        print(f"{'OK' if ok else 'FAIL'}: {reason}")
        raise SystemExit(0 if ok else 1)
    elif args.cmd == "redeem":
        ok, reason = redeem_token(args.token, args.action, args.key)
        print(f"{'OK' if ok else 'FAIL'}: {reason}")
        raise SystemExit(0 if ok else 1)
