#!/usr/bin/env python3
"""Render the stewardship morning briefing by filling templates/morning-briefing.md.

Collects fresh data from the three steward source scripts via their `--json`
interfaces (drift_check, auto_memory_housekeep, horizon_scan_schedule), derives a
status line + rule-based suggested actions, and substitutes the eight `{{TOKEN}}`
placeholders. A source whose subprocess fails (the only realistic failure for
these in-repo, contract-guaranteed scripts) degrades to an `_(… unavailable)_`
section — handled once in build_sections, not threaded through the renderers.
Produced on-demand (`/morning-briefing`) and as the steward's 4th nightly step.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date as date_cls
from datetime import datetime, timezone
from pathlib import Path

_TEMPLATE = Path(__file__).parent.parent / "templates" / "morning-briefing.md"
_DEFAULT_OUT_DIR = Path.home() / ".claude" / "stewardship" / "briefing"
_DEFAULT_HEALTHCHECKS_DIR = Path.home() / ".claude" / "stewardship" / "healthchecks"
_HEALTHCHECK_STALE_DAYS = 8  # weekly probe + 1 day of slack


def _name(p: str) -> str:
    return Path(p).name


def derive_audit_status(drift: dict) -> str:
    checks = drift.get("checks", [])
    fails = [c for c in checks if not c.get("passed")]
    stale = drift.get("stale", [])
    if fails:
        return f"FAILURES DETECTED ({len(fails)} failing, {len(stale)} stale)"
    if stale:
        return f"STALE FILES ({len(stale)} stale)"
    n = len(checks)
    return f"OK ({n}/{n} checks passed, 0 stale)"


def render_drift_section(drift: dict) -> str:
    checks = drift.get("checks", [])
    stale = drift.get("stale", [])
    fails = [c for c in checks if not c.get("passed")]
    if not fails and not stale:
        return f"All {len(checks)} checks passing; no stale files."
    lines: list[str] = []
    if fails:
        lines.append("**Failures:**")
        lines += [f"- `{_name(c['file'])}` — `{c['cmd']}` (exit {c['exit_code']})" for c in fails]
    if stale:
        lines.append("**Stale (past max-age):**")
        lines += [f"- `{_name(s['file'])}` — last verified {s['last_verified']} ({s['age_days']}d ago)"
                  for s in stale]
    lines.append(f"\n{len(checks) - len(fails)}/{len(checks)} checks passing.")
    return "\n".join(lines)


def render_housekeeping_section(house: dict) -> str:
    summ = house.get("summary", {})
    stale = house.get("stale", [])
    broken = house.get("broken_pointers", [])
    if not stale and not broken:
        return f"No stale memory files or broken pointers across {summ.get('memory_dirs', 0)} project(s)."
    lines: list[str] = []
    if stale:
        lines.append(f"**Stale memory files ({len(stale)}):**")
        lines += [f"- `{s['project_key']}/{s['name']}` ({s['age_days']}d)" for s in stale]
    if broken:
        lines.append(f"**Broken MEMORY.md pointers ({len(broken)}):**")
        lines += [f"- `{b['project_key']}` → `{b['target']}`" for b in broken]
    return "\n".join(lines)


def render_horizon_section(horizon: dict) -> str:
    return horizon.get("message", "_(no horizon-scan status)_")


def learning_data_root() -> Path:
    """Resolve the learning plugin's data-root the same way its `storage.py` does.

    Deliberately replicated (not imported) so stewardship stays installable and
    testable without the learning plugin present — the cross-plugin contract is a
    JSON report at a conventional path, not a Python dependency.
    """
    explicit = os.environ.get("LEARNING_DATA_ROOT")
    if explicit:
        return Path(explicit)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "claude-marketplace" / "learning"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "claude-marketplace" / "learning"
    return Path.home() / ".local" / "share" / "claude-marketplace" / "learning"


def read_instinct_report(path=None) -> dict | None:
    """Read the learning nightly report JSON; None if absent/unreadable.

    The report lives at the data-root (project-independent), so the nightly task
    and an interactive `/morning-briefing` resolve the same file.
    """
    p = Path(path) if path else (learning_data_root() / "last_mine_report.json")
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def read_hook_errors(path=None) -> list[dict] | None:
    """Read hook-error records from hooks-errors.jsonl.

    Returns [] when the log is absent (genuinely no errors) and None when it
    exists but can't be read (rendered as 'unavailable' rather than a false
    all-clear). Malformed individual lines are skipped. Bounded at the source
    (run_with_flags keeps a ring buffer), so this reads a small file.
    """
    p = Path(path) if path else (learning_data_root() / "hooks-errors.jsonl")
    if not p.is_file():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    out: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def render_hook_errors_section(errors: list[dict] | None) -> str:
    if errors is None:
        return "_(hook-error log present but unreadable)_"
    if not errors:
        return "No hook errors logged."
    lines = [f"**{len(errors)} hook error(s) logged** (most recent shown):"]
    for rec in errors[-5:]:
        hook = rec.get("hook", "?")
        raw = str(rec.get("error", ""))
        err = raw.splitlines()[0][:160] if raw else ""
        lines.append(f"- `{hook}` — {err}")
    return "\n".join(lines)


def read_healthchecks(dir=None) -> list[dict] | None:
    """Read external health-check records from `<dir>/*.json`.

    Record schema (written by an external producer, e.g. a weekly mail probe):
    `{"name": str, "ok": bool, "summary": str, "checked_at": ISO-8601 UTC str, ...}`.
    Returns [] when the dir is absent (nothing registered) and None when it exists
    but can't be listed. An unreadable/malformed file is skipped-and-flagged: it
    yields a placeholder record (`unreadable: True`) so a broken producer shows up
    in the briefing instead of silently vanishing.
    """
    d = Path(dir) if dir else _DEFAULT_HEALTHCHECKS_DIR
    if not d.is_dir():
        return []
    try:
        files = sorted(d.glob("*.json"))
    except OSError:
        return None
    out: list[dict] = []
    for f in files:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(rec, dict):
                raise ValueError("not an object")
            _parse_checked_at(rec.get("checked_at"))
        except (OSError, ValueError):  # JSONDecodeError/UnicodeDecodeError are ValueErrors
            out.append({"name": f.stem, "unreadable": True})
            continue
        rec.setdefault("name", f.stem)
        out.append(rec)
    return out


def _parse_checked_at(value) -> datetime:
    """Parse an ISO-8601 timestamp to an aware UTC datetime (naive input = UTC)."""
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _healthcheck_state(rec: dict, now: datetime) -> tuple[str, str]:
    """Return (status, age) where status is OK | FAIL | STALE | UNREADABLE.

    FAIL outranks STALE: a failing check is actionable regardless of its age.
    """
    if rec.get("unreadable"):
        return "UNREADABLE", "?"
    days = (now - _parse_checked_at(rec["checked_at"])).days
    age = f"{days}d ago" if days >= 1 else "today"
    if not rec.get("ok"):
        return "FAIL", age
    if days > _HEALTHCHECK_STALE_DAYS:
        return "STALE", age
    return "OK", age


def render_healthchecks_section(records: list[dict] | None, now: datetime | None = None) -> str:
    if records is None:
        return "_(health-check directory present but unreadable)_"
    if not records:
        return "No health checks registered."
    now = now or datetime.now(timezone.utc)
    lines = []
    for rec in records:
        status, age = _healthcheck_state(rec, now)
        if status == "UNREADABLE":
            lines.append(f"- `{rec['name']}` — UNREADABLE (record file malformed)")
        else:
            lines.append(f"- `{rec['name']}` — {status} ({age}) — {rec.get('summary', '')}")
    return "\n".join(lines)


def render_instinct_section(report: dict | None) -> str:
    if not report:
        return "No recent instinct-synthesis run."
    totals = report.get("totals", {})
    written = totals.get("written", 0)
    updated = totals.get("updated", 0)
    projects = report.get("projects", [])
    touched = len([p for p in projects if p.get("written") or p.get("updated")])
    lines = [f"Synthesized **{written} new** + {updated} reinforced instinct(s) "
             f"across {touched} project(s) overnight."]
    samples = [s for p in projects for s in p.get("sample", [])]
    if written and samples:
        lines.append("")
        lines.append("**Sampled instincts:**")
        for s in samples[:8]:
            conf = int(round(s.get("confidence", 0) * 100))
            lines.append(f"- {s.get('title', '?')} ({conf}%)")
    return "\n".join(lines)


def derive_actions(drift: dict, house: dict, horizon: dict, instinct: dict | None = None,
                   healthchecks: list[dict] | None = None, now: datetime | None = None) -> str:
    actions: list[str] = []
    fails = [c for c in drift.get("checks", []) if not c.get("passed")]
    if fails:
        actions.append(f"Re-verify {len(fails)} failing context check(s): "
                       + ", ".join(_name(c["file"]) for c in fails))
    if drift.get("stale"):
        actions.append(f"{len(drift['stale'])} stale context file(s) past max-age — "
                       "re-verify and bump `last_verified`.")
    hs = house.get("summary", {})
    if hs.get("stale_count"):
        actions.append(f"{hs['stale_count']} stale memory file(s) — "
                       "run `auto_memory_housekeep.py --apply` to archive.")
    if hs.get("broken_count"):
        actions.append(f"{hs['broken_count']} broken MEMORY.md pointer(s) — fix or remove.")
    if horizon.get("due"):
        actions.append("Horizon-scan DUE — run `/orchestration:horizon-scanning`, then `--mark-done`.")
    written = (instinct or {}).get("totals", {}).get("written", 0)
    if written:
        actions.append(f"Review {written} new instinct candidate(s) in the Learned Instincts "
                       "section — keep, promote, or let decay.")
    now = now or datetime.now(timezone.utc)
    for rec in healthchecks or []:
        status, age = _healthcheck_state(rec, now)
        if status != "OK":
            actions.append(f"Health check `{rec['name']}` is {status} ({age}) — investigate its producer.")
    if not actions:
        return "No action needed — all checks green."
    return "\n".join(f"- {a}" for a in actions)


def render(template: str, sections: dict, date_str: str) -> str:
    out = template
    for token, value in {
        "{{DATE}}": date_str,
        "{{AUDIT_STATUS}}": sections["audit_status"],
        "{{DRIFT_SECTION}}": sections["drift"],
        "{{HOUSEKEEPING_SECTION}}": sections["housekeeping"],
        "{{HORIZON_SCAN_SECTION}}": sections["horizon"],
        "{{HOOK_ERRORS_SECTION}}": sections["hook_errors"],
        "{{HEALTHCHECKS_SECTION}}": sections["healthchecks"],
        "{{INSTINCT_SECTION}}": sections["instinct"],
        "{{ACTIONS_SECTION}}": sections["actions"],
    }.items():
        out = out.replace(token, value)
    return out


def run_json(scripts_dir, script, *args) -> dict:
    """Run a source script with --json; return its parsed dict, or {"error": …} on
    any subprocess/parse failure (the single error boundary). A source that emits
    JSON then exits non-zero — drift_check on failing checks — parses normally;
    only an empty/garbage stdout becomes an error."""
    cmd = [sys.executable, str(Path(scripts_dir) / script), "--json", *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return json.loads(proc.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as e:
        return {"error": str(e)[:200]}


def collect(scripts_dir, *, context_dir=None, projects_dir=None, state=None,
            max_age_days=None, interval_days=None, instinct_report=None,
            hook_errors_path=None, healthchecks_dir=None) -> dict:
    drift_args = (["--dir", str(context_dir)] if context_dir else []) \
        + (["--max-age-days", str(max_age_days)] if max_age_days is not None else [])
    house_args = ["--projects-dir", str(projects_dir)] if projects_dir else []
    hz_args = (["--state", str(state)] if state else []) \
        + (["--interval-days", str(interval_days)] if interval_days is not None else [])
    return {
        "drift": run_json(scripts_dir, "drift_check.py", *drift_args),
        "housekeeping": run_json(scripts_dir, "auto_memory_housekeep.py", *house_args),
        "horizon": run_json(scripts_dir, "horizon_scan_schedule.py", *hz_args),
        # The learning report is a file read (the learning plugin writes it), not a
        # subprocess like the three steward sources.
        "instinct": read_instinct_report(instinct_report),
        "hook_errors": read_hook_errors(hook_errors_path),
        "healthchecks": read_healthchecks(healthchecks_dir),
    }


def _section(data: dict, renderer, label: str) -> str:
    return f"_({label} unavailable: {data['error']})_" if "error" in data else renderer(data)


def build_sections(data: dict, now: datetime | None = None) -> dict:
    drift = data["drift"]
    now = now or datetime.now(timezone.utc)
    return {
        "audit_status": "UNAVAILABLE" if "error" in drift else derive_audit_status(drift),
        "drift": _section(drift, render_drift_section, "drift check"),
        "housekeeping": _section(data["housekeeping"], render_housekeeping_section, "memory housekeeping"),
        "horizon": _section(data["horizon"], render_horizon_section, "horizon scan"),
        "hook_errors": render_hook_errors_section(data.get("hook_errors", [])),
        "healthchecks": render_healthchecks_section(data.get("healthchecks", []), now),
        "instinct": render_instinct_section(data.get("instinct")),
        "actions": derive_actions(drift, data["housekeeping"], data["horizon"], data.get("instinct"),
                                  data.get("healthchecks"), now),
    }


def main(argv=None) -> int:
    # The briefing contains non-ASCII glyphs (→, em-dash). On a Windows console
    # stdout defaults to cp1252, which can't encode them — force UTF-8 so
    # `--stdout` (and the nightly pipe) never crash. No-op where stdout can't be
    # reconfigured (e.g. pytest's capture buffer).
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):  # pragma: no cover - capture-buffer / non-tty
        pass

    p = argparse.ArgumentParser(prog="render_briefing")
    p.add_argument("--template", default=str(_TEMPLATE))
    p.add_argument("--output", help="output path (default: ~/.claude/stewardship/briefing/<date>.md)")
    p.add_argument("--stdout", action="store_true", help="also print the briefing to stdout")
    p.add_argument("--date", help="YYYY-MM-DD briefing date + default filename (default: today)")
    p.add_argument("--scripts-dir", default=str(Path(__file__).parent))
    p.add_argument("--context-dir")
    p.add_argument("--projects-dir")
    p.add_argument("--state")
    p.add_argument("--max-age-days", type=int)
    p.add_argument("--interval-days", type=int)
    p.add_argument("--instinct-report",
                   help="path to the learning nightly report (default: <learning-data-root>/last_mine_report.json)")
    p.add_argument("--healthchecks-dir",
                   help="dir of external health-check *.json records (default: ~/.claude/stewardship/healthchecks)")
    args = p.parse_args(argv)

    date_str = args.date or date_cls.today().isoformat()
    data = collect(args.scripts_dir, context_dir=args.context_dir, projects_dir=args.projects_dir,
                   state=args.state, max_age_days=args.max_age_days, interval_days=args.interval_days,
                   instinct_report=args.instinct_report,
                   healthchecks_dir=args.healthchecks_dir)
    briefing = render(Path(args.template).read_text(encoding="utf-8"), build_sections(data), date_str)

    out_path = Path(args.output) if args.output else (_DEFAULT_OUT_DIR / f"{date_str}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(briefing, encoding="utf-8")
    print(briefing if args.stdout else f"wrote {out_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
