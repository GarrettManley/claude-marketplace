#!/usr/bin/env python3
"""
PreToolUse hook: warn when a Bash command truncates history.jsonl without
clearing sibling state files (combat_state.json, snapshots/) that the server
loads on boot.

A stale combat_state.json after ledger truncation causes COMBAT_RECONSTRUCTED
on the next server start, silently restoring phantom combat from a prior session.
"""

import json
import re
import sys

# Match only actual shell operations targeting the file, not mentions inside
# --body strings or heredocs. Require the file path to be an unquoted shell
# token: a redirection target, a direct argument to head/sed/truncate, or
# after a pipe. We strip everything after --body / --message flags first.
_FLAG_BODY_RE = re.compile(r'--(?:body|message|comment)\s+(?:"[^"]*"|\'[^\']*\'|\$\'[^\']*\'|\S+)', re.DOTALL)

TRUNCATION_PATTERN = re.compile(
    r'(?:'
    r'>\s*\S*history\.jsonl'               # redirect: > .../history.jsonl
    r'|head\s+-n\s+\d+\s+\S*history\.jsonl'  # head -n N .../history.jsonl
    r'|sed\s+-i\s+\S+\s+\S*history\.jsonl'   # sed -i 's//' .../history.jsonl
    r'|(?:^|[;&|(]\s*)truncate\s+\S*history\.jsonl'  # truncate at cmd start
    r')',
    re.IGNORECASE | re.MULTILINE,
)

WARNING = (
    "Ledger truncation detected. Before proceeding, check for and remove sibling "
    "state files the server loads on boot:\n"
    "  - campaigns/<id>/combat_state.json  (persists encounter state independently of the ledger)\n"
    "  - campaigns/<id>/snapshots/         (may reference blocks beyond the truncation point)\n"
    "Stale files loaded after ledger truncation silently reconstruct invalid world state.\n"
    "See CLAUDE.md §Pitfalls — 'combat_state.json survives ledger truncation'."
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    command = payload.get("tool_input", {}).get("command", "")
    # Strip flag-body strings so mentions inside --body/--message don't trigger.
    command_stripped = _FLAG_BODY_RE.sub("", command)
    if TRUNCATION_PATTERN.search(command_stripped):
        print(json.dumps({"decision": "block", "reason": WARNING}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
