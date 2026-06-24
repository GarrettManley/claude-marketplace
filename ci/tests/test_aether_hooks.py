#!/usr/bin/env python3
"""Tests for the aether PostToolUse reminder hooks and their shared repo helper.

Regression coverage for the path-hardcoding regression: the reminders used to hard-code
``REPO_ROOT = "/c/Users/<username>/<repo>"`` and gate on the literal substring
``"<repo>/"``. These tests build a synthetic Aether repo under a directory
that is deliberately NOT named after the original repo, at an arbitrary temp location, so
they fail against the old name-/path-hardcoded logic and pass against the
marker-based ``aether_repo`` resolution.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / "plugins" / "aether" / "hooks"
SCRIPTS_DIR = REPO_ROOT / "plugins" / "aether" / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))
import aether_repo  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def aether_checkout(tmp_path: Path) -> Path:
    """A synthetic Aether checkout under a directory name unrelated to the original repo."""
    root = tmp_path / "acme-engine"  # intentionally NOT the original repo name
    (root / "core" / "src").mkdir(parents=True)
    (root / "core" / "target" / "release").mkdir(parents=True)
    (root / "src" / "llm").mkdir(parents=True)
    (root / "core" / "Cargo.toml").write_text("[package]\nname='core'\n", encoding="utf-8")
    (root / "core" / "src" / "main.rs").write_text("fn main() {}\n", encoding="utf-8")
    (root / "core" / "target" / "release" / "core.exe").write_text("", encoding="utf-8")
    (root / "src" / "dm.ts").write_text("// dm\n", encoding="utf-8")
    (root / "src" / "llm" / "classifier_prompt.ts").write_text("// clf\n", encoding="utf-8")
    (root / "README.md").write_text("# acme\n", encoding="utf-8")
    return root


def run_hook(hook_name: str, file_path: Path) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"file_path": str(file_path)}})
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / hook_name)],
        input=payload, capture_output=True, text=True, timeout=15,
    )


# --------------------------------------------------------------------------- #
# Helper unit tests
# --------------------------------------------------------------------------- #
def test_find_repo_root_locates_marker(aether_checkout: Path):
    target = aether_checkout / "src" / "llm" / "classifier_prompt.ts"
    assert aether_repo.find_repo_root(str(target)) == aether_checkout.resolve()


def test_find_repo_root_none_outside_repo(tmp_path: Path):
    loose = tmp_path / "loose" / "src" / "llm" / "classifier_prompt.ts"
    loose.parent.mkdir(parents=True)
    loose.write_text("// x\n", encoding="utf-8")
    assert aether_repo.find_repo_root(str(loose)) is None


def test_repo_relative_posix(aether_checkout: Path):
    target = aether_checkout / "core" / "src" / "main.rs"
    root, rel = aether_repo.repo_relative(str(target))
    assert root == aether_checkout.resolve()
    assert rel == "core/src/main.rs"  # forward slashes on every platform


# --------------------------------------------------------------------------- #
# Hook integration tests — name/path independence (the path-hardcoding regression)
# --------------------------------------------------------------------------- #
def test_classifier_eval_fires_in_arbitrary_dir(aether_checkout: Path):
    proc = run_hook("classifier_eval_reminder.py", aether_checkout / "src" / "llm" / "classifier_prompt.ts")
    assert proc.returncode == 0
    assert "[classifier-eval-reminder]" in proc.stdout


def test_gameplay_harness_fires_in_arbitrary_dir(aether_checkout: Path):
    proc = run_hook("gameplay_harness_reminder.py", aether_checkout / "src" / "dm.ts")
    assert proc.returncode == 0
    assert "[gameplay-harness-reminder]" in proc.stdout


def test_rust_rebuild_fires_in_arbitrary_dir(aether_checkout: Path):
    proc = run_hook("rust_rebuild_reminder.py", aether_checkout / "core" / "src" / "main.rs")
    assert proc.returncode == 0
    assert "[rust-rebuild-reminder]" in proc.stdout


# --------------------------------------------------------------------------- #
# rust_rebuild staleness — the REPO_ROOT-hardcode regression
# --------------------------------------------------------------------------- #
def test_rust_rebuild_staleness_when_binary_older(aether_checkout: Path):
    src = aether_checkout / "core" / "src" / "main.rs"
    binary = aether_checkout / "core" / "target" / "release" / "core.exe"
    now = time.time()
    os.utime(binary, (now - 100, now - 100))  # binary older than source
    os.utime(src, (now, now))
    proc = run_hook("rust_rebuild_reminder.py", src)
    assert proc.returncode == 0
    assert "[STALE:" in proc.stdout  # would never appear under the old hardcoded root


def test_rust_rebuild_no_staleness_when_binary_newer(aether_checkout: Path):
    src = aether_checkout / "core" / "src" / "main.rs"
    binary = aether_checkout / "core" / "target" / "release" / "core.exe"
    now = time.time()
    os.utime(src, (now - 100, now - 100))
    os.utime(binary, (now, now))  # binary newer than source
    proc = run_hook("rust_rebuild_reminder.py", src)
    assert proc.returncode == 0
    assert "[rust-rebuild-reminder]" in proc.stdout
    assert "[STALE:" not in proc.stdout


# --------------------------------------------------------------------------- #
# No-op contracts
# --------------------------------------------------------------------------- #
def test_silent_for_nontrigger_file(aether_checkout: Path):
    proc = run_hook("classifier_eval_reminder.py", aether_checkout / "README.md")
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_silent_outside_aether_repo(tmp_path: Path):
    # Trigger *filename* but no core/Cargo.toml ancestor -> must no-op.
    loose = tmp_path / "loose" / "src" / "llm" / "classifier_prompt.ts"
    loose.parent.mkdir(parents=True)
    loose.write_text("// x\n", encoding="utf-8")
    proc = run_hook("classifier_eval_reminder.py", loose)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_worktree_path_resolves(aether_checkout: Path):
    # A linked git worktree carries a full working tree, so it has its own
    # core/Cargo.toml; the nearest-marker walk resolves to the worktree root.
    wt = aether_checkout / ".worktrees" / "feat-x"
    (wt / "core").mkdir(parents=True)
    (wt / "src").mkdir(parents=True)
    (wt / "core" / "Cargo.toml").write_text("[package]\nname='core'\n", encoding="utf-8")
    (wt / "src" / "dm.ts").write_text("// dm\n", encoding="utf-8")
    proc = run_hook("gameplay_harness_reminder.py", wt / "src" / "dm.ts")
    assert proc.returncode == 0
    assert "[gameplay-harness-reminder]" in proc.stdout
