# plugins/stewardship/tests/test_drift_check_extended.py
"""Extended tests for drift_check.py — covers run_check, scan_context_dir,
render_markdown (failure/passed branches), and main() CLI."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from drift_check import (
    CheckResult,
    StaleResult,
    extract_verification_cmd,
    render_markdown,
    run_check,
    scan_context_dir,
    main,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _ctx(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def _front(cmd: str, last_verified: str | None = None) -> str:
    lines = ["---", f"verification_cmd: {cmd}"]
    if last_verified:
        lines.append(f"last_verified: {last_verified}")
    lines += ["---", "body"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# extract_verification_cmd — missing branches
# ---------------------------------------------------------------------------

class TestExtractVerificationCmd:
    def test_basic(self):
        text = "---\nverification_cmd: echo hi\n---\nbody"
        assert extract_verification_cmd(text) == "echo hi"

    def test_single_quoted(self):
        text = "---\nverification_cmd: 'echo hello'\n---\nbody"
        assert extract_verification_cmd(text) == "echo hello"

    def test_double_quoted(self):
        text = '---\nverification_cmd: "nvidia-smi"\n---\nbody'
        assert extract_verification_cmd(text) == "nvidia-smi"

    def test_no_frontmatter(self):
        assert extract_verification_cmd("# plain") is None

    def test_empty_value_returns_none(self):
        # A line like `verification_cmd:  ` (whitespace-only after strip) should return None.
        text = "---\nverification_cmd: \n---\nbody"
        assert extract_verification_cmd(text) is None

    def test_cmd_outside_frontmatter_ignored(self):
        text = "---\ntopic: x\n---\nverification_cmd: echo bad"
        assert extract_verification_cmd(text) is None

    def test_no_end_fence_uses_first_1000_chars(self):
        # No closing --- so the block is capped at 1000 chars; cmd in first block is found.
        text = "---\nverification_cmd: ls\ntopic: x\n" + "x" * 2000
        assert extract_verification_cmd(text) == "ls"


# ---------------------------------------------------------------------------
# run_check
# ---------------------------------------------------------------------------

class TestRunCheck:
    def test_passing_command(self, tmp_path):
        p = tmp_path / "ctx.md"
        p.write_text("")
        result = run_check(p, "exit 0", cwd=tmp_path, timeout=5)
        assert result.passed
        assert result.exit_code == 0

    def test_failing_command(self, tmp_path):
        p = tmp_path / "ctx.md"
        p.write_text("")
        result = run_check(p, "exit 1", cwd=tmp_path, timeout=5)
        assert not result.passed
        assert result.exit_code == 1

    def test_timeout_returns_failed(self, tmp_path):
        p = tmp_path / "ctx.md"
        p.write_text("")
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 1)):
            result = run_check(p, "sleep 999", cwd=tmp_path, timeout=1)
        assert not result.passed
        assert result.exit_code == -1
        assert "timed out" in result.stderr

    def test_oserror_returns_failed(self, tmp_path):
        p = tmp_path / "ctx.md"
        p.write_text("")
        with patch("subprocess.run", side_effect=OSError("no binary")):
            result = run_check(p, "nonexistent_binary_xyz", cwd=tmp_path, timeout=5)
        assert not result.passed
        assert result.exit_code == -1
        assert "command failed to launch" in result.stderr

    def test_stdout_truncated_at_500(self, tmp_path):
        p = tmp_path / "ctx.md"
        p.write_text("")
        long_output = "x" * 1000
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = long_output
        mock_proc.stderr = ""
        with patch("subprocess.run", return_value=mock_proc):
            result = run_check(p, "echo lots", cwd=tmp_path, timeout=5)
        assert len(result.stdout) <= 500


# ---------------------------------------------------------------------------
# scan_context_dir
# ---------------------------------------------------------------------------

class TestScanContextDir:
    def test_empty_dir_returns_empty(self, tmp_path):
        results = scan_context_dir(tmp_path)
        assert results == []

    def test_readme_skipped(self, tmp_path):
        _ctx(tmp_path, "README.md", _front("echo hi"))
        results = scan_context_dir(tmp_path)
        assert results == []

    def test_no_cmd_file_skipped(self, tmp_path):
        _ctx(tmp_path, "nocmd.md", "---\ntopic: x\n---\nbody")
        results = scan_context_dir(tmp_path)
        assert results == []

    def test_passing_cmd_recorded(self, tmp_path):
        _ctx(tmp_path, "good.md", _front("exit 0"))
        results = scan_context_dir(tmp_path)
        assert len(results) == 1
        assert results[0].passed

    def test_failing_cmd_recorded(self, tmp_path):
        _ctx(tmp_path, "bad.md", _front("exit 1"))
        results = scan_context_dir(tmp_path)
        assert len(results) == 1
        assert not results[0].passed

    def test_recurses_subdirs(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        _ctx(sub, "inner.md", _front("exit 0"))
        results = scan_context_dir(tmp_path)
        assert len(results) == 1

    def test_oserror_on_read_skipped(self, tmp_path):
        # Patch read_text to raise OSError on that file.
        p = _ctx(tmp_path, "unreadable.md", _front("exit 0"))
        real_read = Path.read_text

        def fake_read(self, *args, **kwargs):
            if self == p:
                raise OSError("permission denied")
            return real_read(self, *args, **kwargs)

        with patch.object(Path, "read_text", fake_read):
            results = scan_context_dir(tmp_path)
        assert results == []


# ---------------------------------------------------------------------------
# render_markdown — failure + passed branches
# ---------------------------------------------------------------------------

class TestRenderMarkdown:
    def test_failed_section_rendered(self):
        failed = CheckResult(
            file="/ctx/bad.md", cmd="false", passed=False,
            exit_code=1, stdout="", stderr="something went wrong",
        )
        out = render_markdown([failed])
        assert "### Failures" in out
        assert "bad.md" in out
        assert "false" in out
        assert "exit 1" in out

    def test_failed_section_with_stderr(self):
        failed = CheckResult(
            file="/ctx/bad.md", cmd="false", passed=False,
            exit_code=1, stdout="", stderr="err detail",
        )
        out = render_markdown([failed])
        assert "stderr" in out
        assert "err detail" in out

    def test_failed_section_no_stderr(self):
        # When stderr is empty, the stderr sub-bullet must NOT appear.
        failed = CheckResult(
            file="/ctx/bad.md", cmd="false", passed=False,
            exit_code=1, stdout="", stderr="",
        )
        out = render_markdown([failed])
        assert "### Failures" in out
        assert "stderr" not in out

    def test_passed_section_rendered(self):
        passed_r = CheckResult(
            file="/ctx/good.md", cmd="true", passed=True,
            exit_code=0, stdout="ok", stderr="",
        )
        out = render_markdown([passed_r])
        assert "### Passed" in out
        assert "good.md" in out

    def test_mixed_pass_fail(self):
        ok = CheckResult(file="/ctx/ok.md", cmd="true", passed=True, exit_code=0, stdout="", stderr="")
        bad = CheckResult(file="/ctx/bad.md", cmd="false", passed=False, exit_code=1, stdout="", stderr="")
        out = render_markdown([ok, bad])
        assert "### Passed" in out
        assert "### Failures" in out

    def test_stale_count_in_header(self):
        stale = [StaleResult(file="/ctx/old.md", last_verified="2020-01-01", age_days=300)]
        out = render_markdown([], stale)
        assert "1" in out  # stale count

    def test_no_results_no_stale_message(self):
        out = render_markdown([])
        assert "No verifiable context files" in out


# ---------------------------------------------------------------------------
# main() CLI
# ---------------------------------------------------------------------------

class TestMain:
    def test_dir_not_found_returns_2(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["drift_check.py", "--dir", str(tmp_path / "nonexistent")])
        rc = main()
        assert rc == 2

    def test_empty_dir_returns_0(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["drift_check.py", "--dir", str(tmp_path)])
        rc = main()
        assert rc == 0
        out = capsys.readouterr().out
        assert "No verifiable context files" in out

    def test_json_flag(self, tmp_path, monkeypatch, capsys):
        _ctx(tmp_path, "ctx.md", _front("exit 0"))
        monkeypatch.setattr(sys, "argv", ["drift_check.py", "--dir", str(tmp_path), "--json"])
        rc = main()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "checks" in data
        assert "stale" in data

    def test_markdown_output_default(self, tmp_path, monkeypatch, capsys):
        _ctx(tmp_path, "ctx.md", _front("exit 0"))
        monkeypatch.setattr(sys, "argv", ["drift_check.py", "--dir", str(tmp_path)])
        rc = main()
        out = capsys.readouterr().out
        assert "## Drift Check" in out

    def test_returns_1_on_failure(self, tmp_path, monkeypatch, capsys):
        _ctx(tmp_path, "bad.md", _front("exit 1"))
        monkeypatch.setattr(sys, "argv", ["drift_check.py", "--dir", str(tmp_path)])
        rc = main()
        assert rc == 1

    def test_returns_1_on_stale(self, tmp_path, monkeypatch, capsys):
        # A stale file (no cmd) should cause return 1.
        _ctx(tmp_path, "old.md", "---\nlast_verified: 2020-01-01\n---\nbody")
        monkeypatch.setattr(sys, "argv", ["drift_check.py", "--dir", str(tmp_path), "--max-age-days", "45"])
        rc = main()
        assert rc == 1

    def test_max_age_zero_disables_staleness(self, tmp_path, monkeypatch, capsys):
        _ctx(tmp_path, "old.md", "---\nlast_verified: 2020-01-01\n---\nbody")
        monkeypatch.setattr(sys, "argv", ["drift_check.py", "--dir", str(tmp_path), "--max-age-days", "0"])
        rc = main()
        assert rc == 0


# ---------------------------------------------------------------------------
# Additional coverage — scan_staleness OSError branch (line 104-105)
# and extract_last_verified ValueError branch (line 76-77)
# ---------------------------------------------------------------------------

class TestScanStalenessAdditional:
    def test_oserror_on_read_skipped(self, tmp_path):
        """OSError during read_text in scan_staleness should skip the file silently."""
        p = _ctx(tmp_path, "unreadable.md", "---\nlast_verified: 2026-01-01\n---\nbody")
        real_read = Path.read_text

        def fake_read(self, *args, **kwargs):
            if self == p:
                raise OSError("permission denied")
            return real_read(self, *args, **kwargs)

        with patch.object(Path, "read_text", fake_read):
            from drift_check import scan_staleness
            stale = scan_staleness(tmp_path, max_age_days=10, today=date(2026, 6, 1))
        assert stale == []


class TestExtractLastVerifiedValueError:
    def test_malformed_date_returns_none(self):
        """Regex matches but strptime raises ValueError — should return None."""
        from drift_check import extract_last_verified
        import drift_check as dc

        # "2026-13-99" satisfies the \d{4}-\d{2}-\d{2} regex but is not a real
        # date — strptime raises ValueError (month 13 / day 99), and the
        # except branch returns None. No monkeypatching needed (and patching
        # datetime.strptime is illegal on the immutable builtin in 3.14+).
        result = dc.extract_last_verified("---\nlast_verified: 2026-13-99\n---\nbody")
        assert result is None
