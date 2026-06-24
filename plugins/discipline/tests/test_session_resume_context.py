import io
import json
import sys
from pathlib import Path
import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from session_resume_context import main, format_snapshot
from snapshot import get_snapshot_path, write_snapshot


@pytest.fixture
def tmp_snapshot_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCIPLINE_SNAPSHOT_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/explicit/proj")
    return tmp_path


def _call(monkeypatch, stdin_text: str = "{}"):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin_text))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    rc = main([])
    return rc, out.getvalue()


def test_no_snapshot_silent(tmp_snapshot_dir, monkeypatch):
    rc, out = _call(monkeypatch)
    assert rc == 0
    assert out == ""


def test_writes_additional_context_when_snapshot_exists(tmp_snapshot_dir, monkeypatch):
    state = {
        "timestamp": 1000.0,
        "git": {"branch": "feat/x", "head": "a" * 40},
        "recent_files": [{"path": "src/a.py"}, {"path": "src/b.py"}],
    }
    write_snapshot(state)
    rc, out = _call(monkeypatch)
    assert rc == 0
    payload = json.loads(out)
    assert "hookSpecificOutput" in payload
    output = payload["hookSpecificOutput"]
    assert output.get("hookEventName") == "SessionStart"
    ctx = output.get("additionalContext", "")
    assert "feat/x" in ctx
    assert "src/a.py" in ctx
    assert "src/b.py" in ctx


def test_format_includes_branch_and_files():
    state = {
        "timestamp": 1000.0,
        "git": {"branch": "main", "head": "deadbeef" * 5},
        "recent_files": [{"path": "x.py"}, {"path": "y.py"}],
    }
    text = format_snapshot(state)
    assert "main" in text
    assert "x.py" in text
    assert "y.py" in text


def test_format_handles_no_git():
    state = {"timestamp": 1000.0, "git": None, "recent_files": []}
    text = format_snapshot(state)
    # Should still produce something, not error
    assert isinstance(text, str)


def test_truncates_long_file_list():
    state = {
        "timestamp": 1000.0,
        "git": {"branch": "main", "head": "x" * 40},
        "recent_files": [{"path": f"f{i}.py"} for i in range(50)],
    }
    text = format_snapshot(state)
    # Should not contain all 50 files (must truncate)
    assert text.count("\n") < 50


def test_invalid_json_input_still_works(tmp_snapshot_dir, monkeypatch):
    state = {
        "timestamp": 1000.0,
        "git": {"branch": "main", "head": "z" * 40},
        "recent_files": [{"path": "ok.py"}],
    }
    write_snapshot(state)
    rc, out = _call(monkeypatch, stdin_text="not-json{{")
    # Should still emit the snapshot (stdin parse failure is non-fatal)
    assert rc == 0
    payload = json.loads(out)
    assert "additionalContext" in payload["hookSpecificOutput"]
