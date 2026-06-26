import json

import horizon_scan_schedule as hss

NOW = "2026-06-25T03:00:00+00:00"


def _state(tmp_path, last_scan_iso):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"last_scan": last_scan_iso}), encoding="utf-8")
    return p


def test_no_state_is_due(tmp_path, capsys):
    rc = hss.main(["--state", str(tmp_path / "absent.json"), "--now", NOW])
    out = capsys.readouterr().out
    assert rc == 0 and "DUE" in out and "no prior" in out


def test_recent_scan_not_due(tmp_path, capsys):
    p = _state(tmp_path, "2026-06-20T03:00:00+00:00")  # 5 days before NOW
    rc = hss.main(["--state", str(p), "--now", NOW])
    out = capsys.readouterr().out
    assert rc == 0 and out.startswith("OK") and "25d" in out


def test_old_scan_is_due(tmp_path, capsys):
    p = _state(tmp_path, "2026-05-01T03:00:00")  # naive ISO, 55 days
    rc = hss.main(["--state", str(p), "--now", NOW])
    out = capsys.readouterr().out
    assert "DUE" in out and "55d ago" in out


def test_exact_interval_boundary_is_due(tmp_path, capsys):
    p = _state(tmp_path, "2026-05-26T03:00:00+00:00")  # exactly 30 days
    rc = hss.main(["--state", str(p), "--now", NOW, "--interval-days", "30"])
    assert "DUE" in capsys.readouterr().out


def test_interval_override(tmp_path, capsys):
    p = _state(tmp_path, "2026-06-18T03:00:00+00:00")  # 7 days
    hss.main(["--state", str(p), "--now", NOW, "--interval-days", "7"])
    assert "DUE" in capsys.readouterr().out


def test_mark_done_then_not_due(tmp_path, capsys):
    p = tmp_path / "state.json"
    hss.main(["--state", str(p), "--mark-done", "--now", NOW])
    assert json.loads(p.read_text())["last_scan"].startswith("2026-06-25")
    hss.main(["--state", str(p), "--now", NOW])
    assert capsys.readouterr().out.strip().split("\n")[-1].startswith("OK")


def test_mark_done_creates_parent_dir(tmp_path):
    p = tmp_path / "nested" / "dir" / "state.json"
    hss.main(["--state", str(p), "--mark-done", "--now", NOW])
    assert p.exists()


def test_json_output_shape(tmp_path, capsys):
    p = _state(tmp_path, "2026-05-01T03:00:00+00:00")
    hss.main(["--state", str(p), "--now", NOW, "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["due"] is True and data["days_since"] == 55 and data["interval_days"] == 30


def test_malformed_state_treated_as_never_scanned(tmp_path, capsys):
    p = tmp_path / "state.json"
    p.write_text("not json", encoding="utf-8")
    rc = hss.main(["--state", str(p), "--now", NOW])
    assert rc == 0 and "DUE" in capsys.readouterr().out


def test_load_last_scan_missing_key(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"other": 1}), encoding="utf-8")
    assert hss.load_last_scan(p) is None


def test_runs_without_now_override(tmp_path):
    # exercises the real-clock branch (datetime.now); no assertion on due-ness
    assert hss.main(["--state", str(tmp_path / "absent.json")]) == 0
