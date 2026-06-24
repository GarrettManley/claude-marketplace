"""Storage layer for learning@garrettmanley.

Resolves the data root, computes project IDs from git remotes
(machine-portable) with toplevel + cwd fallbacks, and exposes path-builder
helpers for the rest of the plugin to use.

Data layout under the resolved root:

    instincts/
        personal/       # global auto-learned (Phase 2+)
        inherited/      # global imported via /instinct-import
    evolved/            # Phase 3
        agents/
        skills/
        commands/
    projects/
        <project-id>/
            instincts/
                personal/
                inherited/
            observations.jsonl    # Phase 1 (when LEARNING_OBSERVE=on)
            evolved/              # Phase 3

The 12-char project ID hashes the most-stable signal available:
git remote URL > git toplevel > CWD. "global" if nothing detectable.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

GLOBAL_PROJECT_ID = "global"


def get_data_root() -> Path:
    explicit = os.environ.get("LEARNING_DATA_ROOT")
    if explicit:
        return Path(explicit)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "claude-marketplace" / "learning"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "claude-marketplace" / "learning"
    return Path.home() / ".local" / "share" / "claude-marketplace" / "learning"


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
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def get_project_id() -> str:
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
    return GLOBAL_PROJECT_ID


def get_global_instincts_dir() -> Path:
    return get_data_root() / "instincts"


def get_project_dir(project_id: str) -> Path:
    return get_data_root() / "projects" / project_id


def get_project_instincts_dir(project_id: str) -> Path:
    return get_project_dir(project_id) / "instincts"


def get_observations_file(project_id: str) -> Path:
    return get_project_dir(project_id) / "observations.jsonl"


def list_instinct_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.yaml"))
