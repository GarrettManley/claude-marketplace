"""Live workflow-state discovery + the compact-plan intent note.

Discovers what a post-compaction session resumes from — the active plan
file (via the SDD ledger or a pending retro marker) and pending
retrospectives — by reading the project filesystem at injection time.
Nothing discovered is persisted: compaction does not change the disk, so
the live read is always at least as fresh as any snapshot would be.

The single persisted artifact is the skill-authored intent note — the one
piece of conversation state the filesystem cannot rediscover. It lives in
a sidecar JSON next to the discipline snapshot and expires after
NOTE_TTL_SECONDS.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from snapshot import _short_hash, get_snapshot_dir

NOTE_TTL_SECONDS = 4 * 3600

_MD_PATH_RE = re.compile(r"([^\s`\"']+\.md)")
_PLAN_LINE_RE = re.compile(r"(?im)^plan:\s*(.+?\.md)\s*$")
_CHECKBOX_DONE_RE = re.compile(r"^\s*[-*] \[[xX]\]", re.MULTILINE)
_CHECKBOX_OPEN_RE = re.compile(r"^\s*[-*] \[ \]", re.MULTILINE)


def get_project_root() -> Path:
    explicit = os.environ.get("CLAUDE_PROJECT_DIR")
    if explicit:
        return Path(explicit)
    from snapshot import _git_toplevel

    top = _git_toplevel()
    if top:
        return Path(top)
    return Path(os.getcwd())


def get_note_path() -> Path:
    key = _short_hash(str(get_project_root().resolve()))
    return get_snapshot_dir() / f"{key}.note.json"


def write_note(text: str, now: float | None = None) -> Path:
    """Persist the intent note. Raises OSError on failure — the CLI caller
    reports it; nothing on the hook path ever writes."""
    now = time.time() if now is None else now
    path = get_note_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"text": text, "timestamp": now}, indent=2), encoding="utf-8"
    )
    return path


def read_note(now: float | None = None) -> dict[str, Any] | None:
    """Return the note if present, well-formed, and within TTL; else None."""
    now = time.time() if now is None else now
    try:
        data = json.loads(get_note_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    text = data.get("text")
    ts = data.get("timestamp")
    if isinstance(text, str) and isinstance(ts, (int, float)):
        if now - float(ts) < NOTE_TTL_SECONDS:
            return {"text": text, "timestamp": float(ts)}
    return None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _first_md_path(text: str) -> str | None:
    anchored = _PLAN_LINE_RE.search(text)
    if anchored:
        return anchored.group(1).strip()
    match = _MD_PATH_RE.search(text)
    return match.group(1) if match else None


def _count_tasks(plan_path: Path) -> tuple[int | None, int | None]:
    text = _read_text(plan_path)
    if text is None:
        return None, None
    return (
        len(_CHECKBOX_DONE_RE.findall(text)),
        len(_CHECKBOX_OPEN_RE.findall(text)),
    )


def _sdd_ledger(root: Path) -> dict[str, Any] | None:
    ledger = root / ".superpowers" / "sdd" / "progress.md"
    text = _read_text(ledger)
    if text is None:
        return None
    return {"path": str(ledger), "plan_path": _first_md_path(text)}


def _pending_retros(root: Path) -> list[dict[str, Any]]:
    pending = root / "retrospectives" / "pending"
    if not pending.is_dir():
        return []
    return [{"slug": marker.stem} for marker in sorted(pending.glob("*.marker"))]


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _resolve_plan_candidate(root: Path, raw: str) -> Path | None:
    """Root-anchor a discovered plan path and validate it exists on disk."""
    p = Path(raw)
    if not p.is_absolute():
        p = root / p
    return p if p.is_file() else None


def _discover_active_plan(root: Path) -> dict[str, Any] | None:
    ledger = _sdd_ledger(root)
    if ledger and ledger.get("plan_path"):
        resolved = _resolve_plan_candidate(root, ledger["plan_path"])
        if resolved is not None:
            return {"path": str(resolved), "source": "sdd-ledger"}
    pending = root / "retrospectives" / "pending"
    if pending.is_dir():
        markers = sorted(
            pending.glob("*.marker"), key=_safe_mtime, reverse=True
        )
        for marker in markers:
            text = _read_text(marker) or ""
            lines = text.splitlines()
            first = lines[0].strip() if lines else ""
            if first.endswith(".md"):
                resolved = _resolve_plan_candidate(root, first)
                if resolved is not None:
                    return {"path": str(resolved), "source": "pending-marker"}
    return None


def gather_workflow_state() -> dict[str, Any]:
    """Discover live workflow state for the current project."""
    root = get_project_root()
    active = _discover_active_plan(root)
    if active:
        done, open_ = _count_tasks(Path(active["path"]))
        active["tasks_done"] = done
        active["tasks_open"] = open_
    return {
        "active_plan": active,
        "sdd_ledger": _sdd_ledger(root),
        "pending_retros": _pending_retros(root),
    }
