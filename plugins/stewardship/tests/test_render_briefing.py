import pytest

import render_briefing as rb

_DRIFT_OK = {"checks": [{"file": "/c/a.md", "cmd": "true", "passed": True, "exit_code": 0,
                         "stdout": "", "stderr": ""}], "stale": []}
_DRIFT_BAD = {"checks": [{"file": "/c/gpu.md", "cmd": "nvidia-smi", "passed": False, "exit_code": 1,
                          "stdout": "", "stderr": "err"}],
              "stale": [{"file": "/c/old.md", "last_verified": "2026-01-01", "age_days": 175}]}
_HOUSE_EMPTY = {"stale": [], "broken_pointers": [],
                "summary": {"stale_count": 0, "broken_count": 0, "memory_dirs": 2, "threshold_days": 90}}
_HOUSE_FULL = {"stale": [{"path": "/m/x.md", "name": "x.md", "age_days": 120, "project_key": "p"}],
               "broken_pointers": [{"project_key": "p", "target": "y.md", "index_line": "- [y](y.md)"}],
               "summary": {"stale_count": 1, "broken_count": 1, "memory_dirs": 2, "threshold_days": 90}}
_HZ_DUE = {"due": True, "last_scan": "2026-05-01", "days_since": 55, "interval_days": 30,
           "message": "DUE: last horizon-scan 2026-05-01 (55d ago, interval 30d)."}
_HZ_OK = {"due": False, "last_scan": "2026-06-20", "days_since": 5, "interval_days": 30,
          "message": "OK: last horizon-scan 2026-06-20 (5d ago); next due in 25d."}


def test_audit_status_ok():
    assert rb.derive_audit_status(_DRIFT_OK).startswith("OK")


def test_audit_status_failures():
    assert "FAILURES DETECTED" in rb.derive_audit_status(_DRIFT_BAD)


def test_audit_status_stale_only():
    d = {"checks": [{"file": "/c/a.md", "cmd": "true", "passed": True, "exit_code": 0,
                     "stdout": "", "stderr": ""}],
         "stale": [{"file": "/c/o.md", "last_verified": "2026-01-01", "age_days": 175}]}
    assert "STALE FILES" in rb.derive_audit_status(d)


def test_drift_section_lists_failures_and_stale():
    s = rb.render_drift_section(_DRIFT_BAD)
    assert "gpu.md" in s and "old.md" in s


def test_drift_section_all_passing():
    assert "passing" in rb.render_drift_section(_DRIFT_OK).lower()


def test_housekeeping_section_full():
    s = rb.render_housekeeping_section(_HOUSE_FULL)
    assert "x.md" in s and "y.md" in s


def test_housekeeping_section_empty():
    assert "no" in rb.render_housekeeping_section(_HOUSE_EMPTY).lower()


def test_horizon_section_uses_message():
    assert "DUE" in rb.render_horizon_section(_HZ_DUE)


def test_horizon_section_missing_message_fallback():
    assert rb.render_horizon_section({"due": False}).strip() != ""


def test_actions_all_clean():
    assert "No action needed" in rb.derive_actions(_DRIFT_OK, _HOUSE_EMPTY, _HZ_OK)


def test_actions_derives_each_rule():
    a = rb.derive_actions(_DRIFT_BAD, _HOUSE_FULL, _HZ_DUE)
    assert "gpu.md" in a and "--apply" in a and "broken" in a.lower() and "horizon-scan" in a.lower()


def test_render_substitutes_all_tokens():
    template = ("date: {{DATE}}\n# {{DATE}}\n{{AUDIT_STATUS}}\n{{DRIFT_SECTION}}\n"
                "{{HOUSEKEEPING_SECTION}}\n{{HORIZON_SCAN_SECTION}}\n{{HOOK_ERRORS_SECTION}}\n"
                "{{HEALTHCHECKS_SECTION}}\n{{INSTINCT_SECTION}}\n{{ACTIONS_SECTION}}")
    sections = {"audit_status": "OK", "drift": "D", "housekeeping": "H", "horizon": "Z",
                "hook_errors": "HE", "healthchecks": "HC", "instinct": "I", "actions": "A"}
    out = rb.render(template, sections, "2026-06-25")
    assert "{{" not in out and "2026-06-25" in out and "OK" in out


# --- Learned Instincts section (consumes the learning nightly report) ---

_REPORT = {
    "ran_at": 1719300000.0,
    "totals": {"written": 3, "updated": 2, "skipped": 0},
    "projects": [
        {"id": "proj-aaa", "written": 2, "updated": 1, "skipped": 0,
         "sample": [{"id": "auto-bash-git-status", "title": "Frequent command: git status",
                     "confidence": 0.62}]},
        {"id": "proj-bbb", "written": 1, "updated": 1, "skipped": 0,
         "sample": [{"id": "auto-seq-grep-edit", "title": "Edit often follows Grep",
                     "confidence": 0.7}]},
    ],
}


def test_instinct_section_summarizes_report():
    s = rb.render_instinct_section(_REPORT)
    assert "3" in s  # total written
    assert "Frequent command: git status" in s or "Edit often follows Grep" in s


def test_instinct_section_none_is_graceful():
    assert "no recent" in rb.render_instinct_section(None).lower()


def test_actions_includes_instinct_review_when_written():
    a = rb.derive_actions(_DRIFT_OK, _HOUSE_EMPTY, _HZ_OK, _REPORT)
    assert "instinct" in a.lower()


def test_actions_no_instinct_line_when_none():
    assert "No action needed" in rb.derive_actions(_DRIFT_OK, _HOUSE_EMPTY, _HZ_OK, None)


def test_read_instinct_report_missing_returns_none(tmp_path):
    assert rb.read_instinct_report(tmp_path / "nope.json") is None


def test_read_instinct_report_reads_file(tmp_path):
    import json
    p = tmp_path / "last_mine_report.json"
    p.write_text(json.dumps(_REPORT), encoding="utf-8")
    assert rb.read_instinct_report(p)["totals"]["written"] == 3


def test_main_renders_instinct_section_from_report(tmp_path):
    import json
    report = tmp_path / "rep.json"
    report.write_text(json.dumps(_REPORT), encoding="utf-8")
    out = tmp_path / "b.md"
    rc = rb.main(["--context-dir", str(tmp_path / "noctx"), "--projects-dir", str(tmp_path / "noproj"),
                  "--state", str(tmp_path / "s.json"), "--instinct-report", str(report),
                  "--output", str(out), "--date", "2026-06-25"])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "## Learned Instincts" in text
    assert "Frequent command: git status" in text or "Edit often follows Grep" in text


# --- Task 3: collection + main (subprocess) -----------------------------------

from pathlib import Path  # noqa: E402


def test_build_sections_degrades_on_error():
    data = {"drift": {"error": "boom"}, "housekeeping": _HOUSE_EMPTY, "horizon": _HZ_OK}
    s = rb.build_sections(data)
    assert s["audit_status"] == "UNAVAILABLE" and "unavailable" in s["drift"].lower()
    assert "No action needed" in s["actions"]  # derive_actions tolerates the error dict


def test_run_json_handles_bad_script():
    res = rb.run_json(Path(rb.__file__).parent, "does_not_exist.py")
    assert "error" in res


def test_main_writes_briefing(tmp_path):
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    (ctx / "a.md").write_text("---\ntopic: x\nverification_cmd: \"python --version\"\n---\n",
                              encoding="utf-8")
    out = tmp_path / "b.md"
    rc = rb.main(["--context-dir", str(ctx), "--projects-dir", str(tmp_path / "proj"),
                  "--state", str(tmp_path / "hz.json"), "--output", str(out), "--date", "2026-06-25"])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "Morning Briefing — 2026-06-25" in text and "{{" not in text
    assert "## Horizon Scan" in text and "## Suggested Actions" in text


def test_main_stdout(tmp_path, capsys):
    rc = rb.main(["--context-dir", str(tmp_path / "noctx"), "--projects-dir", str(tmp_path / "noproj"),
                  "--state", str(tmp_path / "s.json"), "--output", str(tmp_path / "b.md"),
                  "--stdout", "--date", "2026-06-25"])
    out = capsys.readouterr().out
    assert rc == 0 and "Morning Briefing — 2026-06-25" in out and "{{" not in out


def test_stdout_handles_non_ascii_under_cp1252(tmp_path):
    # Regression: --stdout must not crash printing non-cp1252 chars (the `→` in a
    # broken-pointer line) on a Windows-default console. Run as a subprocess with
    # PYTHONIOENCODING=cp1252 to reproduce the real console encoding.
    import os
    import subprocess
    import sys

    mdir = tmp_path / "p" / "memory"
    mdir.mkdir(parents=True)
    (mdir / "MEMORY.md").write_text("- [gone](missing.md)\n", encoding="utf-8")  # broken pointer -> emits →
    # Isolate the hook-error sink + instinct report explicitly (belt-and-suspenders
    # over the autouse fixture) so this subprocess never reads the developer's real
    # learning data — a polluted real sink would otherwise crash the briefing write.
    env = {**os.environ, "PYTHONIOENCODING": "cp1252",
           "LEARNING_DATA_ROOT": str(tmp_path / "iso-learning")}
    proc = subprocess.run(
        [sys.executable, rb.__file__, "--stdout", "--date", "2026-06-25",
         "--context-dir", str(tmp_path / "noctx"),
         "--projects-dir", str(tmp_path), "--state", str(tmp_path / "s.json")],
        capture_output=True, env=env)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert "→".encode("utf-8") in proc.stdout


# --- Hook Errors section (hb-rap: consumes hooks-errors.jsonl) ---


def test_render_hook_errors_section_empty():
    assert "no hook errors" in rb.render_hook_errors_section([]).lower()


def test_render_hook_errors_section_lists_recent():
    s = rb.render_hook_errors_section([{"ts": 1.0, "hook": "surface.py",
                                        "error": "runtime error: boom"}])
    assert "1 hook error" in s and "surface.py" in s


def test_read_hook_errors_missing_returns_empty(tmp_path):
    assert rb.read_hook_errors(tmp_path / "nope.jsonl") == []


def test_read_hook_errors_reads_and_skips_malformed(tmp_path):
    p = tmp_path / "hooks-errors.jsonl"
    p.write_text('{"hook": "a.py"}\nnot-json\n{"hook": "b.py"}\n', encoding="utf-8")
    assert [r["hook"] for r in rb.read_hook_errors(p)] == ["a.py", "b.py"]


def _load_run_with_flags():
    from importlib.util import spec_from_file_location, module_from_spec
    from pathlib import Path
    rwf_path = (Path(rb.__file__).parent.parent.parent
                / "discipline" / "scripts" / "run_with_flags.py")
    spec = spec_from_file_location("_rwf_probe", rwf_path)
    rwf = module_from_spec(spec)
    spec.loader.exec_module(rwf)
    return rwf


@pytest.mark.parametrize("plat,env", [
    ("win32", {"LOCALAPPDATA": "/win/local"}),
    ("linux", {"XDG_DATA_HOME": "/xdg/data"}),
    ("linux", {}),  # home fallback
])
def test_writer_reader_resolve_same_root(monkeypatch, plat, env):
    # Writer (run_with_flags) and reader (render_briefing) must resolve the SAME
    # data root — the cross-plugin contract hinges on it. Cover the platform
    # branches (not just the explicit-env short-circuit) where drift hides.
    for k in ("LEARNING_DATA_ROOT", "LOCALAPPDATA", "XDG_DATA_HOME"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("sys.platform", plat)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert rb.learning_data_root() == _load_run_with_flags()._learning_data_root()


def test_read_hook_errors_unreadable_returns_none(tmp_path):
    p = tmp_path / "hooks-errors.jsonl"
    p.write_bytes(b"\xff\xfe not valid utf-8 \x80\x81")
    assert rb.read_hook_errors(p) is None


def test_render_hook_errors_section_unreadable():
    assert "unreadable" in rb.render_hook_errors_section(None).lower()


# --- Health checks section (external producers write JSON records) ---

import json as _json  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

_NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def _hc(name="mail-probe", ok=True, days_ago=3, summary="all delivered"):
    return {"name": name, "ok": ok, "summary": summary,
            "checked_at": (_NOW - timedelta(days=days_ago)).isoformat()}


def _write_hc(d, rec, fname="mail-probe.json"):
    (d / fname).write_text(_json.dumps(rec), encoding="utf-8")


def test_read_healthchecks_absent_dir_returns_empty(tmp_path):
    assert rb.read_healthchecks(tmp_path / "nope") == []


def test_read_healthchecks_reads_record(tmp_path):
    _write_hc(tmp_path, _hc())
    assert rb.read_healthchecks(tmp_path)[0]["name"] == "mail-probe"


def test_read_healthchecks_undecodable_file_is_flagged(tmp_path):
    (tmp_path / "broken.json").write_bytes(b"\xff\xfe not json \x80")
    assert rb.read_healthchecks(tmp_path) == [{"name": "broken", "unreadable": True}]


def test_read_healthchecks_malformed_json_is_flagged(tmp_path):
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    assert rb.read_healthchecks(tmp_path)[0]["unreadable"] is True


def test_render_healthchecks_empty():
    assert rb.render_healthchecks_section([], _NOW) == "No health checks registered."


def test_render_healthchecks_ok_record_shows_name_age_summary():
    out = rb.render_healthchecks_section([_hc()], _NOW)
    assert "mail-probe" in out and "OK" in out and "3d ago" in out and "all delivered" in out


def test_render_healthchecks_fail_record():
    assert "FAIL" in rb.render_healthchecks_section([_hc(ok=False)], _NOW)


def test_render_healthchecks_record_older_than_8_days_is_stale():
    assert "STALE" in rb.render_healthchecks_section([_hc(days_ago=9)], _NOW)


def test_render_healthchecks_record_at_8_days_is_not_stale():
    assert "STALE" not in rb.render_healthchecks_section([_hc(days_ago=8)], _NOW)


def test_render_healthchecks_unreadable_record():
    out = rb.render_healthchecks_section([{"name": "broken", "unreadable": True}], _NOW)
    assert "broken" in out and "UNREADABLE" in out


def test_actions_ok_healthcheck_adds_no_action():
    a = rb.derive_actions(_DRIFT_OK, _HOUSE_EMPTY, _HZ_OK, healthchecks=[_hc()], now=_NOW)
    assert "No action needed" in a


def test_actions_fail_healthcheck_adds_action():
    a = rb.derive_actions(_DRIFT_OK, _HOUSE_EMPTY, _HZ_OK, healthchecks=[_hc(ok=False)], now=_NOW)
    assert "mail-probe" in a and "FAIL" in a


def test_actions_stale_healthcheck_adds_action():
    a = rb.derive_actions(_DRIFT_OK, _HOUSE_EMPTY, _HZ_OK, healthchecks=[_hc(days_ago=10)], now=_NOW)
    assert "mail-probe" in a and "STALE" in a


def test_actions_unreadable_healthcheck_adds_action():
    a = rb.derive_actions(_DRIFT_OK, _HOUSE_EMPTY, _HZ_OK,
                          healthchecks=[{"name": "broken", "unreadable": True}], now=_NOW)
    assert "broken" in a and "UNREADABLE" in a


def test_main_renders_healthchecks_from_dir(tmp_path):
    hc = tmp_path / "hc"
    hc.mkdir()
    _write_hc(hc, {**_hc(), "checked_at": datetime.now(timezone.utc).isoformat()})
    out = tmp_path / "b.md"
    rb.main(["--output", str(out), "--healthchecks-dir", str(hc)])
    assert "mail-probe" in out.read_text(encoding="utf-8")
