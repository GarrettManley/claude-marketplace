#!/usr/bin/env python3
"""SessionStart hook: inject the orchestration defaults as additional context.

Emits the bundled ``context/agent-orchestration.md`` policy (the agent/Workflow
orchestration baseline) into the session via the standard SessionStart
``additionalContext`` channel, so the policy travels with the plugin instead of
living in a user-level ``~/.claude/context`` file.

Output contract (Claude Code SessionStart hook):
    {"hookSpecificOutput": {"hookEventName": "SessionStart",
                            "additionalContext": "<policy markdown>"}}

Fails open: any error prints nothing and exits 0, so a missing/garbled policy
file never blocks session start.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

CONTEXT_FILE = Path(__file__).resolve().parent.parent / "context" / "agent-orchestration.md"


def strip_frontmatter(text: str) -> str:
    """Drop a leading ``---`` YAML frontmatter block if present."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[text.find("\n", end + 1) + 1 :].lstrip("\n")
    return text


def main() -> int:
    try:
        body = strip_frontmatter(CONTEXT_FILE.read_text(encoding="utf-8")).strip()
    except OSError:
        return 0
    if not body:
        return 0
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": body,
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
