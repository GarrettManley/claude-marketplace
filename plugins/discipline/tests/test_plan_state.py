import json
import os
import sys
import time
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import snapshot  # noqa: E402
from plan_state import (  # noqa: E402
    NOTE_TTL_SECONDS,
    gather_workflow_state,
    get_note_path,
    get_project_root,
    read_note,
    write_note,
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
    monkeypatch.setenv("DISCIPLINE_SNAPSHOT_DIR", str(tmp_path / "snap"))
    return proj


def _write_plan(path: Path, done: int = 2, open_: int = 3) -> None:
    lines = ["# Plan"]
    lines += [f"- [x] done step {i}" for i in range(done)]
    lines += [f"- [ ] open step {i}" for i in range(open_)]
    path.write_text("\n".join(lines), encoding="utf-8")


def test_empty_project_yields_empty_state(project):
    state = gather_workflow_state()
    assert state["active_plan"] is None
    assert state["sdd_ledger"] is None
    assert state["pending_retros"] == []


def test_sdd_ledger_wins_and_counts_checkboxes(project):
    plan = project / "active-plan.md"
    _write_plan(plan, done=2, open_=3)
    sdd = project / ".superpowers" / "sdd"
    sdd.mkdir(parents=True)
    (sdd / "progress.md").write_text(
        f"# SDD ledger\nPlan: {plan}\nTask 1: in progress\n", encoding="utf-8"
    )
    # A pending marker also exists — the ledger must still win.
    pending = project / "retrospectives" / "pending"
    pending.mkdir(parents=True)
    (pending / "other.marker").write_text(str(plan) + "\n", encoding="utf-8")
    state = gather_workflow_state()
    assert state["active_plan"]["source"] == "sdd-ledger"
    assert state["active_plan"]["path"] == str(plan)
    assert state["active_plan"]["tasks_done"] == 2
    assert state["active_plan"]["tasks_open"] == 3
    assert state["sdd_ledger"]["path"].endswith("progress.md")


def test_pending_marker_fallback(project):
    plan = project / "marker-plan.md"
    _write_plan(plan, done=1, open_=1)
    pending = project / "retrospectives" / "pending"
    pending.mkdir(parents=True)
    (pending / "marker-plan.marker").write_text(str(plan) + "\n", encoding="utf-8")
    state = gather_workflow_state()
    assert state["active_plan"]["source"] == "pending-marker"
    assert state["active_plan"]["path"] == str(plan)
    assert state["pending_retros"] == [{"slug": "marker-plan"}]


def test_sdd_ledger_plan_path_with_spaces_and_earlier_md_token(project):
    plan_dir = project / "John Smith" / ".claude" / "plans"
    plan_dir.mkdir(parents=True)
    plan = plan_dir / "my-plan.md"
    _write_plan(plan, done=1, open_=1)
    sdd = project / ".superpowers" / "sdd"
    sdd.mkdir(parents=True)
    (sdd / "progress.md").write_text(
        f"# SDD ledger (progress.md)\nPlan: {plan}\n", encoding="utf-8"
    )
    state = gather_workflow_state()
    assert state["active_plan"]["path"] == str(plan)
    assert state["active_plan"]["tasks_done"] == 1
    assert state["active_plan"]["tasks_open"] == 1


def test_marker_without_plan_path_yields_no_active_plan(project):
    pending = project / "retrospectives" / "pending"
    pending.mkdir(parents=True)
    (pending / "odd.marker").write_text("not a path\n", encoding="utf-8")
    state = gather_workflow_state()
    assert state["active_plan"] is None
    assert state["pending_retros"] == [{"slug": "odd"}]


def test_nonexistent_fallback_token_yields_no_active_plan(project):
    sdd = project / ".superpowers" / "sdd"
    sdd.mkdir(parents=True)
    (sdd / "progress.md").write_text(
        "# SDD ledger\nsee notes-about-stuff.md for details\n", encoding="utf-8"
    )
    state = gather_workflow_state()
    assert state["active_plan"] is None


def test_relative_ledger_plan_path_anchors_to_root(project, tmp_path, monkeypatch):
    plan = project / "docs" / "p.md"
    plan.parent.mkdir(parents=True)
    _write_plan(plan, done=1, open_=2)
    sdd = project / ".superpowers" / "sdd"
    sdd.mkdir(parents=True)
    (sdd / "progress.md").write_text(
        "# SDD ledger\nPlan: docs/p.md\n", encoding="utf-8"
    )
    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)
    state = gather_workflow_state()
    assert state["active_plan"]["path"] == str(plan)
    assert state["active_plan"]["tasks_done"] == 1
    assert state["active_plan"]["tasks_open"] == 2


def test_project_root_falls_back_to_cwd(project, tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_PROJECT_DIR")
    monkeypatch.setattr(snapshot, "_git_toplevel", lambda: None)
    monkeypatch.chdir(tmp_path)
    assert get_project_root() == Path(os.getcwd())


def test_note_roundtrip_and_path(project, tmp_path):
    path = write_note("resume at task 2", now=1000.0)
    assert path == get_note_path()
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"text": "resume at task 2", "timestamp": 1000.0}
    fresh = read_note(now=1000.0 + NOTE_TTL_SECONDS - 1)
    assert fresh == {"text": "resume at task 2", "timestamp": 1000.0}


def test_expired_note_reads_as_none(project):
    write_note("too old", now=1000.0)
    assert read_note(now=1000.0 + NOTE_TTL_SECONDS + 1) is None


def test_missing_or_malformed_note_reads_as_none(project):
    assert read_note() is None
    get_note_path().parent.mkdir(parents=True, exist_ok=True)
    get_note_path().write_text("not-json{{", encoding="utf-8")
    assert read_note() is None


def test_non_dict_note_json_reads_as_none(project):
    get_note_path().parent.mkdir(parents=True, exist_ok=True)
    get_note_path().write_text("[1]", encoding="utf-8")
    assert read_note() is None


def test_note_key_matches_across_hook_and_cli_contexts(tmp_path, monkeypatch):
    """The hook path (CLAUDE_PROJECT_DIR set) and the Bash-run CLI path (no
    CLAUDE_PROJECT_DIR, falls back to git toplevel) must resolve to the same
    note file for the same project root."""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    monkeypatch.setenv("DISCIPLINE_SNAPSHOT_DIR", str(tmp_path / "snap"))

    # Write WITHOUT CLAUDE_PROJECT_DIR (CLI context): falls back to git toplevel.
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(repo)
    write_note("cross-context note", now=1000.0)

    # Read WITH CLAUDE_PROJECT_DIR set to the same directory (hook context).
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    note = read_note(now=1000.0)
    assert note == {"text": "cross-context note", "timestamp": 1000.0}
