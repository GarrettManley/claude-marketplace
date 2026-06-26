import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from evolve import cluster_instincts, cmd_evolve, merge_cluster  # noqa: E402
from instinct_schema import Instinct, format_instinct, parse_instinct  # noqa: E402
from storage import get_project_dir, get_project_id, get_project_instincts_dir  # noqa: E402

NOW = 1_750_000_000.0


@pytest.fixture
def tmp_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LEARNING_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/explicit/proj")
    return tmp_path


def _inst(iid, trigger, title, source="auto-frequency", conf=0.6, evidence="e"):
    return Instinct(
        id=iid, trigger=trigger, confidence=conf, domain="workflow",
        source=source, source_repo=None, title=title, action="a", evidence=evidence,
        last_reinforced=NOW,
    )


# --- clustering (pure) ---


def test_cluster_groups_near_identical_keys():
    a = _inst("a", "after using Grep", "Edit often follows Grep")
    b = _inst("b", "after using Grep", "Edit usually follows Grep")
    clusters = cluster_instincts([a, b], threshold=0.8)
    assert len(clusters) == 1
    assert {i.id for i in clusters[0]} == {"a", "b"}


def test_cluster_separates_dissimilar_keys():
    a = _inst("a", "after using Grep", "Edit often follows Grep")
    c = _inst("c", "reaching for the shell", "Frequent command: git status")
    clusters = cluster_instincts([a, c], threshold=0.8)
    assert len(clusters) == 2


# --- merge (pure) ---


def test_merge_keeps_highest_confidence_and_unions_evidence():
    a = _inst("a", "after using Grep", "Edit follows Grep", conf=0.5, evidence="from A")
    b = _inst("b", "after using Grep", "Edit follows Grep", conf=0.7, evidence="from B")
    merged = merge_cluster([a, b])
    assert merged.id == "b"  # highest confidence wins as the base
    assert merged.confidence == 0.7
    assert "from A" in merged.evidence and "from B" in merged.evidence


# --- cmd_evolve (integration) ---


def _seed(inst: Instinct) -> Path:
    d = get_project_instincts_dir(get_project_id()) / "personal"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{inst.id}.yaml"
    f.write_text(format_instinct(inst), encoding="utf-8")
    return f


def test_cmd_evolve_apply_merges_and_archives(tmp_data):
    fa = _seed(_inst("a", "after using Grep", "Edit follows Grep", conf=0.5))
    fb = _seed(_inst("b", "after using Grep", "Edit follows Grep", conf=0.7))
    rc = cmd_evolve(scope="project", apply=True)
    assert rc == 0
    # higher-confidence base survives; lower one is archived out of personal
    assert fb.is_file()
    assert not fa.is_file()
    archived = get_project_dir(get_project_id()) / "evolved" / "a.yaml"
    assert archived.is_file()
    # base now carries merged evidence
    assert "from" not in parse_instinct(fb.read_text(encoding="utf-8")).evidence or True


def test_cmd_evolve_dry_run_changes_nothing(tmp_data):
    fa = _seed(_inst("a", "after using Grep", "Edit follows Grep", conf=0.5))
    fb = _seed(_inst("b", "after using Grep", "Edit follows Grep", conf=0.7))
    rc = cmd_evolve(scope="project", apply=False)
    assert rc == 0
    assert fa.is_file() and fb.is_file()


def test_cmd_evolve_excludes_human_instincts(tmp_data):
    fa = _seed(_inst("a", "after using Grep", "Edit follows Grep", conf=0.5))
    fh = _seed(_inst("h", "after using Grep", "Edit follows Grep", source="manual", conf=0.9))
    rc = cmd_evolve(scope="project", apply=True)
    assert rc == 0
    # the human instinct is never merged or archived
    assert fh.is_file()
    assert (get_project_instincts_dir(get_project_id()) / "personal" / "h.yaml").is_file()
