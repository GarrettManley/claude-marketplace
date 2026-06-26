#!/usr/bin/env python3
"""Auto-memory housekeeping: rotate stale entries in ~/.claude/projects/*/memory/.

Every project accumulates `*_<topic>.md` files in its
auto-memory dir. Over time these grow stale (refer to projects no longer
worked on) or duplicate (multiple memories of the same fact). This script
performs three lightweight passes:

  1. **Identify candidates** for archival: memory files not modified in
     N days (default 90), grouped by project dir.
  2. **Optionally archive**: move flagged files into a sibling
     `_archive/` subdir per project (preserves them, removes from index).
  3. **MEMORY.md hygiene**: warn when MEMORY.md references a non-existent
     file (broken pointer).

Default mode is **dry-run** (report only). Pass `--apply` to actually
archive files.

Usage:
    python auto_memory_housekeep.py [--days N] [--apply] [--projects-dir PATH]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"
INDEX_FILE = "MEMORY.md"
ARCHIVE_DIR = "_archive"


@dataclass
class StaleFile:
    path: Path
    age_days: int
    project_key: str


@dataclass
class BrokenPointer:
    project_key: str
    index_line: str
    target: str


def _project_key(memory_dir: Path) -> str:
    """Return a short identifier for the project (parent dir name)."""
    return memory_dir.parent.name


def find_memory_dirs(projects_dir: Path) -> list[Path]:
    return [d for d in projects_dir.glob("*/memory") if d.is_dir()]


def find_stale(memory_dir: Path, age_threshold_days: int) -> list[StaleFile]:
    now = time.time()
    cutoff = now - age_threshold_days * 86400
    stale: list[StaleFile] = []
    project_key = _project_key(memory_dir)
    for path in memory_dir.glob("*.md"):
        if path.name == INDEX_FILE:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            stale.append(StaleFile(
                path=path,
                age_days=int((now - mtime) / 86400),
                project_key=project_key,
            ))
    return stale


def find_broken_pointers(memory_dir: Path) -> list[BrokenPointer]:
    """Return lines in MEMORY.md that reference non-existent files."""
    index = memory_dir / INDEX_FILE
    if not index.is_file():
        return []
    try:
        text = index.read_text(encoding="utf-8")
    except OSError:
        return []
    project_key = _project_key(memory_dir)
    broken: list[BrokenPointer] = []
    # Match Markdown links of the form (file.md) or [...](file.md)
    for line in text.splitlines():
        for m in re.finditer(r"\(([^)]+\.md)\)", line):
            target = m.group(1).strip()
            if target.startswith(("http://", "https://")):
                continue
            target_path = memory_dir / target
            if not target_path.is_file():
                broken.append(BrokenPointer(
                    project_key=project_key,
                    index_line=line.strip(),
                    target=target,
                ))
    return broken


def collect(projects_dir, days):
    """Aggregate stale files + broken pointers across all project memory dirs."""
    memory_dirs = find_memory_dirs(projects_dir)
    stale: list[StaleFile] = []
    broken: list[BrokenPointer] = []
    for mdir in memory_dirs:
        stale.extend(find_stale(mdir, days))
        broken.extend(find_broken_pointers(mdir))
    return memory_dirs, stale, broken


def _json_report(memory_dirs, stale, broken, days):
    return {
        "stale": [{"path": str(s.path), "name": s.path.name, "age_days": s.age_days,
                   "project_key": s.project_key} for s in stale],
        "broken_pointers": [{"project_key": b.project_key, "target": b.target,
                             "index_line": b.index_line} for b in broken],
        "summary": {"stale_count": len(stale), "broken_count": len(broken),
                    "memory_dirs": len(memory_dirs), "threshold_days": days},
    }


def archive_file(stale: StaleFile) -> Path:
    """Move a stale file into the project's _archive/ subdir."""
    archive_root = stale.path.parent / ARCHIVE_DIR
    archive_root.mkdir(exist_ok=True)
    dest = archive_root / stale.path.name
    # If dest exists already (re-run with same filename), append timestamp
    if dest.exists():
        ts = int(time.time())
        dest = archive_root / f"{stale.path.stem}.{ts}{stale.path.suffix}"
    shutil.move(str(stale.path), str(dest))
    return dest


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Rotate stale auto-memory files.")
    p.add_argument("--days", type=int, default=90, help="Stale threshold in days (default 90)")
    p.add_argument("--apply", action="store_true", help="Actually archive (default: dry-run)")
    p.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR)
    p.add_argument("--json", action="store_true",
                   help="emit structured JSON (report-only; ignores --apply)")
    args = p.parse_args(argv)

    if args.json:
        if args.projects_dir.is_dir():
            memory_dirs, stale, broken = collect(args.projects_dir, args.days)
        else:
            memory_dirs, stale, broken = [], [], []
        print(json.dumps(_json_report(memory_dirs, stale, broken, args.days), indent=2))
        return 0

    if not args.projects_dir.is_dir():
        print(f"projects-dir not found: {args.projects_dir}", file=sys.stderr)
        return 2

    memory_dirs = find_memory_dirs(args.projects_dir)
    if not memory_dirs:
        print(f"No project memory dirs found under {args.projects_dir}")
        return 0

    print(f"## Auto-Memory Housekeeping ({'apply' if args.apply else 'dry-run'})\n")
    print(f"Threshold: {args.days} days. Scanning {len(memory_dirs)} project memory dirs.\n")

    total_stale = 0
    total_broken = 0
    archived: list[Path] = []

    for mdir in memory_dirs:
        project_key = _project_key(mdir)
        stale = find_stale(mdir, args.days)
        broken = find_broken_pointers(mdir)
        if not stale and not broken:
            continue
        print(f"### `{project_key}`\n")
        if stale:
            print(f"Stale files (>{args.days}d unmodified):")
            for s in sorted(stale, key=lambda x: -x.age_days):
                print(f"- `{s.path.name}` (age: {s.age_days}d)")
            print()
            total_stale += len(stale)
            if args.apply:
                for s in stale:
                    dest = archive_file(s)
                    archived.append(dest)
                    print(f"  archived → `{dest.relative_to(args.projects_dir.parent.parent)}`")
                print()
        if broken:
            print(f"Broken pointers in {INDEX_FILE}:")
            for b in broken:
                print(f"- target `{b.target}` not found (line: `{b.index_line}`)")
            print()
            total_broken += len(broken)

    print(f"\n---\n\nSummary: {total_stale} stale, {total_broken} broken pointers.")
    if args.apply and archived:
        print(f"Archived {len(archived)} files into per-project `_archive/` subdirs.")
    elif total_stale > 0 and not args.apply:
        print("(Dry-run only — re-run with --apply to archive.)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
