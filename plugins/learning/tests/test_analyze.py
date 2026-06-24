import json
import sys
from pathlib import Path
import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from analyze import (
    load_observations,
    tool_frequency,
    pre_post_sequences,
    bash_command_prefixes,
    file_hotspots,
)
from storage import get_observations_file, get_project_id


@pytest.fixture
def tmp_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LEARNING_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/explicit/proj")
    return tmp_path


def _write_observations(records: list[dict]) -> None:
    obs_file = get_observations_file(get_project_id())
    obs_file.parent.mkdir(parents=True, exist_ok=True)
    with open(obs_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


# --- load_observations ---


def test_load_returns_empty_when_no_file(tmp_data):
    assert load_observations() == []


def test_load_parses_jsonl(tmp_data):
    _write_observations([
        {"timestamp": 1.0, "phase": "pre", "tool_name": "Edit", "tool_input": {}, "session_id": "s"},
        {"timestamp": 2.0, "phase": "post", "tool_name": "Edit", "tool_input": {}, "session_id": "s"},
    ])
    records = load_observations()
    assert len(records) == 2
    assert records[0]["tool_name"] == "Edit"


def test_load_skips_malformed_lines(tmp_data):
    obs_file = get_observations_file(get_project_id())
    obs_file.parent.mkdir(parents=True, exist_ok=True)
    obs_file.write_text(
        json.dumps({"timestamp": 1.0, "tool_name": "Edit"}) + "\n"
        + "not-json{{\n"
        + json.dumps({"timestamp": 2.0, "tool_name": "Bash"}) + "\n",
        encoding="utf-8",
    )
    records = load_observations()
    assert len(records) == 2
    assert {r["tool_name"] for r in records} == {"Edit", "Bash"}


# --- tool_frequency ---


def test_tool_frequency_counts_only_pre_phase():
    # Each tool call appears as a pre + post pair. We count pre only to avoid double-counting.
    records = [
        {"phase": "pre", "tool_name": "Edit"},
        {"phase": "post", "tool_name": "Edit"},
        {"phase": "pre", "tool_name": "Edit"},
        {"phase": "post", "tool_name": "Edit"},
        {"phase": "pre", "tool_name": "Bash"},
        {"phase": "post", "tool_name": "Bash"},
    ]
    freq = tool_frequency(records)
    assert freq == {"Edit": 2, "Bash": 1}


def test_tool_frequency_empty():
    assert tool_frequency([]) == {}


# --- pre_post_sequences ---


def test_pre_post_sequences_counts_pairs_in_window():
    records = [
        {"timestamp": 100.0, "phase": "post", "tool_name": "Grep", "session_id": "s"},
        {"timestamp": 105.0, "phase": "pre", "tool_name": "Edit", "session_id": "s"},
        {"timestamp": 200.0, "phase": "post", "tool_name": "Grep", "session_id": "s"},
        {"timestamp": 250.0, "phase": "pre", "tool_name": "Edit", "session_id": "s"},  # outside 30s window
    ]
    seqs = pre_post_sequences(records, max_gap_seconds=30)
    assert seqs.get(("Grep", "Edit"), 0) == 1


def test_pre_post_sequences_session_isolated():
    records = [
        {"timestamp": 100.0, "phase": "post", "tool_name": "Grep", "session_id": "A"},
        {"timestamp": 105.0, "phase": "pre", "tool_name": "Edit", "session_id": "B"},
    ]
    seqs = pre_post_sequences(records, max_gap_seconds=30)
    assert ("Grep", "Edit") not in seqs


# --- bash_command_prefixes ---


def test_bash_prefixes_extracts_first_two_tokens():
    records = [
        {"phase": "pre", "tool_name": "Bash", "tool_input": {"command": "git status"}},
        {"phase": "pre", "tool_name": "Bash", "tool_input": {"command": "git status --porcelain"}},
        {"phase": "pre", "tool_name": "Bash", "tool_input": {"command": "git log --oneline"}},
        {"phase": "pre", "tool_name": "Bash", "tool_input": {"command": "pytest"}},
    ]
    prefixes = bash_command_prefixes(records, top_n=10)
    prefix_dict = dict(prefixes)
    assert prefix_dict.get("git status") == 2
    assert prefix_dict.get("git log") == 1
    assert prefix_dict.get("pytest") == 1


def test_bash_prefixes_ignores_non_bash_records():
    records = [
        {"phase": "pre", "tool_name": "Edit", "tool_input": {"file_path": "/x"}},
        {"phase": "pre", "tool_name": "Bash", "tool_input": {"command": "ls"}},
    ]
    prefixes = bash_command_prefixes(records, top_n=10)
    assert dict(prefixes) == {"ls": 1}


# --- file_hotspots ---


def test_file_hotspots_counts_edits_per_file():
    records = [
        {"phase": "pre", "tool_name": "Edit", "tool_input": {"file_path": "/a.py"}},
        {"phase": "pre", "tool_name": "Edit", "tool_input": {"file_path": "/a.py"}},
        {"phase": "pre", "tool_name": "Write", "tool_input": {"file_path": "/b.py"}},
        {"phase": "pre", "tool_name": "Bash", "tool_input": {"command": "ls"}},  # not an edit
    ]
    hotspots = file_hotspots(records, top_n=10)
    paths = dict(hotspots)
    assert paths.get("/a.py") == 2
    assert paths.get("/b.py") == 1


def test_file_hotspots_handles_multiedit():
    records = [
        {
            "phase": "pre", "tool_name": "MultiEdit",
            "tool_input": {"edits": [
                {"file_path": "/x.py"},
                {"file_path": "/y.py"},
            ]},
        },
    ]
    hotspots = file_hotspots(records, top_n=10)
    paths = dict(hotspots)
    assert paths.get("/x.py") == 1
    assert paths.get("/y.py") == 1
