import io
import json
import os
import sys
import tempfile
from pathlib import Path
import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from post_edit_accumulator import (
    main,
    get_accumulator_path,
    KNOWN_EXTENSIONS,
)


@pytest.fixture
def tmp_accum(monkeypatch, tmp_path):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))  # Windows
    monkeypatch.setenv("CLAUDE_SESSION_ID", "test-session")
    return tmp_path


def _call(event, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    rc = main([])
    return rc, out.getvalue()


def test_edit_event_appends_path(tmp_accum, monkeypatch):
    rc, _ = _call({
        "tool_name": "Edit",
        "tool_input": {"file_path": "/some/file.ts"},
        "session_id": "test-session",
    }, monkeypatch)
    accum = Path(get_accumulator_path())
    assert accum.exists()
    assert "/some/file.ts" in accum.read_text()


def test_write_event_appends_path(tmp_accum, monkeypatch):
    rc, _ = _call({
        "tool_name": "Write",
        "tool_input": {"file_path": "/some/new.py"},
        "session_id": "test-session",
    }, monkeypatch)
    accum = Path(get_accumulator_path())
    assert "/some/new.py" in accum.read_text()


def test_multiedit_event_appends_all_paths(tmp_accum, monkeypatch):
    rc, _ = _call({
        "tool_name": "MultiEdit",
        "tool_input": {
            "edits": [
                {"file_path": "/a.ts"},
                {"file_path": "/b.py"},
                {"file_path": "/c.rs"},
            ],
        },
        "session_id": "test-session",
    }, monkeypatch)
    content = Path(get_accumulator_path()).read_text()
    assert "/a.ts" in content
    assert "/b.py" in content
    assert "/c.rs" in content


def test_unknown_extension_skipped(tmp_accum, monkeypatch):
    rc, _ = _call({
        "tool_name": "Edit",
        "tool_input": {"file_path": "/docs/README.md"},
        "session_id": "test-session",
    }, monkeypatch)
    accum = Path(get_accumulator_path())
    if accum.exists():
        assert "/docs/README.md" not in accum.read_text()


def test_invalid_json_passthrough(tmp_accum, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not-json{{"))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    rc = main([])
    assert rc == 0  # passthrough on parse error


def test_no_session_id_uses_cwd_hash(tmp_accum, monkeypatch):
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    path1 = get_accumulator_path()
    path2 = get_accumulator_path()
    assert path1 == path2  # deterministic from cwd
    assert "stewardship-edited-" in path1
