# plugins/stewardship/tests/test_init.py
"""
Behavioral subprocess tests for stewardship/scripts/init.sh.

The assignment says: "Skip stewardship (touches the real scheduler) — just
assert its --help/dry path is safe."

The stewardship init.sh has no --help or --dry-run flag, but it degrades
gracefully when crontab(1) is not on PATH: it prints a "skipped" status and
exits 0 without touching the scheduler.  We exercise that safe path by
running init.sh with a synthetic PATH that hides crontab.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

# On Windows the system `bash` resolves to WSL; use Git Bash explicitly. On POSIX
# resolve bash to an ABSOLUTE path so the crontab-free PATH built below (which omits
# the system bin dirs) can't also hide the interpreter itself.
_GIT_BASH = (
    r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt"
    else shutil.which("bash") or "/bin/bash"
)
_INIT_SH = str(Path(__file__).parent.parent / "scripts" / "init.sh")

# Tools init.sh invokes before its `command -v crontab` check (the template parse +
# dir resolution). The shim PATH below provides these but deliberately omits crontab.
_SKIP_PATH_TOOLS = (
    "bash", "sh", "dirname", "basename", "grep", "head", "tail",
    "sed", "awk", "cat", "mkdir", "env", "cut", "tr",
)


def _run_without_crontab(tmp_home: Path, *args) -> subprocess.CompletedProcess:
    """Run init.sh with a PATH from which `crontab` is absent on every platform.

    On Windows Git Bash crontab is already absent. On Linux/macOS crontab lives in
    /usr/bin alongside the coreutils init.sh needs, so listing system dirs would NOT
    hide it (and init.sh would then install a real cron entry — a test side effect).
    Instead we build a shim bin dir containing only the tools init.sh uses (symlinked)
    and omit crontab; `_GIT_BASH` is absolute so bash still launches under it.
    """
    env = {**os.environ, "HOME": str(tmp_home)}
    if os.name != "nt":
        shim = tmp_home / "_nocrontab_bin"
        shim.mkdir(parents=True, exist_ok=True)
        for tool in _SKIP_PATH_TOOLS:
            src = shutil.which(tool)
            link = shim / tool
            if src and not link.exists():
                link.symlink_to(src)
        env["PATH"] = str(shim)
    return subprocess.run(
        [_GIT_BASH, _INIT_SH, *args],
        capture_output=True,
        text=True,
        env=env,
    )


class TestStewardshipInitSafePath:
    """Tests for the safe (no-crontab) degradation path only."""

    def test_exits_0_when_crontab_absent(self, tmp_path):
        result = _run_without_crontab(tmp_path)
        assert result.returncode == 0, (
            f"init.sh should exit 0 when crontab is absent; got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_skipped_status_when_crontab_absent(self, tmp_path):
        result = _run_without_crontab(tmp_path)
        assert result.returncode == 0
        assert "skipped" in result.stdout.lower(), (
            f"Expected 'skipped' in output when crontab is absent.\nstdout: {result.stdout}"
        )

    def test_safe_path_idempotent_second_run(self, tmp_path):
        """Running twice without crontab is still safe and exits 0 both times."""
        first = _run_without_crontab(tmp_path)
        second = _run_without_crontab(tmp_path)
        assert first.returncode == 0
        assert second.returncode == 0

    def test_quiet_flag_suppresses_output_when_crontab_absent(self, tmp_path):
        result = _run_without_crontab(tmp_path, "--quiet")
        assert result.returncode == 0
        assert result.stdout.strip() == "", (
            f"--quiet should suppress all output; got: {result.stdout!r}"
        )

    def test_does_not_touch_crontab_when_absent(self, tmp_path):
        """No crontab modifications should occur in the safe degradation path."""
        result = _run_without_crontab(tmp_path)
        assert result.returncode == 0
        # No error output — clean exit in the skip path
        assert result.stderr.strip() == ""
