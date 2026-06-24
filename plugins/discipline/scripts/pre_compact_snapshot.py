"""PreCompact hook: gather filesystem state and write a snapshot.

Runs before Claude Code compacts conversation context. The snapshot
preserves enough surface state (git branch, HEAD SHA, top-N recently-
modified files) that a SessionStart hook can re-orient the assistant
after the session resumes.

Emits nothing to stdout — PreCompact stdout is not surfaced as
additionalContext.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from snapshot import gather_state, write_snapshot  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    raw = sys.stdin.read()
    try:
        json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        # Malformed event — still attempt the snapshot (state gathering is
        # event-independent), but be tolerant.
        pass
    try:
        state = gather_state()
        write_snapshot(state)
    except Exception:
        # PreCompact failures must never break compaction. Silent.
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
