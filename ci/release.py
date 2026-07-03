#!/usr/bin/env python3
"""Conventional-commit-driven, per-plugin release automation.

plugin.json is the source of truth; this tool bumps it from Conventional Commits
scoped to each plugin, prepends a per-plugin CHANGELOG section, then syncs the new
version into marketplace.json (reusing ci/check-versions.py's sync()).

Per plugin <name>:
  0. if there is no "<name>-v*" tag at all, the plugin has no baseline — plan()
     skips it (no bump) and main() prints a --tag notice: its current version is
     the first release, established on main via --tag (ADR-0012), not bumped over
     full history (#27).
  1. since = last tag matching "<name>-v*"
  2. commits = `git log since..HEAD` whose Conventional-Commit scope == <name>
  3. bump = breaking -> major | feat -> minor | (fix|perf) -> patch | else skip
  4. write plugin.json version, prepend CHANGELOG.md
Before writing, --apply validates every plugin's would-be CHANGELOG H1 count and
aborts (writing nothing) if any is invalid, so an H1-invalid abort never leaves a
partial on-disk bump (#33). (A sync()/commit failure after the write loop still
raises loudly and can leave an uncommitted bump — a narrower residual tracked
separately.) After all plugins: sync marketplace.json, one release commit
(NO tag — tags are born on main post-merge to survive the squash; see
docs/adr/0012-tag-after-merge.md).

  --dry-run  (default)  print the plan, write nothing
  --apply               write files + one release commit (no tag)
  --tag                 (run on main after the squash-merge) tag each plugin whose
                        current version is untagged, at HEAD, and push [--no-push to skip]

--dry-run/--apply refuse (exit 1) if a plugin's last tag is not an ancestor of HEAD
(orphaned by a squash-merge), so a spurious bump is never proposed.

Usage:
    python3 ci/release.py [--dry-run|--apply|--tag] [--no-push]
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
    # stdin=DEVNULL: these git calls never read stdin; inheriting a closed/invalid
    # parent stdin makes subprocess's DuplicateHandle fail on Windows (WinError 6).
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        stdin=subprocess.DEVNULL, check=True, capture_output=True, text=True,
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


def _is_ancestor(ref: str, of: str = "HEAD") -> bool:
    """True if `ref` is an ancestor of `of` (exit 0 from `merge-base --is-ancestor`)."""
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "merge-base", "--is-ancestor", ref, of],
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
    )
    return proc.returncode == 0


def orphaned_tags() -> List[str]:
    """Per-plugin last tags that are not ancestors of HEAD (orphaned by a squash-merge)."""
    bad: List[str] = []
    for name in _ondisk_plugins():
        tag = _last_tag(name)
        if tag and not _is_ancestor(tag):
            bad.append(tag)
    return bad


def _tag_exists(tag: str) -> bool:
    return bool(_git("tag", "--list", tag).strip())


def untagged_releases() -> List[Tuple[str, str]]:
    """[(name, version)] for plugins whose current plugin.json version has no tag."""
    out: List[Tuple[str, str]] = []
    for name in _ondisk_plugins():
        v = _current_version(name)
        if not _tag_exists(f"{name}-v{v}"):
            out.append((name, v))
    return out


def never_tagged_plugins() -> List[Tuple[str, str]]:
    """[(name, current_version)] for plugins with no <name>-v* tag at all. They
    have no baseline to bump from; their current version is the first release,
    established by --tag at HEAD (ADR-0012) — never bumped over full history (#27)."""
    return [(n, _current_version(n)) for n in _ondisk_plugins() if _last_tag(n) is None]


def tag_untagged() -> List[str]:
    """Create a tag at HEAD for each untagged current version. Returns the created tags."""
    created: List[str] = []
    for name, v in untagged_releases():
        tag = f"{name}-v{v}"
        _git("tag", tag)
        created.append(tag)
    return created


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


def _first_version_heading_offset(text: str) -> Optional[int]:
    """Char offset of the first `## ` line that is not inside a fenced code block.

    Tracks fence state by toggling on lines starting with ``` — a `## ` line
    inside a fenced example (e.g. Keep-a-Changelog usage prose) must not be
    mistaken for a real version heading. Returns None if no such line exists.
    """
    in_fence = False
    offset = 0
    for line in text.splitlines(keepends=True):
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence and line.startswith("## "):
            return offset
        offset += len(line)
    return None


def _prepend_changelog(name: str, section: str) -> None:
    """Insert a new `## <version>` section, preserving the file's preamble verbatim.

    Never adds or removes an H1 — it only ever inserts a `## ` section. Three cases:
      1. File absent -> create `# <name> changelog` + the section.
      2. File exists, no `## ` heading outside a fenced code block -> the whole
         file is the preamble; the section is appended after it, body untouched
         (no data loss).
      3. File exists, has a `## ` heading outside any fence -> the section is
         inserted between the preamble (everything above that first heading)
         and the heading itself.
    """
    path = PLUGINS_DIR / name / "CHANGELOG.md"
    section = section.strip("\n")
    if not path.exists():
        path.write_text(f"# {name} changelog\n\n{section}\n", encoding="utf-8")
        return

    existing = path.read_text(encoding="utf-8")
    offset = _first_version_heading_offset(existing)
    if offset is None:
        preamble = existing.rstrip("\n")
        path.write_text(f"{preamble}\n\n{section}\n", encoding="utf-8")
        return

    preamble, rest = existing[:offset], existing[offset:]
    path.write_text(
        preamble.rstrip("\n") + "\n\n" + section + "\n\n" + rest.lstrip("\n"),
        encoding="utf-8",
    )


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
        if _last_tag(name) is None:
            continue  # never-tagged: no baseline; released via --tag, not a bump (#27)
        commits = _commits_for(name)
        kind = bump_for(commits)
        if kind is None:
            continue
        old = _current_version(name)
        out.append((name, old, apply_bump(old, kind), commits))
    return out


def main(argv: List[str]) -> int:
    args = argv[1:]
    modes = [a for a in args if a in ("--dry-run", "--apply", "--tag")]
    unknown = [a for a in args if a not in ("--dry-run", "--apply", "--tag", "--no-push")]
    if unknown or len(modes) > 1:
        print(f"usage: {Path(argv[0]).name} [--dry-run|--apply|--tag] [--no-push]", file=sys.stderr)
        return 2
    mode = modes[0] if modes else "--dry-run"

    # --tag: post-merge step on main. Tag each plugin whose current version is
    # untagged, at HEAD (the merged commit), and push — so the tag is born on main
    # and can never be orphaned by the squash. See docs/adr/0012-tag-after-merge.md.
    if mode == "--tag":
        created = tag_untagged()
        if not created:
            print("release: all current plugin versions already tagged (nothing to tag).")
            return 0
        if "--no-push" not in args:
            _git("push", "origin", *created)
        print(f"release: tagged {', '.join(created)}"
              + ("" if "--no-push" in args else " and pushed to origin"))
        return 0

    # Guard: a last tag not on HEAD's history was orphaned by a squash-merge; the
    # since-last-tag range would be wrong, so refuse rather than propose a spurious bump.
    orphaned = orphaned_tags()
    if orphaned:
        print(
            "release: refusing — these tags are not ancestors of HEAD (orphaned by a "
            f"squash-merge): {', '.join(orphaned)}.\n"
            "Re-point each before releasing, e.g.: "
            "git tag -f <tag> <correct-commit> && git push --force origin <tag>.",
            file=sys.stderr,
        )
        return 1

    releases = plan()
    # Surface plugins with no tag at all: they are skipped by plan() (no baseline),
    # but a genuinely-new plugin with real commits must not read as "nothing to do".
    # Placed before the early-return so it fires even when releases is empty (#27).
    untagged = never_tagged_plugins()
    if untagged:
        listing = ", ".join(f"{n}@{v}" for n, v in untagged)
        print(
            f"release: note — no release tag yet for {listing}; the current version "
            "is the first release, established by `release.py --tag` on main (these are "
            "not bumped here). If a listed plugin is already released, your local tags "
            "may be stale — run `git fetch --tags` and re-check."
        )
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

    # Validate the H1 invariant from the EXISTING changelog BEFORE any write, so an
    # H1-invalid plugin aborts the run leaving every plugin unwritten (#33). The prepended
    # section never adds a `# ` H1 (render_changelog_section emits only `## `/`### `;
    # _prepend_changelog adds a single `# ` iff the file is absent), so the would-be
    # H1 count == the existing `# ` count, or 1 when absent — an invariant locked by
    # the test_prepend_changelog_* / test_render_changelog_* suite.
    for name, _old, _new, _commits in releases:
        changelog_path = PLUGINS_DIR / name / "CHANGELOG.md"
        h1_count = (
            sum(1 for line in changelog_path.read_text(encoding="utf-8").splitlines()
                if line.startswith("# "))
            if changelog_path.exists() else 1
        )
        if h1_count != 1:
            print(
                f"release: aborting — {name}'s {changelog_path} would have {h1_count} "
                "H1 title(s) (expected exactly 1); refusing to write or commit.",
                file=sys.stderr,
            )
            return 1

    for name, _old, new, commits in releases:
        _set_version(name, new)
        _prepend_changelog(name, render_changelog_section(new, commits))
    _load_sync()()  # propagate new versions into marketplace.json
    summary = ", ".join(f"{n}@{v}" for n, _o, v, _c in releases)
    _git("add", "-A")
    _git("commit", "-m", f"chore(release): {summary}")
    print(f"release: committed {summary}. After the squash-merge lands on main, "
          "run `release.py --tag` there to tag + push (tags are born on main).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
