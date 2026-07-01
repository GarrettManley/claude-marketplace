# plugins/stewardship/tests/test_run_with_flags.py
"""Tests for run_with_flags.py (vendored) — stdin reading, hook-enabled gate,
shell-script dispatch, Python import-and-run, generic dispatch, and edge cases."""
from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from run_with_flags import (
    _import_and_run_python,
    _passthrough,
    _spawn_generic,
    _spawn_shell,
    main,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_py_hook(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# _passthrough
# ---------------------------------------------------------------------------

def test_passthrough_returns_0():
    assert _passthrough("some stdin content") == 0


# ---------------------------------------------------------------------------
# main() — argument-count check
# ---------------------------------------------------------------------------

def test_main_too_few_args_returns_2(capsys):
    rc = main(["run_with_flags.py"])
    assert rc == 2


def test_main_exactly_three_args_returns_2(capsys):
    rc = main(["run_with_flags.py", "script.py", "hook:id"])
    assert rc == 2


# ---------------------------------------------------------------------------
# main() — hook disabled path
# ---------------------------------------------------------------------------

def test_main_disabled_hook_skips_invocation(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("STEWARDSHIP_DISABLED_HOOKS", "stewardship:drift")
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    rc = main([
        "run_with_flags.py",
        str(tmp_path / "noop.py"),
        "stewardship:drift",
        "minimal,standard,strict",
    ])
    assert rc == 0


# ---------------------------------------------------------------------------
# main() — hook script not found
# ---------------------------------------------------------------------------

def test_main_hook_script_not_found_passthrough(tmp_path, monkeypatch, capsys, clean_env):
    monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "standard")
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    rc = main([
        "run_with_flags.py",
        str(tmp_path / "missing_hook.py"),
        "stewardship:drift",
        "minimal,standard",
    ])
    assert rc == 0
    err = capsys.readouterr().err
    assert "not found" in err


# ---------------------------------------------------------------------------
# main() → _import_and_run_python
# ---------------------------------------------------------------------------

def test_main_python_hook_main_called(tmp_path, monkeypatch, clean_env, capsys):
    monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "standard")
    hook = _make_py_hook(tmp_path, "my_hook.py", "def main():\n    return 0\n")
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    rc = main(["run_with_flags.py", str(hook), "stewardship:drift", "minimal,standard"])
    assert rc == 0


def test_main_python_hook_main_returns_nonzero(tmp_path, monkeypatch, clean_env):
    monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "standard")
    hook = _make_py_hook(tmp_path, "bad_hook.py", "def main():\n    return 42\n")
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    rc = main(["run_with_flags.py", str(hook), "stewardship:drift", "minimal,standard"])
    assert rc == 42


def test_main_python_hook_no_main_returns_0(tmp_path, monkeypatch, clean_env):
    monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "standard")
    hook = _make_py_hook(tmp_path, "no_main.py", "X = 1\n")
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    rc = main(["run_with_flags.py", str(hook), "stewardship:drift", "minimal,standard"])
    assert rc == 0


def test_main_python_hook_sysexit_at_module_top_level(tmp_path, monkeypatch, clean_env):
    monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "standard")
    hook = _make_py_hook(tmp_path, "exits.py", "import sys\nsys.exit(3)\n")
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    rc = main(["run_with_flags.py", str(hook), "stewardship:drift", "minimal,standard"])
    assert rc == 3


def test_main_python_hook_main_sysexit(tmp_path, monkeypatch, clean_env):
    monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "standard")
    hook = _make_py_hook(tmp_path, "main_exit.py", "import sys\ndef main():\n    sys.exit(7)\n")
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    rc = main(["run_with_flags.py", str(hook), "stewardship:drift", "minimal,standard"])
    assert rc == 7


def test_main_python_hook_import_exception_returns_0(tmp_path, monkeypatch, clean_env, capsys):
    monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "standard")
    hook = _make_py_hook(tmp_path, "broken.py", "raise ValueError('oops')\n")
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    rc = main(["run_with_flags.py", str(hook), "stewardship:drift", "minimal,standard"])
    assert rc == 0  # don't break the hook chain
    err = capsys.readouterr().err
    assert "import error" in err


def test_main_python_hook_runtime_exception_returns_0(tmp_path, monkeypatch, clean_env, capsys):
    monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "standard")
    hook = _make_py_hook(tmp_path, "runtime_err.py", "def main():\n    raise RuntimeError('boom')\n")
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    rc = main(["run_with_flags.py", str(hook), "stewardship:drift", "minimal,standard"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "runtime error" in err


# ---------------------------------------------------------------------------
# _import_and_run_python — spec is None path
# ---------------------------------------------------------------------------

def test_import_and_run_python_spec_none(tmp_path, monkeypatch):
    hook = _make_py_hook(tmp_path, "ok.py", "def main():\n    return 0\n")
    with patch("importlib.util.spec_from_file_location", return_value=None):
        rc = _import_and_run_python(hook, "stdin text")
    assert rc == 0


def test_import_and_run_python_spec_no_loader(tmp_path, monkeypatch):
    hook = _make_py_hook(tmp_path, "ok2.py", "def main():\n    return 0\n")
    mock_spec = MagicMock()
    mock_spec.loader = None
    with patch("importlib.util.spec_from_file_location", return_value=mock_spec):
        rc = _import_and_run_python(hook, "stdin text")
    assert rc == 0


# ---------------------------------------------------------------------------
# _spawn_shell
# ---------------------------------------------------------------------------

def test_spawn_shell_runs_script(tmp_path, monkeypatch, capsys):
    script = tmp_path / "greet.sh"
    script.write_text("echo hello\n", encoding="utf-8")
    mock_result = MagicMock()
    mock_result.stdout = "hello\n"
    mock_result.stderr = ""
    mock_result.returncode = 0
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        rc = _spawn_shell(script, "")
    assert rc == 0
    out = capsys.readouterr().out
    assert "hello" in out


def test_spawn_shell_nonexistent_script_surfaces_bash_error(tmp_path, capsys):
    """_spawn_shell no longer reads the script's content in Python (it passes the
    real path directly to bash, to preserve BASH_SOURCE self-location semantics --
    see run_with_flags.py's _spawn_shell) so there is no more run_with_flags-authored
    "cannot read" message for an unreadable/missing script. bash itself now surfaces
    the failure: a nonexistent path reliably reproduces this across platforms (a
    permission-denied file does not, since chmod 000 does not block reads on this
    filesystem)."""
    script = tmp_path / "does_not_exist.sh"
    rc = _spawn_shell(script, "")
    assert rc != 0
    err = capsys.readouterr().err
    assert "no such file or directory" in err.lower()


# ---------------------------------------------------------------------------
# _spawn_generic
# ---------------------------------------------------------------------------

def test_spawn_generic_runs_and_returns_code(tmp_path, capsys):
    script = tmp_path / "tool"
    script.write_text("")
    mock_result = MagicMock()
    mock_result.stdout = "output\n"
    mock_result.stderr = ""
    mock_result.returncode = 5
    with patch("subprocess.run", return_value=mock_result):
        rc = _spawn_generic(script, "stdin data")
    assert rc == 5
    out = capsys.readouterr().out
    assert "output" in out


# ---------------------------------------------------------------------------
# main() → shell script suffix routing
# ---------------------------------------------------------------------------

def test_main_sh_suffix_routes_to_spawn_shell(tmp_path, monkeypatch, clean_env, capsys):
    monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "standard")
    script = tmp_path / "my_hook.sh"
    script.write_text("echo from-shell\n", encoding="utf-8")
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    mock_result = MagicMock()
    mock_result.stdout = "from-shell\n"
    mock_result.stderr = ""
    mock_result.returncode = 0
    with patch("subprocess.run", return_value=mock_result):
        rc = main(["run_with_flags.py", str(script), "stewardship:drift", "minimal,standard"])
    assert rc == 0


# ---------------------------------------------------------------------------
# main() → unknown suffix routes to spawn_generic
# ---------------------------------------------------------------------------

def test_main_unknown_suffix_routes_to_spawn_generic(tmp_path, monkeypatch, clean_env, capsys):
    monkeypatch.setenv("STEWARDSHIP_HOOK_PROFILE", "standard")
    script = tmp_path / "my_hook.rb"
    script.write_text("puts 'hi'", encoding="utf-8")
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    mock_result = MagicMock()
    mock_result.stdout = "hi\n"
    mock_result.stderr = ""
    mock_result.returncode = 0
    with patch("subprocess.run", return_value=mock_result):
        rc = main(["run_with_flags.py", str(script), "stewardship:drift", "minimal,standard"])
    assert rc == 0
