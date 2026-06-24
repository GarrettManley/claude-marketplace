"""Shared helper for the PreCompact snapshot + SessionStart resume-context hooks.

Responsibilities:
  - Resolve the snapshot directory (DISCIPLINE_SNAPSHOT_DIR or default).
  - Compute a deterministic per-project key (CLAUDE_PROJECT_DIR → git remote
    URL → git toplevel → CWD → "global").
  - Gather filesystem-side state (git branch + HEAD SHA + top-N recently-
    modified files via git log --name-only).
  - Read/write the JSON snapshot file.

No transcript parsing in v1.

Adapted in spirit from affaan-m/everything-claude-code @ 4774946d
(scripts/hooks/pre-compact.js was a 30-line timestamp logger; this version
ships the actual state-snapshot half).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

GLOBAL_PROJECT_KEY = "global"
RECENT_FILES_LIMIT = 10
GIT_LOG_DEPTH = 20  # commits to inspect for recent files

# Module-level only as documentation; runtime resolves via get_snapshot_dir()
SNAPSHOT_DIR = "~/.claude/discipline/snapshots"


def get_snapshot_dir() -> Path:
    explicit = os.environ.get("DISCIPLINE_SNAPSHOT_DIR")
    if explicit:
        return Path(explicit)
    return Path.home() / ".claude" / "discipline" / "snapshots"


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _git_remote_url() -> str | None:
    try:
        out = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _git_toplevel() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def get_project_key() -> str:
    explicit = os.environ.get("CLAUDE_PROJECT_DIR")
    if explicit:
        return _short_hash(str(Path(explicit).resolve()))
    remote = _git_remote_url()
    if remote:
        return _short_hash(remote)
    top = _git_toplevel()
    if top:
        return _short_hash(top)
    cwd = os.getcwd()
    if cwd:
        return _short_hash(cwd)
    return GLOBAL_PROJECT_KEY


def get_snapshot_path(project_key: str | None = None) -> Path:
    key = project_key or get_project_key()
    return get_snapshot_dir() / f"{key}.json"


def _git_branch() -> str | None:
    try:
        out = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _git_head_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _recent_files() -> list[dict[str, str]]:
    """Return top-N most-recently-touched files from the last GIT_LOG_DEPTH commits.

    Each entry: {"path": str, "ref": "HEAD~N"}. Order is most-recent-first.
    Skips files that no longer exist (deletions).
    """
    try:
        out = subprocess.run(
            ["git", "log", f"-{GIT_LOG_DEPTH}", "--name-only", "--pretty=format:"],
            capture_output=True, text=True, timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []
    if out.returncode != 0:
        return []
    seen: set[str] = set()
    files: list[dict[str, str]] = []
    for line in out.stdout.splitlines():
        path = line.strip()
        if not path or path in seen:
            continue
        seen.add(path)
        files.append({"path": path})
        if len(files) >= RECENT_FILES_LIMIT:
            break
    return files


def gather_state() -> dict[str, Any]:
    """Collect snapshot-eligible state from the current filesystem."""
    branch = _git_branch()
    head = _git_head_sha()
    git_info: dict[str, str] | None
    if branch and head:
        git_info = {"branch": branch, "head": head}
    else:
        git_info = None
    return {
        "timestamp": time.time(),
        "git": git_info,
        "recent_files": _recent_files() if git_info else [],
    }


def write_snapshot(state: dict[str, Any]) -> bool:
    path = get_snapshot_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False


def read_snapshot() -> dict[str, Any] | None:
    path = get_snapshot_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
