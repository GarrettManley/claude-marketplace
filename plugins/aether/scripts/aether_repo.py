#!/usr/bin/env python3
"""Shared repo-shape detection for the aether PostToolUse reminder hooks.

The three reminder hooks (``classifier_eval_reminder``, ``gameplay_harness_reminder``,
``rust_rebuild_reminder``) fire on edits to specific source files in an Aether
Engine checkout. Each must:

  1. compute the *repo-relative* path of the edited file, so the trigger-file
     match is stable regardless of where the repo is checked out or what the
     top-level directory is named; and
  2. no-op when the edit is outside an Aether repo.

Earlier versions hard-coded ``REPO_ROOT = "/c/Users/<username>/<repo>"`` and gated
on the literal substring ``"<repo>/"``. That broke once the repo lived
anywhere else (e.g. ``…/<workspace>/<repo>``): the rust-rebuild staleness
probe silently no-opped (wrong absolute root -> OSError -> swallowed), and the
whole family was brittle to the directory name. We instead locate the repo root
by walking up from the edited file to the nearest ancestor that contains the
Aether root marker ``core/Cargo.toml`` — name-independent and worktree-safe
(each linked git worktree carries a full working tree, so the marker is present
at the worktree root too).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Aether repo-root sentinel: the Rust core's manifest. A tuple so it joins with
# the OS-native separator on either platform.
_ROOT_MARKER = ("core", "Cargo.toml")


def load_payload():
    """Parse the hook's stdin JSON payload, or None if it is not valid JSON."""
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return None


def edited_file_path(payload) -> str | None:
    """Extract the edited file path from an Edit/Write/MultiEdit payload."""
    if not isinstance(payload, dict):
        return None
    raw = (
        payload.get("tool_input", {}).get("file_path")
        or payload.get("tool_response", {}).get("filePath")
        or ""
    )
    return raw or None


def find_repo_root(file_path: str) -> Path | None:
    """Nearest ancestor of ``file_path`` containing ``core/Cargo.toml``.

    Returns None when the edit is outside an Aether-shaped repo, which callers
    treat as "no-op".
    """
    try:
        resolved = Path(file_path).resolve()
    except (OSError, ValueError):
        return None
    for ancestor in resolved.parents:
        if ancestor.joinpath(*_ROOT_MARKER).is_file():
            return ancestor
    return None


def repo_relative(file_path: str):
    """Return ``(repo_root, posix_relative_path)`` or ``(None, None)``.

    ``posix_relative_path`` always uses ``/`` separators so callers can compare
    against the forward-slash trigger-file constants on any platform.
    """
    root = find_repo_root(file_path)
    if root is None:
        return None, None
    try:
        rel = Path(file_path).resolve().relative_to(root)
    except (OSError, ValueError):
        return None, None
    return root, rel.as_posix()
