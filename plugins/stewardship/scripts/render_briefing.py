#!/usr/bin/env python3
"""Render the stewardship morning briefing by filling templates/morning-briefing.md.

Collects fresh data from the three steward source scripts via their `--json`
interfaces (drift_check, auto_memory_housekeep, horizon_scan_schedule), derives a
status line + rule-based suggested actions, and substitutes the six `{{TOKEN}}`
placeholders. A source whose subprocess fails (the only realistic failure for
these in-repo, contract-guaranteed scripts) degrades to an `_(… unavailable)_`
section — handled once in build_sections, not threaded through the renderers.
Produced on-demand (`/morning-briefing`) and as the steward's 4th nightly step.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date as date_cls
from pathlib import Path

_TEMPLATE = Path(__file__).parent.parent / "templates" / "morning-briefing.md"
_DEFAULT_OUT_DIR = Path.home() / ".claude" / "stewardship" / "briefing"


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


def derive_actions(drift: dict, house: dict, horizon: dict) -> str:
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
            max_age_days=None, interval_days=None) -> dict:
    drift_args = (["--dir", str(context_dir)] if context_dir else []) \
        + (["--max-age-days", str(max_age_days)] if max_age_days is not None else [])
    house_args = ["--projects-dir", str(projects_dir)] if projects_dir else []
    hz_args = (["--state", str(state)] if state else []) \
        + (["--interval-days", str(interval_days)] if interval_days is not None else [])
    return {
        "drift": run_json(scripts_dir, "drift_check.py", *drift_args),
        "housekeeping": run_json(scripts_dir, "auto_memory_housekeep.py", *house_args),
        "horizon": run_json(scripts_dir, "horizon_scan_schedule.py", *hz_args),
    }


def _section(data: dict, renderer, label: str) -> str:
    return f"_({label} unavailable: {data['error']})_" if "error" in data else renderer(data)


def build_sections(data: dict) -> dict:
    drift = data["drift"]
    return {
        "audit_status": "UNAVAILABLE" if "error" in drift else derive_audit_status(drift),
        "drift": _section(drift, render_drift_section, "drift check"),
        "housekeeping": _section(data["housekeeping"], render_housekeeping_section, "memory housekeeping"),
        "horizon": _section(data["horizon"], render_horizon_section, "horizon scan"),
        "actions": derive_actions(drift, data["housekeeping"], data["horizon"]),
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
    args = p.parse_args(argv)

    date_str = args.date or date_cls.today().isoformat()
    data = collect(args.scripts_dir, context_dir=args.context_dir, projects_dir=args.projects_dir,
                   state=args.state, max_age_days=args.max_age_days, interval_days=args.interval_days)
    briefing = render(Path(args.template).read_text(encoding="utf-8"), build_sections(data), date_str)

    out_path = Path(args.output) if args.output else (_DEFAULT_OUT_DIR / f"{date_str}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(briefing, encoding="utf-8")
    print(briefing if args.stdout else f"wrote {out_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
