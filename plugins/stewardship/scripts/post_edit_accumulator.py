"""PostToolUse hook: record Edit/Write/MultiEdit paths to a per-session tmpfile.

stop_format_typecheck.py reads the accumulator at Stop time and runs
formatter + typechecker once across all edited files per language, instead
of after every Edit.

Adapted from affaan-m/everything-claude-code @ 4774946d,
scripts/hooks/post-edit-accumulator.js. Python port; extension filter
covers TS/JS, Python, and Rust (vs ecc's TS/JS-only filter).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

# Reuse language_detect's extension set
_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from language_detect import LANGUAGES  # noqa: E402

KNOWN_EXTENSIONS = frozenset(
    ext for spec in LANGUAGES.values() for ext in spec["extensions"]
)


def _sanitize(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", value)[:64]


def get_accumulator_path() -> str:
    sid = os.environ.get("CLAUDE_SESSION_ID")
    if sid:
        key = _sanitize(sid)
    else:
        key = hashlib.sha1(os.getcwd().encode("utf-8")).hexdigest()[:12]
    return str(Path(tempfile.gettempdir()) / f"stewardship-edited-{key}.txt")


def _append_path(file_path: str) -> None:
    if not file_path:
        return
    if Path(file_path).suffix.lower() not in KNOWN_EXTENSIONS:
        return
    with open(get_accumulator_path(), "a", encoding="utf-8") as f:
        f.write(file_path + "\n")


def main(argv: list[str] | None = None) -> int:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return 0
    if not isinstance(data, dict):
        return 0
    tool_input = data.get("tool_input") or {}
    _append_path(tool_input.get("file_path") or "")
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict):
            _append_path(edit.get("file_path") or "")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
