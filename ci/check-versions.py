#!/usr/bin/env python3
"""Check (and optionally fix) plugin version drift.

plugin.json is the single source of truth (the install cache keys off it). Each
plugin's version is duplicated into its entry in .claude-plugin/marketplace.json;
this script keeps the duplicate honest.

  --check  (default)  Assert every marketplace entry version == its plugin.json
                      version, and that the marketplace entry set == the on-disk
                      plugin set. Exit 1 with a per-plugin report on any drift.
  --fix               Copy each plugin.json version into its marketplace entry.

Exposes check() and sync() for import (ci/release.py reuses sync()).

Usage:
    python3 ci/check-versions.py [--check|--fix]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"
PLUGINS_DIR = REPO_ROOT / "plugins"


def _plugin_version(name: str) -> str:
    pj = PLUGINS_DIR / name / ".claude-plugin" / "plugin.json"
    return json.loads(pj.read_text(encoding="utf-8"))["version"]


def _ondisk_plugins() -> Set[str]:
    return {p.parent.parent.name for p in PLUGINS_DIR.glob("*/.claude-plugin/plugin.json")}


def _load_marketplace() -> dict:
    return json.loads(MARKETPLACE.read_text(encoding="utf-8"))


def check() -> List[str]:
    """Return a list of human-readable drift problems (empty == clean)."""
    data = _load_marketplace()
    entries = data["plugins"]
    problems: List[str] = []

    entry_names = {e["name"] for e in entries}
    ondisk = _ondisk_plugins()
    for missing in sorted(ondisk - entry_names):
        problems.append(f"{missing}: on disk but missing from marketplace.json")
    for extra in sorted(entry_names - ondisk):
        problems.append(
            f"{extra}: in marketplace.json but no plugins/{extra}/.claude-plugin/plugin.json"
        )

    for entry in entries:
        name = entry["name"]
        if name not in ondisk:
            continue  # already reported as extra
        canonical = _plugin_version(name)
        listed = entry.get("version")
        if listed != canonical:
            problems.append(
                f"{name}: marketplace.json has {listed!r}, plugin.json has {canonical!r}"
            )
    return problems


def sync() -> List[Tuple[str, str, str]]:
    """Copy plugin.json versions into marketplace.json.

    Returns a list of (name, old, new) for each entry changed. Only the `version`
    field is mutated; all other fields (description, keywords, ...) are preserved.
    """
    data = _load_marketplace()
    ondisk = _ondisk_plugins()
    changed: List[Tuple[str, str, str]] = []
    for entry in data["plugins"]:
        name = entry["name"]
        if name not in ondisk:
            continue
        canonical = _plugin_version(name)
        if entry.get("version") != canonical:
            changed.append((name, entry.get("version"), canonical))
            entry["version"] = canonical
    if changed:
        MARKETPLACE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return changed


def main(argv: List[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--check"
    if mode not in ("--check", "--fix"):
        print(f"usage: {Path(argv[0]).name} [--check|--fix]", file=sys.stderr)
        return 2

    if mode == "--fix":
        changed = sync()
        if not changed:
            print("check-versions: already in sync.")
            return 0
        for name, old, new in changed:
            print(f"check-versions: synced {name} {old} -> {new}")
        return 0

    problems = check()
    if not problems:
        print("check-versions: clean.")
        return 0
    print(f"check-versions: {len(problems)} version drift problem(s):\n", file=sys.stderr)
    for p in problems:
        print(f"  {p}", file=sys.stderr)
    print(
        "\nplugin.json is the source of truth. Run "
        "`python3 ci/check-versions.py --fix` to propagate versions into marketplace.json.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
