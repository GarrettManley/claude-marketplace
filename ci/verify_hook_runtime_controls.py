#!/usr/bin/env python3
# ci/verify_hook_runtime_controls.py
"""Verify how plugin hooks are launched. Two rules:

1. Every gated plugin's hook commands go through run_with_flags.py.

   Without this check, a contributor could add a hook to a gated plugin's
   hooks.json that bypasses the runtime controls — silently breaking
   DISCIPLINE_HOOK_PROFILE / DISCIPLINE_DISABLED_HOOKS (and the equivalent
   learning/stewardship env vars) for that specific hook. CI rejection on
   first review is the cheapest fix.

2. No plugin registers a `uv run` hook in shell form (scan_launch_form).

   Claude Code runs a shell-form command through a shell (on Windows, two
   Git Bash processes per hook command) before uv starts. Exec form —
   `"command": "uv"` plus an `"args"` array — starts uv directly, so every
   `uv run` hook must use it. Shell form stays allowed for commands that
   need a shell (`bash <script>.sh`, `.cmd` shims).

Accepted limitations of rule 1 (intentional, not bugs):
  (a) The all-commands-must-wrap rule has no per-hook opt-out. A bypassing
      hook must fail CI, not be quietly excused.
  (b) The check is a substring match on the command string (shell form) or
      on `command` and each `args` element (exec form), so a wrapper merely
      named in a comment or an unexecuted argument would pass. This is a
      pre-existing false-negative vector, acceptable for a first-line gate.
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


def _launch_words(entry: dict) -> list[str] | None:
    """What a hook entry launches: `command` alone in shell form, `command`
    followed by each `args` element in exec form (Claude Code starts the
    executable directly, without a shell, when `args` is present). None when
    either field has the wrong type."""
    cmd = entry.get("command")
    args = entry.get("args", [])
    if not isinstance(cmd, str) or not isinstance(args, list):
        return None
    if not all(isinstance(arg, str) for arg in args):
        return None
    return [cmd, *args]


def _read_entries(name: str, hooks_json: Path) -> tuple[list[tuple[str, dict]], list[str]]:
    """Read one plugin's hooks.json. Returns the hook entries, each paired with
    a "<plugin>: <event> / matcher <m>" label for violation messages, and the
    problems that stopped the file from being read in full (invalid JSON, a
    structure that is not event -> matchers -> hooks)."""
    try:
        data = json.loads(hooks_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [], [f"{name}: invalid JSON: {e}"]

    entries: list[tuple[str, dict]] = []
    try:
        for event, matchers in data.get("hooks", {}).items():
            for matcher in matchers:
                where = f"{name}: {event} / matcher {matcher.get('matcher')!r}"
                for entry in matcher.get("hooks", []):
                    if not isinstance(entry, dict):
                        raise TypeError(f"hook entry is not an object: {entry!r}")
                    entries.append((where, entry))
    except (TypeError, AttributeError) as e:
        return entries, [f"{name}: malformed hooks.json structure: {e}"]
    return entries, []


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

        entries, problems = _read_entries(name, hooks_json)
        violations.extend(problems)
        for where, entry in entries:
            words = _launch_words(entry)
            if words is None:
                violations.append(
                    f"{where} :: command must be a string and args a list "
                    f"of strings: command={entry.get('command')!r} "
                    f"args={entry.get('args')!r}"
                )
                continue
            if not any(WRAPPER_SUBSTR in word for word in words):
                violations.append(f"{where} :: {' '.join(words)}")

    return violations


def scan_launch_form(root: Path) -> list[str]:
    """Return a violation string for every hook, in any plugin under root,
    whose shell-form `command` starts with `uv run`, plus one for every
    hooks.json that cannot be read. Pure function, like scan()."""
    violations: list[str] = []
    for hooks_json in sorted(root.glob("plugins/*/hooks/hooks.json")):
        entries, problems = _read_entries(hooks_json.parent.parent.name, hooks_json)
        violations.extend(problems)
        for where, entry in entries:
            cmd = entry.get("command")
            if "args" in entry or not isinstance(cmd, str):
                continue
            if cmd.split()[:2] == ["uv", "run"]:
                violations.append(f"{where} :: {cmd}")
    return violations


def main(root: Path = REPO_ROOT) -> int:
    bypasses = scan(root)
    # A gated plugin's unreadable hooks.json is already in `bypasses`.
    shell_form = [v for v in scan_launch_form(root) if v not in bypasses]

    if bypasses:
        print(
            "verify_hook_runtime_controls: the following hooks bypass run_with_flags.py "
            "(or violate the GATED_PLUGINS consistency assertion):\n",
            file=sys.stderr,
        )
        for v in bypasses:
            print(f"  {v}", file=sys.stderr)
        print(
            "\nEvery command in a gated plugin's hooks/hooks.json must invoke "
            "scripts/run_with_flags.py so its runtime-control env vars apply "
            "uniformly, and GATED_PLUGINS must match the plugins that ship the "
            "wrapper.",
            file=sys.stderr,
        )

    if shell_form:
        print(
            "verify_hook_runtime_controls: the following hooks run `uv run` in shell "
            "form (or sit in a hooks.json that cannot be read):\n",
            file=sys.stderr,
        )
        for v in shell_form:
            print(f"  {v}", file=sys.stderr)
        print(
            "\nA hook that runs `uv run ...` must be registered in exec form so "
            'Claude Code starts it without a shell: use "command": "uv" plus an '
            '"args" array holding the remaining words, one element per word '
            '(for example "args": ["run", "--no-project", '
            '"${CLAUDE_PLUGIN_ROOT}/hooks/my_hook.py"]).',
            file=sys.stderr,
        )

    if bypasses or shell_form:
        return 1

    print("verify_hook_runtime_controls: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
