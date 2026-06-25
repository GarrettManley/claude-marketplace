import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from surface import select, render, collect_instincts, main  # noqa: E402
from instinct_schema import Instinct, format_instinct  # noqa: E402
from storage import (  # noqa: E402
    get_global_instincts_dir,
    get_project_instincts_dir,
    get_project_id,
)


@pytest.fixture
def tmp_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LEARNING_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/explicit/proj")
    return tmp_path


def _inst(iid, conf, *, domain="workflow", trigger="when X", action="Do the thing."):
    return Instinct(
        id=iid, trigger=trigger, confidence=conf, domain=domain,
        source="auto-frequency", source_repo=None,
        title=iid, action=action, evidence="evidence",
    )


# --- select ---


def test_select_filters_below_threshold():
    out = select([_inst("a", 0.4), _inst("b", 0.8)], min_conf=0.6, cap=15)
    assert [i.id for i in out] == ["b"]


def test_select_sorts_by_confidence_desc():
    out = select([_inst("a", 0.7), _inst("b", 0.9), _inst("c", 0.8)], min_conf=0.0, cap=15)
    assert [i.id for i in out] == ["b", "c", "a"]


def test_select_caps_count():
    out = select([_inst(f"i{n}", 0.9) for n in range(30)], min_conf=0.0, cap=15)
    assert len(out) == 15


# --- render ---


def test_render_includes_trigger_and_action():
    txt = render([_inst("a", 0.9, trigger="after Grep", action="Use Edit next.")])
    assert "after Grep" in txt
    assert "Use Edit next." in txt


# --- collect (project + global merge) ---


def test_collect_merges_project_and_global(tmp_data):
    g = get_global_instincts_dir() / "personal"
    g.mkdir(parents=True)
    (g / "g.yaml").write_text(format_instinct(_inst("g", 0.9)))
    p = get_project_instincts_dir(get_project_id()) / "inherited"
    p.mkdir(parents=True)
    (p / "p.yaml").write_text(format_instinct(_inst("p", 0.9)))
    ids = {i.id for i in collect_instincts()}
    assert ids == {"g", "p"}


# --- main gating ---


def test_main_silent_when_surface_off(tmp_data, monkeypatch, capsys):
    monkeypatch.delenv("LEARNING_SURFACE", raising=False)
    g = get_global_instincts_dir() / "personal"
    g.mkdir(parents=True)
    (g / "g.yaml").write_text(format_instinct(_inst("g", 0.9)))
    rc = main([])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_main_emits_block_when_on(tmp_data, monkeypatch, capsys):
    monkeypatch.setenv("LEARNING_SURFACE", "on")
    g = get_global_instincts_dir() / "personal"
    g.mkdir(parents=True)
    (g / "g.yaml").write_text(format_instinct(_inst("g", 0.9, trigger="after Grep")))
    rc = main([])
    assert rc == 0
    assert "after Grep" in capsys.readouterr().out


def test_main_respects_min_confidence_env(tmp_data, monkeypatch, capsys):
    monkeypatch.setenv("LEARNING_SURFACE", "on")
    monkeypatch.setenv("LEARNING_SURFACE_MIN_CONFIDENCE", "0.95")
    g = get_global_instincts_dir() / "personal"
    g.mkdir(parents=True)
    (g / "g.yaml").write_text(format_instinct(_inst("g", 0.9)))  # 0.9 < 0.95
    rc = main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip() == ""  # nothing meets the raised threshold → no block
