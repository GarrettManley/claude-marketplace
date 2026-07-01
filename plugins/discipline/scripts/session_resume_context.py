"""SessionStart hook: read the latest PreCompact snapshot for the current
project-key and emit a one-screen summary as additionalContext.

Output contract: JSON to stdout matching Claude Code's hookSpecificOutput
schema for SessionStart:
    {"hookSpecificOutput": {"hookEventName": "SessionStart",
                            "additionalContext": "<text>"}}

If no snapshot exists, exits silently (empty stdout).
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from snapshot import read_snapshot  # noqa: E402
import plan_state  # noqa: E402

MAX_FILES_SHOWN = 10


def _format_timestamp(ts: float) -> str:
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return "unknown time"


def format_snapshot(state: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("## Resume context (from previous compaction)")
    lines.append("")
    ts = state.get("timestamp")
    if isinstance(ts, (int, float)):
        lines.append(f"Snapshot taken: {_format_timestamp(float(ts))}")
        lines.append("")
    git = state.get("git")
    if isinstance(git, dict):
        branch = git.get("branch") or "<unknown>"
        head = git.get("head") or ""
        head_short = head[:8] if len(head) >= 8 else head
        lines.append(f"**Git:** branch `{branch}` @ `{head_short}`")
    else:
        lines.append("**Git:** not in a git repository at snapshot time")
    lines.append("")
    recent = state.get("recent_files") or []
    if recent:
        shown = recent[:MAX_FILES_SHOWN]
        lines.append(f"**Recently touched files (top {len(shown)}):**")
        for entry in shown:
            path = entry.get("path") if isinstance(entry, dict) else None
            if path:
                lines.append(f"- `{path}`")
        if len(recent) > MAX_FILES_SHOWN:
            lines.append(f"- ... and {len(recent) - MAX_FILES_SHOWN} more")
    return "\n".join(lines)


def _format_workflow(
    workflow: dict[str, Any], note: dict[str, Any] | None
) -> list[str]:
    lines: list[str] = []
    plan = workflow.get("active_plan") if isinstance(workflow, dict) else None
    if isinstance(plan, dict) and plan.get("path"):
        detail = f" (via {plan.get('source', 'unknown')})"
        done = plan.get("tasks_done")
        open_ = plan.get("tasks_open")
        if isinstance(done, int) and isinstance(open_, int):
            detail += f" - {done} done / {open_} open"
        lines.append(f"**Active plan:** `{plan['path']}`{detail}")
    retros = workflow.get("pending_retros") or [] if isinstance(workflow, dict) else []
    slugs = [r.get("slug") for r in retros if isinstance(r, dict) and r.get("slug")]
    if slugs:
        # Cap at 5: this lands in every session start; the +N carries the rest.
        shown = ", ".join(slugs[:5])
        more = f" (+{len(slugs) - 5} more)" if len(slugs) > 5 else ""
        lines.append(f"**Pending retros:** {shown}{more}")
    if note:
        when = _format_timestamp(float(note["timestamp"]))
        lines.append(f"**Where you were** (as of {when}): {note['text']}")
    return lines


def main(argv: list[str] | None = None) -> int:
    # Drain stdin (SessionStart events include some metadata; we don't need it
    # but must consume it to avoid breaking pipelines).
    try:
        sys.stdin.read()
    except Exception:
        pass
    parts: list[str] = []
    state = read_snapshot()
    if state is not None:
        parts.append(format_snapshot(state))
    try:
        workflow = plan_state.gather_workflow_state()
        note = plan_state.read_note()
    except Exception:
        # Hook safety: live discovery must never break session start.
        workflow, note = {}, None
    wf_lines = _format_workflow(workflow, note)
    if wf_lines:
        if state is None:
            parts.append("## Workflow context\n\n" + "\n".join(wf_lines))
        else:
            parts.append("\n".join(wf_lines))
    if not parts:
        return 0
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n\n".join(parts),
        }
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
