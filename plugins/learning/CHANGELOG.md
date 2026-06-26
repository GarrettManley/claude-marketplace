# learning changelog

## 1.3.0

### Features
- add Phase 2c detection + Phase 3 evolve/promote/prune

# Changelog

All notable changes to the **learning** plugin are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres
to [Semantic Versioning](https://semver.org/).

## 1.2.0 — 2026-06-25

- **Phase 2b — automated instinct creation.** New `synthesize.py` converts frequency patterns in `observations.jsonl` into instincts: tool-pair sequences become `workflow` instincts (scored by support × consistency) and Bash command prefixes become `tooling` instincts. Confidence is auto-derived via a saturating, capped model (≤0.85 workflow, ≤0.70 bash) and auto-created instincts carry `source: auto-frequency`. Writes are idempotent and never overwrite a manually-promoted instinct of the same id.
- New `synthesize` CLI subcommand (`instinct_cli.py synthesize`, dry-run by default, `--write` to persist) and `/instinct-synthesize` slash command.
- **Surfacing hook.** New opt-in `SessionStart` hook (`surface.py`, gated by `LEARNING_SURFACE=on` + `strict` profile) injects high-confidence project + global instincts into session context, filtered by `LEARNING_SURFACE_MIN_CONFIDENCE` (default 0.6) and capped at 15. This closes the loop — previously, stored instincts influenced nothing.
- Factored env-var truthiness into shared `env_flags.py` (reused by `observe.py` and `surface.py`).
- Added `tests/test_synthesize.py` and `tests/test_surface.py`; extended `tests/test_instinct_cli.py`.

## 1.1.0 — 2026-06-24

- Fixed `observe.py` phase detection: it now reads `hook_event_name` from the stdin event JSON (the only reliable production signal), so PreToolUse observations are recorded as `pre` instead of always falling through to `post`. argv/env paths retained as test/direct-invocation fallbacks.
- Added `tests/test_observe.py` covering the corrected phase-detection logic.
- Manifest enriched with `$schema`, `homepage`, `repository`, `license`, `keywords`, and category metadata.

## 1.0.0 — initial public release

First public release. Continuous-learning toolkit: atomic instinct storage plus project-scoped observation hooks (default-off) and an /analyze-observations review report.
