#!/usr/bin/env python3
"""Parse/validate/diff helpers for review archetype persona files.

A persona is a markdown file (`agents/<name>.agent.md`) with a YAML-ish
frontmatter block and a body carrying the pushback-triggers, NOT-covered, and
severity-rubric sections. Frontmatter is parsed by regex (stdlib only — no
PyYAML); `_KEY_RE` matches only column-0 keys, so indented continuation lines
of a `description: |` block scalar are correctly ignored.
"""
from __future__ import annotations

import difflib
import os
import re
import tempfile
from pathlib import Path

REQUIRED_SECTIONS = (
    "**Pushback triggers:**",
    "**NOT covered",
    "**Severity rubric:**",
    "**Last updated:**",
)
_REQUIRED_FM_KEYS = ("name", "description", "tools")
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):", re.MULTILINE)
_NAME_RE = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)
_LAST_UPDATED_RE = re.compile(r"^.*\*\*Last updated:\*\*.*$", re.MULTILINE)


def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter-inner, body). Raise ValueError if no frontmatter."""
    m = _FM_RE.match(text)
    if not m:
        raise ValueError("no frontmatter block found")
    return m.group(1), m.group(2)


def frontmatter_keys(fm: str) -> set[str]:
    return set(_KEY_RE.findall(fm))


def extract_name(fm: str) -> str | None:
    m = _NAME_RE.search(fm)
    return m.group(1) if m else None


def last_updated_line(text: str) -> str | None:
    m = _LAST_UPDATED_RE.search(text)
    return m.group(0) if m else None


def validate_persona(text: str, expected_name: str) -> list[str]:
    """Return a list of structural errors (empty = valid)."""
    try:
        fm, body = split_frontmatter(text)
    except ValueError as e:
        return [f"frontmatter: {e}"]
    errors: list[str] = []
    keys = frontmatter_keys(fm)
    for k in _REQUIRED_FM_KEYS:
        if k not in keys:
            errors.append(f"frontmatter missing required key: {k}")
    name = extract_name(fm)
    if name != expected_name:
        errors.append(f"frontmatter name {name!r} != expected {expected_name!r}")
    for section in REQUIRED_SECTIONS:
        if section not in body:
            errors.append(f"body missing required section: {section}")
    return errors


def render_diff(old: str, new: str, path: str) -> str:
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    return "".join(diff)


def atomic_write(path: Path, text: str) -> None:
    """Write atomically (temp file in same dir + os.replace)."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:  # pragma: no cover - cleanup on rare I/O failure
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
