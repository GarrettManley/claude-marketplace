---
status: active
author: Garrett Manley
created: 2026-06-25
diataxis: reference
---

# 0010. The nightly steward reminds about horizon-scans; it does not run them

## Status

Accepted

## Context

The `orchestration` plugin ships a `horizon-scanning` skill: a periodic (monthly) sweep that
re-evaluates the local-model tier assignments in `configs/tiers.json` against current
benchmarks. Its own frontmatter anticipated being "triggered … via the stewardship plugin's
nightly steward when implemented," and `stewardship-overview/SKILL.md` listed automating it as
a future enhancement that "would call out to the orchestration skill via the Claude Code CLI."

Wiring it in for real runs into three facts that a naïve "run the scan every night" design
ignores:

1. **horizon-scanning is pure Claude reasoning.** It has no backing script. It web-searches the
   HF Open LLM Leaderboard and the MCP Server Gallery, weighs candidates against the 8 GB VRAM
   ceiling, and **runs load tests** (t/s under contention, JSON validity, tool-calling precision)
   before editing `tiers.json`. None of that is a deterministic computation a headless process
   can perform.
2. **The nightly steward is headless.** It is a Windows Task Scheduler / cron / launchd job that
   runs two pure-Python scripts (`drift_check.py`, `auto_memory_housekeep.py`) with no model in
   the loop and no interactive session.
3. **Cadence mismatch.** horizon-scanning is monthly; the steward is nightly.

A headless `claude -p` path that actually executes the scan would depend on network, an API key,
and spinning up `llama-server` for load tests unattended — and would fail silently when any of
those is absent, the documented failure mode of headless cloud routines on this setup.

## Decision

The steward **schedules and reminds; it does not execute** the scan.

- A new deterministic step, `scripts/horizon_scan_schedule.py`, runs third in the nightly
  sequence (after drift-check and housekeep) on all three platforms. It reads a `last_scan`
  timestamp from `~/.claude/stewardship/horizon-scan-state.json` and, when
  `now - last_scan >= --interval-days` (default 30), prints a `DUE` reminder to `nightly.log`
  under a `## horizon_scan` section. A missing or unreadable state file is treated as
  never-scanned → DUE.
- The human runs `/orchestration:horizon-scanning` **interactively** when reminded. That skill's
  closing step calls `horizon_scan_schedule.py --mark-done`, which stamps `last_scan = now` and
  clears the reminder — closing the loop so the notice does not fire forever.
- D4 adds a `{{HORIZON_SCAN_SECTION}}` token to `templates/morning-briefing.md`; filling it from
  the `## horizon_scan` log section is the morning-briefing renderer's job (D5). This is the
  D4/D5 boundary.

## Consequences

**Positive**

- The capability ships honestly: the deterministic, headless-safe part (cadence tracking) is
  automated and tested; the judgment-and-load-test part stays where it can actually run.
- No silent-failure surface — there is no unattended network/model/load-test dependency.
- The `--mark-done` reset, wired into the scan skill itself, keeps the reminder truthful.

**Negative / mitigations**

- The scan is not fully hands-off; a human must act on the reminder. Mitigation: that is
  inherent to a sweep that requires benchmark judgment and load testing — automating the
  *trigger* is the available, safe win, and the briefing surfaces it where it will be seen.
- A new state file under `~/.claude/stewardship/`. Mitigation: it is a single small JSON object,
  self-healing (absent → DUE), and owned solely by this script.

Cross-references: the `orchestration:horizon-scanning` skill (the interactive scan + its
`--mark-done` closing step); ADR-0008 (root CHANGELOG — the program-level entry is curated there).
