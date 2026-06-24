import io
import json
import subprocess
import sys
from pathlib import Path
import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from pre_compact_snapshot import main


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "a.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def tmp_snapshot_dir(monkeypatch, tmp_path):
    snap = tmp_path / "snap"
    monkeypatch.setenv("DISCIPLINE_SNAPSHOT_DIR", str(snap))
    return snap


def _call(event, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    monkeypatch.setattr("sys.stdout", io.StringIO())
    return main([])


def test_writes_snapshot_to_disk(git_repo, tmp_snapshot_dir, monkeypatch):
    rc = _call({"session_id": "s1"}, monkeypatch)
    assert rc == 0
    files = list(tmp_snapshot_dir.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["git"]["branch"] == "main"
    assert "recent_files" in data
    assert any(f["path"] == "a.py" for f in data["recent_files"])


def test_stdout_is_empty(git_repo, tmp_snapshot_dir, monkeypatch):
    """PreCompact hook should not emit to stdout — that channel isn't used for context."""
    in_buf = io.StringIO(json.dumps({"session_id": "s2"}))
    out_buf = io.StringIO()
    monkeypatch.setattr("sys.stdin", in_buf)
    monkeypatch.setattr("sys.stdout", out_buf)
    rc = main([])
    assert rc == 0
    assert out_buf.getvalue() == ""


def test_invalid_json_passthrough(tmp_snapshot_dir, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not-json{{"))
    monkeypatch.setattr("sys.stdout", io.StringIO())
    rc = main([])
    assert rc == 0
