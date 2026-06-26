import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from detect import (  # noqa: E402
    build_observation_summary,
    cmd_detect,
    ingest_candidates,
    normalize_candidate,
)
from instinct_schema import MAX_CONF_DETECTED, Instinct, parse_instinct  # noqa: E402
from synthesize import get_target_dir  # noqa: E402


@pytest.fixture
def tmp_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LEARNING_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/explicit/proj")
    return tmp_path


# --- normalize (pure) ---


def test_normalize_forces_detected_source_and_caps_confidence():
    raw = Instinct(
        id="prefer-x", trigger="t", confidence=0.99, domain="workflow",
        source="manual", source_repo=None, title="Prefer X", action="a", evidence="e",
    )
    out = normalize_candidate(raw)
    assert out.source == "claude-detected"
    assert out.confidence == MAX_CONF_DETECTED


def test_normalize_leaves_low_confidence_untouched():
    raw = Instinct(
        id="prefer-x", trigger="t", confidence=0.5, domain="workflow",
        source="claude-detected", source_repo=None, title="Prefer X", action="a", evidence="e",
    )
    assert normalize_candidate(raw).confidence == 0.5


# --- observation summary (pure) ---


def test_build_observation_summary_reports_sequences_and_frequency():
    records = [
        {"timestamp": 1.0, "phase": "post", "tool_name": "Grep", "session_id": "s"},
        {"timestamp": 2.0, "phase": "pre", "tool_name": "Edit", "session_id": "s"},
    ]
    summary = build_observation_summary(records)
    assert "tool_frequency" in summary
    assert "top_sequences" in summary
    assert ["Grep", "Edit", 1] in summary["top_sequences"]


# --- ingest (integration) ---

CANDIDATE_YAML = """---
id: prefer-rg-over-grep
trigger: when searching code
confidence: 0.99
domain: tooling
source: manual
---

# Prefer ripgrep

## Action

Use rg instead of grep.

## Evidence

- User corrected grep -> rg twice this session.
"""


def test_ingest_apply_writes_capped_detected_instinct(tmp_data):
    f = tmp_data / "cand.yaml"
    f.write_text(CANDIDATE_YAML, encoding="utf-8")
    counts = ingest_candidates(f.read_text(encoding="utf-8"), get_target_dir("project"), apply=True)
    assert counts["written"] == 1
    out = get_target_dir("project") / "prefer-rg-over-grep.yaml"
    parsed = parse_instinct(out.read_text(encoding="utf-8"))
    assert parsed.source == "claude-detected"
    assert parsed.confidence == MAX_CONF_DETECTED


def test_ingest_dry_run_writes_nothing(tmp_data):
    target = get_target_dir("project")
    counts = ingest_candidates(CANDIDATE_YAML, target, apply=False)
    assert counts["written"] == 1
    assert not target.exists() or list(target.glob("*.yaml")) == []


# --- cmd_detect (integration) ---


def test_cmd_detect_dump_observations_emits_json(tmp_data, capsys):
    # No observations file -> empty-but-valid summary
    rc = cmd_detect(scope="project", dump_observations=True)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "tool_frequency" in payload


def test_cmd_detect_ingest_apply(tmp_data):
    f = tmp_data / "cand.yaml"
    f.write_text(CANDIDATE_YAML, encoding="utf-8")
    rc = cmd_detect(scope="project", ingest_path=str(f), apply=True)
    assert rc == 0
    assert (get_target_dir("project") / "prefer-rg-over-grep.yaml").is_file()


def test_cmd_detect_no_action_returns_error(tmp_data, capsys):
    rc = cmd_detect(scope="project")  # neither dump nor ingest
    assert rc == 1
    assert "--dump-observations" in capsys.readouterr().out


def test_cmd_detect_ingest_dry_run_announces(tmp_data, capsys):
    f = tmp_data / "cand.yaml"
    f.write_text(CANDIDATE_YAML, encoding="utf-8")
    rc = cmd_detect(scope="project", ingest_path=str(f), apply=False)
    assert rc == 0
    assert "dry-run" in capsys.readouterr().out
    assert not (get_target_dir("project") / "prefer-rg-over-grep.yaml").exists()


def test_build_observation_summary_flags_error_outcomes():
    records = [
        {"phase": "post", "tool_name": "Bash", "session_id": "s",
         "tool_response": {"stderr": "fatal: Error: command failed"}},
    ]
    summary = build_observation_summary(records)
    assert summary["error_samples"] == [{"tool_name": "Bash", "session_id": "s"}]
