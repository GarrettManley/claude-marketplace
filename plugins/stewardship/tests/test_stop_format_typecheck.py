import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from stop_format_typecheck import (
    main,
    group_files,
    build_commands_for,
    DEFAULT_TIMEOUT_S,
    TOTAL_BUDGET_S,
)


@pytest.fixture
def ts_layout(tmp_path):
    (tmp_path / "tsconfig.json").write_text("{}")
    (tmp_path / "package.json").write_text('{"name":"x"}')
    src = tmp_path / "src"
    src.mkdir()
    f = src / "a.ts"
    f.write_text("")
    return tmp_path, f


@pytest.fixture
def py_layout(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    f = tmp_path / "mod.py"
    f.write_text("")
    return tmp_path, f


@pytest.fixture
def rs_layout(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n")
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    f = src / "main.rs"
    f.write_text("")
    return tmp_path, f


def test_group_files_separates_languages(ts_layout, py_layout, rs_layout):
    _, tsf = ts_layout
    _, pyf = py_layout
    _, rsf = rs_layout
    groups = group_files([str(tsf), str(pyf), str(rsf)])
    langs = {g["language"] for g in groups}
    assert langs == {"typescript", "python", "rust"}


def test_group_files_collapses_same_project(ts_layout):
    root, tsf = ts_layout
    other = root / "src" / "b.ts"
    other.write_text("")
    groups = group_files([str(tsf), str(other)])
    assert len(groups) == 1
    assert len(groups[0]["files"]) == 2


def test_build_commands_ts():
    cmds = build_commands_for("typescript", Path("/proj"), [Path("/proj/src/a.ts")])
    # Expect both prettier and tsc invocations
    assert any("prettier" in " ".join(c["args"]) for c in cmds)
    assert any("tsc" in " ".join(c["args"]) for c in cmds)


def test_build_commands_python():
    cmds = build_commands_for("python", Path("/proj"), [Path("/proj/mod.py")])
    assert any("ruff" in " ".join(c["args"]) for c in cmds)


def test_build_commands_rust():
    cmds = build_commands_for("rust", Path("/proj"), [Path("/proj/src/main.rs")])
    assert any("cargo" in " ".join(c["args"]) for c in cmds)
    args_joined = " ".join(" ".join(c["args"]) for c in cmds)
    assert "fmt" in args_joined or "check" in args_joined


def test_main_clears_accumulator(tmp_path, monkeypatch, ts_layout):
    """Accumulator should be deleted after Stop runs (clears state for next response)."""
    monkeypatch.setenv("CLAUDE_SESSION_ID", "test-clears")
    monkeypatch.setenv("STEWARDSHIP_TEST_NO_INVOKE", "1")
    # tempfile.tempdir is checked before env vars; patch it to use tmp_path
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    _, tsf = ts_layout
    accum = tmp_path / "stewardship-edited-test-clears.txt"
    accum.write_text(str(tsf) + "\n")
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    monkeypatch.setattr("sys.stdout", io.StringIO())
    rc = main([])
    assert rc == 0
    assert not accum.exists()


def test_main_passthrough_when_no_accumulator(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_SESSION_ID", "no-accum")
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    monkeypatch.setattr("sys.stdout", io.StringIO())
    rc = main([])
    assert rc == 0


def test_main_no_invoke_under_test_flag(tmp_path, monkeypatch, ts_layout):
    """STEWARDSHIP_TEST_NO_INVOKE=1 should prevent any subprocess.run call."""
    monkeypatch.setenv("CLAUDE_SESSION_ID", "no-invoke")
    monkeypatch.setenv("STEWARDSHIP_TEST_NO_INVOKE", "1")
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    _, tsf = ts_layout
    accum = tmp_path / "stewardship-edited-no-invoke.txt"
    accum.write_text(str(tsf) + "\n")
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    monkeypatch.setattr("sys.stdout", io.StringIO())
    with patch("subprocess.run") as mock_run:
        rc = main([])
    assert rc == 0
    mock_run.assert_not_called()
