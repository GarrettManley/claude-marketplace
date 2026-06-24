#!/usr/bin/env python3
"""Lint plugin files for bare `python` invocations.

Bare `python` is not on PATH for many macOS users (and modern Linux distros
that ship only `python3`). Always use `python3` in plugin source so installs
work universally. Users who prefer uv-managed Python can post-patch their
local plugin cache or set up a shim.

Scans files where bare `python` is unambiguously a command invocation:
  *.sh, *.bash, *.zsh    — shell scripts (commands, heredocs)
  *.json                  — hooks.json, plugin.json command strings

Skipped:
  *.py                    — too many false positives in docstrings, usage
                            strings, and markdown fence language hints.
                            Authors should use python3 in those too for
                            example-setting, but the lint doesn't enforce it.
  *.md, *.txt, README*    — prose
  *.yml, *.yaml           — CI workflows; use python3 explicitly per CI host

Exit 0 on clean. Exit 1 with per-file report on hits.

Usage:
    python3 lint-no-bare-python.py [path...]    # specific paths
    python3 lint-no-bare-python.py              # repo root
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files exempt from scanning. Empty by default: the precise BARE_PYTHON_RE below no
# longer trips on the linter's own name (`lint-no-bare-python`), so scripts/verify.sh
# is scanned for real. Add a path here only for a genuine, unavoidable false positive.
EXEMPT_PATHS: set = set()

SKIP_DIRS = {
    ".git", "__pycache__", ".pytest_cache", "node_modules",
    ".venv", "venv", ".idea", ".vscode",
}

SCAN_EXTENSIONS = {
    ".sh", ".bash", ".zsh",
    ".json",
}

# Match the whole tokens `python` and `python2` (both non-portable) as commands.
# Catches `python script.py`, `python -c`, `python "$VAR"`, `python2 ...`, etc.
# Excludes: `python3`, `python3.11` (versioned, fine); `pythonic` (longer word);
# and `python` inside a hyphenated identifier like `lint-no-bare-python` (the
# `(?<![\w-])`/`(?![\w-])` token guards). The trailing `2?` keeps `python2` in
# scope — a naive `(?<![\w-])python(?![\w-])` would silently drop it.
BARE_PYTHON_RE = re.compile(r"(?<![\w-])python2?(?![\w-])")


def is_exempt(path: Path) -> bool:
    rel = str(path.relative_to(REPO_ROOT))
    if rel in EXEMPT_PATHS:
        return True
    parts = rel.split(os.sep)
    if any(p in SKIP_DIRS for p in parts):
        return True
    return False


def should_scan(path: Path) -> bool:
    if not path.is_file():
        return False
    if is_exempt(path):
        return False
    return path.suffix.lower() in SCAN_EXTENSIONS


def iter_files(targets: List[Path]):
    for target in targets:
        if target.is_file():
            if should_scan(target):
                yield target
            continue
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in files:
                p = Path(root) / name
                if should_scan(p):
                    yield p


def scan_file(path: Path) -> List[Tuple[int, str]]:
    """Return a list of (line_number, matching_line) hits."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return [(0, f"could not read file: {e}")]

    hits: List[Tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if BARE_PYTHON_RE.search(line):
            hits.append((lineno, line.strip()))
    return hits


def main(argv: List[str]) -> int:
    if len(argv) > 1:
        targets = [Path(a).resolve() for a in argv[1:]]
    else:
        targets = [REPO_ROOT]

    total_hits = 0
    files_with_hits: List[Tuple[Path, List[Tuple[int, str]]]] = []
    for path in iter_files(targets):
        hits = scan_file(path)
        if hits:
            files_with_hits.append((path, hits))
            total_hits += len(hits)

    if not files_with_hits:
        print("lint-no-bare-python: clean.")
        return 0

    print(f"lint-no-bare-python: {total_hits} bare-python reference(s) across "
          f"{len(files_with_hits)} file(s).\n")
    for path, hits in files_with_hits:
        try:
            rel = path.relative_to(REPO_ROOT)
        except ValueError:
            rel = path
        print(f"  {rel}")
        for lineno, line in hits:
            print(f"    line {lineno}: {line[:120]}")
        print()
    print("Replace bare `python` with `python3`. Universal across macOS, "
          "Linux distros, and CI runners. Users who prefer uv-managed Python "
          "can post-install patch the local plugin cache.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
