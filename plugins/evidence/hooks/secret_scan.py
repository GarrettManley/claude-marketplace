#!/usr/bin/env python3
"""PreToolUse hook: scan tool inputs for credential / secret patterns.

Blocks Bash commands and Edit/Write/MultiEdit/NotebookEdit content that contain known
secret patterns (AWS access keys, GitHub PATs, OpenAI keys, Anthropic
keys, Stripe keys, generic high-entropy strings in obvious credential
contexts).

This is a defense-in-depth check, not a complete secret scanner. It
catches the obvious patterns; for thorough scanning use a tool like
`gitleaks` or `trufflehog` in CI.

Override: a redeemed override token for action `secret_scan` skips the
block. Set EVIDENCE_OVERRIDE_TOKEN env var to provide it.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Make the plugin's scripts/ importable for the HMAC framework
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# (label, regex, sample-redaction)
PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("AWS Access Key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AKIA****"),
    (
        "AWS Secret (regex)",
        re.compile(r"\baws[_-]?secret[_-]?(access[_-]?)?key\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?", re.IGNORECASE),
        "<aws-secret>",
    ),
    ("GitHub PAT (classic)", re.compile(r"\bghp_[A-Za-z0-9]{36}\b"), "ghp_****"),
    ("GitHub OAuth", re.compile(r"\bgho_[A-Za-z0-9]{36}\b"), "gho_****"),
    ("GitHub User Token", re.compile(r"\bghu_[A-Za-z0-9]{36}\b"), "ghu_****"),
    ("GitHub Server Token", re.compile(r"\bghs_[A-Za-z0-9]{36}\b"), "ghs_****"),
    ("GitHub Refresh Token", re.compile(r"\bghr_[A-Za-z0-9]{36}\b"), "ghr_****"),
    ("OpenAI API Key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"), "sk-****"),
    ("Anthropic API Key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"), "sk-ant-****"),
    ("Stripe Live Key", re.compile(r"\bsk_live_[A-Za-z0-9]{24,}\b"), "sk_live_****"),
    ("Slack Bot Token", re.compile(r"\bxoxb-[A-Za-z0-9-]{20,}\b"), "xoxb-****"),
    ("Slack User Token", re.compile(r"\bxoxp-[A-Za-z0-9-]{20,}\b"), "xoxp-****"),
    ("Generic Bearer (regex)", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{40,}", re.IGNORECASE), "Bearer ****"),
    (
        "Private Key Block",
        re.compile(r"-----BEGIN\s+(RSA\s+|OPENSSH\s+|EC\s+|DSA\s+)?PRIVATE\s+KEY-----"),
        "<private-key-block>",
    ),
]


def extract_text(tool_name: str, tool_input: dict) -> str:
    """Concatenate all the user-supplied text from a tool input."""
    parts = []
    if tool_name == "Bash":
        parts.append(tool_input.get("command", ""))
    elif tool_name == "Write":
        parts.append(tool_input.get("content", ""))
        parts.append(tool_input.get("file_path", ""))
    elif tool_name == "Edit":
        parts.append(tool_input.get("new_string", ""))
        parts.append(tool_input.get("file_path", ""))
    elif tool_name == "MultiEdit":
        parts.append(tool_input.get("file_path", ""))
        for edit in tool_input.get("edits", []):
            parts.append(edit.get("new_string", ""))
    elif tool_name == "WebFetch":
        # URL might encode credentials but params/headers don't pass through here
        parts.append(tool_input.get("url", ""))
    elif tool_name == "NotebookEdit":
        parts.append(tool_input.get("new_source", ""))
        parts.append(tool_input.get("notebook_path", ""))
    return "\n".join(parts)


def check_text(text: str) -> list[tuple[str, str]]:
    """Return list of (label, matched-substring) for each detected pattern."""
    hits = []
    for label, pattern, _ in PATTERNS:
        for m in pattern.finditer(text):
            hits.append((label, m.group(0)))
    return hits


def check_override(action: str = "secret_scan") -> bool:
    """Check for a valid override token in EVIDENCE_OVERRIDE_TOKEN env var."""
    token = os.environ.get("EVIDENCE_OVERRIDE_TOKEN")
    if not token:
        return False
    try:
        from evidence_hmac import redeem_token
    except ImportError:
        return False
    ok, _ = redeem_token(token, action)
    return ok


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    text = extract_text(tool_name, tool_input)
    if not text:
        return 0

    hits = check_text(text)
    if not hits:
        return 0

    if check_override():
        sys.stderr.write(
            f"[secret_scan] {len(hits)} hit(s) detected but override token redeemed; allowing.\n"
        )
        return 0

    msg_lines = [
        f"Blocked: secret_scan detected {len(hits)} potential credential pattern(s).",
        "Each match should be redacted, replaced with an env var reference, or moved out of the tool input.",
        "",
        "Detections:",
    ]
    for label, matched in hits[:5]:
        # Show only first 8 chars + length to avoid leaking the secret in the block message
        preview = matched[:8] + f"... ({len(matched)} chars)"
        msg_lines.append(f"  - {label}: {preview}")
    msg_lines.append("")
    msg_lines.append("Override (use sparingly): issue a token with")
    msg_lines.append("  python <plugin>/scripts/evidence_hmac.py issue secret_scan --ttl 60 --uses 1")
    msg_lines.append("then re-run with EVIDENCE_OVERRIDE_TOKEN=<token> in the environment.")

    sys.stderr.write("\n".join(msg_lines) + "\n")
    return 2  # block


if __name__ == "__main__":
    sys.exit(main())
