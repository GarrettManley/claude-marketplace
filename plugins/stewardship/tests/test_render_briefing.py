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
                "{{HOUSEKEEPING_SECTION}}\n{{HORIZON_SCAN_SECTION}}\n{{ACTIONS_SECTION}}")
    sections = {"audit_status": "OK", "drift": "D", "housekeeping": "H", "horizon": "Z", "actions": "A"}
    out = rb.render(template, sections, "2026-06-25")
    assert "{{" not in out and "2026-06-25" in out and "OK" in out


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
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    proc = subprocess.run(
        [sys.executable, rb.__file__, "--stdout", "--date", "2026-06-25",
         "--context-dir", str(tmp_path / "noctx"),
         "--projects-dir", str(tmp_path), "--state", str(tmp_path / "s.json")],
        capture_output=True, env=env)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert "→".encode("utf-8") in proc.stdout
