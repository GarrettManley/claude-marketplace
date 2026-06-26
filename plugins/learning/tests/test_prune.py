import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from prune import (  # noqa: E402
    HALF_LIFE_DAYS,
    PRUNE_FLOOR,
    cmd_prune,
    decayed_confidence,
    plan_prune,
)
from instinct_schema import Instinct, format_instinct  # noqa: E402
from storage import get_project_instincts_dir, get_project_id  # noqa: E402

DAY = 86400.0
NOW = 1_750_000_000.0


@pytest.fixture
def tmp_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LEARNING_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/explicit/proj")
    return tmp_path


# --- decay math (pure) ---


def test_decay_fresh_returns_full_confidence():
    assert decayed_confidence(0.8, NOW, NOW, half_life_days=30) == pytest.approx(0.8)


def test_decay_one_half_life_halves():
    older = NOW - 30 * DAY
    assert decayed_confidence(0.8, older, NOW, half_life_days=30) == pytest.approx(0.4)


def test_decay_two_half_lives_quarters():
    older = NOW - 60 * DAY
    assert decayed_confidence(0.8, older, NOW, half_life_days=30) == pytest.approx(0.2)


def test_decay_none_last_reinforced_is_not_decayed():
    # Legacy instincts without a timestamp can't be aged; keep full confidence.
    assert decayed_confidence(0.8, None, NOW, half_life_days=30) == pytest.approx(0.8)


# --- selection (pure) ---


def _inst(iid, source, conf, last):
    return Instinct(
        id=iid, trigger="t", confidence=conf, domain="workflow",
        source=source, source_repo=None, title=iid, action="a", evidence="e",
        last_reinforced=last,
    )


def test_plan_prune_selects_decayed_machine_instinct():
    old = NOW - 120 * DAY  # 4 half-lives → 0.5*0.0625 = 0.03 < 0.2
    loaded = [(Path("x.yaml"), _inst("x", "claude-detected", 0.5, old))]
    prunable = plan_prune(loaded, NOW, floor=PRUNE_FLOOR, half_life_days=HALF_LIFE_DAYS)
    assert [p[0] for p in prunable] == [Path("x.yaml")]


def test_plan_prune_exempts_human_source():
    old = NOW - 365 * DAY
    loaded = [(Path("h.yaml"), _inst("h", "manual", 0.5, old))]
    assert plan_prune(loaded, NOW, floor=PRUNE_FLOOR, half_life_days=HALF_LIFE_DAYS) == []


def test_plan_prune_keeps_fresh_machine_instinct():
    loaded = [(Path("f.yaml"), _inst("f", "auto-frequency", 0.7, NOW))]
    assert plan_prune(loaded, NOW, floor=PRUNE_FLOOR, half_life_days=HALF_LIFE_DAYS) == []


# --- cmd_prune (integration) ---


def _seed(source, conf, last, iid="auto-seq-a-b"):
    target = get_project_instincts_dir(get_project_id()) / "personal"
    target.mkdir(parents=True, exist_ok=True)
    f = target / f"{iid}.yaml"
    f.write_text(format_instinct(_inst(iid, source, conf, last)), encoding="utf-8")
    return f


def test_cmd_prune_dry_run_deletes_nothing(tmp_data):
    f = _seed("claude-detected", 0.5, NOW - 200 * DAY)
    rc = cmd_prune(scope="project", apply=False, now=NOW)
    assert rc == 0
    assert f.is_file()  # dry-run never deletes


def test_cmd_prune_apply_removes_decayed_and_snapshots(tmp_data):
    f = _seed("claude-detected", 0.5, NOW - 200 * DAY)
    rc = cmd_prune(scope="project", apply=True, now=NOW)
    assert rc == 0
    assert not f.is_file()
    # a snapshot backup was taken before deletion
    assert (tmp_data / ".snapshots").is_dir()
    assert any((tmp_data / ".snapshots").iterdir())


def test_cmd_prune_apply_keeps_human_instinct(tmp_data):
    f = _seed("manual", 0.5, NOW - 999 * DAY)
    rc = cmd_prune(scope="project", apply=True, now=NOW)
    assert rc == 0
    assert f.is_file()
