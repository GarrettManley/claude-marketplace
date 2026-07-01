import io
import json
import sys
from pathlib import Path
import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from session_resume_context import main, format_snapshot
from snapshot import get_snapshot_path, write_snapshot


@pytest.fixture
def tmp_snapshot_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCIPLINE_SNAPSHOT_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/explicit/proj")
    return tmp_path


def _call(monkeypatch, stdin_text: str = "{}"):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin_text))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    rc = main([])
    return rc, out.getvalue()


def test_no_snapshot_silent(tmp_snapshot_dir, monkeypatch):
    rc, out = _call(monkeypatch)
    assert rc == 0
    assert out == ""


def test_writes_additional_context_when_snapshot_exists(tmp_snapshot_dir, monkeypatch):
    state = {
        "timestamp": 1000.0,
        "git": {"branch": "feat/x", "head": "a" * 40},
        "recent_files": [{"path": "src/a.py"}, {"path": "src/b.py"}],
    }
    write_snapshot(state)
    rc, out = _call(monkeypatch)
    assert rc == 0
    payload = json.loads(out)
    assert "hookSpecificOutput" in payload
    output = payload["hookSpecificOutput"]
    assert output.get("hookEventName") == "SessionStart"
    ctx = output.get("additionalContext", "")
    assert "feat/x" in ctx
    assert "src/a.py" in ctx
    assert "src/b.py" in ctx


def test_format_includes_branch_and_files():
    state = {
        "timestamp": 1000.0,
        "git": {"branch": "main", "head": "deadbeef" * 5},
        "recent_files": [{"path": "x.py"}, {"path": "y.py"}],
    }
    text = format_snapshot(state)
    assert "main" in text
    assert "x.py" in text
    assert "y.py" in text


def test_format_handles_no_git():
    state = {"timestamp": 1000.0, "git": None, "recent_files": []}
    text = format_snapshot(state)
    # Should still produce something, not error
    assert isinstance(text, str)


def test_truncates_long_file_list():
    state = {
        "timestamp": 1000.0,
        "git": {"branch": "main", "head": "x" * 40},
        "recent_files": [{"path": f"f{i}.py"} for i in range(50)],
    }
    text = format_snapshot(state)
    # Should not contain all 50 files (must truncate)
    assert text.count("\n") < 50


def test_invalid_json_input_still_works(tmp_snapshot_dir, monkeypatch):
    state = {
        "timestamp": 1000.0,
        "git": {"branch": "main", "head": "z" * 40},
        "recent_files": [{"path": "ok.py"}],
    }
    write_snapshot(state)
    rc, out = _call(monkeypatch, stdin_text="not-json{{")
    # Should still emit the snapshot (stdin parse failure is non-fatal)
    assert rc == 0
    payload = json.loads(out)
    assert "additionalContext" in payload["hookSpecificOutput"]


# --- live workflow section rendering ---


def test_format_workflow_renders_plan_retros_and_note():
    from session_resume_context import _format_workflow

    workflow = {
        "active_plan": {
            "path": "/tmp/plans/example-plan.md",
            "source": "sdd-ledger",
            "tasks_done": 3,
            "tasks_open": 2,
        },
        "sdd_ledger": {"path": "/tmp/x/.superpowers/sdd/progress.md", "plan_path": None},
        "pending_retros": [{"slug": "example-plan"}],
    }
    note = {"text": "next: wire the CLI", "timestamp": 1700000000.0}
    lines = _format_workflow(workflow, note)
    joined = "\n".join(lines)
    assert "**Active plan:** `/tmp/plans/example-plan.md` (via sdd-ledger) - 3 done / 2 open" in joined
    assert "**Pending retros:** example-plan" in joined
    assert "**Where you were**" in joined
    assert "next: wire the CLI" in joined


def test_format_workflow_empty_yields_no_lines():
    from session_resume_context import _format_workflow

    assert _format_workflow({}, None) == []
    assert (
        _format_workflow(
            {"active_plan": None, "sdd_ledger": None, "pending_retros": []}, None
        )
        == []
    )


def test_main_snapshot_only_output_unchanged(tmp_path, monkeypatch, capsys):
    """Legacy: with a snapshot and no workflow, output is exactly format_snapshot."""
    import io
    import json as _json

    import session_resume_context
    from snapshot import write_snapshot

    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
    monkeypatch.setenv("DISCIPLINE_SNAPSHOT_DIR", str(tmp_path / "snap"))
    state = {"timestamp": 1700000000.0, "git": {"branch": "main", "head": "a" * 40}, "recent_files": []}
    assert write_snapshot(state) is True
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    rc = session_resume_context.main([])
    assert rc == 0
    payload = _json.loads(capsys.readouterr().out)
    expected = session_resume_context.format_snapshot(state)
    assert payload["hookSpecificOutput"]["additionalContext"] == expected


def test_main_emits_workflow_without_snapshot(tmp_path, monkeypatch, capsys):
    import io
    import json as _json

    import session_resume_context

    proj = tmp_path / "proj"
    proj.mkdir()
    plan = proj / "p.md"
    plan.write_text("# P\n- [x] a\n- [ ] b\n", encoding="utf-8")
    pending = proj / "retrospectives" / "pending"
    pending.mkdir(parents=True)
    (pending / "p.marker").write_text(str(plan) + "\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
    monkeypatch.setenv("DISCIPLINE_SNAPSHOT_DIR", str(tmp_path / "snap-empty"))
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    rc = session_resume_context.main([])
    assert rc == 0
    payload = _json.loads(capsys.readouterr().out)
    ctx = payload["hookSpecificOutput"]["additionalContext"]
    assert "## Workflow context" in ctx
    assert f"**Active plan:** `{plan}` (via pending-marker) - 1 done / 1 open" in ctx


def test_main_silent_when_nothing_exists(tmp_path, monkeypatch, capsys):
    import io

    import session_resume_context

    proj = tmp_path / "empty-proj"
    proj.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
    monkeypatch.setenv("DISCIPLINE_SNAPSHOT_DIR", str(tmp_path / "no-snap"))
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    rc = session_resume_context.main([])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_main_survives_workflow_discovery_crash(tmp_path, monkeypatch, capsys):
    """Hook safety: a crashing plan_state must not break the hook."""
    import io

    import plan_state
    import session_resume_context

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("DISCIPLINE_SNAPSHOT_DIR", str(tmp_path / "no-snap"))
    monkeypatch.setattr(
        plan_state, "gather_workflow_state", lambda: (_ for _ in ()).throw(RuntimeError)
    )
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    rc = session_resume_context.main([])
    assert rc == 0
    assert capsys.readouterr().out == ""
