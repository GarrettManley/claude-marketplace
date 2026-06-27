#!/usr/bin/env python3
"""Lint skill/agent/command frontmatter: presence + parseability, nothing subjective.

Checks every plugins/*/skills/*/SKILL.md, plugins/*/agents/*.md, and
plugins/*/commands/*.md for:
  - a frontmatter block (--- ... ---) at the top of the file
  - the keys required for that file type (per-type — see REQUIRED_KEYS below)

Skills and agents require both `name` and `description`. Commands derive their
invocation name from the filename, so `name` is optional there — but when a
command *does* declare a `name`, it must match the filename stem (a stale name
after a rename is the real defect class). Description *quality* is deliberately
out of scope — subjective lint on a single-maintainer repo is noise.

Usage:
    python3 ci/lint-frontmatter.py        # exit 1 on any failure
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_KEYS = ("name", "description")
COMMAND_REQUIRED_KEYS = ("description",)  # commands name themselves by filename
MAX_DESCRIPTION_CHARS = 4096  # sanity bound, far above any legitimate description


def _is_command(path: Path) -> bool:
    return path.parent.name == "commands"


def _required_keys(path: Path) -> tuple[str, ...]:
    return COMMAND_REQUIRED_KEYS if _is_command(path) else REQUIRED_KEYS


def extract_frontmatter(text: str) -> str | None:
    """Return the frontmatter block body, or None if absent/malformed."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    return text[3:end]


def key_value(block: str, key: str) -> str | None:
    """Extract a top-level key's value; handles single-line and block scalars."""
    m = re.search(rf"^{key}:\s*(.*)$", block, re.MULTILINE)
    if m is None:
        return None
    val = m.group(1).strip()
    if val in {">", "|", ">-", "|-"} or not val:
        # Block scalar / empty inline value: collect following indented lines.
        lines = block[m.end():].splitlines()
        collected = []
        for line in lines:
            if line.strip() and not line.startswith((" ", "\t")):
                break
            collected.append(line.strip())
        val = " ".join(c for c in collected if c).strip()
    return val.strip("'\"")


def lint_file(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return [f"unreadable: {e}"]
    block = extract_frontmatter(text)
    if block is None:
        return ["missing or unterminated frontmatter block"]
    for key in _required_keys(path):
        val = key_value(block, key)
        if val is None:
            problems.append(f"missing key: {key}")
        elif not val:
            problems.append(f"empty value: {key}")
        elif key == "description" and len(val) > MAX_DESCRIPTION_CHARS:
            problems.append(
                f"description too long ({len(val)} > {MAX_DESCRIPTION_CHARS} chars)"
            )
    # Commands name themselves by filename; a declared `name` that disagrees with
    # the stem is a rename left half-done.
    if _is_command(path):
        name = key_value(block, "name")
        if name and name != path.stem:
            problems.append(f"name '{name}' does not match filename stem '{path.stem}'")
    return problems


def main() -> int:
    targets = (
        sorted(ROOT.glob("plugins/*/skills/*/SKILL.md"))
        + sorted(ROOT.glob("plugins/*/agents/*.md"))
        + sorted(ROOT.glob("plugins/*/commands/*.md"))
    )
    if not targets:
        print("lint-frontmatter: no skill/agent/command files found", file=sys.stderr)
        return 1
    failures = 0
    for path in targets:
        problems = lint_file(path)
        for p in problems:
            print(f"lint-frontmatter: {path.relative_to(ROOT)}: {p}")
        failures += len(problems)
    if failures:
        print(f"lint-frontmatter: {failures} problem(s) across {len(targets)} files.")
        return 1
    print(f"lint-frontmatter: clean ({len(targets)} files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
