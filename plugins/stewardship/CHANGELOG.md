# stewardship changelog

## 1.3.1

### Fixes
- Force UTF-8 stdout in render_briefing so --stdout survives cp1252 consoles

## 1.3.0

### Features
- Wire briefing render as the 4th nightly step
- Add /morning-briefing command
- Add briefing integration tests; render-clean template intro
- Add briefing render/derive pure functions
- Add --json report mode to auto_memory_housekeep

## 1.2.0

### Features
- Wire horizon-scan step into all nightly schedulers (Windows/cron/launchd)
- Add horizon-scan cadence tracker

# Changelog

All notable changes to the **stewardship** plugin are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres
to [Semantic Versioning](https://semver.org/).

## 1.1.0 — 2026-06-24

- Dropped the unimplemented `--markdown` flag from `drift_check.py` (and its docs/usage) — markdown is the default output; pass `--json` for machine-readable output.
- `harness-optimizer` agent's inline audit commands now run through `uv run --no-project` for cross-platform interpreter resolution (avoids the Windows `python3`/`python`/`py` split).
- Manifest enriched with `$schema`, `homepage`, `repository`, `license`, `keywords`, and category metadata.

## 1.0.0 — initial public release

First public release. Autonomous maintenance toolkit: drift-check runner against context-file verification commands, morning-briefing template, Windows Task Scheduler registration helper, auto-memory housekeeping for ~/.claude/projects/*/memory/.
