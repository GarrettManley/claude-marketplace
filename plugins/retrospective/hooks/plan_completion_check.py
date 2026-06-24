#!/usr/bin/env python3
"""Completion pre-check for plan files + SessionStart soft-nag hook.

Two roles, one module:

1. **Library** (used by the `/plan-completion` skill and by tests): pure-stdlib
   functions that take a markdown plan path and answer "is this plan actually
   DONE?" via four generic checks that work on any markdown plan:

     - Retrospective/completion section exists and is non-placeholder.
     - No unchecked task checkboxes (`- [ ]`) remain.
     - The Verification section's criteria are addressed (not left as TODO).
     - At least one issue/tracker reference is present if the plan cites one.

   `check_plan(path)` returns a `CompletionReport` describing pass/fail + blockers.

2. **Hook** (`main()`): a SessionStart soft-nag. Resolves the workspace root the
   same way the bash hooks do (.claude/ walk -> git toplevel fallback), scans
   `retrospectives/pending/*.marker`, resolves each marker to its plan under
   `~/.claude/plans/`, runs the checks, and prints a SOFT reminder listing any
   pending plan that does NOT yet pass completion checks. Never hard-blocks;
   always exits 0 — matching the retrospective plugin's nag philosophy.

Self-contained: pure stdlib, no cross-plugin imports.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------- #
# Patterns
# --------------------------------------------------------------------------- #

# A "completion" section header: Retrospective, Completion, or Done.
_COMPLETION_HEADER_RE = re.compile(
    r"(?im)^\s{0,3}#{1,6}\s+(Retrospective|Completion|Done)\b.*$"
)
_VERIFICATION_HEADER_RE = re.compile(r"(?im)^\s{0,3}#{1,6}\s+Verification\b.*$")
_ANY_HEADER_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s+")

# An unchecked markdown task box: `- [ ]` / `* [ ]` / `+ [ ]` (any indent).
_UNCHECKED_BOX_RE = re.compile(r"(?m)^\s*[-*+]\s+\[\s\]")

# A tracker reference: GitHub issue (#N) or a beads id (hb-… / bd-…).
_TRACKER_RE = re.compile(r"(?:#\d+|\b(?:hb|bd)-[0-9a-z]+(?:\.\d+)?\b)")

# Words that mark a section as unfinished placeholder content.
_PLACEHOLDER_RE = re.compile(r"(?i)\b(TODO|TBD|FIXME|XXX|WIP|placeholder|<[^>]+>)\b")


# --------------------------------------------------------------------------- #
# Report types
# --------------------------------------------------------------------------- #
@dataclass
class CompletionReport:
    """Verdict for a single plan file."""

    path: Path
    blockers: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.blockers

    def verdict(self) -> str:
        """One-line human verdict."""
        if self.complete:
            return f"COMPLETE -> run /plan-retrospective  ({self.path})"
        head = f"INCOMPLETE ({self.path}) — {len(self.blockers)} blocker(s):"
        return "\n".join([head] + [f"  - {b}" for b in self.blockers])


# --------------------------------------------------------------------------- #
# Section extraction
# --------------------------------------------------------------------------- #
def _section_body(text: str, header_re: re.Pattern[str]) -> str | None:
    """Return the body of the first section whose header matches, else None.

    The body runs from just after the header line up to the next header of any
    level (or end of file).
    """
    m = header_re.search(text)
    if not m:
        return None
    start = m.end()
    nxt = _ANY_HEADER_RE.search(text, start)
    return text[start: nxt.start()] if nxt else text[start:]


def _is_placeholder_body(body: str) -> bool:
    """True if a section body is empty or only placeholder content.

    A body counts as real content when it has at least one non-blank line that
    is not solely a placeholder token (TODO/TBD/<...>) or a template comment.
    """
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Strip leading list/heading markers so "- TODO" still reads as placeholder.
        stripped = line.lstrip("-*+# >").strip()
        if not stripped:
            continue
        # A line that is wholly an angle-bracket template token (<fill this in>)
        # is placeholder even though it lacks a recognised keyword.
        if re.fullmatch(r"<[^>]*>", stripped):
            continue
        # A line that is *entirely* a placeholder token doesn't count as content.
        without_placeholders = _PLACEHOLDER_RE.sub("", stripped).strip(" .:-")
        if without_placeholders:
            return False  # found real content
    return True  # nothing but blanks / placeholders


# --------------------------------------------------------------------------- #
# Individual checks (each returns a blocker string or None)
# --------------------------------------------------------------------------- #
def check_completion_section(text: str) -> str | None:
    """Check (1): a Retrospective/Completion section exists and is non-placeholder."""
    body = _section_body(text, _COMPLETION_HEADER_RE)
    if body is None:
        return (
            "No '## Retrospective' (or '## Completion') section found. "
            "Add one summarizing the outcome before retrospecting."
        )
    if _is_placeholder_body(body):
        return (
            "The Retrospective/Completion section is empty or still placeholder "
            "(TODO/TBD/<...>). Fill in the actual outcome."
        )
    return None


def check_unchecked_tasks(text: str) -> str | None:
    """Check (2): no unchecked `- [ ]` task boxes remain."""
    count = len(_UNCHECKED_BOX_RE.findall(text))
    if count:
        plural = "task" if count == 1 else "tasks"
        return (
            f"{count} unchecked {plural} remain (`- [ ]`). "
            "Tick every checkbox, or remove tasks that were dropped."
        )
    return None


def check_verification_addressed(text: str) -> str | None:
    """Check (3): the Verification section's criteria are addressed, not left TODO.

    Absent Verification section is not a blocker (not every plan has one); a
    present-but-placeholder one is.
    """
    body = _section_body(text, _VERIFICATION_HEADER_RE)
    if body is None:
        return None
    if _is_placeholder_body(body):
        return (
            "The Verification section is empty or still placeholder (TODO/TBD). "
            "Record how each criterion was verified."
        )
    if _PLACEHOLDER_RE.search(body):
        return (
            "The Verification section still contains TODO/TBD/placeholder markers. "
            "Resolve them — every verification criterion must be addressed."
        )
    return None


def check_tracker_reference(text: str) -> str | None:
    """Check (4): at least one issue/tracker reference is present.

    Generic plans frequently cite a tracker; if none is present at all, surface
    it as a (soft, last-priority) blocker so the plan ties back to tracked work.
    """
    if not _TRACKER_RE.search(text):
        return (
            "No issue/tracker reference found (e.g. '#123' or 'hb-9yw.4'). "
            "Cite the issue this plan closes or advances."
        )
    return None


# Ordered so the most actionable blockers surface first.
_CHECKS = (
    check_unchecked_tasks,
    check_completion_section,
    check_verification_addressed,
    check_tracker_reference,
)


def check_text(text: str, path: Path) -> CompletionReport:
    """Run all checks against already-read plan text."""
    report = CompletionReport(path=path)
    for check in _CHECKS:
        blocker = check(text)
        if blocker:
            report.blockers.append(blocker)
    return report


def check_plan(path: str | Path) -> CompletionReport:
    """Read a plan file and run the completion checks.

    A missing/unreadable file is itself a blocker (you can't retrospect a plan
    that isn't there).
    """
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return CompletionReport(path=p, blockers=[f"Plan file not readable: {p}"])
    return check_text(text, p)


# --------------------------------------------------------------------------- #
# Workspace-root discovery (mirrors scripts/find_workspace_root.sh)
# --------------------------------------------------------------------------- #
def _has_dot_claude(path: Path) -> bool:
    """True if `path` contains a `.claude/` directory. Seam for testing."""
    return (path / ".claude").is_dir()


def find_workspace_root(start: str | Path | None = None) -> Path | None:
    """Walk upward from `start` (default cwd) for a `.claude/` dir; else git root.

    Returns None if neither can be determined.
    """
    dir_ = Path(start or os.getcwd()).resolve()
    for cand in (dir_, *dir_.parents):
        if _has_dot_claude(cand):
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


def plans_dir() -> Path:
    """The user's plans directory: ~/.claude/plans."""
    return Path.home() / ".claude" / "plans"


def resolve_marker_to_plan(marker: Path) -> Path | None:
    """Resolve a pending marker to its plan file.

    The marker's first line is the plan path written by exit-plan-mode-marker.sh.
    Fall back to `~/.claude/plans/<slug>.md` (slug = marker stem) when the marker
    is empty or its recorded path no longer exists.
    """
    try:
        first = marker.read_text(encoding="utf-8").splitlines()
    except OSError:
        first = []
    if first:
        candidate = Path(first[0].strip())
        if candidate.is_file():
            return candidate
    fallback = plans_dir() / f"{marker.stem}.md"
    return fallback if fallback.is_file() else None


def scan_pending(root: Path) -> list[tuple[str, CompletionReport | None]]:
    """For each pending marker under `root`, return (slug, report-or-None).

    report is None when the plan file cannot be resolved (so the nag can mention
    the marker without crashing).
    """
    pending = root / "retrospectives" / "pending"
    if not pending.is_dir():
        return []
    results: list[tuple[str, CompletionReport | None]] = []
    for marker in sorted(pending.glob("*.marker")):
        plan = resolve_marker_to_plan(marker)
        report = check_plan(plan) if plan else None
        results.append((marker.stem, report))
    return results


# --------------------------------------------------------------------------- #
# Hook entry point
# --------------------------------------------------------------------------- #
def _run_cli(plan_path: str) -> int:
    """CLI mode: check one plan path and print its verdict. Always returns 0."""
    print(check_plan(plan_path).verdict())
    return 0


def main(argv: list[str] | None = None) -> int:
    """Dual entry point.

    - With a plan-path argument (CLI / skill use): check that one plan and print
      its verdict (COMPLETE or a blocker list).
    - With no argument (SessionStart hook): read the hook JSON payload from stdin
      (best-effort), scan pending markers, and print a soft reminder for any plan
      that does not yet pass completion checks.

    Always returns 0 — never hard-blocks.
    """
    args = sys.argv[1:] if argv is None else argv
    # A non-flag positional argument selects CLI mode against that plan path.
    positionals = [a for a in args if not a.startswith("-")]
    if positionals:
        return _run_cli(positionals[0])

    # The payload may carry `cwd`; fall back to the process cwd otherwise.
    cwd = None
    try:
        payload = json.load(sys.stdin)
        if isinstance(payload, dict):
            cwd = payload.get("cwd")
    except (json.JSONDecodeError, ValueError, OSError):
        pass

    root = find_workspace_root(cwd)
    if root is None:
        return 0

    incomplete: list[str] = []
    for slug, report in scan_pending(root):
        if report is None:
            incomplete.append(f"  - {slug}: plan file not found (cannot pre-check)")
        elif not report.complete:
            first = report.blockers[0]
            more = f" (+{len(report.blockers) - 1} more)" if len(report.blockers) > 1 else ""
            incomplete.append(f"  - {slug}: {first}{more}")

    if incomplete:
        print(
            "Pending plans that are NOT yet complete — run /plan-completion to "
            "see the full blocker list before /plan-retrospective:"
        )
        for line in incomplete:
            print(line)

    return 0


if __name__ == "__main__":
    sys.exit(main())
