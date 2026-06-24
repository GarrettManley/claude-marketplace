# plugins/orchestration/tests/test_init.py
"""Behavioral subprocess tests for orchestration/scripts/init.sh (idempotency)."""
import json
import os
import subprocess
from pathlib import Path

import pytest

# On Windows the system `bash` resolves to WSL; we must use Git Bash explicitly.
_GIT_BASH = r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else "bash"
_INIT_SH = str(Path(__file__).parent.parent / "scripts" / "init.sh")

_TIERS_DEST = Path(".claude") / "context" / "tiers.local.json"
_PROFILE_DEST = Path(".claude") / "context" / "hardware-profile.md"


def _run(tmp_home: Path, *args) -> subprocess.CompletedProcess:
    env = {**os.environ, "HOME": str(tmp_home)}
    return subprocess.run(
        [_GIT_BASH, _INIT_SH, *args],
        capture_output=True,
        text=True,
        env=env,
    )


class TestOrchestrationInit:
    def test_creates_both_files_on_first_run(self, tmp_path):
        result = _run(tmp_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert (tmp_path / _TIERS_DEST).is_file(), "tiers.local.json should be created"
        assert (tmp_path / _PROFILE_DEST).is_file(), "hardware-profile.md should be created"

    def test_tiers_json_is_valid_json(self, tmp_path):
        _run(tmp_path)
        content = (tmp_path / _TIERS_DEST).read_text()
        parsed = json.loads(content)
        assert isinstance(parsed, (dict, list)), "tiers.local.json should be valid JSON"

    def test_status_line_on_first_run(self, tmp_path):
        result = _run(tmp_path)
        assert result.returncode == 0
        assert "CONFIGURED" in result.stdout

    def test_idempotent_already_configured(self, tmp_path):
        # First run: create both files
        first = _run(tmp_path)
        assert first.returncode == 0
        tiers_content = (tmp_path / _TIERS_DEST).read_text()
        profile_content = (tmp_path / _PROFILE_DEST).read_text()

        # Second run: should be no-op
        second = _run(tmp_path)
        assert second.returncode == 0
        assert "already configured" in second.stdout

        # Files unchanged
        assert (tmp_path / _TIERS_DEST).read_text() == tiers_content
        assert (tmp_path / _PROFILE_DEST).read_text() == profile_content

    def test_exit_0_on_both_runs(self, tmp_path):
        assert _run(tmp_path).returncode == 0
        assert _run(tmp_path).returncode == 0

    def test_force_overwrites_both_files(self, tmp_path):
        _run(tmp_path)
        sentinel = "# sentinel content\n"
        (tmp_path / _TIERS_DEST).write_text(sentinel)
        (tmp_path / _PROFILE_DEST).write_text(sentinel)

        result = _run(tmp_path, "--force")
        assert result.returncode == 0
        assert (tmp_path / _TIERS_DEST).read_text() != sentinel
        assert (tmp_path / _PROFILE_DEST).read_text() != sentinel

    def test_quiet_suppresses_output_on_first_run(self, tmp_path):
        result = _run(tmp_path, "--quiet")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_quiet_suppresses_output_on_second_run(self, tmp_path):
        _run(tmp_path, "--quiet")
        result = _run(tmp_path, "--quiet")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_unknown_argument_exits_nonzero(self, tmp_path):
        result = _run(tmp_path, "--bogus-flag")
        assert result.returncode != 0
        assert "FAILED" in result.stderr or "FAILED" in result.stdout

    def test_creates_context_dir_if_absent(self, tmp_path):
        context_dir = tmp_path / ".claude" / "context"
        assert not context_dir.exists()
        _run(tmp_path)
        assert context_dir.is_dir()

    def test_mixed_state_reported_correctly(self, tmp_path):
        """First run creates both; delete one, re-run to exercise mixed state."""
        _run(tmp_path)
        (tmp_path / _TIERS_DEST).unlink()

        result = _run(tmp_path)
        assert result.returncode == 0
        assert "CONFIGURED" in result.stdout
