#!/usr/bin/env python3
"""Lint for retired Claude model IDs and Ollama-era runtime references.

Flags stale identifiers left behind by a generation-boundary rot event: dated
gen-4 Claude model IDs (`claude-opus-4-\\d`, `claude-sonnet-4-\\d`), pre-4.5
Claude Haiku IDs (`claude-haiku-4-[0-4]`, which excludes the current
`claude-haiku-4-5`), and Ollama-runtime references (`src/llm/ollama.ts`,
`OLLAMA_*` env vars, `gemma3:4b`) that should have migrated to llama-server
naming. This gate covers *this* generation's rot; when Claude gen-6 ships,
extend the denylist below rather than genericizing the regex.

Scan roots (each tolerated if absent): `plugins/`, `docs/`, `templates/`,
`README.md`, `.claude-plugin/marketplace.json`. Only `.md`, `.py`, `.json`
files are scanned. `CHANGELOG.md` files and anything under `docs/adr/` are
skipped — historical changelog and ADR prose legitimately references retired
IDs and must not be flagged.

Usage:
    python3 ci/lint-model-ids.py        # exit 1 on any finding
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCAN_ROOTS = ("plugins", "docs", "templates", "README.md", ".claude-plugin/marketplace.json")
SCAN_EXTENSIONS = (".md", ".py", ".json")
SKIP_DIR_PARTS = ("docs/adr", "__pycache__")

DENYLIST = [
    re.compile(r"claude-(?:opus|sonnet)-4-\d", re.IGNORECASE),
    re.compile(r"claude-haiku-4-[0-4]\b", re.IGNORECASE),
    re.compile(r"src/llm/ollama\.ts", re.IGNORECASE),
    re.compile(r"\bOLLAMA_[A-Z_]+\b", re.IGNORECASE),
    re.compile(r"gemma3:4b", re.IGNORECASE),
]


def _is_skipped(path: Path, root: Path) -> bool:
    if path.name == "CHANGELOG.md":
        return True
    rel_posix = path.relative_to(root).as_posix()
    return any(skip in rel_posix for skip in SKIP_DIR_PARTS)


def _iter_files(root: Path):
    for scan_root in SCAN_ROOTS:
        target = root / scan_root
        if not target.exists():
            continue
        if target.is_file():
            yield target
            continue
        for path in sorted(target.rglob("*")):
            if path.is_file() and path.suffix in SCAN_EXTENSIONS:
                yield path


def scan_tree(root: Path | str) -> list[str]:
    """Return one finding per denylist pattern match, `<relpath>:<line>: <text>`."""
    root = Path(root)
    findings: list[str] = []
    for path in _iter_files(root):
        if _is_skipped(path, root):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relpath = path.relative_to(root).as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern in DENYLIST:
                for match in pattern.finditer(line):
                    findings.append(f"{relpath}:{lineno}: {match.group(0)}")
    return findings


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover - capture buffers
        pass

    argv = sys.argv[1:] if argv is None else argv
    root = Path(argv[0]) if argv else ROOT
    findings = scan_tree(root)
    for finding in findings:
        print(f"lint-model-ids: {finding}")
    if findings:
        print(f"lint-model-ids: {len(findings)} finding(s).")
        return 1
    print("lint-model-ids: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
