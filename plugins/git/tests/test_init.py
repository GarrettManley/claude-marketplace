# plugins/git/tests/test_init.py
"""Behavioral subprocess tests for git/scripts/init.sh (idempotency)."""
import os
import subprocess
from pathlib import Path

import pytest

# On Windows the system `bash` resolves to WSL; we must use Git Bash explicitly.
_GIT_BASH = r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else "bash"
_INIT_SH = str(Path(__file__).parent.parent / "scripts" / "init.sh")

_TARGET = ".claude/commit-message-rules.yaml"


def _git_init_repo(path: Path) -> None:
    """Initialize a git repo with an initial empty commit."""
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "t@t.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "t@t.com",
    }
    subprocess.run(
        ["git", "-C", str(path), "commit", "--allow-empty", "-m", "init"],
        capture_output=True,
        env=git_env,
    )


def _run(cwd: Path, *args) -> subprocess.CompletedProcess:
    # Stop `git rev-parse` from ascending out of the temp dir into an ambient
    # parent repo (CI/dev home dirs are often themselves git repos), which would
    # break the "outside a git repo" case. The ceiling halts the upward walk.
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(Path(cwd).resolve().parent)}
    return subprocess.run(
        [_GIT_BASH, _INIT_SH, *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd),
    )


class TestGitInit:
    def test_creates_rules_file_inside_git_repo(self, tmp_path):
        _git_init_repo(tmp_path)
        result = _run(tmp_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        rules_file = tmp_path / _TARGET
        assert rules_file.is_file(), "commit-message-rules.yaml should be created"
        assert rules_file.stat().st_size > 0

    def test_status_line_on_first_run(self, tmp_path):
        _git_init_repo(tmp_path)
        result = _run(tmp_path)
        assert result.returncode == 0
        assert "CONFIGURED" in result.stdout
        assert "commit-message-rules.yaml" in result.stdout

    def test_idempotent_already_configured(self, tmp_path):
        _git_init_repo(tmp_path)
        first = _run(tmp_path)
        assert first.returncode == 0
        first_content = (tmp_path / _TARGET).read_text()

        second = _run(tmp_path)
        assert second.returncode == 0
        assert "already configured" in second.stdout

        # File unchanged
        assert (tmp_path / _TARGET).read_text() == first_content

    def test_exit_0_on_both_runs(self, tmp_path):
        _git_init_repo(tmp_path)
        assert _run(tmp_path).returncode == 0
        assert _run(tmp_path).returncode == 0

    def test_force_overwrites_existing_file(self, tmp_path):
        _git_init_repo(tmp_path)
        _run(tmp_path)

        sentinel = "# sentinel content\n"
        (tmp_path / _TARGET).write_text(sentinel)

        result = _run(tmp_path, "--force")
        assert result.returncode == 0
        assert "CONFIGURED" in result.stdout
        restored = (tmp_path / _TARGET).read_text()
        assert "sentinel content" not in restored

    def test_quiet_suppresses_status_on_first_run(self, tmp_path):
        _git_init_repo(tmp_path)
        result = _run(tmp_path, "--quiet")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_quiet_suppresses_status_on_second_run(self, tmp_path):
        _git_init_repo(tmp_path)
        _run(tmp_path, "--quiet")
        result = _run(tmp_path, "--quiet")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_skips_gracefully_outside_git_repo(self, tmp_path):
        """Outside a git repo: init.sh should exit 0 with a 'skipped' message."""
        result = _run(tmp_path)
        assert result.returncode == 0
        assert "skipped" in result.stdout

    def test_creates_dot_claude_dir_inside_git_repo(self, tmp_path):
        _git_init_repo(tmp_path)
        assert not (tmp_path / ".claude").exists()
        _run(tmp_path)
        assert (tmp_path / ".claude").is_dir()
