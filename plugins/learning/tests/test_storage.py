import os
import sys
import hashlib
from pathlib import Path
import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from storage import (
    get_data_root,
    get_project_id,
    get_project_dir,
    get_global_instincts_dir,
    get_project_instincts_dir,
    get_observations_file,
    list_instinct_files,
    GLOBAL_PROJECT_ID,
)


@pytest.fixture
def tmp_data_root(monkeypatch, tmp_path):
    monkeypatch.setenv("LEARNING_DATA_ROOT", str(tmp_path))
    return tmp_path


class TestGetDataRoot:
    def test_uses_learning_data_root_env(self, tmp_data_root):
        assert get_data_root() == tmp_data_root

    def test_falls_back_to_localappdata_on_win(self, monkeypatch, tmp_path):
        monkeypatch.delenv("LEARNING_DATA_ROOT", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        monkeypatch.setattr("sys.platform", "win32")
        result = get_data_root()
        assert "claude-marketplace" in str(result).lower() and "learning" in str(result).lower()

    def test_falls_back_to_xdg_data_home_on_posix(self, monkeypatch, tmp_path):
        monkeypatch.delenv("LEARNING_DATA_ROOT", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        monkeypatch.setattr("sys.platform", "linux")
        result = get_data_root()
        # tmp_path / claude-marketplace / learning
        assert "claude-marketplace" in result.parts
        assert "learning" in result.parts


class TestGetProjectId:
    def test_env_var_wins(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/explicit/dir")
        pid = get_project_id()
        assert len(pid) == 12  # 12-char hex
        # Should be deterministic
        assert get_project_id() == pid

    def test_falls_back_to_global_when_no_signals(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        # No git in tmp_path
        pid = get_project_id()
        # Either a CWD-hash (12 chars) or "global" if cwd unavailable
        assert pid == GLOBAL_PROJECT_ID or len(pid) == 12


class TestDirectoryStructure:
    def test_global_instincts_dir_resolves(self, tmp_data_root):
        d = get_global_instincts_dir()
        assert "instincts" in d.parts
        assert d.is_relative_to(tmp_data_root)

    def test_project_dir_uses_project_id(self, tmp_data_root, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/some/dir")
        pid = get_project_id()
        d = get_project_dir(pid)
        assert pid in d.parts

    def test_observations_file_under_project(self, tmp_data_root, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/some/dir")
        pid = get_project_id()
        f = get_observations_file(pid)
        assert f.name == "observations.jsonl"
        assert pid in f.parts


class TestListInstinctFiles:
    def test_empty_when_no_files(self, tmp_data_root):
        d = get_global_instincts_dir() / "personal"
        d.mkdir(parents=True)
        assert list_instinct_files(d) == []

    def test_finds_yaml_files(self, tmp_data_root):
        d = get_global_instincts_dir() / "personal"
        d.mkdir(parents=True)
        (d / "a.yaml").write_text("dummy")
        (d / "b.yaml").write_text("dummy")
        (d / "ignored.txt").write_text("dummy")
        files = list_instinct_files(d)
        assert len(files) == 2
        assert all(f.suffix == ".yaml" for f in files)


def test_global_project_id_constant():
    assert GLOBAL_PROJECT_ID == "global"
