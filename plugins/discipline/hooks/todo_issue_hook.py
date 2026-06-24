#!/usr/bin/env python3
"""PreToolUse hook: block bare TODO/FIXME/XXX/HACK comments without a GitHub issue reference.

Reads the Claude Code tool payload from stdin (JSON).
Exits 2 (blocking) when a newly-added TODO-family comment is found in a source file
without a #NNN issue reference on the same line.
Exits 0 (allow) otherwise.

Source extensions are configurable via DISCIPLINE_SOURCE_EXTENSIONS env var or
`source-extensions` in `.claude/discipline.local.md`. Defaults cover common
languages (TS/JS/Rust/Python/Go/Java/Kotlin/C#).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Make the plugin's scripts/ importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from discipline_config import get_config  # noqa: E402

TODO_PATTERN = re.compile(r'\b(TODO|FIXME|XXX|HACK)\b', re.IGNORECASE)
HEURISTIC_PATTERN = re.compile(r'\b(heuristic|workaround|temporary\s+fix|band-?aid)\b', re.IGNORECASE)
ISSUE_REF_PATTERN = re.compile(r'#\d+')

BLOCK_MESSAGE = (
    "Blocked: added TODO/FIXME/XXX/HACK without a GitHub issue reference.\n"
    "Either:\n"
    "  (a) file a GitHub issue and use TODO(#NNN): your note\n"
    "  (b) handle the work inline and remove the comment\n"
)

HEURISTIC_BLOCK_MESSAGE = (
    "Blocked: added 'heuristic' / 'workaround' / 'temporary fix' label without a tracking issue reference.\n"
    "File a GitHub issue for the correct long-term fix and cite it as #N on the same or adjacent line.\n"
)


def has_source_extension(path: str, source_exts: tuple[str, ...]) -> bool:
    _, ext = os.path.splitext(path)
    return ext.lower() in source_exts


def get_new_lines(tool_name: str, tool_input: dict, source_exts: tuple[str, ...]) -> list[str]:
    """Extract only the newly-added text from the tool input."""
    if tool_name == 'Write':
        path = tool_input.get('file_path', '')
        if not has_source_extension(path, source_exts):
            return []
        return tool_input.get('content', '').splitlines()

    if tool_name in ('Edit', 'MultiEdit'):
        if tool_name == 'Edit':
            edits = [tool_input]
        else:
            edits = tool_input.get('edits', [])

        lines = []
        for edit in edits:
            path = edit.get('file_path', tool_input.get('file_path', ''))
            if not has_source_extension(path, source_exts):
                continue
            new_string = edit.get('new_string', '')
            lines.extend(new_string.splitlines())
        return lines

    return []


def check_lines(lines: list[str]) -> list[str]:
    """Return lines that contain a TODO-family comment without an issue reference."""
    return [line.rstrip() for line in lines
            if TODO_PATTERN.search(line) and not ISSUE_REF_PATTERN.search(line)]


def check_heuristic_lines(lines: list[str]) -> list[str]:
    """Return lines with heuristic/workaround labels missing a nearby issue reference."""
    violations = []
    for i, line in enumerate(lines):
        if not HEURISTIC_PATTERN.search(line):
            continue
        # Accept if this line or either adjacent line carries an issue ref.
        window = lines[max(0, i - 1): i + 2]
        if not any(ISSUE_REF_PATTERN.search(ln) for ln in window):
            violations.append(line.rstrip())
    return violations


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    cfg = get_config()
    tool_name = payload.get('tool_name', '')
    tool_input = payload.get('tool_input', {})

    new_lines = get_new_lines(tool_name, tool_input, cfg.source_extensions)

    violations = check_lines(new_lines)
    if violations:
        print(BLOCK_MESSAGE, file=sys.stderr)
        for v in violations[:5]:
            print(f"  {v}", file=sys.stderr)
        return 2

    heuristic_violations = check_heuristic_lines(new_lines)
    if heuristic_violations:
        print(HEURISTIC_BLOCK_MESSAGE, file=sys.stderr)
        for v in heuristic_violations[:5]:
            print(f"  {v}", file=sys.stderr)
        return 2

    return 0


if __name__ == '__main__':
    sys.exit(main())
