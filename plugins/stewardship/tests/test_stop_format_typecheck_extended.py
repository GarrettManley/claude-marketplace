# plugins/stewardship/tests/test_stop_format_typecheck_extended.py
"""Extended tests for stop_format_typecheck.py — covers _run_command, edge
cases in group_files (nonexistent file, no language, no root), and the
main() budget / timeout logic."""
from __future__ import annotations

import io
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from stop_format_typecheck import (
    _run_command,
    build_commands_for,
    group_files,
    main,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def py_layout(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    f = tmp_path / "mod.py"
    f.write_text("x = 1\n")
    return tmp_path, f


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
def rs_layout(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n")
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    f = src / "main.rs"
    f.write_text("")
    return tmp_path, f


# ---------------------------------------------------------------------------
# _run_command
# ---------------------------------------------------------------------------

class TestRunCommand:
    def _make_cmd(self, bin_name: str, root: Path) -> dict:
        return {
            "bin": bin_name,
            "args": [bin_name, "--version"],
            "cwd": root,
            "shell": False,
            "label": "test-label",
        }

    def test_bin_not_on_path_silently_skips(self, tmp_path):
        """When shutil.which returns None the command must be skipped (no exception)."""
        cmd = self._make_cmd("definitely_not_a_real_binary_xyzzy", tmp_path)
        with patch("shutil.which", return_value=None):
            _run_command(cmd, timeout_s=5)  # must not raise

    def test_timeout_expired_silently_skipped(self, tmp_path):
        cmd = self._make_cmd("ruff", tmp_path)
        with patch("shutil.which", return_value="/usr/bin/ruff"):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ruff", 5)):
                _run_command(cmd, timeout_s=5)  # must not raise

    def test_oserror_silently_skipped(self, tmp_path):
        cmd = self._make_cmd("ruff", tmp_path)
        with patch("shutil.which", return_value="/usr/bin/ruff"):
            with patch("subprocess.run", side_effect=OSError("no binary")):
                _run_command(cmd, timeout_s=5)  # must not raise

    def test_nonzero_exit_writes_to_stderr(self, tmp_path, capsys):
        cmd = self._make_cmd("ruff", tmp_path)
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "some stdout\n"
        mock_result.stderr = "some error\n"
        with patch("shutil.which", return_value="/usr/bin/ruff"):
            with patch("subprocess.run", return_value=mock_result):
                _run_command(cmd, timeout_s=5)
        captured = capsys.readouterr()
        assert "test-label" in captured.err
        assert "some stdout" in captured.err or "some error" in captured.err

    def test_zero_exit_no_stderr_output(self, tmp_path, capsys):
        cmd = self._make_cmd("ruff", tmp_path)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        with patch("shutil.which", return_value="/usr/bin/ruff"):
            with patch("subprocess.run", return_value=mock_result):
                _run_command(cmd, timeout_s=5)
        captured = capsys.readouterr()
        assert captured.err == ""


# ---------------------------------------------------------------------------
# group_files — edge cases (lines 44, 47, 50)
# ---------------------------------------------------------------------------

class TestGroupFilesEdgeCases:
    def test_nonexistent_file_skipped(self, tmp_path):
        groups = group_files([str(tmp_path / "ghost.ts")])
        assert groups == []

    def test_unknown_language_skipped(self, tmp_path):
        f = tmp_path / "README.md"
        f.write_text("")
        groups = group_files([str(f)])
        assert groups == []

    def test_no_project_root_skipped(self, tmp_path):
        # .py file exists but no pyproject.toml anywhere near tmp_path
        f = tmp_path / "orphan.py"
        f.write_text("")
        groups = group_files([str(f)])
        # No pyproject.toml → find_project_root returns None → group skipped
        assert groups == []


# ---------------------------------------------------------------------------
# build_commands_for — typescript without .ts files (tsc omitted)
# ---------------------------------------------------------------------------

class TestBuildCommandsForEdgeCases:
    def test_ts_only_js_no_tsc(self):
        # .js files should trigger prettier but NOT tsc
        cmds = build_commands_for("typescript", Path("/proj"), [Path("/proj/src/a.js")])
        labels = [c["label"] for c in cmds]
        assert "prettier" in labels
        assert "tsc" not in labels

    def test_ts_with_ts_files_includes_tsc(self):
        cmds = build_commands_for("typescript", Path("/proj"), [Path("/proj/src/a.ts")])
        labels = [c["label"] for c in cmds]
        assert "tsc" in labels

    def test_unknown_language_returns_empty(self):
        cmds = build_commands_for("cobol", Path("/proj"), [Path("/proj/main.cbl")])
        assert cmds == []


# ---------------------------------------------------------------------------
# main() — budget / per-cmd-timeout calculation and early-exit paths
# ---------------------------------------------------------------------------

class TestMainBudget:
    def test_empty_accumulator_file_returns_0(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_SESSION_ID", "budget-empty")
        monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
        accum = tmp_path / "stewardship-edited-budget-empty.txt"
        accum.write_text("\n\n")  # only blank lines
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        rc = main([])
        assert rc == 0

    def test_all_groups_skipped_returns_0(self, tmp_path, monkeypatch):
        """If group_files produces no groups, main returns 0 before any command."""
        monkeypatch.setenv("CLAUDE_SESSION_ID", "budget-nogrp")
        monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
        accum = tmp_path / "stewardship-edited-budget-nogrp.txt"
        # Ghost file that doesn't exist → group_files skips it
        accum.write_text("/nonexistent/path/to/file.py\n")
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        rc = main([])
        assert rc == 0

    def test_multiple_batches_respect_budget(self, tmp_path, monkeypatch, py_layout, rs_layout):
        """When multiple language groups exist, STEWARDSHIP_TEST_NO_INVOKE=1 prevents invocations."""
        monkeypatch.setenv("CLAUDE_SESSION_ID", "budget-multi")
        monkeypatch.setenv("STEWARDSHIP_TEST_NO_INVOKE", "1")
        monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
        _, pyf = py_layout
        _, rsf = rs_layout
        accum = tmp_path / "stewardship-edited-budget-multi.txt"
        accum.write_text(f"{pyf}\n{rsf}\n")
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        with patch("subprocess.run") as mock_run:
            rc = main([])
        assert rc == 0
        mock_run.assert_not_called()

    def test_accumulator_deleted_even_on_empty_groups(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_SESSION_ID", "budget-del")
        monkeypatch.setenv("STEWARDSHIP_TEST_NO_INVOKE", "1")
        monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
        accum = tmp_path / "stewardship-edited-budget-del.txt"
        accum.write_text("/nonexistent/file.py\n")
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        main([])
        assert not accum.exists()

    def test_unlink_oserror_swallowed(self, tmp_path, monkeypatch, py_layout):
        """OSError on unlink (line 155-156) should be swallowed; rest of main runs."""
        monkeypatch.setenv("CLAUDE_SESSION_ID", "budget-unlink-err")
        monkeypatch.setenv("STEWARDSHIP_TEST_NO_INVOKE", "1")
        monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
        _, pyf = py_layout
        accum = tmp_path / "stewardship-edited-budget-unlink-err.txt"
        accum.write_text(str(pyf) + "\n")

        real_unlink = Path.unlink

        def fake_unlink(self, *args, **kwargs):
            if self == accum:
                raise OSError("cannot delete")
            return real_unlink(self, *args, **kwargs)

        with patch.object(Path, "unlink", fake_unlink):
            rc = main([])
        assert rc == 0

    def test_invokes_run_command_when_no_skip_flag(self, tmp_path, monkeypatch, py_layout):
        """Without STEWARDSHIP_TEST_NO_INVOKE, _run_command is reached (line 183)."""
        monkeypatch.setenv("CLAUDE_SESSION_ID", "budget-invoke")
        monkeypatch.delenv("STEWARDSHIP_TEST_NO_INVOKE", raising=False)
        monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
        _, pyf = py_layout
        accum = tmp_path / "stewardship-edited-budget-invoke.txt"
        accum.write_text(str(pyf) + "\n")
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        # _run_command skips silently when bin not on PATH — shutil.which returns None
        import shutil
        with patch.object(shutil, "which", return_value=None):
            rc = main([])
        assert rc == 0

    def test_oserror_on_accumulator_read_returns_0(self, tmp_path, monkeypatch):
        """OSError when reading the accumulator is swallowed → return 0."""
        monkeypatch.setenv("CLAUDE_SESSION_ID", "budget-oserr")
        monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
        accum = tmp_path / "stewardship-edited-budget-oserr.txt"
        accum.write_text("")

        real_read_text = Path.read_text

        def fake_read(self, *args, **kwargs):
            if self == accum:
                raise OSError("boom")
            return real_read_text(self, *args, **kwargs)

        with patch.object(Path, "read_text", fake_read):
            rc = main([])
        assert rc == 0
