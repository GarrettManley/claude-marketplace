#!/usr/bin/env python3
# ci/verify_hook_runtime_controls.py
"""Verify every discipline hook command goes through run_with_flags.py.

Without this check, a contributor could add a hook to hooks.json that bypasses
the runtime controls — silently breaking DISCIPLINE_DISABLED_HOOKS for that
specific hook. CI rejection on first review is the cheapest fix.

Exit 0 on clean; exit 1 with per-violation report on miss.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_JSON = REPO_ROOT / "plugins" / "discipline" / "hooks" / "hooks.json"
WRAPPER_SUBSTR = "scripts/run_with_flags.py"


def main() -> int:
    if not HOOKS_JSON.is_file():
        print(f"verify_hook_runtime_controls: {HOOKS_JSON} missing", file=sys.stderr)
        return 1

    try:
        data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"verify_hook_runtime_controls: invalid JSON: {e}", file=sys.stderr)
        return 1

    violations: list[str] = []
    for event, matchers in data.get("hooks", {}).items():
        for matcher in matchers:
            for entry in matcher.get("hooks", []):
                cmd = entry.get("command", "")
                if WRAPPER_SUBSTR not in cmd:
                    violations.append(f"{event} / matcher {matcher.get('matcher')!r} :: {cmd}")

    if violations:
        print(
            "verify_hook_runtime_controls: the following hooks bypass run_with_flags.py:\n",
            file=sys.stderr,
        )
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "\nEvery command in plugins/discipline/hooks/hooks.json must invoke "
            "scripts/run_with_flags.py so DISCIPLINE_HOOK_PROFILE and "
            "DISCIPLINE_DISABLED_HOOKS apply uniformly.",
            file=sys.stderr,
        )
        return 1

    print("verify_hook_runtime_controls: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
