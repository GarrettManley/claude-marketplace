"""Tests for the headless nightly synthesis runner (Phase 2b automation).

The nightly runner iterates EVERY observed project (it has no cwd/project
context at 03:00), synthesizes deterministic instincts per project, and emits a
single combined report at the data-root — so the stewardship briefing can read
it without resolving a project id.
"""
import json
import time
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
    """Write an observations.jsonl for project `pid` with enough signal to synthesize.

    Timestamps are fresh (observe.py always stamps time.time()), so the records
    survive the post-mine retention compaction — required by the double-apply
    idempotency test.
    """
    now = time.time()
    proj = data_root / "projects" / pid
    proj.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for i in range(pairs):  # immediate Grep(post) -> Edit(pre), distinct sessions
        sid = f"{pid}-s{i}"
        lines.append(json.dumps({"timestamp": now, "phase": "post", "tool_name": "Grep", "session_id": sid}))
        lines.append(json.dumps({"timestamp": now + 1, "phase": "pre", "tool_name": "Edit", "session_id": sid}))
    for _ in range(bash):
        lines.append(json.dumps({"timestamp": now, "phase": "pre", "tool_name": "Bash",
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


# --- retention compaction ---


from synthesize_nightly import (  # noqa: E402
    RETENTION_DAYS_DEFAULT,
    RETENTION_ENV,
    compact_observations,
    retention_days,
)


def _obs_path(data_root: Path, pid: str) -> Path:
    return data_root / "projects" / pid / "observations.jsonl"


def test_retention_days_default_and_override(monkeypatch, capsys):
    monkeypatch.delenv(RETENTION_ENV, raising=False)
    assert retention_days() == RETENTION_DAYS_DEFAULT
    monkeypatch.setenv(RETENTION_ENV, "7")
    assert retention_days() == 7
    # A SET but unparseable value fails safe to 0 (keep everything) with a
    # warning — silently substituting the default would delete data the user
    # explicitly configured retention for.
    monkeypatch.setenv(RETENTION_ENV, "not-a-number")
    assert retention_days() == 0
    assert RETENTION_ENV in capsys.readouterr().err


def test_compact_drops_old_keeps_recent_drops_malformed(tmp_data):
    now = time.time()
    proj = tmp_data / "projects" / "p"
    proj.mkdir(parents=True)
    path = proj / "observations.jsonl"
    lines = [
        json.dumps({"timestamp": now, "phase": "pre", "tool_name": "Edit", "session_id": "s"}),
        json.dumps({"timestamp": now - 90 * 86400, "phase": "pre", "tool_name": "Old", "session_id": "s"}),
        json.dumps({"phase": "pre", "tool_name": "NoTs", "session_id": "s"}),  # invalid ts -> dropped
        "{not json",
        json.dumps(["not", "a", "dict"]),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    counters = compact_observations(path, cutoff_ts=now - 30 * 86400)

    assert counters["kept"] == 1
    assert counters["dropped"] == 2  # too-old + missing-timestamp
    assert counters["malformed"] == 2
    assert counters["bytes_after"] < counters["bytes_before"]
    survivors = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    assert [r["tool_name"] for r in survivors] == ["Edit"]
    # atomic: no tmp leftovers
    assert [p.name for p in proj.iterdir()] == ["observations.jsonl"]


def test_compact_truncates_oversized_tool_response(tmp_data):
    now = time.time()
    proj = tmp_data / "projects" / "p"
    proj.mkdir(parents=True)
    path = proj / "observations.jsonl"
    fat = json.dumps({"timestamp": now, "phase": "post", "tool_name": "Read",
                      "session_id": "s", "tool_response": "x" * 50_000})
    slim = json.dumps({"timestamp": now, "phase": "post", "tool_name": "Bash",
                       "session_id": "s", "tool_response": "ok"})
    path.write_text(fat + "\n" + slim + "\n", encoding="utf-8")

    counters = compact_observations(path, cutoff_ts=0.0, response_max_chars=2000)

    assert counters == {**counters, "kept": 2, "truncated": 1}
    recs = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    assert recs[0]["tool_response"]["truncated"] is True
    assert len(recs[0]["tool_response"]["text"]) == 2000
    assert recs[1]["tool_response"] == "ok"


def test_run_nightly_dry_run_leaves_observations_byte_identical(tmp_data):
    _seed_observations(tmp_data, "proj-aaa")
    before = _obs_path(tmp_data, "proj-aaa").read_bytes()

    run_nightly(apply=False)

    assert _obs_path(tmp_data, "proj-aaa").read_bytes() == before


def test_run_nightly_apply_reports_compaction_counts(tmp_data):
    _seed_observations(tmp_data, "proj-aaa")

    report = run_nightly(apply=True)

    entry = report["projects"][0]
    assert "compaction" in entry
    assert entry["compaction"]["kept"] == 18  # 6 pairs x 2 + 6 bash, all fresh
    assert entry["compaction"]["dropped"] == 0


def test_run_nightly_apply_respects_retention_env(tmp_data, monkeypatch):
    _seed_observations(tmp_data, "proj-aaa")
    # Window of 0 days disables age-dropping entirely.
    monkeypatch.setenv(RETENTION_ENV, "0")
    report = run_nightly(apply=True)
    assert report["projects"][0]["compaction"]["dropped"] == 0


def test_compact_is_idempotent_on_truncation_markers(tmp_data):
    """A second nightly pass must not re-wrap already-truncated markers."""
    now = time.time()
    proj = tmp_data / "projects" / "p"
    proj.mkdir(parents=True)
    path = proj / "observations.jsonl"
    path.write_text(json.dumps({"timestamp": now, "phase": "post", "tool_name": "Read",
                                "session_id": "s", "tool_response": "x" * 50_000}) + "\n",
                    encoding="utf-8")

    compact_observations(path, cutoff_ts=0.0, response_max_chars=2000)
    first = path.read_bytes()
    counters = compact_observations(path, cutoff_ts=0.0, response_max_chars=2000)

    assert path.read_bytes() == first
    assert counters["truncated"] == 0  # marker passed through, not re-counted
    rec = json.loads(first.decode("utf-8"))
    assert set(rec["tool_response"]) == {"truncated", "text"}
    assert not rec["tool_response"]["text"].startswith('{"truncated"')  # no nesting


def test_compact_sweeps_orphaned_tmp_files(tmp_data):
    now = time.time()
    proj = tmp_data / "projects" / "p"
    proj.mkdir(parents=True)
    path = proj / "observations.jsonl"
    path.write_text(json.dumps({"timestamp": now, "phase": "pre", "tool_name": "Edit",
                                "session_id": "s"}) + "\n", encoding="utf-8")
    (proj / "tmpdead123.tmp").write_text("orphan from a hard kill", encoding="utf-8")

    compact_observations(path, cutoff_ts=0.0)

    assert [p.name for p in proj.iterdir()] == ["observations.jsonl"]


def test_run_nightly_survives_per_project_compaction_failure(tmp_data, monkeypatch):
    """A compaction OSError (e.g. Windows PermissionError while a live hook
    holds the log) must not abort remaining projects or suppress the report."""
    import synthesize_nightly as sn

    _seed_observations(tmp_data, "proj-aaa")
    _seed_observations(tmp_data, "proj-bbb")

    def _boom(path, *, cutoff_ts, response_max_chars=2000):
        raise PermissionError("log held by another process")

    monkeypatch.setattr(sn, "compact_observations", _boom)
    rc = cmd_synthesize_nightly(apply=True)

    assert rc == 0
    payload = json.loads(default_report_path(tmp_data).read_text(encoding="utf-8"))
    assert len(payload["projects"]) == 2  # second project still mined
    for entry in payload["projects"]:
        assert "compaction_error" in entry
        assert "held by another process" in entry["compaction_error"]
    assert payload["totals"]["written"] == 4  # mining unaffected
