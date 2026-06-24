# plugins/discipline/tests/test_init.py
"""Behavioral subprocess tests for discipline/scripts/init.sh (idempotency)."""
import os
import subprocess
from pathlib import Path

import pytest

# On Windows the system `bash` resolves to WSL; we must use Git Bash explicitly.
_GIT_BASH = r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else "bash"
_INIT_SH = str(Path(__file__).parent.parent / "scripts" / "init.sh")

_TARGET = Path(".claude") / "discipline.local.md"


def _run(cwd: Path, *args) -> subprocess.CompletedProcess:
    """Run init.sh with cwd set to the temp project directory."""
    return subprocess.run(
        [_GIT_BASH, _INIT_SH, *args],
        capture_output=True,
        text=True,
        env=os.environ,
        cwd=str(cwd),
    )


class TestDisciplineInit:
    def test_creates_config_on_first_run(self, tmp_path):
        result = _run(tmp_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        config_file = tmp_path / _TARGET
        assert config_file.is_file(), "discipline.local.md should be created"
        assert config_file.stat().st_size > 0

    def test_status_line_on_first_run(self, tmp_path):
        result = _run(tmp_path)
        assert result.returncode == 0
        assert "CONFIGURED" in result.stdout
        assert "discipline.local.md" in result.stdout

    def test_idempotent_already_configured(self, tmp_path):
        # First run: scaffold the file
        first = _run(tmp_path)
        assert first.returncode == 0
        first_content = (tmp_path / _TARGET).read_text()

        # Second run: should be no-op
        second = _run(tmp_path)
        assert second.returncode == 0
        assert "already configured" in second.stdout

        # File unchanged
        assert (tmp_path / _TARGET).read_text() == first_content

    def test_exit_0_on_both_runs(self, tmp_path):
        assert _run(tmp_path).returncode == 0
        assert _run(tmp_path).returncode == 0

    def test_force_overwrites_existing_config(self, tmp_path):
        _run(tmp_path)
        config_file = tmp_path / _TARGET
        # Corrupt the file to verify --force restores it
        config_file.write_text("# overwritten sentinel\n")

        result = _run(tmp_path, "--force")
        assert result.returncode == 0
        assert "CONFIGURED" in result.stdout
        # Original template content restored (not the sentinel)
        restored = config_file.read_text()
        assert "overwritten sentinel" not in restored

    def test_quiet_suppresses_status_on_first_run(self, tmp_path):
        result = _run(tmp_path, "--quiet")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_quiet_suppresses_status_on_second_run(self, tmp_path):
        _run(tmp_path, "--quiet")
        result = _run(tmp_path, "--quiet")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_creates_dot_claude_dir_if_absent(self, tmp_path):
        # tmp_path is a fresh empty dir with no .claude/ subdir
        assert not (tmp_path / ".claude").exists()
        _run(tmp_path)
        assert (tmp_path / ".claude").is_dir()
