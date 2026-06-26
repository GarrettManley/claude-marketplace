"""Tests for the headless nightly synthesis runner (Phase 2b automation).

The nightly runner iterates EVERY observed project (it has no cwd/project
context at 03:00), synthesizes deterministic instincts per project, and emits a
single combined report at the data-root — so the stewardship briefing can read
it without resolving a project id.
"""
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from synthesize_nightly import (  # noqa: E402
    iter_project_dirs,
    run_nightly,
    cmd_synthesize_nightly,
    write_report,
    default_report_path,
)
from instinct_schema import parse_instinct  # noqa: E402
from storage import get_project_instincts_dir  # noqa: E402


@pytest.fixture
def tmp_data(monkeypatch, tmp_path):
    """Point the whole storage layer at a throwaway data-root — never the real store."""
    monkeypatch.setenv("LEARNING_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    return tmp_path


def _seed_observations(data_root: Path, pid: str, *, pairs: int = 6, bash: int = 6) -> None:
    """Write an observations.jsonl for project `pid` with enough signal to synthesize."""
    proj = data_root / "projects" / pid
    proj.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for i in range(pairs):  # immediate Grep(post) -> Edit(pre), distinct sessions
        sid = f"{pid}-s{i}"
        lines.append(json.dumps({"timestamp": 1.0, "phase": "post", "tool_name": "Grep", "session_id": sid}))
        lines.append(json.dumps({"timestamp": 2.0, "phase": "pre", "tool_name": "Edit", "session_id": sid}))
    for _ in range(bash):
        lines.append(json.dumps({"phase": "pre", "tool_name": "Bash",
                                 "tool_input": {"command": "git status"}, "session_id": f"{pid}-b"}))
    (proj / "observations.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- iter_project_dirs ---


def test_iter_includes_only_dirs_with_nonempty_observations(tmp_data):
    _seed_observations(tmp_data, "proj-aaa")
    # a project dir with no observations file
    (tmp_data / "projects" / "proj-empty").mkdir(parents=True)
    # a project dir with an empty observations file
    barren = tmp_data / "projects" / "proj-barren"
    barren.mkdir(parents=True)
    (barren / "observations.jsonl").write_text("", encoding="utf-8")

    dirs = iter_project_dirs(tmp_data)

    assert [d.name for d in dirs] == ["proj-aaa"]


def test_iter_no_projects_dir_returns_empty(tmp_data):
    assert iter_project_dirs(tmp_data) == []


# --- run_nightly ---


def test_run_nightly_writes_instincts_per_project(tmp_data):
    _seed_observations(tmp_data, "proj-aaa")
    _seed_observations(tmp_data, "proj-bbb")

    report = run_nightly(apply=True)

    for pid in ("proj-aaa", "proj-bbb"):
        personal = get_project_instincts_dir(pid) / "personal"
        ids = {p.stem for p in personal.glob("*.yaml")}
        assert "auto-seq-grep-edit" in ids
        assert "auto-bash-git-status" in ids
    assert report["totals"]["written"] == 4  # 2 instincts x 2 projects


def test_run_nightly_dry_run_writes_no_files(tmp_data):
    _seed_observations(tmp_data, "proj-aaa")

    report = run_nightly(apply=False)

    personal = get_project_instincts_dir("proj-aaa") / "personal"
    assert not personal.exists() or list(personal.glob("*.yaml")) == []
    assert report["totals"]["written"] == 2  # counted, not written


def test_run_nightly_report_shape(tmp_data):
    _seed_observations(tmp_data, "proj-aaa")

    report = run_nightly(apply=True)

    assert set(report["totals"]) == {"written", "updated", "skipped"}
    assert len(report["projects"]) == 1
    entry = report["projects"][0]
    assert entry["id"] == "proj-aaa"
    assert entry["written"] == 2
    assert entry["sample"]  # at least one candidate summarized
    sample = entry["sample"][0]
    assert set(sample) == {"id", "title", "confidence"}


def test_run_nightly_is_idempotent(tmp_data):
    _seed_observations(tmp_data, "proj-aaa")
    run_nightly(apply=True)
    report = run_nightly(apply=True)

    personal = get_project_instincts_dir("proj-aaa") / "personal"
    assert report["totals"]["updated"] == 2
    assert report["totals"]["written"] == 0
    assert len(list(personal.glob("*.yaml"))) == 2  # no accumulation


# --- write_report (atomic) ---


def test_write_report_is_atomic_no_temp_leftover(tmp_data):
    path = tmp_data / "last_mine_report.json"
    write_report(path, {"totals": {"written": 1, "updated": 0, "skipped": 0}, "projects": []})
    assert path.is_file()
    leftovers = [p.name for p in tmp_data.iterdir() if p.is_file() and not p.name.endswith(".json")]
    assert leftovers == []
    assert json.loads(path.read_text(encoding="utf-8"))["totals"]["written"] == 1


# --- cmd_synthesize_nightly (report emission gated on apply) ---


def test_cmd_apply_writes_report_at_data_root(tmp_data):
    _seed_observations(tmp_data, "proj-aaa")

    rc = cmd_synthesize_nightly(apply=True)

    assert rc == 0
    report_file = default_report_path(tmp_data)
    assert report_file == tmp_data / "last_mine_report.json"
    payload = json.loads(report_file.read_text(encoding="utf-8"))
    assert payload["totals"]["written"] == 2
    assert "ran_at" in payload


def test_cmd_dry_run_does_not_write_report(tmp_data):
    _seed_observations(tmp_data, "proj-aaa")

    rc = cmd_synthesize_nightly(apply=False)

    assert rc == 0
    assert not default_report_path(tmp_data).exists()
