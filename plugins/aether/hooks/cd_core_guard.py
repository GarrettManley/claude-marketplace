"""PreToolUse hook: warn against `cd core && cargo …` (cwd-leak idiom).

Bash tool calls share working directory across invocations. After
`cd core && cargo test`, the next relative path resolves under `core/`
and silently breaks (e.g. `universe/characters/druid_harness.json` →
not found). The fix is to use `--manifest-path` instead of `cd`.

Documented in CLAUDE.md as a T3.5 lesson. This hook surfaces the
warning at the moment the bad command is staged, not after it bites.

Behavior:
  - Exit 2 (block) when a Bash command starts with `cd core && cargo …`
  - Exit 0 (allow) otherwise
  - The block message offers the corrected form

The hook is intentionally narrow: only `cd core && cargo …` is blocked.
`cd core && cargo build --release` is the canonical first-time build
recipe in CLAUDE.md so it's allowed via an explicit allowlist of the
build invocation. Test, run, check, doc — anything else with cargo —
should use --manifest-path.
"""
from __future__ import annotations

import json
import re
import sys


# Match: `cd core && cargo <subcommand> ...`
# Allow `cd core && cargo build [...]` as the documented first-build path.
PATTERN = re.compile(r"^\s*cd\s+core\s*&&\s*cargo\s+(\w+)")
ALLOWED_SUBCOMMANDS = {"build"}


BLOCK_MESSAGE = (
    "Blocked: `cd core && cargo {sub}` leaks cwd into the next Bash call.\n"
    "After this command, the next relative path resolves under core/ and\n"
    "silently breaks (e.g. universe/characters/x.json → not found).\n\n"
    "Use --manifest-path instead:\n"
    "  cargo {sub} --manifest-path core/Cargo.toml --release [args]\n\n"
    "Documented in CLAUDE.md (T3.5 lesson). The Common-commands block\n"
    "still shows `cd core && cargo build --release` for first-time setup,\n"
    "which IS allowed by this hook. Other subcommands (test, check, run,\n"
    "doc) require --manifest-path.\n"
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if payload.get("tool_name") != "Bash":
        return 0

    command = payload.get("tool_input", {}).get("command", "")
    if not command:
        return 0

    match = PATTERN.match(command)
    if not match:
        return 0

    subcommand = match.group(1)
    if subcommand in ALLOWED_SUBCOMMANDS:
        return 0

    print(BLOCK_MESSAGE.format(sub=subcommand), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
