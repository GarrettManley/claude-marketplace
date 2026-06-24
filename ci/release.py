#!/usr/bin/env python3
"""Conventional-commit-driven, per-plugin release automation.

plugin.json is the source of truth; this tool bumps it from Conventional Commits
scoped to each plugin, prepends a per-plugin CHANGELOG section, then syncs the new
version into marketplace.json (reusing ci/check-versions.py's sync()).

Per plugin <name>:
  1. since = last tag matching "<name>-v*"  (else full history)
  2. commits = `git log since..HEAD` whose Conventional-Commit scope == <name>
  3. bump = breaking -> major | feat -> minor | (fix|perf) -> patch | else skip
  4. write plugin.json version, prepend CHANGELOG.md
After all plugins: sync marketplace.json, one release commit, per-plugin tags.

  --dry-run  (default)  print the plan, write nothing
  --apply               write files, commit, and tag

Usage:
    python3 ci/release.py [--dry-run|--apply]
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "plugins"

# Conventional Commit subject: type(scope)!: description
_SUBJECT_RE = re.compile(
    r"^(?P<type>\w+)(?:\((?P<scope>[^)]+)\))?(?P<bang>!)?:\s?(?P<desc>.+)$"
)
_BUMP_RANK = {"major": 3, "minor": 2, "patch": 1}


@dataclass(frozen=True)
class Commit:
    type: str
    scope: Optional[str]
    breaking: bool
    desc: str


# --- pure functions (unit-tested) ---------------------------------------------

def parse_commit(subject: str, body: str = "") -> Optional[Commit]:
    """Parse a Conventional Commit subject (+body for BREAKING CHANGE). None if non-conforming."""
    m = _SUBJECT_RE.match(subject.strip())
    if not m:
        return None
    breaking = bool(m.group("bang")) or "BREAKING CHANGE" in body
    return Commit(
        type=m.group("type"),
        scope=m.group("scope"),
        breaking=breaking,
        desc=m.group("desc").strip(),
    )


def bump_for(commits: List[Commit]) -> Optional[str]:
    """Highest-precedence semver bump implied by commits, or None if nothing release-worthy."""
    kind: Optional[str] = None
    for c in commits:
        if c.breaking:
            cand = "major"
        elif c.type == "feat":
            cand = "minor"
        elif c.type in ("fix", "perf"):
            cand = "patch"
        else:
            continue
        if kind is None or _BUMP_RANK[cand] > _BUMP_RANK[kind]:
            kind = cand
    return kind


def apply_bump(version: str, kind: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def render_changelog_section(version: str, commits: List[Commit]) -> str:
    breaks = [c for c in commits if c.breaking]
    feats = [c for c in commits if c.type == "feat" and not c.breaking]
    fixes = [c for c in commits if c.type in ("fix", "perf") and not c.breaking]
    lines = [f"## {version}", ""]
    for title, group in (("Breaking", breaks), ("Features", feats), ("Fixes", fixes)):
        if group:
            lines.append(f"### {title}")
            lines.extend(f"- {c.desc}" for c in group)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# --- git / filesystem I/O -----------------------------------------------------

def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=True, capture_output=True, text=True,
    ).stdout


def _ondisk_plugins() -> List[str]:
    return sorted(p.parent.parent.name for p in PLUGINS_DIR.glob("*/.claude-plugin/plugin.json"))


def _plugin_json(name: str) -> Path:
    return PLUGINS_DIR / name / ".claude-plugin" / "plugin.json"


def _current_version(name: str) -> str:
    return json.loads(_plugin_json(name).read_text(encoding="utf-8"))["version"]


def _last_tag(name: str) -> Optional[str]:
    out = _git("tag", "--list", f"{name}-v*", "--sort=-v:refname").strip()
    return out.splitlines()[0] if out else None


def _commits_for(name: str) -> List[Commit]:
    tag = _last_tag(name)
    rng = f"{tag}..HEAD" if tag else "HEAD"
    # Records separated by 0x1e; subject/body within a record by 0x1f.
    raw = _git("log", rng, "--format=%s%x1f%b%x1e")
    commits: List[Commit] = []
    for rec in raw.split("\x1e"):
        if not rec.strip():
            continue
        subject, _, body = rec.strip("\n").partition("\x1f")
        c = parse_commit(subject, body)
        if c and c.scope == name:
            commits.append(c)
    return commits


def _set_version(name: str, version: str) -> None:
    path = _plugin_json(name)
    text = path.read_text(encoding="utf-8")
    new = re.sub(r'("version"\s*:\s*")[^"]+(")', rf"\g<1>{version}\g<2>", text, count=1)
    path.write_text(new, encoding="utf-8")


def _prepend_changelog(name: str, section: str) -> None:
    path = PLUGINS_DIR / name / "CHANGELOG.md"
    header = f"# {name} changelog\n\n"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        body = existing[len(header):] if existing.startswith(header) else existing
        path.write_text(header + section + "\n" + body, encoding="utf-8")
    else:
        path.write_text(header + section, encoding="utf-8")


def _load_sync():
    spec = importlib.util.spec_from_file_location(
        "check_versions", Path(__file__).resolve().parent / "check-versions.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.sync


# --- orchestration ------------------------------------------------------------

def plan() -> List[Tuple[str, str, str, List[Commit]]]:
    """Return [(name, old, new, commits)] for plugins with a release-worthy change."""
    out: List[Tuple[str, str, str, List[Commit]]] = []
    for name in _ondisk_plugins():
        commits = _commits_for(name)
        kind = bump_for(commits)
        if kind is None:
            continue
        old = _current_version(name)
        out.append((name, old, apply_bump(old, kind), commits))
    return out


def main(argv: List[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--dry-run"
    if mode not in ("--dry-run", "--apply"):
        print(f"usage: {Path(argv[0]).name} [--dry-run|--apply]", file=sys.stderr)
        return 2

    releases = plan()
    if not releases:
        print("release: no release-worthy commits since last tags (nothing to do).")
        return 0

    for name, old, new, commits in releases:
        print(f"release: {name} {old} -> {new} ({len(commits)} commit(s))")
        if mode == "--dry-run":
            print(render_changelog_section(new, commits))

    if mode == "--dry-run":
        print("release: dry-run — no changes written. Re-run with --apply to ship.")
        return 0

    for name, _old, new, commits in releases:
        _set_version(name, new)
        _prepend_changelog(name, render_changelog_section(new, commits))
    _load_sync()()  # propagate new versions into marketplace.json
    summary = ", ".join(f"{n}@{v}" for n, _o, v, _c in releases)
    _git("add", "-A")
    _git("commit", "-m", f"chore(release): {summary}")
    for name, _old, new, _commits in releases:
        _git("tag", f"{name}-v{new}")
    print(f"release: committed and tagged {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
