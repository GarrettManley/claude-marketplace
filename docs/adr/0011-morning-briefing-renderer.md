---
status: active
author: Garrett Manley
created: 2026-06-25
diataxis: reference
---

# 0011. The morning-briefing renderer composes the steward scripts via a `--json` contract

## Status

Accepted

## Context

The stewardship `templates/morning-briefing.md` shipped as a `{{TOKEN}}` skeleton with the note
"wire your own renderer to fill this template." Three nightly steward scripts already produce the
data a briefing needs: `drift_check.py` (context-file verification), `auto_memory_housekeep.py`
(stale memory + broken pointers), and `horizon_scan_schedule.py` (scan cadence). D5 builds the
renderer that turns the skeleton into a filled daily briefing.

The renderer could obtain its data two ways: **import** the sibling modules' pure functions, or
**subprocess** each script with a `--json` flag. The import path is lighter (no process spawn, no
JSON round-trip). The subprocess path treats each script's CLI as the contract.

## Decision

`render_briefing.py` collects data by **subprocess-invoking each source script with `--json`**,
then substitutes the six template tokens.

- **Why subprocess over import.** Each source script is the single source of truth for *its own*
  structured output; the renderer stays a thin composer decoupled from each script's internals. A
  script can change how it computes `stale`/`checks`/`due` without the renderer knowing, as long as
  its `--json` shape holds. The same `--json` interface also serves any other consumer (a future
  dashboard, a CI summary) without importing Python. This is the deliberate trade for a small
  per-run subprocess cost. `auto_memory_housekeep.py` gained a `--json` flag for parity (the other
  two already had one); `--json` is report-only there (never archives).
- **Fresh re-collect, not log-parsing.** Data is collected at render time by running the scripts,
  not by parsing the 03:00 `nightly.log` (which holds free-text markdown). Structured `--json` is
  robust where markdown-scraping is brittle, and an on-demand briefing then reflects the moment it
  is run.
- **Rule-based actions.** `{{ACTIONS_SECTION}}` is derived deterministically from the collected
  data (failing checks → re-verify; stale memory → `--apply`; horizon DUE → run the scan; else
  "no action needed"). No model in the loop — the briefing is fully headless.
- **Dual delivery.** An on-demand `/morning-briefing` command (fresh when read in the morning) and
  a 4th nightly step (a briefing is always pre-rendered at 03:00).
- **Single error boundary.** `run_json` is the only place that handles failure: a subprocess or
  JSON-parse error returns `{"error": …}`, and `build_sections` degrades that one source's section
  to `_(… unavailable)_`. The render functions assume valid data — no defensive `if "error"`
  branches threaded through them (per the repo's "trust internal code" posture; the sources are
  in-repo and contract-guaranteed).

## Consequences

**Positive**

- The template's long-standing "wire your own renderer" promise is fulfilled; the operator gets one
  rendered view (status + per-area detail + suggested actions) instead of scraping the log.
- The `--json` contract is reusable and keeps the renderer decoupled from each script's internals.
- A single failing source never blanks the whole briefing.

**Negative / mitigations**

- **03:00 double-run.** The nightly steps 1–3 run the three scripts (logging to `nightly.log`), and
  step 4's renderer runs them again via `--json`. Their checks are idempotent, so this is harmless;
  the cost is a few extra cheap subprocesses.
- **`-ApplyHousekeep` ordering.** When the nightly is registered with `-ApplyHousekeep`, step 2
  archives stale memory *before* the step-4 briefing re-scans, so the briefing reports the
  *post*-archival state. This is intended — the briefing shows "what still needs attention," and
  `nightly.log` retains the pre-archival report.
- **Subprocess cost vs. import.** Accepted for the decoupling benefit above; the per-run cost is
  negligible against the nightly cadence.

Cross-references: ADR-0010 (the horizon-scan cadence step this builds on); ADR-0008 (root CHANGELOG
— the program-level entry is curated there, not by `ci/release.py`).
