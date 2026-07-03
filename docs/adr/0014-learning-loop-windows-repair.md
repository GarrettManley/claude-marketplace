---
status: active
author: Garrett Manley
created: 2026-07-03
diataxis: reference
---

# 0014. Learning-loop Windows repair: UTF-8 at entry points, marketplace-checkout scheduler paths, dual-bound observation retention

## Status

Accepted

## Context

A full review of the learning plugin (#51) found Phase 1 (observation capture)
live but every downstream stage silently broken on Windows:

- `surface.py` (SessionStart injection) and `instinct_cli.py status` crashed on
  cp1252 stdout (`→`, `█░`); the fail-open `run_with_flags` wrapper exited 0,
  so instinct surfacing had **never** worked on the machine.
- The stewardship nightly wrapper baked a dev-clone path that moved on
  2026-06-30 and the bare interpreter name `python3`; every nightly step failed
  (eventually with no output at all), and the task had been registered without
  `-LearningScript`, so headless instinct mining (`synthesize_nightly.py`, the
  1.5.0 headline) never executed.
- `observations.jsonl` grew unbounded: 106 MB / 35K records in 8 days, ~90%
  verbatim `tool_response` blobs.

Three decisions were made; each had credible alternatives worth recording.

## Decision 1 — force UTF-8 per printing entry point, not in the vendored wrapper

`force_utf8()` lives in learning's `env_flags.py` and is called first in
`surface.main`, `instinct_cli.main`, and `synthesize_nightly.main`; stewardship's
`auto_memory_housekeep.py` got the same inline idiom.

**Rejected: fixing canonical `run_with_flags.py` (discipline) and re-syncing the
vendored copies.** Two reasons: `instinct_cli.py` is invoked directly by slash
commands — a wrapper-level fix cannot reach it — and the vendored-sync discipline
(ADR 0002) means one wrapper change forces coordinated releases of three plugins
for zero additional currently-broken cases (a repo-wide scan found non-ASCII
stdout only in learning + stewardship, and the other emitters already reconfigure:
`retro_brief.py`, `render_briefing.py`). Wrapper-level defense-in-depth remains a
sensible follow-up, tracked outside this delivery.

## Decision 2 — scheduled-task wrappers bake marketplace-checkout paths only

`register_nightly.ps1` now bakes the resolved absolute interpreter path
(`(Get-Command).Source`) and warns when run from outside
`~/.claude/plugins/marketplaces/`. Documentation directs registration (and the
`-LearningScript` argument) at the marketplace checkout.

**Rejected: dev clone** — it moves (that is exactly what broke: relocation to
`Workspace/` on 2026-06-30 killed every step for three nights, invisibly).
**Rejected: versioned install cache** (`plugins/cache/<mp>/<plugin>/<version>/`) —
the actual hook load location, but its path changes on every release, so baked
paths rot on the next version bump. The marketplace checkout is the only location
that is both updated in place and permanently addressed.

## Decision 3 — observation retention is dual-bound: capture-time cap + post-mine compaction

`observe.py` truncates `tool_response` over 2000 serialized chars at capture
time; `synthesize_nightly.py --apply` rewrites each project's log atomically
after a successful mine, dropping records older than
`LEARNING_OBS_RETENTION_DAYS` (default 30, `<=0` disables) and truncating
oversized survivors, reporting counters via `last_mine_report.json`.

The bounds are deliberately redundant: the cap stops ~90% of new growth at the
source but cannot shrink history; compaction shrinks history (including the
pre-existing 106 MB file, on first apply) but runs only nightly. Analytically
safe: analysis uses 30 s pre/post pairing plus frequency counts whose confidence
saturates (`n/(n+5)`, capped at 0.70/0.85), and `detect`'s error scan greps the
leading bytes of `tool_response`, which truncation preserves.

**Rejected: size-triggered rotation in `observe.py`** — the observe hook runs on
every tool call; adding stat/rewrite logic to the hottest path buys latency and
lock-contention risk for no signal. **Rejected: standalone rotate script in the
nightly wrapper** — a third moving part with its own failure modes, when the
nightly miner already reads and owns the file.

## Consequences

- SessionStart surfacing and `/instinct-status` work on Windows; the cp1252
  regression is pinned by tests that wrap stdout in a real cp1252
  `TextIOWrapper` (fails on any OS pre-fix).
- The nightly loop is closed end-to-end once the task is re-registered from the
  marketplace checkout with `-LearningScript` (machine-local runbook, not repo
  state).
- Observation stores stabilize at roughly one month of capped records
  (~10 MB/project at current rates) instead of growing ~14 MB/day.
- A silent-hook-failure class remains: `run_with_flags` reports runtime errors
  to stderr and exits 0 by design. Observability follow-up tracked separately.
