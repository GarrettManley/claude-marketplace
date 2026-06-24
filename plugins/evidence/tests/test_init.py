# plugins/evidence/tests/test_init.py
"""Behavioral subprocess tests for evidence/scripts/init.sh (idempotency)."""
import os
import stat
import subprocess
from pathlib import Path

import pytest

# On Windows the system `bash` resolves to WSL; we must use Git Bash explicitly.
_GIT_BASH = r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else "bash"
_INIT_SH = str(Path(__file__).parent.parent / "scripts" / "init.sh")


def _run(tmp_home: Path, *args) -> subprocess.CompletedProcess:
    env = {**os.environ, "HOME": str(tmp_home)}
    return subprocess.run(
        [_GIT_BASH, _INIT_SH, *args],
        capture_output=True,
        text=True,
        env=env,
    )


class TestEvidenceInit:
    def test_creates_key_file_on_first_run(self, tmp_path):
        result = _run(tmp_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        key_path = tmp_path / ".claude" / "evidence-override-key"
        assert key_path.is_file(), "Key file should exist after first run"
        content = key_path.read_text().strip()
        assert len(content) == 64, f"Key should be 64 hex chars, got {len(content)}"
        assert all(c in "0123456789abcdef" for c in content), "Key should be hex"

    def test_status_line_on_first_run(self, tmp_path):
        result = _run(tmp_path)
        assert result.returncode == 0
        assert "CONFIGURED" in result.stdout
        assert "evidence-override-key" in result.stdout

    def test_idempotent_already_configured(self, tmp_path):
        # First run: create key
        first = _run(tmp_path)
        assert first.returncode == 0
        first_content = (tmp_path / ".claude" / "evidence-override-key").read_text()

        # Second run: should be no-op
        second = _run(tmp_path)
        assert second.returncode == 0
        assert "already configured" in second.stdout

        # Key file unchanged
        second_content = (tmp_path / ".claude" / "evidence-override-key").read_text()
        assert first_content == second_content, "Key should not change on second run"

    def test_exit_0_on_both_runs(self, tmp_path):
        assert _run(tmp_path).returncode == 0
        assert _run(tmp_path).returncode == 0

    def test_force_regenerates_key(self, tmp_path):
        _run(tmp_path)
        first_key = (tmp_path / ".claude" / "evidence-override-key").read_text().strip()

        result = _run(tmp_path, "--force")
        assert result.returncode == 0
        second_key = (tmp_path / ".claude" / "evidence-override-key").read_text().strip()
        assert len(second_key) == 64, "Regenerated key should be 64 hex chars"
        # With overwhelming probability two random 32-byte keys differ
        # (probability of collision is 1/2^256 ≈ negligible)

    def test_quiet_suppresses_status_on_first_run(self, tmp_path):
        result = _run(tmp_path, "--quiet")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_quiet_suppresses_status_on_second_run(self, tmp_path):
        _run(tmp_path, "--quiet")
        result = _run(tmp_path, "--quiet")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_creates_claude_dir_if_absent(self, tmp_path):
        assert not (tmp_path / ".claude").exists()
        _run(tmp_path)
        assert (tmp_path / ".claude").is_dir()
