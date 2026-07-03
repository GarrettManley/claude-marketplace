"""Headless nightly automation for Phase 2b deterministic synthesis.

`/instinct-synthesize --write` already mines observations into instincts with no
LLM and no live session — but only for the *current* project, and only when a
human remembers to run it. This runner closes that gap: invoked by the
stewardship nightly steward at 03:00, it has no cwd/project context, so it
iterates EVERY observed project explicitly, synthesizes each, and writes a
single combined report at the data-root for the morning briefing to read.

Why a data-root-level report (not per-project): the nightly task and an
interactive `/morning-briefing` resolve different project ids, so a per-project
report path would diverge between producer and consumer. The data-root path
(`{LEARNING_DATA_ROOT}/last_mine_report.json`) is project-independent and
resolved identically by both sides.

No new mining logic lives here — it reuses `synthesize.synthesize` and
`synthesize.write_instincts` verbatim (already idempotent, atomic, reinforcing
via stable ids).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from analyze import load_observations  # noqa: E402
from env_flags import force_utf8  # noqa: E402
from observe import RESPONSE_MAX_CHARS, cap_tool_response  # noqa: E402
from storage import get_data_root, get_project_instincts_dir  # noqa: E402
from synthesize import (  # noqa: E402
    MIN_CONSISTENCY,
    MIN_SUPPORT,
    synthesize,
    write_instincts,
)

REPORT_NAME = "last_mine_report.json"
_SAMPLE_LIMIT = 5

# Observation retention. Analysis only uses 30 s pre/post pairing plus
# frequency counts whose confidence saturates (n/(n+5), capped) long before a
# month of support, so records older than the window add bytes, not signal.
RETENTION_DAYS_DEFAULT = 30
RETENTION_ENV = "LEARNING_OBS_RETENTION_DAYS"


def retention_days() -> int:
    """Retention window in days; <=0 disables age-based dropping (size
    truncation of oversized tool_response blobs still applies).

    An unset var means the default; a SET but unparseable var fails safe to 0
    (keep everything) with a stderr warning — silently substituting 30 would
    delete data the user explicitly tried to configure retention for.
    """
    raw = os.environ.get(RETENTION_ENV)
    if raw is None or raw == "":
        return RETENTION_DAYS_DEFAULT
    try:
        return int(raw)
    except ValueError:
        print(
            f"[synthesize-nightly] {RETENTION_ENV}={raw!r} is not an integer; "
            "age-based dropping disabled for this run",
            file=sys.stderr,
        )
        return 0


def compact_observations(
    path: Path,
    *,
    cutoff_ts: float,
    response_max_chars: int = RESPONSE_MAX_CHARS,
) -> dict:
    """Rewrite observations.jsonl in place: drop records older than cutoff_ts
    (or with a missing/invalid timestamp), truncate oversized tool_response
    payloads in survivors, drop malformed lines. Atomic (tmp + os.replace) so a
    crash mid-rewrite can't lose the log. Returns compaction counters.
    """
    # Sweep tmp files orphaned by a hard kill (power loss) mid-rewrite on a
    # previous run — nothing else in the project dir uses the .tmp suffix.
    for stale in path.parent.glob("*.tmp"):
        try:
            stale.unlink()
        except OSError:
            pass
    bytes_before = path.stat().st_size
    counters = {"kept": 0, "dropped": 0, "malformed": 0, "truncated": 0}
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out, \
                open(path, encoding="utf-8") as src:
            for line in src:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    counters["malformed"] += 1
                    continue
                if not isinstance(rec, dict):
                    counters["malformed"] += 1
                    continue
                ts = rec.get("timestamp")
                if not isinstance(ts, (int, float)) or ts < cutoff_ts:
                    counters["dropped"] += 1
                    continue
                resp = rec.get("tool_response")
                if resp is not None:
                    capped = cap_tool_response(resp, response_max_chars)
                    if capped is not resp:
                        rec["tool_response"] = capped
                        counters["truncated"] += 1
                out.write(json.dumps(rec) + "\n")
                counters["kept"] += 1
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    counters["bytes_before"] = bytes_before
    counters["bytes_after"] = path.stat().st_size
    return counters


def iter_project_dirs(data_root: Path) -> list[Path]:
    """Project dirs under `data_root/projects/*` with a non-empty observations log.

    Empty / observation-less projects are skipped: there is nothing to mine, and
    `synthesize` would return no candidates anyway.
    """
    projects = data_root / "projects"
    if not projects.is_dir():
        return []
    out: list[Path] = []
    for child in sorted(projects.iterdir()):
        if not child.is_dir():
            continue
        obs = child / "observations.jsonl"
        if obs.is_file() and obs.stat().st_size > 0:
            out.append(child)
    return out


def default_report_path(data_root: Path) -> Path:
    return data_root / REPORT_NAME


def run_nightly(
    *,
    apply: bool,
    min_support: int = MIN_SUPPORT,
    min_consistency: float = MIN_CONSISTENCY,
) -> dict:
    """Synthesize every observed project, returning the combined report payload.

    Each project's instincts are written to its own `instincts/personal/` dir
    (reinforced in place via stable ids); counts are accumulated across projects.
    """
    data_root = get_data_root()
    totals = {"written": 0, "updated": 0, "skipped": 0}
    projects: list[dict] = []
    days = retention_days()
    cutoff_ts = (time.time() - days * 86400) if days > 0 else 0.0
    for proj_dir in iter_project_dirs(data_root):
        pid = proj_dir.name
        records = load_observations(pid)
        candidates = synthesize(
            records, min_support=min_support, min_consistency=min_consistency
        )
        target = get_project_instincts_dir(pid) / "personal"
        counts = write_instincts(candidates, target, dry_run=not apply)
        for key in totals:
            totals[key] += counts[key]
        entry = {
            "id": pid,
            "written": counts["written"],
            "updated": counts["updated"],
            "skipped": counts["skipped"],
            "sample": [
                {"id": c.id, "title": c.title, "confidence": c.confidence}
                for c in candidates[:_SAMPLE_LIMIT]
            ],
        }
        if apply:
            # Compact only after the mine succeeded, and never on dry-run —
            # a preview must leave the log byte-identical. A per-project
            # compaction failure (e.g. Windows PermissionError from os.replace
            # while a live session's observe hook holds the log) must not
            # abort the remaining projects or the report.
            try:
                entry["compaction"] = compact_observations(
                    proj_dir / "observations.jsonl", cutoff_ts=cutoff_ts
                )
            except OSError as e:
                entry["compaction_error"] = str(e)
        projects.append(entry)
    return {"totals": totals, "projects": projects}


def write_report(path: Path, payload: dict) -> None:
    """Write the report JSON atomically (temp file + os.replace).

    A crash mid-write must not leave the briefing reading a partial/stale report.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def cmd_synthesize_nightly(
    *,
    apply: bool = False,
    report_path: str | None = None,
    min_support: int = MIN_SUPPORT,
    min_consistency: float = MIN_CONSISTENCY,
) -> int:
    """Run nightly synthesis across all projects; emit the report only on --apply.

    Dry-run previews counts to stdout without touching the instinct store or the
    report file (so a manual preview never clobbers the last real run's report).
    """
    data_root = get_data_root()
    report = run_nightly(
        apply=apply, min_support=min_support, min_consistency=min_consistency
    )
    totals = report["totals"]
    n_projects = len(report["projects"])
    if apply:
        report["ran_at"] = time.time()
        rp = Path(report_path) if report_path else default_report_path(data_root)
        write_report(rp, report)
        print(f"[synthesize-nightly] {n_projects} project(s): "
              f"{totals['written']} written, {totals['updated']} updated, "
              f"{totals['skipped']} skipped -> {rp}")
    else:
        print(f"[synthesize-nightly] dry-run: {n_projects} project(s), "
              f"{totals['written']} new, {totals['updated']} would update, "
              f"{totals['skipped']} preserved. Re-run with --apply to persist.")
    return 0


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    parser = argparse.ArgumentParser(
        prog="synthesize_nightly",
        description="Headless nightly Phase 2b synthesis across all observed projects.",
    )
    parser.add_argument("--apply", action="store_true",
                        help="persist instincts + write the report (default: dry-run)")
    parser.add_argument("--report-path", metavar="FILE",
                        help="override the report path (default: <data-root>/last_mine_report.json)")
    parser.add_argument("--min-support", type=int, default=MIN_SUPPORT)
    parser.add_argument("--min-consistency", type=float, default=MIN_CONSISTENCY)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return cmd_synthesize_nightly(
        apply=args.apply,
        report_path=args.report_path,
        min_support=args.min_support,
        min_consistency=args.min_consistency,
    )


if __name__ == "__main__":
    sys.exit(main())
