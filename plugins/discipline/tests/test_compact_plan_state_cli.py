import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import compact_plan_state  # noqa: E402
from compact_plan_state import main  # noqa: E402


@pytest.fixture
def env(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
    monkeypatch.setenv("DISCIPLINE_SNAPSHOT_DIR", str(tmp_path / "snap"))
    return proj


def test_saves_note_and_reports_path(env, tmp_path, capsys):
    rc = main(["--note", "resume at task 2"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "note saved:" in out
    notes = list((tmp_path / "snap").glob("*.note.json"))
    assert len(notes) == 1
    data = json.loads(notes[0].read_text(encoding="utf-8"))
    assert data["text"] == "resume at task 2"


def test_digest_reports_discovered_plan(env, capsys):
    plan = env / "the-plan.md"
    plan.write_text("# P\n- [x] a\n- [ ] b\n", encoding="utf-8")
    pending = env / "retrospectives" / "pending"
    pending.mkdir(parents=True)
    (pending / "the-plan.marker").write_text(str(plan) + "\n", encoding="utf-8")
    rc = main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert f"active plan: {plan} (source: pending-marker) - 1 done / 1 open" in out
    assert "pending retros: the-plan" in out


def test_empty_project_fail_soft(env, capsys):
    rc = main([])
    assert rc == 0
    assert "no workflow state discovered" in capsys.readouterr().out


def test_note_write_failure_reported_not_raised(env, monkeypatch, capsys):
    def boom(text):
        raise OSError("disk full")

    monkeypatch.setattr(compact_plan_state, "write_note", boom)
    rc = main(["--note", "anything"])
    assert rc == 0
    assert "note write FAILED" in capsys.readouterr().out


def test_output_is_ascii(env, capsys):
    main(["--note", "plain note"])
    capsys.readouterr().out.encode("ascii")  # raises if any non-ASCII slipped in
