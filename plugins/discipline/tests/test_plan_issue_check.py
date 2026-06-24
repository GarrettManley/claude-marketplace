"""Tests for the plan_issue_check PostToolUse hook.

Covers issue/beads citation (Rule 1), Retrospective state-change markers
(Rule 2), the false-positive guard on the beads-id regex, the broadened
default plan_pattern (docs-dated + .claude/plans/), and bd auto-close.

The hook is driven the way Claude Code drives it: a PostToolUse JSON payload
on stdin; it emits a `{"decision": "block", ...}` JSON on stdout (and always
`sys.exit(0)`), or nothing on pass.
"""
import io
import json
from pathlib import Path

import pytest

# conftest puts the plugin's scripts/ and hooks/ on sys.path.
import discipline_config
import plan_issue_check


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #
def _run(monkeypatch, payload):
    """Invoke main() with `payload` on stdin; return emitted stdout ('' == pass)."""
    discipline_config.get_config.cache_clear()
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    with pytest.raises(SystemExit) as exc:
        plan_issue_check.main()
    assert exc.value.code == 0
    return out.getvalue()


def _write_plan(tmp_path, body, name="2026-01-01-plan.md", subdir="docs/plans"):
    d = tmp_path / subdir if subdir else tmp_path
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    f.write_text(body, encoding="utf-8")
    return f


def _payload(path):
    return {"tool_input": {"file_path": str(path)}}


def _is_block(out):
    return bool(out) and json.loads(out.splitlines()[0])["decision"] == "block"


@pytest.fixture
def hermetic(clean_env, monkeypatch):
    """No git auto-detection (repo_root/repo = None) so gh stays out of the path
    and path normalization is deterministic regardless of the test's cwd."""
    monkeypatch.setattr(discipline_config, "_detect_git_root", lambda: None)
    monkeypatch.setattr(discipline_config, "_detect_repo", lambda: None)
    return monkeypatch


@pytest.fixture
def permissive(hermetic):
    """hermetic + treat any .md as a plan, to isolate Rule 1/2 logic from path matching."""
    hermetic.setenv("DISCIPLINE_PLAN_PATTERN", r".*\.md$")
    return hermetic


# --------------------------------------------------------------------------- #
# Rule 1 — citation required, GitHub #N OR beads id
# --------------------------------------------------------------------------- #
def test_github_issue_passes(permissive, tmp_path):
    out = _run(permissive, _payload(_write_plan(tmp_path, "Implements #123.")))
    assert out == ""


def test_beads_hb_id_passes(permissive, tmp_path):
    out = _run(permissive, _payload(_write_plan(tmp_path, "Advances hb-9yw.4 today.")))
    assert out == ""


def test_beads_bd_id_passes(permissive, tmp_path):
    out = _run(permissive, _payload(_write_plan(tmp_path, "Advances bd-abc1.")))
    assert out == ""


def test_no_citation_blocks(permissive, tmp_path):
    out = _run(permissive, _payload(_write_plan(tmp_path, "Just some plan text, no tracker.")))
    assert _is_block(out)


def test_hyphenated_words_do_not_count_as_ids(permissive, tmp_path):
    """The regex must not match ordinary hyphenated words, or Rule 1 is toothless."""
    body = "We wire claude-code and pre-commit hooks end-to-end."
    out = _run(permissive, _payload(_write_plan(tmp_path, body)))
    assert _is_block(out)


# --------------------------------------------------------------------------- #
# Rule 2 — Retrospective must record issue-state changes
# --------------------------------------------------------------------------- #
def test_retro_without_marker_blocks(permissive, tmp_path):
    body = "Implements #123.\n\n## Retrospective\n\nAll done, went well.\n"
    out = _run(permissive, _payload(_write_plan(tmp_path, body)))
    assert _is_block(out)


def test_retro_with_github_marker_passes(permissive, tmp_path):
    body = "Implements #123.\n\n## Retrospective\n\nCloses #123.\n"
    out = _run(permissive, _payload(_write_plan(tmp_path, body)))
    assert out == ""  # repo=None -> no gh auto-close attempted


def test_retro_with_beads_marker_passes(permissive, tmp_path):
    """bd marker satisfies Rule 2; with no ledger configured, no auto-close runs."""
    body = "Advances hb-9yw.4.\n\n## Retrospective\n\nCloses hb-9yw.4.\n"
    out = _run(permissive, _payload(_write_plan(tmp_path, body)))
    assert out == ""


# --------------------------------------------------------------------------- #
# bd auto-close
# --------------------------------------------------------------------------- #
def test_beads_closes_marker_invokes_bd_close(permissive, tmp_path, monkeypatch):
    ledger = str(tmp_path / "ledger")
    monkeypatch.setenv("DISCIPLINE_BD_LEDGER", ledger)
    # Force the gate True so the test doesn't depend on `bd` being installed in CI.
    monkeypatch.setattr(discipline_config.DisciplineConfig, "has_bd", property(lambda self: True))

    calls = {}

    def fake_check_output(cmd, **kw):
        calls["show"] = cmd
        bid = cmd[cmd.index("show") + 1]
        return json.dumps([{"id": bid, "status": "open"}])

    class _Ok:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kw):
        calls["close"] = cmd
        return _Ok()

    monkeypatch.setattr(plan_issue_check.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(plan_issue_check.subprocess, "run", fake_run)

    body = "Advances hb-test.1.\n\n## Retrospective\n\nCloses hb-test.1.\n"
    _run(monkeypatch, _payload(_write_plan(tmp_path, body)))

    assert "close" in calls, "bd close was not invoked"
    assert "hb-test.1" in calls["close"]
    assert "-C" in calls["close"] and ledger in calls["close"]


def test_beads_already_closed_is_skipped(permissive, tmp_path, monkeypatch):
    monkeypatch.setenv("DISCIPLINE_BD_LEDGER", str(tmp_path / "ledger"))
    monkeypatch.setattr(discipline_config.DisciplineConfig, "has_bd", property(lambda self: True))

    closed_attempted = {"n": 0}
    monkeypatch.setattr(
        plan_issue_check.subprocess, "check_output",
        lambda cmd, **kw: json.dumps([{"status": "closed"}]),
    )

    def fake_run(cmd, **kw):
        closed_attempted["n"] += 1
        class _Ok:
            returncode = 0
            stderr = ""
        return _Ok()

    monkeypatch.setattr(plan_issue_check.subprocess, "run", fake_run)

    body = "Advances hb-done.2.\n\n## Retrospective\n\nCloses hb-done.2.\n"
    _run(monkeypatch, _payload(_write_plan(tmp_path, body)))
    assert closed_attempted["n"] == 0, "already-closed bead should not be re-closed"


# --------------------------------------------------------------------------- #
# Default plan_pattern — covers docs-dated AND .claude/plans/
# --------------------------------------------------------------------------- #
def test_default_pattern_matches_claude_plans(hermetic, tmp_path):
    f = _write_plan(tmp_path, "Advances hb-9yw.4.", name="foo.md", subdir=".claude/plans")
    assert _run(hermetic, _payload(f)) == ""  # engaged + citation present


def test_default_pattern_engages_on_claude_plans_without_citation(hermetic, tmp_path):
    f = _write_plan(tmp_path, "No tracker here.", name="foo.md", subdir=".claude/plans")
    assert _is_block(_run(hermetic, _payload(f)))  # proves the hook actually ran


def test_default_pattern_still_matches_dated_docs_plan(hermetic, tmp_path):
    f = _write_plan(tmp_path, "Implements #5.", name="2026-01-01-x.md", subdir="docs/plans")
    assert _run(hermetic, _payload(f)) == ""


def test_non_plan_path_is_skipped(hermetic, tmp_path):
    """A file that matches no plan location is ignored even with no citation."""
    f = _write_plan(tmp_path, "No tracker here.", name="notes.md", subdir="")
    assert _run(hermetic, _payload(f)) == ""
