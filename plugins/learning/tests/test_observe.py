import io
import json
import os
import sys
import time
from pathlib import Path
import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from observe import main, _build_observation


@pytest.fixture
def tmp_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LEARNING_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/explicit/proj")
    return tmp_path


def _call(event, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    monkeypatch.setattr("sys.stdout", io.StringIO())
    return main([])


def test_observation_recorded_to_project_jsonl(tmp_data, monkeypatch):
    monkeypatch.setenv("LEARNING_OBSERVE", "on")
    rc = _call({
        "tool_name": "Edit",
        "tool_input": {"file_path": "/x.py"},
        "session_id": "test",
    }, monkeypatch)
    assert rc == 0
    from storage import get_project_id, get_observations_file
    obs_file = get_observations_file(get_project_id())
    assert obs_file.exists()
    lines = obs_file.read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["tool_name"] == "Edit"
    assert "timestamp" in rec


def test_disabled_by_default(tmp_data, monkeypatch):
    monkeypatch.delenv("LEARNING_OBSERVE", raising=False)
    rc = _call({
        "tool_name": "Edit",
        "tool_input": {"file_path": "/x.py"},
        "session_id": "test",
    }, monkeypatch)
    assert rc == 0
    from storage import get_project_id, get_observations_file
    obs_file = get_observations_file(get_project_id())
    assert not obs_file.exists()


def test_invalid_json_passthrough(tmp_data, monkeypatch):
    monkeypatch.setenv("LEARNING_OBSERVE", "on")
    monkeypatch.setattr("sys.stdin", io.StringIO("not-json{{"))
    monkeypatch.setattr("sys.stdout", io.StringIO())
    rc = main([])
    assert rc == 0


def test_build_observation_shape():
    obs = _build_observation(
        {"tool_name": "Bash", "tool_input": {"command": "ls"}},
        phase="pre",
    )
    assert obs["tool_name"] == "Bash"
    assert obs["phase"] == "pre"
    assert isinstance(obs["timestamp"], (int, float))


# --- Phase 2a schema enrichment ---


def test_post_observation_captures_tool_response():
    obs = _build_observation(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_response": {"stdout": "file1\nfile2\n", "exit_code": 0},
        },
        phase="post",
    )
    assert obs["tool_response"] == {"stdout": "file1\nfile2\n", "exit_code": 0}


def test_pre_observation_does_not_carry_tool_response():
    # PreToolUse events shouldn't have a tool_response; even if one's
    # present in the event, we don't store it on pre records (it's
    # semantically meaningless before the tool has run).
    obs = _build_observation(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_response": {"would-not": "exist-on-pre"},
        },
        phase="pre",
    )
    assert "tool_response" not in obs


def test_tool_use_id_captured_when_present():
    obs = _build_observation(
        {"tool_name": "Edit", "tool_input": {}, "tool_use_id": "toolu_01abc"},
        phase="pre",
    )
    assert obs["tool_use_id"] == "toolu_01abc"


def test_tool_use_id_camelcase_also_captured():
    obs = _build_observation(
        {"tool_name": "Edit", "tool_input": {}, "toolUseId": "toolu_02xyz"},
        phase="post",
    )
    assert obs["tool_use_id"] == "toolu_02xyz"


def test_observation_without_new_fields_remains_backward_compatible():
    obs = _build_observation(
        {"tool_name": "Read", "tool_input": {"file_path": "/x"}},
        phase="post",
    )
    # No tool_response, no tool_use_id → record has neither key. Old readers
    # that don't expect them still work.
    assert "tool_response" not in obs
    assert "tool_use_id" not in obs


# --- Phase detection from the canonical hook_event_name signal ---


def test_phase_detected_from_hook_event_name_pre(tmp_data, monkeypatch):
    monkeypatch.setenv("LEARNING_OBSERVE", "on")
    rc = _call({
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": "/x.py"},
        "session_id": "test",
    }, monkeypatch)
    assert rc == 0
    from storage import get_project_id, get_observations_file
    rec = json.loads(get_observations_file(get_project_id()).read_text().splitlines()[0])
    assert rec["phase"] == "pre"


def test_phase_detected_from_hook_event_name_post(tmp_data, monkeypatch):
    monkeypatch.setenv("LEARNING_OBSERVE", "on")
    rc = _call({
        "hook_event_name": "PostToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": "/x.py"},
        "session_id": "test",
    }, monkeypatch)
    assert rc == 0
    from storage import get_project_id, get_observations_file
    rec = json.loads(get_observations_file(get_project_id()).read_text().splitlines()[0])
    assert rec["phase"] == "post"


def test_hook_event_name_wins_over_argv(monkeypatch):
    # The wrapper path passes the wrapper's own argv to observe.main(); the
    # stdin hook_event_name must take precedence over any stray argv token.
    from observe import _detect_phase
    event = {"hook_event_name": "PreToolUse"}
    assert _detect_phase(event, ["run_with_flags.py", "observe.py", "post"]) == "pre"


def test_phase_via_run_with_flags_production_path(tmp_data, monkeypatch):
    # End-to-end regression for the real production path: run_with_flags.py
    # imports observe and calls main() WITHOUT setting sys.argv, so observe sees
    # the wrapper's argv. Before the fix this always recorded phase="post".
    monkeypatch.setenv("LEARNING_OBSERVE", "on")
    # The observe hook is gated to the "strict" profile (see hooks.json); the
    # wrapper would otherwise passthrough without running it.
    monkeypatch.setenv("LEARNING_HOOK_PROFILE", "strict")
    import run_with_flags

    event = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "session_id": "test",
    }
    observe_path = str(SCRIPTS_DIR / "observe.py")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    monkeypatch.setattr("sys.stdout", io.StringIO())
    # Default profile "strict" keeps the hook enabled.
    rc = run_with_flags.main(
        ["run_with_flags.py", observe_path, "learning:pre-tool:observe", "strict"]
    )
    assert rc == 0
    from storage import get_project_id, get_observations_file
    rec = json.loads(get_observations_file(get_project_id()).read_text().splitlines()[0])
    assert rec["phase"] == "pre"
