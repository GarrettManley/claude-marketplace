#!/usr/bin/env python3
"""Opt-in PreToolUse hook: confine tool egress/writes to the loaded evidence scope.

NOT registered in the plugin's hooks.json. A consuming project wires this into
its own .claude/settings.json (see the evidence README) and drops a
.claude/evidence-scope.yaml manifest.

Gates structured tools whose URL/path is an explicit input field:
  - WebFetch              -> check_url(url)        [only when the manifest declares `hosts`]
  - Edit/Write/MultiEdit  -> check_path(file_path) [only restrictive when `path_prefixes` set]

Returns 0 (allow) when no manifest is loaded, when the tool is not gated, or
when an out-of-scope op carries a redeemed `scope_binding` override token
(EVIDENCE_OVERRIDE_TOKEN). Out-of-scope ops are blocked with exit 2.
Bash, WebSearch, and Read are intentionally not gated (see ADR-0004).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from scope_binding import check_path, check_url, load_scope  # noqa: E402

_PATH_TOOLS = {"Edit", "Write", "MultiEdit"}


def check_override() -> bool:
    """True if EVIDENCE_OVERRIDE_TOKEN holds a redeemable `scope_binding` token."""
    token = os.environ.get("EVIDENCE_OVERRIDE_TOKEN")
    if not token:
        return False
    try:
        from evidence_hmac import redeem_token
    except ImportError:  # pragma: no cover
        return False
    ok, _ = redeem_token(token, "scope_binding")
    return ok


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    scope = load_scope()
    if not scope.is_loaded:
        return 0  # no manifest -> dormant

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    if tool_name == "WebFetch":
        url = tool_input.get("url")
        # Only gate URLs when the manifest declares an allow-list of hosts; a
        # path-only manifest must not reject every fetch (check_url rejects-all
        # when `hosts` is empty).
        if not url or not scope.hosts:
            return 0
        in_scope, reason = check_url(url, scope)
    elif tool_name in _PATH_TOOLS:
        path = tool_input.get("file_path")
        if not path:
            return 0
        in_scope, reason = check_path(path, scope)
    else:
        return 0

    if in_scope:
        return 0

    if check_override():
        sys.stderr.write(f"[scope_bind] out-of-scope op allowed via override token; {reason}\n")
        return 0

    msg = [
        "Blocked: scope_binding — this operation is outside the loaded engagement scope.",
        f"  {reason}",
        "",
        "Confine the operation to the scope, or override (sparingly):",
        "  python <plugin>/scripts/evidence_hmac.py issue scope_binding --ttl 60 --uses 1",
        "then re-run with EVIDENCE_OVERRIDE_TOKEN=<token> in the environment.",
    ]
    sys.stderr.write("\n".join(msg) + "\n")
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
