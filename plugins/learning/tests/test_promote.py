import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from promote import cmd_promote, select_auto_promotions  # noqa: E402
from instinct_schema import Instinct, format_instinct, parse_instinct  # noqa: E402
from storage import (  # noqa: E402
    get_data_root,
    get_global_instincts_dir,
    get_project_id,
    get_project_instincts_dir,
)

DAY = 86400.0
NOW = 1_750_000_000.0


@pytest.fixture
def tmp_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LEARNING_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/explicit/proj")
    return tmp_path


def _inst(iid, source="claude-detected", conf=0.9, last=NOW, repo=None):
    return Instinct(
        id=iid, trigger="t", confidence=conf, domain="workflow",
        source=source, source_repo=repo, title=iid, action="a", evidence="e",
        last_reinforced=last,
    )


def _seed_project_personal(pid: str, inst: Instinct) -> Path:
    d = get_data_root() / "projects" / pid / "instincts" / "personal"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{inst.id}.yaml"
    f.write_text(format_instinct(inst), encoding="utf-8")
    return f


def _global_personal_file(iid: str) -> Path:
    return get_global_instincts_dir() / "personal" / f"{iid}.yaml"


# --- explicit promote (integration) ---


def test_promote_explicit_copies_to_global_and_deletes_project(tmp_data):
    project_personal = get_project_instincts_dir(get_project_id()) / "personal"
    project_personal.mkdir(parents=True, exist_ok=True)
    src = project_personal / "auto-seq-a-b.yaml"
    src.write_text(format_instinct(_inst("auto-seq-a-b", repo="git@example:repo")), encoding="utf-8")

    rc = cmd_promote("auto-seq-a-b", scope="project", apply=True, now=NOW)
    assert rc == 0
    g = _global_personal_file("auto-seq-a-b")
    assert g.is_file()
    promoted = parse_instinct(g.read_text(encoding="utf-8"))
    assert promoted.source == "claude-detected"          # original source preserved
    assert promoted.source_repo == "git@example:repo"     # source_repo preserved
    assert not src.is_file()                              # project copy removed


def test_promote_explicit_dry_run_changes_nothing(tmp_data):
    project_personal = get_project_instincts_dir(get_project_id()) / "personal"
    project_personal.mkdir(parents=True, exist_ok=True)
    src = project_personal / "auto-seq-a-b.yaml"
    src.write_text(format_instinct(_inst("auto-seq-a-b")), encoding="utf-8")

    rc = cmd_promote("auto-seq-a-b", scope="project", apply=False, now=NOW)
    assert rc == 0
    assert src.is_file()
    assert not _global_personal_file("auto-seq-a-b").exists()


def test_promote_explicit_missing_id_returns_error(tmp_data):
    rc = cmd_promote("does-not-exist", scope="project", apply=True, now=NOW)
    assert rc == 1


# --- auto selection (pure) ---


def test_select_auto_requires_two_stores_and_high_confidence():
    by_project = {
        "p1": [_inst("auto-x", conf=0.9, last=NOW)],
        "p2": [_inst("auto-x", conf=0.9, last=NOW)],
        "p3": [_inst("auto-only-once", conf=0.95, last=NOW)],
    }
    chosen = {iid for iid, _best in select_auto_promotions(by_project, NOW)}
    assert chosen == {"auto-x"}  # in 2 stores + high conf; the single-store one is excluded


def test_select_auto_excludes_low_confidence_even_if_widespread():
    by_project = {
        "p1": [_inst("auto-low", conf=0.5, last=NOW)],
        "p2": [_inst("auto-low", conf=0.5, last=NOW)],
    }
    assert select_auto_promotions(by_project, NOW) == []


# --- auto promote (integration) ---


def test_promote_auto_promotes_widespread_and_clears_projects(tmp_data):
    _seed_project_personal("p1", _inst("auto-x", conf=0.9, last=NOW))
    _seed_project_personal("p2", _inst("auto-x", conf=0.9, last=NOW))
    rc = cmd_promote(None, auto=True, apply=True, now=NOW)
    assert rc == 0
    assert _global_personal_file("auto-x").is_file()
    assert not (get_data_root() / "projects" / "p1" / "instincts" / "personal" / "auto-x.yaml").exists()
    assert not (get_data_root() / "projects" / "p2" / "instincts" / "personal" / "auto-x.yaml").exists()
