import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from instinct_schema import (  # noqa: E402
    MAX_CONF_DETECTED,
    Instinct,
    is_machine_source,
    parse_instinct,
)
from retro_mine import (  # noqa: E402
    cmd_retro_mine,
    build_retro_summary,
    ingest_candidates,
    normalize_candidate,
    parse_retro,
)
from synthesize import get_target_dir  # noqa: E402


@pytest.fixture
def tmp_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LEARNING_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/explicit/proj")
    return tmp_path


CONFORMING_RETRO = """# Retrospective: Sample

**Date:** 2026-06-26

## Outcome

Shipped a thing.

## What worked

- Something good.

## Friction / bugs

- **First problem header**
  - *What happened:* The X broke at runtime.
  - *Root cause:* Y was wrong.
  - *How caught:* The unit tests.
  - *Fix:* Corrected Y.
  - *Rule:* Always check Y before reaching for Z.

- **Second problem header**
  - *Root cause:* Stale local tracking ref.
  - *Rule (generalizable):* Fetch before trusting cache state.

- **Third entry has no rule**
  - *What happened:* A cosmetic glitch.

## Concrete improvements

- Do better next time.
"""

NON_CONFORMING_RETRO = """# Retrospective: Old vintage

## Outcome

An older retro predating the Friction template. Nothing to mine here.

## Concrete improvements

- None.
"""


# --- parse_retro (pure) ---


def test_parse_retro_extracts_all_friction_entries():
    doc = parse_retro(CONFORMING_RETRO, slug="sample")
    assert doc.slug == "sample"
    assert doc.date == "2026-06-26"
    assert len(doc.friction) == 3


def test_parse_retro_pulls_sublabel_fields():
    entry = parse_retro(CONFORMING_RETRO, slug="sample").friction[0]
    assert entry.what_happened == "The X broke at runtime."
    assert entry.root_cause == "Y was wrong."
    assert entry.how_caught == "The unit tests."
    assert entry.rule == "Always check Y before reaching for Z."


def test_parse_retro_handles_rule_label_variant():
    entry = parse_retro(CONFORMING_RETRO, slug="sample").friction[1]
    assert entry.rule == "Fetch before trusting cache state."
    assert entry.root_cause == "Stale local tracking ref."


def test_parse_retro_entry_without_rule_is_none():
    assert parse_retro(CONFORMING_RETRO, slug="sample").friction[2].rule is None


def test_parse_retro_non_conforming_yields_empty_friction():
    doc = parse_retro(NON_CONFORMING_RETRO, slug="old")
    assert doc.friction == []


# --- build_retro_summary (integration over a dir) ---


def _seed_retros(d: Path) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "sample.md").write_text(CONFORMING_RETRO, encoding="utf-8")
    (d / "old.md").write_text(NON_CONFORMING_RETRO, encoding="utf-8")
    return d


def test_build_retro_summary_counts_rules_and_empty(tmp_path):
    retros = _seed_retros(tmp_path / "done")
    summary = build_retro_summary(retros)
    assert summary["total_rules"] == 2  # two rule-bearing entries in sample.md
    assert summary["parsed_empty"] == 1  # old.md has no rule-bearing friction
    slugs = {r["slug"] for r in summary["retros"]}
    assert slugs == {"sample"}  # only rule-bearing retros surface


def test_build_retro_summary_entries_carry_what_happened(tmp_path):
    retros = _seed_retros(tmp_path / "done")
    summary = build_retro_summary(retros)
    entry = summary["retros"][0]["friction"][0]
    assert set(entry) == {"what_happened", "root_cause", "how_caught", "rule"}


# --- normalize_candidate (pure) ---


def test_normalize_forces_retro_source_and_caps_confidence():
    raw = Instinct(
        id="check-the-glob", trigger="t", confidence=0.99, domain="workflow",
        source="manual", source_repo=None, title="Check the glob", action="a", evidence="e",
    )
    out = normalize_candidate(raw)
    assert out.source == "retro-mined"
    assert out.confidence == MAX_CONF_DETECTED


def test_retro_mined_source_is_machine_owned():
    assert is_machine_source("retro-mined") is True


# --- ingest (integration) ---

CANDIDATE_YAML = """---
id: read-the-gate-glob
trigger: before asserting a CI gate covers a new file type
confidence: 0.99
domain: workflow
source: manual
---

# Read the gate's glob before claiming coverage

## Action

Read the gate's actual glob; don't infer coverage from a sibling plan.

## Evidence

- Derived from 2 retro friction entries: review-persona-evolution, briefing-renderer.
"""


def test_ingest_apply_writes_capped_retro_instinct(tmp_data):
    counts = ingest_candidates(CANDIDATE_YAML, get_target_dir("project"), apply=True)
    assert counts["written"] == 1
    out = get_target_dir("project") / "read-the-gate-glob.yaml"
    parsed = parse_instinct(out.read_text(encoding="utf-8"))
    assert parsed.source == "retro-mined"
    assert parsed.confidence == MAX_CONF_DETECTED


def test_ingest_dry_run_writes_nothing(tmp_data):
    target = get_target_dir("project")
    counts = ingest_candidates(CANDIDATE_YAML, target, apply=False)
    assert counts["written"] == 1
    assert not target.exists() or list(target.glob("*.yaml")) == []


# --- cmd_retro_mine (integration) ---


def test_cmd_retro_mine_dump_emits_json(tmp_data, tmp_path, capsys):
    retros = _seed_retros(tmp_path / "done")
    rc = cmd_retro_mine(scope="project", dump_retros=True, retros_dir=str(retros))
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_rules"] == 2


def test_cmd_retro_mine_ingest_apply(tmp_data):
    f = tmp_data / "cand.yaml"
    f.write_text(CANDIDATE_YAML, encoding="utf-8")
    rc = cmd_retro_mine(scope="project", ingest_path=str(f), apply=True)
    assert rc == 0
    assert (get_target_dir("project") / "read-the-gate-glob.yaml").is_file()


def test_cmd_retro_mine_no_action_returns_error(tmp_data, capsys):
    rc = cmd_retro_mine(scope="project")
    assert rc == 1
    assert "--dump-retros" in capsys.readouterr().out
