#!/usr/bin/env python3
# ci/verify_hook_runtime_controls.py
"""Verify every gated plugin's hook commands go through run_with_flags.py.

Without this check, a contributor could add a hook to a gated plugin's
hooks.json that bypasses the runtime controls — silently breaking
DISCIPLINE_HOOK_PROFILE / DISCIPLINE_DISABLED_HOOKS (and the equivalent
learning/stewardship env vars) for that specific hook. CI rejection on first
review is the cheapest fix.

Accepted limitations (intentional, not bugs):
  (a) The all-commands-must-wrap rule has no per-hook opt-out. A bypassing
      hook must fail CI, not be quietly excused.
  (b) The check is a substring match on the command string, so a wrapper
      merely named in a comment or an unexecuted argument would pass. This
      is a pre-existing false-negative vector, acceptable for a first-line
      gate.
  (c) The match requires the literal forward-slash form
      "scripts/run_with_flags.py". Every hooks.json in this repo already
      uses that form via "${CLAUDE_PLUGIN_ROOT}/scripts/...".

Exit 0 on clean; exit 1 with per-violation report on miss.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WRAPPER_SUBSTR = "scripts/run_with_flags.py"

# Explicit, auditable list of plugins whose hooks must route through
# run_with_flags.py. Checked for consistency against disk in scan() below —
# a plugin that ships the wrapper but is missing here (or vice versa) is
# itself a violation.
GATED_PLUGINS = ("discipline", "learning", "stewardship")


def _plugins_with_wrapper(root: Path) -> set[str]:
    return {
        p.parent.parent.name
        for p in root.glob("plugins/*/scripts/run_with_flags.py")
    }


def scan(root: Path) -> list[str]:
    """Return violation strings for the gated plugins under root, plus any
    consistency-assertion violations. Pure function, no I/O side effects
    beyond reading files under root."""
    violations: list[str] = []

    on_disk = _plugins_with_wrapper(root)
    gated = set(GATED_PLUGINS)
    for name in sorted(on_disk - gated):
        violations.append(
            f"{name}: ships scripts/run_with_flags.py but is not listed in "
            "GATED_PLUGINS"
        )
    for name in sorted(gated - on_disk):
        violations.append(
            f"{name}: listed in GATED_PLUGINS but has no "
            "scripts/run_with_flags.py"
        )

    # Scan every plugin that is either gated or ships the wrapper on disk —
    # not just GATED_PLUGINS — so a plugin whose listing is itself wrong
    # (finding: wrapper-but-not-gated) still has its actual hooks.json
    # commands enumerated instead of being masked behind the generic
    # consistency-assertion message above.
    for name in sorted(gated | on_disk):
        hooks_json = root / "plugins" / name / "hooks" / "hooks.json"
        if not hooks_json.is_file():
            violations.append(f"{name}: {hooks_json} missing")
            continue

        try:
            data = json.loads(hooks_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            violations.append(f"{name}: invalid JSON: {e}")
            continue

        try:
            for event, matchers in data.get("hooks", {}).items():
                for matcher in matchers:
                    for entry in matcher.get("hooks", []):
                        cmd = entry.get("command")
                        if not isinstance(cmd, str):
                            violations.append(
                                f"{name}: {event} / matcher {matcher.get('matcher')!r} "
                                f":: non-string command: {cmd!r}"
                            )
                            continue
                        if WRAPPER_SUBSTR not in cmd:
                            violations.append(
                                f"{name}: {event} / matcher {matcher.get('matcher')!r} :: {cmd}"
                            )
        except (TypeError, AttributeError) as e:
            violations.append(f"{name}: malformed hooks.json structure: {e}")
            continue

    return violations


def main(root: Path = REPO_ROOT) -> int:
    violations = scan(root)

    if violations:
        print(
            "verify_hook_runtime_controls: the following hooks bypass run_with_flags.py "
            "(or violate the GATED_PLUGINS consistency assertion):\n",
            file=sys.stderr,
        )
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "\nEvery command in a gated plugin's hooks/hooks.json must invoke "
            "scripts/run_with_flags.py so its runtime-control env vars apply "
            "uniformly, and GATED_PLUGINS must match the plugins that ship the "
            "wrapper.",
            file=sys.stderr,
        )
        return 1

    print("verify_hook_runtime_controls: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
