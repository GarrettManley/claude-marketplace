#!/usr/bin/env python3
"""Anti-rot gate: assert every in-repo doc reference points at a file that exists.

Documentation rots when a markdown link or a `references/X.md`-style path mention
outlives the file it names — the recent audit found exactly this (broken
`references/…` paths, hardcoded sibling paths). This gate scans every git-tracked
markdown file and fails the build if any clearly-repo-relative reference dangles.

What it checks, per file:
  1. Inline markdown links `[text](target)` whose target is repo-relative.
  2. Backticked `references/…` / `dimensions/…` path mentions — the SKILL.md idiom
     where a sibling reference is named in code-font prose, not written as a link.
     These two prefixes are checked (and ONLY these) because they denote a
     doc-relative sibling tree; an arbitrary backticked repo path like
     `ci/release.py` is repo-ROOT-relative prose, not a doc-relative link, so
     resolving it against the doc's own directory would be a false positive.

Resolution: a target is resolved against the containing file's directory. For a
SKILL.md (or any file under a skill dir), plugin-root-relative resolution is ALSO
allowed, because `${CLAUDE_PLUGIN_ROOT}`-style refs and README path tables resolve
from the plugin root at install time, not from the doc's own directory. A target
passes if it exists under EITHER base.

What is skipped (never flagged):
  - External URLs: http(s)://, mailto:, protocol-relative `//host`, and bare
    `scheme:` URLs.
  - Pure anchors (`#section`) and the anchor/query suffix on any link (stripped
    before existence check).
  - Absolute paths (`/foo`, `C:\\…`) and `${CLAUDE_PLUGIN_ROOT}`-prefixed paths
    (runtime-resolved, not in-repo).
  - Image/badge links and any link whose target doesn't look repo-relative.

Conservative heuristic (a noisy gate is worse than a lenient one):
  - Markdown links are checked when the target CLEARLY denotes an intended repo
    path: it contains a `/`, or ends in a known doc/code extension
    (.md/.py/.sh/.json/.yaml/.yml/.toml/.txt), or is a `references/…`/`dimensions/…`
    path. Anything else (a lone word, a `#anchor`, an external URL) is left alone.
  - Backticked inline mentions are checked ONLY for the `references/…` and
    `dimensions/…` sibling idiom — never arbitrary backticked paths (those are
    repo-root prose, not doc-relative links).

Run: python3 ci/check-doc-links.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Extensions that mark a bare token as an intended repo file (not prose).
KNOWN_EXTS = (".md", ".py", ".sh", ".json", ".yaml", ".yml", ".toml", ".txt")

# Path-prefixes that are always treated as intended repo references even without
# an extension on the leading segment (they end in a file, but be explicit).
INTENT_PREFIXES = ("references/", "dimensions/")

# `[text](target)` — non-greedy target, stops at the first ')'. Good enough for
# the link styles in this repo (no parenthesised titles in targets).
_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

# Backticked sibling-idiom mentions, restricted to the `references/…` and
# `dimensions/…` trees (the SKILL.md convention). Deliberately NOT a general
# backticked-path matcher: a bare `ci/release.py` in prose is repo-root-relative,
# not doc-relative, so matching it would manufacture false positives.
_INLINE_PATH = re.compile(
    r"`((?:references|dimensions)/[A-Za-z0-9_./-]+\.(?:md|py|sh|json|ya?ml|toml|txt))`"
)


def tracked_markdown() -> list[Path]:
    """Git-tracked *.md files, as absolute paths."""
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "*.md"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [ROOT / line for line in out.stdout.splitlines() if line.strip()]


def _is_external(target: str) -> bool:
    """True for things that are not in-repo relative paths and must be skipped."""
    if not target or target.startswith("#"):
        return True  # pure anchor
    if target.startswith(("http://", "https://", "mailto:", "//")):
        return True
    if target.startswith("${CLAUDE_PLUGIN_ROOT}"):
        return True  # runtime-resolved, not in-repo
    if target.startswith("/") or target.startswith("\\"):
        return True  # absolute (POSIX or UNC)
    if re.match(r"^[A-Za-z]:[\\/]", target):
        return True  # Windows drive-absolute
    # Bare `scheme:rest` URL (tel:, slack:, vscode:, etc.) but NOT a Windows path
    # (already handled) and NOT a relative path (no colon before a slash).
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target) and not target[1:2] == ":":
        return True
    return False


def _looks_repo_relative(target: str) -> bool:
    """Conservative gate: only treat clearly-intended repo paths as checkable."""
    if "/" in target:
        return True
    if target.endswith(KNOWN_EXTS):
        return True
    if any(target.startswith(p) for p in INTENT_PREFIXES):
        return True
    return False


def _strip_suffix(target: str) -> str:
    """Drop trailing #anchor and ?query so the path can be existence-checked."""
    return target.split("#", 1)[0].split("?", 1)[0]


def _plugin_root_for(md_file: Path) -> Path | None:
    """If md_file lives inside a plugin, return that plugin's root dir, else None.

    A SKILL.md's `references/…` and a README's `skills/…/references/…` both resolve
    from the plugin root (plugins/<name>/), so we offer it as an alternate base.
    """
    try:
        parts = md_file.relative_to(ROOT).parts
    except ValueError:
        return None
    if len(parts) >= 2 and parts[0] == "plugins":
        return ROOT / parts[0] / parts[1]
    return None


def _resolves(md_file: Path, rel: str) -> bool:
    """True if `rel` exists relative to the doc's dir OR (if applicable) the plugin root."""
    bases = [md_file.parent]
    plugin_root = _plugin_root_for(md_file)
    if plugin_root is not None:
        bases.append(plugin_root)
    for base in bases:
        candidate = (base / rel).resolve()
        if candidate.exists():
            return True
    return False


def _candidates(line: str) -> list[str]:
    """All checkable targets on a line: markdown links + backticked path mentions."""
    found = [m.group(1) for m in _MD_LINK.finditer(line)]
    found += [m.group(1) for m in _INLINE_PATH.finditer(line)]
    return found


def broken_links() -> list[str]:
    """Return `<file>:<line>: broken link -> <target>` for every dangling ref."""
    problems: list[str] = []
    for md_file in tracked_markdown():
        if not md_file.is_file():
            continue
        text = md_file.read_text(encoding="utf-8", errors="replace")
        rel_name = md_file.relative_to(ROOT).as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            for target in _candidates(line):
                if _is_external(target):
                    continue
                if not _looks_repo_relative(target):
                    continue
                rel = _strip_suffix(target)
                if not rel:
                    continue  # was a pure anchor after stripping
                if not _resolves(md_file, rel):
                    problems.append(f"{rel_name}:{lineno}: broken link -> {target}")
    return problems


def main() -> int:
    problems = broken_links()
    if problems:
        print(f"check-doc-links: {len(problems)} broken reference(s):", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    print(f"check-doc-links: clean ({len(tracked_markdown())} markdown file(s) scanned).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
