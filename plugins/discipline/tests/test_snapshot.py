import json
import os
import sys
import subprocess
from pathlib import Path
import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from snapshot import (
    SNAPSHOT_DIR,
    GLOBAL_PROJECT_KEY,
    get_snapshot_dir,
    get_project_key,
    get_snapshot_path,
    gather_state,
    write_snapshot,
    read_snapshot,
)


@pytest.fixture
def tmp_snapshot_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCIPLINE_SNAPSHOT_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """Initialize a small git repo in tmp_path with one commit + one file."""
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    f = tmp_path / "foo.py"
    f.write_text("x = 1\n")
    subprocess.run(["git", "add", "foo.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestProjectKey:
    def test_uses_explicit_env(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/explicit/dir")
        key = get_project_key()
        assert len(key) == 12

    def test_deterministic(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/some/dir")
        assert get_project_key() == get_project_key()

    def test_falls_back_to_cwd_when_no_signals(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        key = get_project_key()
        assert key == GLOBAL_PROJECT_KEY or len(key) == 12


class TestSnapshotDir:
    def test_explicit_env_wins(self, tmp_snapshot_dir):
        assert get_snapshot_dir() == tmp_snapshot_dir

    def test_default_under_dot_claude(self, monkeypatch):
        monkeypatch.delenv("DISCIPLINE_SNAPSHOT_DIR", raising=False)
        d = get_snapshot_dir()
        assert "discipline" in d.parts
        assert "snapshots" in d.parts


class TestGatherState:
    def test_in_git_repo_returns_branch_and_head(self, git_repo):
        state = gather_state()
        assert state["git"]["branch"] == "main"
        assert len(state["git"]["head"]) == 40  # full SHA
        assert isinstance(state["recent_files"], list)
        assert "foo.py" in [f["path"] for f in state["recent_files"]]

    def test_outside_git_returns_no_git_section(self, tmp_path, monkeypatch):
        # Stop git's repo discovery from walking up into an enclosing repo (the
        # home dir is itself a git repo on some dev machines, and tmp_path lives
        # under it), so this genuinely exercises the "outside any git repo" path.
        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
        monkeypatch.chdir(tmp_path)
        state = gather_state()
        assert state["git"] is None
        assert state["recent_files"] == []

    def test_timestamp_present(self, git_repo):
        state = gather_state()
        assert isinstance(state["timestamp"], (int, float))


class TestWriteReadSnapshot:
    def test_roundtrip(self, tmp_snapshot_dir, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/test/proj")
        state = {"git": {"branch": "main", "head": "abc" * 10 + "abcdef0123"}, "recent_files": [], "timestamp": 100.0}
        write_snapshot(state)
        loaded = read_snapshot()
        assert loaded == state

    def test_read_missing_returns_none(self, tmp_snapshot_dir, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/test/proj-never-written")
        assert read_snapshot() is None

    def test_read_corrupt_returns_none(self, tmp_snapshot_dir, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/test/proj-corrupt")
        path = get_snapshot_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not-json{{")
        assert read_snapshot() is None
