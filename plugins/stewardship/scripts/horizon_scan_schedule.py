#!/usr/bin/env python3
"""Cadence tracker for the orchestration horizon-scan, run headless by the nightly steward.

`orchestration:horizon-scanning` is a Claude-reasoning skill — it web-searches SOTA local
models, weighs the 8 GB VRAM ceiling, and runs load tests before editing tiers.json. It
cannot run headless. So the nightly steward does not *execute* it; it tracks cadence and
surfaces a DUE reminder when the monthly interval elapses, leaving the scan to an
interactive `/orchestration:horizon-scanning` session. Completing a scan resets the clock
via `--mark-done` (wired into the skill's closing step). See docs/adr/0010-horizon-scan-cadence-reminder.md.

Usage:
    python horizon_scan_schedule.py [--state PATH] [--interval-days N] [--json] [--now ISO]
    python horizon_scan_schedule.py --mark-done [--state PATH] [--now ISO]

Prints a markdown body line (DUE/OK) by default; --json emits a machine-readable object.
The nightly wrapper prints the `## horizon_scan` section header before invoking this.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_INTERVAL_DAYS = 30


def default_state_path() -> Path:
    return Path.home() / ".claude" / "stewardship" / "horizon-scan-state.json"


def _parse_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_last_scan(state_path: Path) -> datetime | None:
    """Return the recorded last-scan time, or None if absent/unreadable/malformed."""
    try:
        data = json.loads(Path(state_path).read_text(encoding="utf-8"))
        return _parse_iso(data["last_scan"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def mark_done(state_path: Path, now: datetime) -> None:
    p = Path(state_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"last_scan": now.isoformat()}), encoding="utf-8")


@dataclass
class ScanStatus:
    due: bool
    last_scan: str | None
    days_since: int | None
    interval_days: int
    message: str


def evaluate(last_scan: datetime | None, now: datetime, interval_days: int) -> ScanStatus:
    run_hint = "Run /orchestration:horizon-scanning, then `horizon_scan_schedule.py --mark-done`."
    if last_scan is None:
        return ScanStatus(True, None, None, interval_days,
                          f"DUE: no prior horizon-scan recorded. {run_hint}")
    days = (now - last_scan).days
    if days >= interval_days:
        return ScanStatus(True, last_scan.date().isoformat(), days, interval_days,
                          f"DUE: last horizon-scan {last_scan.date()} ({days}d ago, "
                          f"interval {interval_days}d). {run_hint}")
    return ScanStatus(False, last_scan.date().isoformat(), days, interval_days,
                      f"OK: last horizon-scan {last_scan.date()} ({days}d ago); "
                      f"next due in {interval_days - days}d.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="horizon_scan_schedule")
    parser.add_argument("--state", default=str(default_state_path()))
    parser.add_argument("--interval-days", type=int, default=DEFAULT_INTERVAL_DAYS)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--mark-done", action="store_true",
                        help="stamp last_scan = now (run after completing an interactive scan)")
    parser.add_argument("--now", help="ISO8601 override for the current time (testing)")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    now = _parse_iso(args.now) if args.now else datetime.now(timezone.utc)
    state_path = Path(args.state)

    if args.mark_done:
        mark_done(state_path, now)
        print(f"horizon-scan marked done at {now.date()} (state: {state_path})")
        return 0

    status = evaluate(load_last_scan(state_path), now, args.interval_days)
    print(json.dumps(asdict(status), indent=2) if args.json else status.message)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
