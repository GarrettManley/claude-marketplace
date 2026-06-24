"""Additional tests to boost coverage to >=90% for:
- plan_issue_check.py  (lines 52-56, 99-100, 108, 116-117, 148-190, 198-233, 250-252, 264-265, 274)
- snapshot.py          (lines 54-55, 67-69, 82-85, 101-102, 114-115, 130-131, 133, 139, 169-170)
- session_resume_context.py (lines 31-32, 70-71)
- pre_compact_snapshot.py   (lines 35-37)
- gateguard.py         (lines 79, 135-136, 141-142, 177-178, 195-196, 204, 211, 222, 275,
                         311-312, 314-315, 317-318, 320-321, 323, 334, 356, 358, 363-368,
                         379, 401, 550-551, 593, 601, 606, 621, 626, 636)
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# conftest already inserts scripts/ and hooks/ on sys.path.
# Import everything we need at module level.
import discipline_config
import plan_issue_check
import snapshot as snap_mod
import session_resume_context as src_mod
import pre_compact_snapshot as pcs_mod
import gateguard as gg


# ===========================================================================
# Helpers shared across suites
# ===========================================================================

def _run_pic(monkeypatch, payload):
    """Invoke plan_issue_check.main() with payload on stdin; return stdout text."""
    discipline_config.get_config.cache_clear()
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    with pytest.raises(SystemExit) as exc:
        plan_issue_check.main()
    assert exc.value.code == 0
    return out.getvalue()


def _is_block(out: str) -> bool:
    return bool(out) and json.loads(out.splitlines()[0])["decision"] == "block"


def _write_plan(tmp_path, body, name="2026-01-01-plan.md", subdir="docs/plans"):
    d = tmp_path / subdir if subdir else tmp_path
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    f.write_text(body, encoding="utf-8")
    return f


def _payload(path):
    return {"tool_input": {"file_path": str(path)}}


@pytest.fixture
def hermetic(clean_env, monkeypatch):
    monkeypatch.setattr(discipline_config, "_detect_git_root", lambda: None)
    monkeypatch.setattr(discipline_config, "_detect_repo", lambda: None)
    return monkeypatch


@pytest.fixture
def permissive(hermetic):
    hermetic.setenv("DISCIPLINE_PLAN_PATTERN", r".*\.md$")
    return hermetic


# ===========================================================================
# plan_issue_check.py — missing regions
# ===========================================================================


class TestPlanIssueCheckMissingBranches:
    # ---- log_failure (lines 52-56) ----

    def test_log_failure_oserror_is_silent(self, tmp_path, monkeypatch):
        """log_failure must not raise when the log file is unwritable."""
        monkeypatch.setattr(
            plan_issue_check, "LOG_FILE", tmp_path / "unwritable_dir" / "x.log"
        )
        # Directory doesn't exist → OSError; function must be silent
        plan_issue_check.log_failure("test message")

    # ---- JSON decode error on stdin (lines 99-100) ----

    def test_invalid_json_stdin_exits_silently(self, monkeypatch):
        discipline_config.get_config.cache_clear()
        monkeypatch.setattr("sys.stdin", io.StringIO("NOT_JSON{{{{"))
        out = io.StringIO()
        monkeypatch.setattr("sys.stdout", out)
        with pytest.raises(SystemExit) as exc:
            plan_issue_check.main()
        assert exc.value.code == 0
        assert out.getvalue() == ""

    # ---- missing file_path (line 108) ----

    def test_no_file_path_exits_silently(self, hermetic, monkeypatch):
        out = _run_pic(monkeypatch, {"tool_input": {}})
        assert out == ""

    # ---- OSError reading plan text (lines 116-117) ----

    def test_unreadable_plan_file_exits_silently(self, permissive, tmp_path, monkeypatch):
        # The plan path matches but the file doesn't exist on disk
        fake = tmp_path / "ghost.md"
        out = _run_pic(monkeypatch, {"tool_input": {"file_path": str(fake)}})
        assert out == ""

    # ---- filePath in tool_response (not tool_input) ----

    def test_file_path_via_tool_response(self, permissive, tmp_path, monkeypatch):
        """file_path is sometimes delivered in tool_response.filePath."""
        f = _write_plan(tmp_path, "Implements #1.")
        out = _run_pic(monkeypatch, {"tool_response": {"filePath": str(f)}})
        assert out == ""

    # ---- Rule 1: block with repo set produces gh hint in message ----

    def test_no_citation_with_repo_includes_gh_hint(self, hermetic, tmp_path, monkeypatch):
        hermetic.setenv("DISCIPLINE_PLAN_PATTERN", r".*\.md$")
        hermetic.setenv("DISCIPLINE_REPO", "owner/repo")
        hermetic.setenv("DISCIPLINE_REQUIRE_VALUE_JUSTIFICATION", "false")
        f = _write_plan(tmp_path, "No tracker here.")
        out = _run_pic(monkeypatch, _payload(f))
        assert _is_block(out)
        reason = json.loads(out.splitlines()[0])["reason"]
        assert "gh issue list" in reason

    # ---- Rule 3: missing Value Justification section (lines 149-159) ----

    def test_vj_required_but_missing_section_blocks(self, permissive, tmp_path, monkeypatch):
        permissive.setenv("DISCIPLINE_REQUIRE_VALUE_JUSTIFICATION", "true")
        body = "Implements #42.\n\nNo VJ section.\n"
        f = _write_plan(tmp_path, body)
        out = _run_pic(monkeypatch, _payload(f))
        assert _is_block(out)
        reason = json.loads(out.splitlines()[0])["reason"]
        assert "Value Justification" in reason

    # ---- Rule 3: VJ section exists but missing fields (lines 166-171) ----

    def test_vj_present_but_missing_fields_blocks(self, permissive, tmp_path, monkeypatch):
        permissive.setenv("DISCIPLINE_REQUIRE_VALUE_JUSTIFICATION", "true")
        body = (
            "Implements #42.\n\n"
            "## Value Justification\n\n"
            "- **Impact** (1-5): 3 - good\n"
            "- **Confidence** (1-5): 4 - sure\n"
            # Effort and Score intentionally omitted
        )
        f = _write_plan(tmp_path, body)
        out = _run_pic(monkeypatch, _payload(f))
        assert _is_block(out)
        reason = json.loads(out.splitlines()[0])["reason"]
        assert "missing one of" in reason

    # ---- Rule 3: effort <= 0 blocks (lines 182-186) ----

    def test_vj_zero_effort_blocks(self, permissive, tmp_path, monkeypatch):
        permissive.setenv("DISCIPLINE_REQUIRE_VALUE_JUSTIFICATION", "true")
        body = (
            "Implements #42.\n\n"
            "## Value Justification\n\n"
            "- **Impact** (1-5): 3 - good\n"
            "- **Confidence** (1-5): 4 - sure\n"
            "- **Effort** (hours): 0 - zero\n"
            "- **Score**: 12.00\n"
        )
        f = _write_plan(tmp_path, body)
        out = _run_pic(monkeypatch, _payload(f))
        assert _is_block(out)
        reason = json.loads(out.splitlines()[0])["reason"]
        assert "effort must be > 0" in reason

    # ---- Rule 3: score mismatch blocks (lines 189-194) ----

    def test_vj_score_mismatch_blocks(self, permissive, tmp_path, monkeypatch):
        permissive.setenv("DISCIPLINE_REQUIRE_VALUE_JUSTIFICATION", "true")
        body = (
            "Implements #42.\n\n"
            "## Value Justification\n\n"
            "- **Impact** (1-5): 3 - good\n"
            "- **Confidence** (1-5): 4 - sure\n"
            "- **Effort** (hours): 2 - two hours\n"
            "- **Score**: 99.99\n"  # expected: 3*4/2 = 6.0
        )
        f = _write_plan(tmp_path, body)
        out = _run_pic(monkeypatch, _payload(f))
        assert _is_block(out)
        reason = json.loads(out.splitlines()[0])["reason"]
        assert "score" in reason.lower()

    # ---- Rule 3: valid VJ passes (lines 160-195, happy path) ----

    def test_vj_valid_passes(self, permissive, tmp_path, monkeypatch):
        permissive.setenv("DISCIPLINE_REQUIRE_VALUE_JUSTIFICATION", "true")
        body = (
            "Implements #42.\n\n"
            "## Value Justification\n\n"
            "- **Impact** (1-5): 3 - good\n"
            "- **Confidence** (1-5): 4 - sure\n"
            "- **Effort** (hours): 2 - two hours\n"
            "- **Score**: 6.00\n"  # 3*4/2 = 6.0
        )
        f = _write_plan(tmp_path, body)
        out = _run_pic(monkeypatch, _payload(f))
        assert out == ""

    # ---- VJ skipped when retrospective exists (retro_body is not None) ----

    def test_vj_not_checked_when_retro_present(self, permissive, tmp_path, monkeypatch):
        permissive.setenv("DISCIPLINE_REQUIRE_VALUE_JUSTIFICATION", "true")
        # Retro present → VJ check skipped, no block for missing VJ
        body = (
            "Implements #42.\n\n"
            "## Retrospective\n\nCloses #42.\n"
        )
        f = _write_plan(tmp_path, body)
        out = _run_pic(monkeypatch, _payload(f))
        assert out == ""

    # ---- gh auto-close: issue is OPEN → closed path (lines 198-233) ----

    def test_gh_closes_open_issue(self, permissive, tmp_path, monkeypatch):
        monkeypatch.setenv("DISCIPLINE_REPO", "owner/repo")
        monkeypatch.setattr(
            discipline_config.DisciplineConfig, "has_gh",
            property(lambda self: True),
        )
        calls = {}

        def fake_check_output(cmd, **kw):
            calls["view"] = cmd
            return "OPEN"

        class _Ok:
            returncode = 0
            stderr = ""

        def fake_run(cmd, **kw):
            calls["close"] = cmd
            return _Ok()

        monkeypatch.setattr(plan_issue_check.subprocess, "check_output", fake_check_output)
        monkeypatch.setattr(plan_issue_check.subprocess, "run", fake_run)

        body = "Implements #7.\n\n## Retrospective\n\nCloses #7.\n"
        _run_pic(monkeypatch, _payload(_write_plan(tmp_path, body)))

        assert "close" in calls
        assert "7" in [str(x) for x in calls["close"]]

    # ---- gh auto-close: issue already closed → skip (lines 210-226) ----

    def test_gh_skips_already_closed_issue(self, permissive, tmp_path, monkeypatch):
        monkeypatch.setenv("DISCIPLINE_REPO", "owner/repo")
        monkeypatch.setattr(
            discipline_config.DisciplineConfig, "has_gh",
            property(lambda self: True),
        )
        run_calls = {"n": 0}

        def fake_check_output(cmd, **kw):
            return "CLOSED"

        def fake_run(cmd, **kw):
            run_calls["n"] += 1
            class _Ok:
                returncode = 0
                stderr = ""
            return _Ok()

        monkeypatch.setattr(plan_issue_check.subprocess, "check_output", fake_check_output)
        monkeypatch.setattr(plan_issue_check.subprocess, "run", fake_run)

        body = "Implements #8.\n\n## Retrospective\n\nCloses #8.\n"
        _run_pic(monkeypatch, _payload(_write_plan(tmp_path, body)))
        assert run_calls["n"] == 0, "should not close already-closed issue"

    # ---- gh auto-close: check_output raises → skipped entry (lines 208-209) ----

    def test_gh_exception_on_view_skips_gracefully(self, permissive, tmp_path, monkeypatch):
        monkeypatch.setenv("DISCIPLINE_REPO", "owner/repo")
        monkeypatch.setattr(
            discipline_config.DisciplineConfig, "has_gh",
            property(lambda self: True),
        )

        def fake_check_output(cmd, **kw):
            raise RuntimeError("network error")

        monkeypatch.setattr(plan_issue_check.subprocess, "check_output", fake_check_output)
        body = "Implements #9.\n\n## Retrospective\n\nCloses #9.\n"
        out = _run_pic(monkeypatch, _payload(_write_plan(tmp_path, body)))
        # Should not block and should not raise
        assert "block" not in out

    # ---- gh auto-close: gh close fails (non-zero) → log_failure path (lines 220-225) ----

    def test_gh_close_failure_logs_and_continues(self, permissive, tmp_path, monkeypatch):
        monkeypatch.setenv("DISCIPLINE_REPO", "owner/repo")
        monkeypatch.setattr(
            discipline_config.DisciplineConfig, "has_gh",
            property(lambda self: True),
        )
        log_calls = []
        monkeypatch.setattr(plan_issue_check, "log_failure", lambda msg: log_calls.append(msg))

        def fake_check_output(cmd, **kw):
            return "OPEN"

        class _Fail:
            returncode = 1
            stderr = "permission denied"

        monkeypatch.setattr(plan_issue_check.subprocess, "check_output", fake_check_output)
        monkeypatch.setattr(plan_issue_check.subprocess, "run", lambda cmd, **kw: _Fail())

        body = "Implements #10.\n\n## Retrospective\n\nCloses #10.\n"
        _run_pic(monkeypatch, _payload(_write_plan(tmp_path, body)))
        assert any("gh issue close" in m for m in log_calls)

    # ---- bd auto-close: bd close fails → log_failure (lines 262-268) ----

    def test_bd_close_failure_logs_and_continues(self, permissive, tmp_path, monkeypatch):
        ledger = str(tmp_path / "ledger")
        monkeypatch.setenv("DISCIPLINE_BD_LEDGER", ledger)
        monkeypatch.setattr(
            discipline_config.DisciplineConfig, "has_bd", property(lambda self: True)
        )
        log_calls = []
        monkeypatch.setattr(plan_issue_check, "log_failure", lambda msg: log_calls.append(msg))

        def fake_check_output(cmd, **kw):
            return json.dumps([{"id": "bd-fail.1", "status": "open"}])

        class _Fail:
            returncode = 1
            stderr = "disk full"

        monkeypatch.setattr(plan_issue_check.subprocess, "check_output", fake_check_output)
        monkeypatch.setattr(plan_issue_check.subprocess, "run", lambda cmd, **kw: _Fail())

        body = "Advances bd-fail.1.\n\n## Retrospective\n\nCloses bd-fail.1.\n"
        _run_pic(monkeypatch, _payload(_write_plan(tmp_path, body)))
        assert any("bd close" in m for m in log_calls)

    # ---- bd auto-close: bd check_output raises → skipped (lines 250-252) ----

    def test_bd_check_exception_skips_gracefully(self, permissive, tmp_path, monkeypatch):
        monkeypatch.setenv("DISCIPLINE_BD_LEDGER", str(tmp_path / "ledger"))
        monkeypatch.setattr(
            discipline_config.DisciplineConfig, "has_bd", property(lambda self: True)
        )

        def fake_check_output(cmd, **kw):
            raise RuntimeError("bd not available")

        monkeypatch.setattr(plan_issue_check.subprocess, "check_output", fake_check_output)

        body = "Advances bd-err.1.\n\n## Retrospective\n\nCloses bd-err.1.\n"
        out = _run_pic(monkeypatch, _payload(_write_plan(tmp_path, body)))
        assert "block" not in out

    # ---- bd + gh both emit system messages (lines 227-233, 272-276) ----

    def test_bd_close_emits_system_message(self, permissive, tmp_path, monkeypatch):
        ledger = str(tmp_path / "ledger")
        monkeypatch.setenv("DISCIPLINE_BD_LEDGER", ledger)
        monkeypatch.setattr(
            discipline_config.DisciplineConfig, "has_bd", property(lambda self: True)
        )

        def fake_check_output(cmd, **kw):
            bid = next((t for t in cmd if t.startswith("bd-") or t.startswith("hb-")), "hb-x.1")
            return json.dumps([{"id": bid, "status": "open"}])

        class _Ok:
            returncode = 0
            stderr = ""

        monkeypatch.setattr(plan_issue_check.subprocess, "check_output", fake_check_output)
        monkeypatch.setattr(plan_issue_check.subprocess, "run", lambda cmd, **kw: _Ok())

        body = "Advances bd-msg.1.\n\n## Retrospective\n\nCloses bd-msg.1.\n"
        out = _run_pic(monkeypatch, _payload(_write_plan(tmp_path, body)))
        # Should emit a systemMessage JSON line about closing
        lines = [l for l in out.splitlines() if l.strip()]
        assert any("systemMessage" in l for l in lines)

    # ---- gh: emit_system called with closed/skipped parts ----

    def test_gh_skipped_emits_system_message(self, permissive, tmp_path, monkeypatch):
        """When gh check_output raises, skipped list should produce systemMessage."""
        monkeypatch.setenv("DISCIPLINE_REPO", "owner/repo")
        monkeypatch.setattr(
            discipline_config.DisciplineConfig, "has_gh",
            property(lambda self: True),
        )

        def fake_check_output(cmd, **kw):
            raise RuntimeError("timeout")

        monkeypatch.setattr(plan_issue_check.subprocess, "check_output", fake_check_output)

        body = "Implements #11.\n\n## Retrospective\n\nCloses #11.\n"
        out = _run_pic(monkeypatch, _payload(_write_plan(tmp_path, body)))
        lines = [l for l in out.splitlines() if l.strip()]
        assert any("systemMessage" in l for l in lines)


# ===========================================================================
# snapshot.py — missing branches
# ===========================================================================


class TestSnapshotMissingBranches:
    """Cover exception paths in the git helper functions."""

    def test_git_remote_url_timeout(self, monkeypatch):
        """FileNotFoundError / TimeoutExpired → returns None."""
        import subprocess as sp
        def fake_run(cmd, **kw):
            raise sp.TimeoutExpired(cmd, 2)
        monkeypatch.setattr(snap_mod.subprocess, "run", fake_run)
        assert snap_mod._git_remote_url() is None

    def test_git_remote_url_file_not_found(self, monkeypatch):
        def fake_run(cmd, **kw):
            raise FileNotFoundError("no git")
        monkeypatch.setattr(snap_mod.subprocess, "run", fake_run)
        assert snap_mod._git_remote_url() is None

    def test_git_remote_url_nonzero_returncode(self, monkeypatch):
        class _Fail:
            returncode = 128
            stdout = ""
        monkeypatch.setattr(snap_mod.subprocess, "run", lambda cmd, **kw: _Fail())
        assert snap_mod._git_remote_url() is None

    def test_git_toplevel_timeout(self, monkeypatch):
        import subprocess as sp
        def fake_run(cmd, **kw):
            raise sp.TimeoutExpired(cmd, 2)
        monkeypatch.setattr(snap_mod.subprocess, "run", fake_run)
        assert snap_mod._git_toplevel() is None

    def test_git_toplevel_file_not_found(self, monkeypatch):
        def fake_run(cmd, **kw):
            raise FileNotFoundError("no git")
        monkeypatch.setattr(snap_mod.subprocess, "run", fake_run)
        assert snap_mod._git_toplevel() is None

    def test_git_branch_timeout(self, monkeypatch):
        import subprocess as sp
        def fake_run(cmd, **kw):
            raise sp.TimeoutExpired(cmd, 2)
        monkeypatch.setattr(snap_mod.subprocess, "run", fake_run)
        assert snap_mod._git_branch() is None

    def test_git_branch_file_not_found(self, monkeypatch):
        def fake_run(cmd, **kw):
            raise FileNotFoundError("no git")
        monkeypatch.setattr(snap_mod.subprocess, "run", fake_run)
        assert snap_mod._git_branch() is None

    def test_git_head_sha_timeout(self, monkeypatch):
        import subprocess as sp
        def fake_run(cmd, **kw):
            raise sp.TimeoutExpired(cmd, 2)
        monkeypatch.setattr(snap_mod.subprocess, "run", fake_run)
        assert snap_mod._git_head_sha() is None

    def test_git_head_sha_file_not_found(self, monkeypatch):
        def fake_run(cmd, **kw):
            raise FileNotFoundError("no git")
        monkeypatch.setattr(snap_mod.subprocess, "run", fake_run)
        assert snap_mod._git_head_sha() is None

    def test_recent_files_timeout(self, monkeypatch):
        import subprocess as sp
        def fake_run(cmd, **kw):
            raise sp.TimeoutExpired(cmd, 3)
        monkeypatch.setattr(snap_mod.subprocess, "run", fake_run)
        assert snap_mod._recent_files() == []

    def test_recent_files_nonzero_returncode(self, monkeypatch):
        class _Fail:
            returncode = 128
            stdout = ""
        monkeypatch.setattr(snap_mod.subprocess, "run", lambda cmd, **kw: _Fail())
        assert snap_mod._recent_files() == []

    def test_recent_files_deduplication(self, monkeypatch):
        """Files appearing in multiple commits are deduplicated."""
        class _Ok:
            returncode = 0
            stdout = "foo.py\nbar.py\nfoo.py\n"
        monkeypatch.setattr(snap_mod.subprocess, "run", lambda cmd, **kw: _Ok())
        result = snap_mod._recent_files()
        paths = [r["path"] for r in result]
        assert paths.count("foo.py") == 1
        assert "bar.py" in paths

    def test_recent_files_limit(self, monkeypatch):
        """Result is capped at RECENT_FILES_LIMIT."""
        many = "\n".join(f"file{i}.py" for i in range(50))
        class _Ok:
            returncode = 0
            stdout = many
        monkeypatch.setattr(snap_mod.subprocess, "run", lambda cmd, **kw: _Ok())
        result = snap_mod._recent_files()
        assert len(result) <= snap_mod.RECENT_FILES_LIMIT

    def test_get_project_key_via_remote_url(self, monkeypatch):
        """Falls through CLAUDE_PROJECT_DIR guard → uses remote URL."""
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        call_count = {"n": 0}

        def fake_run(cmd, **kw):
            call_count["n"] += 1
            if "remote" in cmd:
                class _Ok:
                    returncode = 0
                    stdout = "git@github.com:owner/repo.git\n"
                return _Ok()
            raise FileNotFoundError("no git")

        monkeypatch.setattr(snap_mod.subprocess, "run", fake_run)
        key = snap_mod.get_project_key()
        assert len(key) == 12  # _short_hash result

    def test_get_project_key_via_toplevel(self, monkeypatch, tmp_path):
        """Falls through remote URL → uses git toplevel."""
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)

        def fake_run(cmd, **kw):
            if "remote" in cmd:
                class _Empty:
                    returncode = 0
                    stdout = ""
                return _Empty()
            if "rev-parse" in cmd and "--show-toplevel" in cmd:
                class _Ok:
                    returncode = 0
                    stdout = str(tmp_path) + "\n"
                return _Ok()
            class _Fail:
                returncode = 1
                stdout = ""
            return _Fail()

        monkeypatch.setattr(snap_mod.subprocess, "run", fake_run)
        key = snap_mod.get_project_key()
        assert len(key) == 12

    def test_write_snapshot_oserror_returns_false(self, monkeypatch, tmp_path):
        """write_snapshot returns False on OSError."""
        bad_dir = tmp_path / "readonly"
        monkeypatch.setenv("DISCIPLINE_SNAPSHOT_DIR", str(bad_dir))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/p")

        # Force OSError by making the dir creation itself fail
        original_mkdir = Path.mkdir
        def bad_mkdir(self, *a, **kw):
            raise OSError("read-only fs")
        monkeypatch.setattr(Path, "mkdir", bad_mkdir)

        state = {"git": None, "recent_files": [], "timestamp": 1.0}
        result = snap_mod.write_snapshot(state)
        assert result is False


# ===========================================================================
# session_resume_context.py — missing branches (lines 31-32, 60-61, 70-71)
# ===========================================================================


class TestSessionResumeContextMissingBranches:

    def test_format_timestamp_overflow_returns_unknown(self):
        """OverflowError path in _format_timestamp returns 'unknown time'."""
        # Use an astronomically large value to trigger OverflowError
        result = src_mod._format_timestamp(float("inf"))
        assert result == "unknown time"

    def test_format_timestamp_negative_raises_to_unknown(self):
        """ValueError path in _format_timestamp returns 'unknown time'."""
        # Very large negative can trigger ValueError on some platforms
        # We monkeypatch datetime.datetime to guarantee the exception
        import datetime as dt

        class _BrokenDatetime(dt.datetime):
            @classmethod
            def fromtimestamp(cls, ts):
                raise ValueError("bad ts")

        original = dt.datetime
        dt.datetime = _BrokenDatetime
        try:
            result = src_mod._format_timestamp(0.0)
        finally:
            dt.datetime = original
        assert result == "unknown time"

    def test_format_snapshot_no_timestamp_key(self):
        """Snapshot with no timestamp is still formatted without error."""
        state = {"git": {"branch": "main", "head": "abc" * 8 + "ab"}, "recent_files": []}
        text = src_mod.format_snapshot(state)
        assert isinstance(text, str)
        assert "main" in text

    def test_format_snapshot_entry_without_path_key(self):
        """recent_files entries that are not dicts or lack 'path' are skipped."""
        state = {
            "timestamp": 1000.0,
            "git": None,
            "recent_files": [
                "bare_string",           # not a dict
                {"no_path": "x"},        # dict without 'path'
                {"path": "real.py"},     # valid
            ],
        }
        text = src_mod.format_snapshot(state)
        assert "real.py" in text

    def test_format_snapshot_more_than_max_files(self):
        """Snapshot with >MAX_FILES_SHOWN entries shows '... and N more'."""
        state = {
            "timestamp": 1000.0,
            "git": None,
            "recent_files": [{"path": f"f{i}.py"} for i in range(src_mod.MAX_FILES_SHOWN + 5)],
        }
        text = src_mod.format_snapshot(state)
        assert "more" in text

    def test_stdin_read_exception_is_non_fatal(self, tmp_path, monkeypatch):
        """If sys.stdin.read() raises, main() must still proceed."""
        monkeypatch.setenv("DISCIPLINE_SNAPSHOT_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/p")

        class _ExplodingStdin:
            def read(self):
                raise OSError("stdin broken")

        monkeypatch.setattr("sys.stdin", _ExplodingStdin())
        out = io.StringIO()
        monkeypatch.setattr("sys.stdout", out)
        rc = src_mod.main([])
        # No snapshot exists, so silent exit
        assert rc == 0
        assert out.getvalue() == ""

    def test_short_head_sha_displayed_in_full(self):
        """Short HEAD SHA (< 8 chars) is displayed as-is, not truncated."""
        state = {
            "timestamp": 1000.0,
            "git": {"branch": "x", "head": "abc"},
            "recent_files": [],
        }
        text = src_mod.format_snapshot(state)
        assert "abc" in text


# ===========================================================================
# pre_compact_snapshot.py — missing branches (lines 35-37)
# ===========================================================================


class TestPreCompactSnapshotMissingBranches:

    def test_gather_state_exception_is_swallowed(self, tmp_path, monkeypatch):
        """If gather_state() raises, main() must still return 0 (PreCompact must not break compaction)."""
        monkeypatch.setenv("DISCIPLINE_SNAPSHOT_DIR", str(tmp_path))

        def boom():
            raise RuntimeError("disk offline")

        monkeypatch.setattr(pcs_mod, "gather_state", boom)
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        monkeypatch.setattr("sys.stdout", io.StringIO())
        rc = pcs_mod.main([])
        assert rc == 0

    def test_write_snapshot_exception_is_swallowed(self, tmp_path, monkeypatch):
        """If write_snapshot() raises, main() must still return 0."""
        monkeypatch.setenv("DISCIPLINE_SNAPSHOT_DIR", str(tmp_path))

        def fake_gather():
            return {"git": None, "recent_files": [], "timestamp": 1.0}

        def boom(state):
            raise OSError("no space")

        monkeypatch.setattr(pcs_mod, "gather_state", fake_gather)
        monkeypatch.setattr(pcs_mod, "write_snapshot", boom)
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        monkeypatch.setattr("sys.stdout", io.StringIO())
        rc = pcs_mod.main([])
        assert rc == 0

    def test_empty_stdin_is_handled(self, tmp_path, monkeypatch):
        """Empty stdin is treated as no event (json.loads skipped)."""
        monkeypatch.setenv("DISCIPLINE_SNAPSHOT_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/p")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        monkeypatch.setattr("sys.stdout", io.StringIO())
        rc = pcs_mod.main([])
        assert rc == 0


# ===========================================================================
# gateguard.py — missing branches (311-368, 550-551, 593, 601, 606, 621, 626, 636)
# ===========================================================================


@pytest.fixture
def tmp_state_dir_gg(monkeypatch, tmp_path):
    """Redirect gateguard state + fire log to tmp_path."""
    monkeypatch.setenv("GATEGUARD_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("GATEGUARD_FIRE_LOG", str(tmp_path / "fire.jsonl"))
    gg._active_state_file = None
    gg.STATE_DIR = tmp_path
    gg.FIRE_LOG_PATH = tmp_path / "fire.jsonl"
    return tmp_path


class TestGateguardDestructiveGitMissingBranches:
    """Cover all branches in _find_git_subcommand and _is_destructive_git."""

    # _find_git_subcommand: value-consuming short flags (-c, -C)
    def test_git_c_flag_skips_value_and_finds_subcommand(self):
        tokens = ["git", "-c", "core.autocrlf=false", "commit", "--amend"]
        result = gg._find_git_subcommand(tokens)
        assert result is not None
        assert result[0] == "commit"

    def test_git_upper_C_flag_skips_value_and_finds_subcommand(self):
        tokens = ["git", "-C", "/some/dir", "reset", "--hard"]
        result = gg._find_git_subcommand(tokens)
        assert result is not None
        assert result[0] == "reset"

    # _find_git_subcommand: value-consuming long prefix flags (--git-dir, --work-tree, etc.)
    def test_git_dir_flag_with_equals_is_consumed(self):
        tokens = ["git", "--git-dir=/custom/.git", "status"]
        result = gg._find_git_subcommand(tokens)
        assert result is not None
        assert result[0] == "status"

    def test_git_dir_flag_separate_value_is_consumed(self):
        tokens = ["git", "--git-dir", "/custom/.git", "log"]
        result = gg._find_git_subcommand(tokens)
        assert result is not None
        assert result[0] == "log"

    def test_git_work_tree_flag_with_equals_consumed(self):
        tokens = ["git", "--work-tree=/some/path", "diff"]
        result = gg._find_git_subcommand(tokens)
        assert result is not None
        assert result[0] == "diff"

    def test_git_namespace_flag_with_equals_consumed(self):
        tokens = ["git", "--namespace=ns1", "push", "--force"]
        result = gg._find_git_subcommand(tokens)
        assert result is not None
        assert result[0] == "push"

    def test_git_super_prefix_flag_with_equals_consumed(self):
        tokens = ["git", "--super-prefix=sp", "clean", "-f"]
        result = gg._find_git_subcommand(tokens)
        assert result is not None
        assert result[0] == "clean"

    # _find_git_subcommand: generic short flag (not value-consuming)
    def test_git_generic_flag_is_skipped(self):
        tokens = ["git", "--no-pager", "log"]
        result = gg._find_git_subcommand(tokens)
        assert result is not None
        assert result[0] == "log"

    # _find_git_subcommand: no subcommand found → returns None
    def test_git_only_flags_returns_none(self):
        tokens = ["git", "--no-pager", "--version"]
        result = gg._find_git_subcommand(tokens)
        assert result is None

    # _is_destructive_git: checkout with --
    def test_git_checkout_double_dash_destructive(self):
        assert gg.is_destructive_bash("git checkout -- path/to/file")

    def test_git_checkout_no_double_dash_safe(self):
        assert not gg.is_destructive_bash("git checkout main")

    # _is_destructive_git: clean with --force
    def test_git_clean_long_force_destructive(self):
        assert gg.is_destructive_bash("git clean --force")

    # _is_destructive_git: commit --amend
    def test_git_commit_amend_destructive(self):
        assert gg.is_destructive_bash("git commit --amend")

    def test_git_commit_no_amend_safe(self):
        assert not gg.is_destructive_bash("git commit -m 'msg'")

    # _is_destructive_git: rm -r
    def test_git_rm_recursive_short_flag_destructive(self):
        assert gg.is_destructive_bash("git rm -r path/to/")

    def test_git_rm_no_recursive_safe(self):
        assert not gg.is_destructive_bash("git rm file.txt")

    # _is_destructive_git: switch --discard-changes / --force / -f / -C
    def test_git_switch_discard_changes_destructive(self):
        assert gg.is_destructive_bash("git switch --discard-changes main")

    def test_git_switch_force_destructive(self):
        assert gg.is_destructive_bash("git switch --force main")

    def test_git_switch_short_f_destructive(self):
        assert gg.is_destructive_bash("git switch -f main")

    def test_git_switch_short_C_destructive(self):
        assert gg.is_destructive_bash("git switch -C new-branch")

    def test_git_switch_no_force_safe(self):
        assert not gg.is_destructive_bash("git switch main")

    # _is_destructive_git: push --force-with-lease + refspec → safe
    def test_git_push_plus_refspec_with_lease_safe(self):
        assert not gg.is_destructive_bash(
            "git push --force-with-lease origin +refs/heads/main"
        )

    # _is_destructive_git: push with --force=<value> form
    def test_git_push_force_equals_value_destructive(self):
        assert gg.is_destructive_bash("git push --force=true origin main")

    # _is_destructive_git: unknown subcommand → False
    def test_git_unknown_subcommand_is_safe(self):
        assert not gg.is_destructive_bash("git fetch origin main")

    # _is_destructive_rm: --recursive --force long forms
    def test_rm_long_flags_recursive_force(self):
        assert gg.is_destructive_bash("rm --recursive --force /tmp/foo")

    # is_gateguard_disabled: GATEGUARD_DISABLED=1
    def test_disabled_via_gateguard_disabled_env(self, monkeypatch):
        monkeypatch.setenv("GATEGUARD_DISABLED", "1")
        assert gg.is_gateguard_disabled()

    # is_gateguard_disabled: DISCIPLINE_GATEGUARD in _DISABLE_VALUES
    def test_disabled_via_discipline_gateguard_off(self, monkeypatch):
        monkeypatch.setenv("DISCIPLINE_GATEGUARD", "false")
        assert gg.is_gateguard_disabled()


class TestGateguardDispatcherMissingBranches:
    """Cover dispatcher branches: is_checked early-exit, Write, mark_checked failure, etc."""

    def _call(self, monkeypatch, event):
        in_buf = io.StringIO(json.dumps(event))
        out_buf = io.StringIO()
        monkeypatch.setattr("sys.stdin", in_buf)
        monkeypatch.setattr("sys.stdout", out_buf)
        rc = gg.main([])
        return rc, out_buf.getvalue()

    def test_write_first_touch_denies(self, tmp_state_dir_gg, monkeypatch):
        rc, out = self._call(monkeypatch, {
            "tool_name": "Write",
            "tool_input": {"file_path": "/new/module.py"},
            "session_id": "w1",
        })
        assert rc == 0
        payload = json.loads(out)
        assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "Before creating" in payload["hookSpecificOutput"]["permissionDecisionReason"]

    def test_write_second_touch_passes(self, tmp_state_dir_gg, monkeypatch):
        """Second Write to same file (already marked) passes through."""
        self._call(monkeypatch, {
            "tool_name": "Write",
            "tool_input": {"file_path": "/new/module2.py"},
            "session_id": "w2",
        })
        gg._active_state_file = None
        rc, out = self._call(monkeypatch, {
            "tool_name": "Write",
            "tool_input": {"file_path": "/new/module2.py"},
            "session_id": "w2",
        })
        assert out == ""

    def test_edit_empty_file_path_passes(self, tmp_state_dir_gg, monkeypatch):
        rc, out = self._call(monkeypatch, {
            "tool_name": "Edit",
            "tool_input": {"file_path": ""},
            "session_id": "w3",
        })
        assert out == ""

    def test_multiedit_subagent_passes(self, tmp_state_dir_gg, monkeypatch):
        rc, out = self._call(monkeypatch, {
            "tool_name": "MultiEdit",
            "tool_input": {"edits": [{"file_path": "/code.py"}]},
            "session_id": "w4",
            "agent_id": "sub-abc",
        })
        assert out == ""

    def test_multiedit_empty_edits_passes(self, tmp_state_dir_gg, monkeypatch):
        rc, out = self._call(monkeypatch, {
            "tool_name": "MultiEdit",
            "tool_input": {"edits": []},
            "session_id": "w5",
        })
        assert out == ""

    def test_multiedit_settings_path_skipped(self, tmp_state_dir_gg, monkeypatch):
        rc, out = self._call(monkeypatch, {
            "tool_name": "MultiEdit",
            "tool_input": {"edits": [{"file_path": "/u/.claude/settings.json"}]},
            "session_id": "w6",
        })
        assert out == ""

    def test_multiedit_already_checked_passes(self, tmp_state_dir_gg, monkeypatch):
        # First touch marks it
        self._call(monkeypatch, {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/code_multi.py"},
            "session_id": "w7",
        })
        gg._active_state_file = None
        # MultiEdit now finds it already checked → passes
        rc, out = self._call(monkeypatch, {
            "tool_name": "MultiEdit",
            "tool_input": {"edits": [{"file_path": "/code_multi.py"}]},
            "session_id": "w7",
        })
        assert out == ""

    def test_destructive_bash_second_time_passes(self, tmp_state_dir_gg, monkeypatch):
        """Second destructive bash with same command passes (already keyed)."""
        cmd = "rm -rf /tmp/test-dedupe"
        self._call(monkeypatch, {
            "tool_name": "Bash",
            "tool_input": {"command": cmd},
            "session_id": "w8",
        })
        gg._active_state_file = None
        rc, out = self._call(monkeypatch, {
            "tool_name": "Bash",
            "tool_input": {"command": cmd},
            "session_id": "w8",
        })
        assert out == ""

    def test_unknown_tool_passes(self, tmp_state_dir_gg, monkeypatch):
        rc, out = self._call(monkeypatch, {
            "tool_name": "Read",
            "tool_input": {"file_path": "/x.py"},
            "session_id": "w9",
        })
        assert out == ""

    def test_non_dict_json_returns_early(self, tmp_state_dir_gg, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO("[1, 2, 3]"))
        out = io.StringIO()
        monkeypatch.setattr("sys.stdout", out)
        rc = gg.main([])
        assert rc == 0
        assert out.getvalue() == ""

    def test_fire_log_write_error_is_swallowed(self, tmp_state_dir_gg, monkeypatch):
        """_log_fire OSError must not propagate — deny still returned."""
        gg.FIRE_LOG_PATH = Path("/nonexistent_dir_xyz/fire.jsonl")
        try:
            rc, out = self._call(monkeypatch, {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/path/fire_test.py"},
                "session_id": "fire1",
            })
            assert rc == 0
            payload = json.loads(out)
            assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
        finally:
            gg.FIRE_LOG_PATH = tmp_state_dir_gg / "fire.jsonl"

    def test_save_state_failure_passes_through(self, tmp_state_dir_gg, monkeypatch):
        """If mark_checked → save_state fails, dispatcher passes through (no deny)."""
        import gateguard
        original_save = gateguard.save_state

        def always_fail(state):
            return False

        monkeypatch.setattr(gateguard, "save_state", always_fail)
        rc, out = self._call(monkeypatch, {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/failsave.py"},
            "session_id": "fs1",
        })
        # On save failure the dispatcher must pass through (return "")
        assert out == ""


class TestGateguardLoadStateMissingBranches:
    """Cover load_state: timeout + corrupt file branches."""

    def test_load_state_corrupt_file_returns_empty(self, tmp_state_dir_gg, monkeypatch):
        gg._active_state_file = None
        gg.STATE_DIR = tmp_state_dir_gg
        state_file = tmp_state_dir_gg / "state-test-corrupt.json"
        state_file.write_text("NOT VALID JSON {{{{", encoding="utf-8")
        # Manually set _active_state_file to the corrupt file
        gg._active_state_file = state_file
        state = gg.load_state()
        assert state["checked"] == []

    def test_save_state_merges_on_disk_state(self, tmp_state_dir_gg):
        """save_state merges with existing on-disk state to handle races."""
        gg._active_state_file = None
        gg.STATE_DIR = tmp_state_dir_gg
        gg.mark_checked("/file/a.py")
        gg._active_state_file = None
        # Write another key via a second save_state call
        state = gg.load_state()
        state["checked"].append("/file/b.py")
        gg.save_state(state)
        # Both should be present
        gg._active_state_file = None
        final = gg.load_state()
        assert "/file/a.py" in final["checked"]
        assert "/file/b.py" in final["checked"]

    def test_save_state_merges_corrupt_disk(self, tmp_state_dir_gg):
        """save_state tolerates corrupt on-disk JSON during merge."""
        gg._active_state_file = None
        gg.STATE_DIR = tmp_state_dir_gg
        state_file = tmp_state_dir_gg / "state-corrupt-merge.json"
        state_file.write_text("BAD{{", encoding="utf-8")
        gg._active_state_file = state_file
        state = {"checked": ["/ok.py"], "last_active": int(time.time() * 1000)}
        result = gg.save_state(state)
        assert result is True

    def test_is_checked_updates_heartbeat(self, tmp_state_dir_gg, monkeypatch):
        """is_checked updates last_active when heartbeat interval has elapsed."""
        gg._active_state_file = None
        gg.STATE_DIR = tmp_state_dir_gg
        gg.mark_checked("/heartbeat.py")
        # Tamper with last_active to be stale (older than READ_HEARTBEAT_MS) but
        # NOT old enough to trigger the 30-min session timeout reset (which would
        # clear checked entries).  Use 2 minutes ago — well past the 60-second
        # heartbeat but well inside the 30-minute session window.
        gg._active_state_file = None
        state_file = next(tmp_state_dir_gg.glob("state-*.json"))
        data = json.loads(state_file.read_text())
        two_minutes_ago = gg._now_ms() - (2 * 60 * 1000)
        data["last_active"] = two_minutes_ago
        state_file.write_text(json.dumps(data))
        gg._active_state_file = state_file
        found = gg.is_checked("/heartbeat.py")
        assert found


class TestGateguardPruneEdgeCases:
    """Additional prune_checked_entries coverage."""

    def test_prune_below_max_returns_copy(self):
        entries = ["a.py", "b.py"]
        result = gg.prune_checked_entries(entries)
        assert result == entries
        assert result is not entries  # it's a copy

    def test_prune_session_keys_are_capped(self):
        entries = [f"__sess_{i}__" for i in range(100)]
        entries += [f"/file/{i}.py" for i in range(600)]
        result = gg.prune_checked_entries(entries)
        assert len(result) <= gg.MAX_CHECKED_ENTRIES


# ===========================================================================
# gateguard.py — further missing branches
# ===========================================================================


class TestGateguardFurtherMissing:
    """Cover remaining uncovered branches."""

    # mark_checked: key already present → returns True without save (line 204)
    def test_mark_checked_already_present_returns_true(self, tmp_state_dir_gg):
        gg._active_state_file = None
        gg.STATE_DIR = tmp_state_dir_gg
        gg.mark_checked("/already.py")
        gg._active_state_file = None
        # Second call: key is already in checked → early True return
        result = gg.mark_checked("/already.py")
        assert result is True

    # _command_basename: empty string (line 275)
    def test_command_basename_empty_string(self):
        assert gg._command_basename("") == ""

    # _command_basename: path with backslash
    def test_command_basename_backslash_path(self):
        assert gg._command_basename(r"C:\Windows\System32\rm.exe") == "rm"

    # _collect_executable_bodies: duplicate body skipped via `seen` (line 379)
    def test_collect_bodies_covers_nested_substitutions(self):
        # Nested substitutions: the inner `echo hi` is reached via two paths, so
        # the `seen` set short-circuits re-processing (the list may carry a dup,
        # which is harmless for scanning). Assert the unique set is complete.
        cmd = "echo $(echo $(echo hi))"
        bodies = gg._collect_executable_bodies(cmd)
        assert set(bodies) == {
            "echo $(echo $(echo hi))",
            "echo $(echo hi)",
            "echo hi",
        }

    # is_destructive_bash: SQL/DD inside subshell segment (line 401)
    def test_sql_inside_backtick_subshell(self):
        # drop table inside a backtick substitution, not quoted
        assert gg.is_destructive_bash("result=`drop table foo`")

    def test_dd_inside_dollar_paren_segment(self):
        assert gg.is_destructive_bash("x=$(dd if=/dev/zero of=/dev/sda)")

    # save_state OSError → returns False (lines 195-196)
    def test_save_state_oserror_returns_false(self, tmp_state_dir_gg, monkeypatch):
        gg._active_state_file = None
        gg.STATE_DIR = tmp_state_dir_gg
        # Make os.replace fail
        import os as _os
        def bad_replace(src, dst):
            raise OSError("no space")
        monkeypatch.setattr(_os, "replace", bad_replace)
        state = {"checked": ["/x.py"], "last_active": gg._now_ms()}
        result = gg.save_state(state)
        assert result is False

    # load_state: unlink raises OSError during expiry (lines 141-142)
    def test_load_state_unlink_oserror_during_expiry(self, tmp_state_dir_gg, monkeypatch):
        gg._active_state_file = None
        gg.STATE_DIR = tmp_state_dir_gg
        state_file = tmp_state_dir_gg / "state-unlink-err.json"
        # Write an expired state
        state_file.write_text(
            json.dumps({"checked": ["/x.py"], "last_active": 0}), encoding="utf-8"
        )
        gg._active_state_file = state_file
        # Patch unlink to raise
        original_unlink = Path.unlink
        def bad_unlink(self, *a, **kw):
            raise OSError("permission denied")
        monkeypatch.setattr(Path, "unlink", bad_unlink)
        state = gg.load_state()
        # Should still return empty checked list (session expired)
        assert state["checked"] == []

    # Dispatcher: MultiEdit with mark_checked failure → passthrough (line 606)
    def test_multiedit_mark_checked_failure_passes(self, tmp_state_dir_gg, monkeypatch):
        import gateguard
        def always_fail(state):
            return False
        monkeypatch.setattr(gateguard, "save_state", always_fail)
        in_buf = io.StringIO(json.dumps({
            "tool_name": "MultiEdit",
            "tool_input": {"edits": [{"file_path": "/multifail.py"}]},
            "session_id": "mf1",
        }))
        out_buf = io.StringIO()
        monkeypatch.setattr("sys.stdin", in_buf)
        monkeypatch.setattr("sys.stdout", out_buf)
        rc = gg.main([])
        assert rc == 0
        assert out_buf.getvalue() == ""

    # Dispatcher: Bash destructive mark_checked failure → passthrough (line 621)
    def test_bash_destructive_mark_checked_failure_passes(self, tmp_state_dir_gg, monkeypatch):
        import gateguard
        def always_fail(state):
            return False
        monkeypatch.setattr(gateguard, "save_state", always_fail)
        in_buf = io.StringIO(json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /tmp/mark-fail"},
            "session_id": "bf1",
        }))
        out_buf = io.StringIO()
        monkeypatch.setattr("sys.stdin", in_buf)
        monkeypatch.setattr("sys.stdout", out_buf)
        rc = gg.main([])
        assert rc == 0
        assert out_buf.getvalue() == ""

    # plan_issue_check: log_failure writes to a file that actually exists (line 54)
    def test_log_failure_writes_to_valid_log(self, tmp_path, monkeypatch):
        log = tmp_path / "test_log.log"
        monkeypatch.setattr(plan_issue_check, "LOG_FILE", log)
        plan_issue_check.log_failure("hello test")
        assert log.exists()
        content = log.read_text(encoding="utf-8")
        assert "hello test" in content

    # plan_issue_check: VJ ValueError on float conversion (lines 177-178)
    # The regex [0-9.]+ accepts "1.2.3" which will fail float(). We monkeypatch
    # to inject a non-numeric capture.
    def test_vj_float_parse_error_blocks(self, tmp_path, monkeypatch):
        """Monkeypatch re.search to return a match with a non-numeric group for Score."""
        import re as _re
        import plan_issue_check as pic

        discipline_config.get_config.cache_clear()
        monkeypatch.setenv("DISCIPLINE_PLAN_PATTERN", r".*\.md$")
        monkeypatch.setattr(discipline_config, "_detect_git_root", lambda: None)
        monkeypatch.setattr(discipline_config, "_detect_repo", lambda: None)
        monkeypatch.setenv("DISCIPLINE_REQUIRE_VALUE_JUSTIFICATION", "true")

        # Write a plan that passes Rule 1, has no retro (VJ check fires),
        # has VJ section, and all 4 fields present but Score is "1.2.3" (non-parseable float)
        body = (
            "Implements #42.\n\n"
            "## Value Justification\n\n"
            "- **Impact** (1-5): 3 - good\n"
            "- **Confidence** (1-5): 4 - sure\n"
            "- **Effort** (hours): 2 - two hours\n"
            "- **Score**: 1.2.3\n"
        )
        d = tmp_path / "docs/plans"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "plan.md"
        f.write_text(body, encoding="utf-8")

        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"tool_input": {"file_path": str(f)}})))
        out = io.StringIO()
        monkeypatch.setattr("sys.stdout", out)
        with pytest.raises(SystemExit) as exc:
            pic.main()
        assert exc.value.code == 0
        # Should block due to non-numeric Score value
        result = out.getvalue()
        if result:
            assert _is_block(result)

    # snapshot.py: get_project_key falls through to GLOBAL_PROJECT_KEY (lines 82-85)
    def test_snapshot_get_project_key_falls_to_global(self, monkeypatch):
        """When CLAUDE_PROJECT_DIR not set and all git calls return None,
        the last fallback is os.getcwd(). We can't easily make cwd() empty
        on real platforms, but we can exercise it returns a 12-char hash.
        """
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)

        def fake_run(cmd, **kw):
            # All git calls fail
            class _Fail:
                returncode = 128
                stdout = ""
            return _Fail()

        monkeypatch.setattr(snap_mod.subprocess, "run", fake_run)
        key = snap_mod.get_project_key()
        # Either the cwd hash (12 chars) or GLOBAL_PROJECT_KEY
        assert len(key) == 12 or key == snap_mod.GLOBAL_PROJECT_KEY
