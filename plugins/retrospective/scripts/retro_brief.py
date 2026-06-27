#!/usr/bin/env python3
"""Pre-plan brief: surface prior retrospective findings for an area before planning.

The meta-gap this closes: a retro finding is captured and read *within* its
session, then silently recurs in the next similar plan because nobody re-reads
prior retros before planning. The passive SessionStart nag did not fix that.
This actively pulls the *matching* findings for a named area on demand.

It scans `retrospectives/done/*.md` at the workspace root, extracts the bullet
items from the findings-bearing sections (Friction / bugs, Concrete
improvements, What worked), and prints those whose text — or whose retro slug —
matches the query area. Recall-biased: a missed finding is the failure mode, a
slightly-noisy one merely shows an extra bullet.

Self-contained: pure stdlib, no cross-plugin imports.

Usage:
    python3 retro_brief.py <area-or-keywords>      # e.g. "commands lint", "release"
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Sections that carry actionable findings, matched by header *prefix* so variants
# like "What worked (harness-level)" are still caught.
FINDINGS_SECTIONS = ("Friction / bugs", "Concrete improvements", "What worked")

# Query noise: too-short or ubiquitous-in-this-repo tokens that would match almost
# anything and drown the signal.
_STOPWORDS = frozenset(
    {"the", "and", "for", "plugin", "with", "from", "this", "that", "into"}
)

_ANY_HEADER_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s+")
_TOP_BULLET_RE = re.compile(r"^[-*+]\s+")  # a top-level (unindented) list item
_BOLD_LEAD_RE = re.compile(r"^\s*[-*+]\s+\*\*(.+?)\*\*")


@dataclass
class Finding:
    """One bullet item lifted from a findings section of one retro."""

    slug: str       # retro filename stem
    section: str    # which findings section it came from
    lead: str       # short label (bold lead or first words)
    text: str       # full item text, used for matching


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def section_body(text: str, header_name: str) -> str | None:
    """Body of the first section whose header *starts with* `header_name`, else None.

    Runs from just after the header line to the next header of any level (or EOF).
    """
    header_re = re.compile(
        rf"(?im)^\s{{0,3}}#{{1,6}}\s+{re.escape(header_name)}\b.*$"
    )
    m = header_re.search(text)
    if not m:
        return None
    start = m.end()
    nxt = _ANY_HEADER_RE.search(text, start)
    return text[start: nxt.start()] if nxt else text[start:]


def extract_items(body: str) -> list[str]:
    """Split a section body into top-level bullet items (continuation lines folded)."""
    items: list[str] = []
    current: list[str] | None = None
    for raw in body.splitlines():
        if _TOP_BULLET_RE.match(raw):
            if current is not None:
                items.append(" ".join(current).strip())
            current = [raw.strip()]
        elif current is not None and raw.strip():
            current.append(raw.strip())
        elif current is not None:
            # blank line ends the current item
            items.append(" ".join(current).strip())
            current = None
    if current is not None:
        items.append(" ".join(current).strip())
    return [it for it in items if it]


def lead_of(item: str) -> str:
    """A short label for an item: its bold lead if present, else the first ~12 words."""
    m = _BOLD_LEAD_RE.match(item)
    if m:
        return m.group(1).strip()
    words = _TOP_BULLET_RE.sub("", item).split()
    short = " ".join(words[:12])
    return short + ("…" if len(words) > 12 else "")


def extract_findings(text: str, slug: str) -> list[Finding]:
    """Every finding across the findings-bearing sections of one retro's text."""
    findings: list[Finding] = []
    for section in FINDINGS_SECTIONS:
        body = section_body(text, section)
        if body is None:
            continue
        for item in extract_items(body):
            findings.append(
                Finding(slug=slug, section=section, lead=lead_of(item), text=item)
            )
    return findings


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #
def query_tokens(query: str) -> list[str]:
    """Meaningful lowercase tokens from the query (len>=3, minus stopwords)."""
    raw = re.split(r"[^a-z0-9]+", query.lower())
    return [t for t in raw if len(t) >= 3 and t not in _STOPWORDS]


def matches(finding: Finding, tokens: list[str]) -> bool:
    """True if any query token appears in the finding text or its retro slug."""
    hay = f"{finding.text}\n{finding.slug}".lower()
    return any(t in hay for t in tokens)


# --------------------------------------------------------------------------- #
# Workspace-root discovery (mirrors scripts/find_workspace_root.sh)
# --------------------------------------------------------------------------- #
def find_workspace_root(start: str | Path | None = None) -> Path | None:
    """Walk upward from `start` (default cwd) for a `.claude/` dir; else git root."""
    dir_ = Path(start or os.getcwd()).resolve()
    for cand in (dir_, *dir_.parents):
        if (cand / ".claude").is_dir():
            return cand
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True,
            stderr=subprocess.DEVNULL,
            cwd=str(dir_),
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return Path(out) if out else None


def iter_retro_files(root: Path) -> list[Path]:
    """Sorted retrospectives/done/*.md under the workspace root."""
    return sorted((root / "retrospectives" / "done").glob("*.md"))


def brief(root: Path, query: str) -> list[Finding]:
    """All findings across all retros whose text/slug match the query area."""
    tokens = query_tokens(query)
    if not tokens:
        return []
    out: list[Finding] = []
    for path in iter_retro_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for finding in extract_findings(text, path.stem):
            if matches(finding, tokens):
                out.append(finding)
    return out


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def format_brief(query: str, findings: list[Finding]) -> str:
    """Render the brief: findings grouped by retro, or a no-match line."""
    if not findings:
        return (
            f'Pre-plan brief for "{query}": no matching retro findings. '
            "Plan with a clear slate — but consider broadening the area term."
        )
    by_slug: dict[str, list[Finding]] = {}
    for f in findings:
        by_slug.setdefault(f.slug, []).append(f)
    lines = [
        f'Pre-plan brief for "{query}" — {len(findings)} finding(s) across '
        f"{len(by_slug)} retro(s). Read these before planning:",
        "",
    ]
    for slug, group in by_slug.items():
        lines.append(f"{slug}:")
        for f in group:
            lines.append(f"  [{f.section}] {f.lead}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _force_utf8() -> None:
    """Make stdout/stderr UTF-8 so arbitrary retro content (arrows, ✓, …) can't
    crash on a cp1252 Windows console. No-op where reconfigure is unavailable."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    """Print a pre-plan brief for the area given as the positional argument.

    Returns 2 on missing query; 0 otherwise (informational — never hard-blocks).
    """
    _force_utf8()
    args = sys.argv[1:] if argv is None else argv
    positionals = [a for a in args if not a.startswith("-")]
    if not positionals:
        print(
            "usage: retro_brief.py <area-or-keywords>\n"
            "  e.g. retro_brief.py \"commands lint\"",
            file=sys.stderr,
        )
        return 2
    query = " ".join(positionals)

    root = find_workspace_root()
    if root is None:
        print(
            "Pre-plan brief: could not resolve a workspace root "
            "(no .claude/ dir, not in a git repo) — skipping."
        )
        return 0

    print(format_brief(query, brief(root, query)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
