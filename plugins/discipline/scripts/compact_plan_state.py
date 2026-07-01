"""Skill entry point for /discipline:compact-plan (a CLI, not a hook).

Saves the intent note (the one piece of conversation state the filesystem
cannot rediscover) and prints an ASCII digest of the live workflow state,
which the skill uses to template its /compact preservation instructions.
Always exits 0: a broken note-save is reported in the digest, never raised
— it must not block the user from compacting.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from plan_state import gather_workflow_state, write_note  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Save an intent note and print live workflow state before /compact."
    )
    parser.add_argument(
        "--note", default=None, help="One line: current task and exact next step."
    )
    args = parser.parse_args(argv)

    note_line = None
    if args.note:
        try:
            note_line = f"note saved: {write_note(args.note)}"
        except OSError:
            note_line = "note write FAILED"

    workflow = gather_workflow_state()
    emitted = False
    plan = workflow.get("active_plan")
    if isinstance(plan, dict) and plan.get("path"):
        line = f"active plan: {plan['path']} (source: {plan.get('source', 'unknown')})"
        if isinstance(plan.get("tasks_done"), int) and isinstance(plan.get("tasks_open"), int):
            line += f" - {plan['tasks_done']} done / {plan['tasks_open']} open"
        print(line)
        emitted = True
    ledger = workflow.get("sdd_ledger")
    if isinstance(ledger, dict) and ledger.get("path"):
        print(f"sdd ledger: {ledger['path']}")
        emitted = True
    slugs = [
        r["slug"]
        for r in workflow.get("pending_retros") or []
        if isinstance(r, dict) and r.get("slug")
    ]
    if slugs:
        print(f"pending retros: {', '.join(slugs)}")
        emitted = True
    if not emitted:
        print("no workflow state discovered")
    if note_line:
        print(note_line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
