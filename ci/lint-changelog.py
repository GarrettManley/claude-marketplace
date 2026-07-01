#!/usr/bin/env python3
"""Lint per-plugin CHANGELOG.md files for exactly one H1 title.

Checks every plugins/*/CHANGELOG.md for exactly one line matching `# ` (single
hash + space). Zero or two-or-more H1s is the double-H1 defect this gate exists
to prevent from silently reappearing (see plan hb-w61.4): `release.py` used to
prepend a fresh H1 above a hand-authored `# Changelog`, landing two titles and
interleaving intro prose between version sections.

Deliberately out of scope (YAGNI, see plan Scope section):
  - The repo-root CHANGELOG.md is hand-curated and never written by release.py —
    it is intentionally NOT in the glob and must stay that way.
  - No title-equality check: a single `# Changelog` (the 8 "latent" files) is
    just as valid as `# <plugin> changelog` — this gate checks COUNT only.
  - No fence-awareness: a `# ` line inside a fenced code block would be
    miscounted, but no CHANGELOG in this repo contains one — add fence-awareness
    only if a real false positive appears.

Usage:
    python3 ci/lint-changelog.py        # exit 1 on any failure
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def count_h1s(path: Path) -> int:
    """Count lines that are an H1 (single `# `, not `## `)."""
    text = path.read_text(encoding="utf-8")
    # Naive line-prefix check — not fence-aware (see module docstring); the
    # corpus has zero fenced `#` lines today, so this is deliberately simple.
    return sum(1 for line in text.splitlines() if line.startswith("# "))


def main() -> int:
    targets = sorted(ROOT.glob("plugins/*/CHANGELOG.md"))
    if not targets:
        print("lint-changelog: no plugin CHANGELOG.md files found", file=sys.stderr)
        return 1
    failures = 0
    for path in targets:
        count = count_h1s(path)
        if count != 1:
            print(f"lint-changelog: {path.relative_to(ROOT)}: {count} H1 titles (expected 1)")
            failures += 1
    if failures:
        print(f"lint-changelog: {failures} problem(s) across {len(targets)} files.")
        return 1
    print(f"lint-changelog: clean ({len(targets)} files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
