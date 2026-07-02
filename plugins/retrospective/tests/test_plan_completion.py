"""Tests for plan_completion_check: the four completion checks + the SessionStart nag.

The check functions are pure (text in, blocker-or-None out); the nag is exercised
both in-process (main() with a fake stdin) and via subprocess (the blessed
`uv run` launcher) to prove the hook wiring works end-to-end.
"""
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# conftest puts the plugin's hooks/ on sys.path.
import plan_completion_check as pcc

_HOOK_PATH = Path(__file__).parent.parent / "hooks" / "plan_completion_check.py"


# --------------------------------------------------------------------------- #
# Plan fixtures
# --------------------------------------------------------------------------- #
COMPLETE_PLAN = """\
# Plan: Ship the widget

Closes #42.

## Tasks

- [x] Build the widget
- [x] Wire it up

## Verification

- `pytest` passes (verified: 12 passed).
- Manual smoke test of the widget rendered correctly.

## Retrospective

Shipped the widget; eval passed on first try. Closes #42.
"""

PLAN_UNCHECKED_TASKS = """\
# Plan: Ship the widget

Closes #42.

## Tasks

- [x] Build the widget
- [ ] Wire it up

## Verification

- `pytest` passes (verified).

## Retrospective

Mostly done.
"""

PLAN_PLACEHOLDER_RETRO = """\
# Plan: Ship the widget

Closes #42.

## Tasks

- [x] Build the widget

## Verification

- `pytest` passes (verified).

## Retrospective

TODO
"""

PLAN_NO_RETRO = """\
# Plan: Ship the widget

Closes #42.

## Tasks

- [x] Build the widget
"""

PLAN_PLACEHOLDER_VERIFICATION = """\
# Plan: Ship the widget

Closes #42.

## Tasks

- [x] Build the widget

## Verification

- TODO: run the test suite

## Retrospective

Shipped it.
"""

PLAN_NO_TRACKER = """\
# Plan: Ship the widget

## Tasks

- [x] Build the widget

## Verification

- `pytest` passes (verified).

## Retrospective

Shipped it, no issue tracked.
"""

TODO_PROSE_RETRO = """\
# Plan: Ship the widget

- [x] Build the widget

## Retrospective

TODO (#30): fill in the details here
"""


def _write(tmp_path, body, name="my-plan.md"):
    f = tmp_path / name
    f.write_text(body, encoding="utf-8")
    return f


# --------------------------------------------------------------------------- #
# check_plan — top-level verdict
# --------------------------------------------------------------------------- #
def test_complete_plan_passes(tmp_path):
    report = pcc.check_plan(_write(tmp_path, COMPLETE_PLAN))
    assert report.complete, report.blockers
    assert report.blockers == []
    assert "COMPLETE -> run /plan-retrospective" in report.verdict()


def test_unchecked_tasks_fail(tmp_path):
    report = pcc.check_plan(_write(tmp_path, PLAN_UNCHECKED_TASKS))
    assert not report.complete
    assert any("unchecked" in b for b in report.blockers)
    assert "INCOMPLETE" in report.verdict()


def test_placeholder_retro_fails(tmp_path):
    report = pcc.check_plan(_write(tmp_path, PLAN_PLACEHOLDER_RETRO))
    assert not report.complete
    assert any("placeholder" in b.lower() for b in report.blockers)


def test_missing_retro_fails(tmp_path):
    report = pcc.check_plan(_write(tmp_path, PLAN_NO_RETRO))
    assert not report.complete
    assert any("Retrospective" in b for b in report.blockers)


def test_placeholder_verification_fails(tmp_path):
    report = pcc.check_plan(_write(tmp_path, PLAN_PLACEHOLDER_VERIFICATION))
    assert not report.complete
    assert any("Verification" in b for b in report.blockers)


def test_missing_tracker_fails(tmp_path):
    report = pcc.check_plan(_write(tmp_path, PLAN_NO_TRACKER))
    assert not report.complete
    assert any("tracker" in b.lower() for b in report.blockers)


def test_missing_file_is_a_blocker(tmp_path):
    report = pcc.check_plan(tmp_path / "does-not-exist.md")
    assert not report.complete
    assert any("not readable" in b for b in report.blockers)


# --------------------------------------------------------------------------- #
# Individual check functions
# --------------------------------------------------------------------------- #
def test_check_unchecked_tasks_counts_correctly():
    assert pcc.check_unchecked_tasks("- [x] a\n- [ ] b\n- [ ] c\n") is not None
    assert "2 unchecked tasks" in pcc.check_unchecked_tasks("- [ ] b\n- [ ] c\n")
    assert "1 unchecked task" in pcc.check_unchecked_tasks("- [ ] b\n")
    assert pcc.check_unchecked_tasks("- [x] a\n") is None


def test_check_unchecked_tasks_indented_and_star_bullets():
    assert pcc.check_unchecked_tasks("  * [ ] nested\n") is not None
    assert pcc.check_unchecked_tasks("+ [ ] plus\n") is not None


def test_check_completion_section_accepts_completion_header():
    text = "## Completion\n\nAll wrapped up and verified.\n"
    assert pcc.check_completion_section(text) is None


def test_check_completion_section_accepts_done_header():
    text = "### Done\n\nDelivered and merged.\n"
    assert pcc.check_completion_section(text) is None


def test_check_completion_section_empty_body_is_placeholder():
    text = "## Retrospective\n\n## Next\n"
    assert pcc.check_completion_section(text) is not None


def test_check_completion_section_angle_bracket_placeholder():
    text = "## Retrospective\n\n<fill this in>\n"
    assert pcc.check_completion_section(text) is not None


def test_todo_prose_retrospective_is_placeholder():
    # A Retrospective whose only line begins with a placeholder keyword must
    # NOT pass the completion gate, even with trailing prose after the keyword.
    assert pcc.check_completion_section(TODO_PROSE_RETRO) is not None


def test_mid_sentence_placeholder_keyword_is_real_content():
    # A line that merely mentions a placeholder keyword mid-sentence is real content.
    body = "We resolved the issue in the parser and shipped it."
    assert pcc._is_placeholder_body(body) is False


def test_check_verification_absent_is_not_a_blocker():
    assert pcc.check_verification_addressed("## Retrospective\n\nDone.\n") is None


def test_check_verification_with_inline_todo_fails():
    text = "## Verification\n\n- pytest passes\n- TODO: smoke test\n"
    assert pcc.check_verification_addressed(text) is not None


def test_check_verification_clean_passes():
    text = "## Verification\n\n- pytest passes (verified)\n"
    assert pcc.check_verification_addressed(text) is None


def test_check_tracker_reference_accepts_beads_ids():
    assert pcc.check_tracker_reference("Advances hb-9yw.4.") is None
    assert pcc.check_tracker_reference("Advances bd-abc1.") is None
    assert pcc.check_tracker_reference("Closes #7.") is None
    assert pcc.check_tracker_reference("No tracker here.") is not None


# --------------------------------------------------------------------------- #
# Workspace-root discovery
# --------------------------------------------------------------------------- #
def test_find_workspace_root_via_dot_claude(tmp_path):
    (tmp_path / ".claude").mkdir()
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert pcc.find_workspace_root(nested) == tmp_path.resolve()


def test_find_workspace_root_none_when_absent(tmp_path, monkeypatch):
    # No .claude/ anywhere up-tree (stub the detector) and git returns nothing.
    monkeypatch.setattr(pcc, "_has_dot_claude", lambda p: False)
    monkeypatch.setattr(
        pcc.subprocess, "check_output",
        lambda *a, **k: (_ for _ in ()).throw(subprocess.CalledProcessError(1, "git")),
    )
    assert pcc.find_workspace_root(tmp_path) is None


def test_find_workspace_root_git_fallback(tmp_path, monkeypatch):
    # No .claude/ up-tree -> falls through to the git branch.
    monkeypatch.setattr(pcc, "_has_dot_claude", lambda p: False)
    monkeypatch.setattr(pcc.subprocess, "check_output", lambda *a, **k: "/repo/root\n")
    assert pcc.find_workspace_root(tmp_path) == Path("/repo/root")


# --------------------------------------------------------------------------- #
# Marker resolution + scan
# --------------------------------------------------------------------------- #
def test_resolve_marker_uses_recorded_path(tmp_path):
    plan = _write(tmp_path, COMPLETE_PLAN, name="recorded.md")
    marker = tmp_path / "recorded.marker"
    marker.write_text(str(plan) + "\n", encoding="utf-8")
    assert pcc.resolve_marker_to_plan(marker) == plan


def test_resolve_marker_falls_back_to_plans_dir(tmp_path, monkeypatch):
    fake_plans = tmp_path / "plans"
    fake_plans.mkdir()
    plan = fake_plans / "slug.md"
    plan.write_text(COMPLETE_PLAN, encoding="utf-8")
    monkeypatch.setattr(pcc, "plans_dir", lambda: fake_plans)

    marker = tmp_path / "slug.marker"
    marker.write_text("", encoding="utf-8")  # empty -> fallback by stem
    assert pcc.resolve_marker_to_plan(marker) == plan


def test_resolve_marker_handles_unreadable_marker(tmp_path, monkeypatch):
    # An unreadable marker (read_text raises) falls back to the plans-dir stem.
    fake_plans = tmp_path / "plans"
    fake_plans.mkdir()
    (fake_plans / "broken.md").write_text(COMPLETE_PLAN, encoding="utf-8")
    monkeypatch.setattr(pcc, "plans_dir", lambda: fake_plans)
    monkeypatch.setattr(
        pcc.Path, "read_text",
        lambda self, *a, **k: (_ for _ in ()).throw(OSError("nope")),
    )
    marker = tmp_path / "broken.marker"
    assert pcc.resolve_marker_to_plan(marker) == fake_plans / "broken.md"


def test_plans_dir_points_at_home_claude_plans():
    assert pcc.plans_dir() == Path.home() / ".claude" / "plans"


def test_completion_section_blank_markers_only_is_placeholder():
    # A body of nothing but list/heading markers (no text) reads as placeholder.
    assert pcc.check_completion_section("## Retrospective\n\n-\n>\n#\n") is not None


def test_resolve_marker_returns_none_when_unresolvable(tmp_path, monkeypatch):
    monkeypatch.setattr(pcc, "plans_dir", lambda: tmp_path / "nope")
    marker = tmp_path / "ghost.marker"
    marker.write_text("/path/does/not/exist.md\n", encoding="utf-8")
    assert pcc.resolve_marker_to_plan(marker) is None


def test_scan_pending_empty_when_no_dir(tmp_path):
    assert pcc.scan_pending(tmp_path) == []


def test_scan_pending_reports_complete_and_incomplete(tmp_path):
    pending = tmp_path / "retrospectives" / "pending"
    pending.mkdir(parents=True)

    good = _write(tmp_path, COMPLETE_PLAN, name="good.md")
    bad = _write(tmp_path, PLAN_UNCHECKED_TASKS, name="bad.md")
    (pending / "good.marker").write_text(str(good) + "\n", encoding="utf-8")
    (pending / "bad.marker").write_text(str(bad) + "\n", encoding="utf-8")

    results = dict(pcc.scan_pending(tmp_path))
    assert results["good"].complete
    assert not results["bad"].complete


def test_scan_pending_unresolvable_marker_yields_none(tmp_path, monkeypatch):
    pending = tmp_path / "retrospectives" / "pending"
    pending.mkdir(parents=True)
    monkeypatch.setattr(pcc, "plans_dir", lambda: tmp_path / "nope")
    (pending / "ghost.marker").write_text("/no/such/plan.md\n", encoding="utf-8")
    results = dict(pcc.scan_pending(tmp_path))
    assert results["ghost"] is None


# --------------------------------------------------------------------------- #
# main() — in-process nag behavior
# --------------------------------------------------------------------------- #
def _run_main(monkeypatch, payload, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    rc = pcc.main([])  # explicit empty argv => SessionStart-nag mode
    return rc, capsys.readouterr().out


def test_main_nags_for_incomplete_plan(tmp_path, monkeypatch, capsys):
    (tmp_path / ".claude").mkdir()  # stop the workspace-root walk here
    pending = tmp_path / "retrospectives" / "pending"
    pending.mkdir(parents=True)
    bad = _write(tmp_path, PLAN_UNCHECKED_TASKS, name="bad.md")
    (pending / "bad.marker").write_text(str(bad) + "\n", encoding="utf-8")

    rc, out = _run_main(monkeypatch, {"cwd": str(tmp_path)}, capsys)
    assert rc == 0
    assert "NOT yet complete" in out
    assert "bad" in out
    assert "unchecked" in out


def test_main_silent_for_complete_plan(tmp_path, monkeypatch, capsys):
    (tmp_path / ".claude").mkdir()
    pending = tmp_path / "retrospectives" / "pending"
    pending.mkdir(parents=True)
    good = _write(tmp_path, COMPLETE_PLAN, name="good.md")
    (pending / "good.marker").write_text(str(good) + "\n", encoding="utf-8")

    rc, out = _run_main(monkeypatch, {"cwd": str(tmp_path)}, capsys)
    assert rc == 0
    assert out.strip() == ""


def test_main_lists_multiple_blockers_with_more_suffix(tmp_path, monkeypatch, capsys):
    (tmp_path / ".claude").mkdir()
    pending = tmp_path / "retrospectives" / "pending"
    pending.mkdir(parents=True)
    # No tracker + no retro + placeholder verification => multiple blockers.
    multi = _write(tmp_path, "## Verification\n\nTODO\n", name="multi.md")
    (pending / "multi.marker").write_text(str(multi) + "\n", encoding="utf-8")

    rc, out = _run_main(monkeypatch, {"cwd": str(tmp_path)}, capsys)
    assert rc == 0
    assert "more)" in out


def test_main_mentions_unresolvable_marker(tmp_path, monkeypatch, capsys):
    (tmp_path / ".claude").mkdir()
    pending = tmp_path / "retrospectives" / "pending"
    pending.mkdir(parents=True)
    monkeypatch.setattr(pcc, "plans_dir", lambda: tmp_path / "nope")
    (pending / "ghost.marker").write_text("/no/such/plan.md\n", encoding="utf-8")

    rc, out = _run_main(monkeypatch, {"cwd": str(tmp_path)}, capsys)
    assert rc == 0
    assert "ghost" in out
    assert "not found" in out


def test_main_no_pending_dir_is_silent(tmp_path, monkeypatch, capsys):
    (tmp_path / ".claude").mkdir()  # workspace root resolves, but no pending/
    rc, out = _run_main(monkeypatch, {"cwd": str(tmp_path)}, capsys)
    assert rc == 0
    assert out.strip() == ""


def test_main_handles_unresolvable_workspace_root(monkeypatch, capsys):
    monkeypatch.setattr(pcc, "find_workspace_root", lambda *a, **k: None)
    rc, out = _run_main(monkeypatch, {}, capsys)
    assert rc == 0
    assert out.strip() == ""


def test_main_tolerates_bad_stdin(tmp_path, monkeypatch, capsys):
    # Non-JSON stdin must not crash; falls back to process cwd (no pending there).
    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
    monkeypatch.setattr(pcc, "find_workspace_root", lambda *a, **k: None)
    rc = pcc.main([])
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""


# --------------------------------------------------------------------------- #
# main() — CLI mode (plan-path argument)
# --------------------------------------------------------------------------- #
def test_main_cli_mode_complete_plan(tmp_path, capsys):
    plan = _write(tmp_path, COMPLETE_PLAN)
    rc = pcc.main([str(plan)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "COMPLETE -> run /plan-retrospective" in out


def test_main_cli_mode_incomplete_plan(tmp_path, capsys):
    plan = _write(tmp_path, PLAN_UNCHECKED_TASKS)
    rc = pcc.main([str(plan)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "INCOMPLETE" in out
    assert "unchecked" in out


def test_main_cli_ignores_leading_flags(tmp_path, capsys):
    plan = _write(tmp_path, COMPLETE_PLAN)
    rc = pcc.main(["--whatever", str(plan)])
    assert rc == 0
    assert "COMPLETE" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Behavioral / subprocess test of the hook via the blessed `uv run` launcher
# --------------------------------------------------------------------------- #
def test_hook_subprocess_nags_via_uv(tmp_path):
    """End-to-end: invoke the hook exactly as hooks.json does (uv run) and assert
    it emits a soft nag for an incomplete pending plan and exits 0."""
    (tmp_path / ".claude").mkdir()  # stop the workspace-root walk at tmp_path
    pending = tmp_path / "retrospectives" / "pending"
    pending.mkdir(parents=True)
    bad = tmp_path / "bad.md"
    bad.write_text(PLAN_UNCHECKED_TASKS, encoding="utf-8")
    (pending / "bad.marker").write_text(str(bad) + "\n", encoding="utf-8")

    result = subprocess.run(
        ["uv", "run", "--no-project", str(_HOOK_PATH)],
        input=json.dumps({"cwd": str(tmp_path)}),
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=os.environ,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "NOT yet complete" in result.stdout
    assert "bad" in result.stdout
