# learning changelog

All notable changes to the **learning** plugin are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres
to [Semantic Versioning](https://semver.org/).

## 1.6.1

### Fixes
- re-sync vendored run_with_flags UTF-8 defense (hb-zxg)
- sync vendored run_with_flags (hb-rap CR)
- sync vendored run_with_flags + isolate hook-error log in tests (hb-rap)
- cap oversized tool_input at capture (hb-168) (#55)

## 1.6.0

### Features
- bound observation growth â€” capture-time cap + nightly retention compaction (#51)

### Fixes
- harden compaction + nightly wrapper per adversarial review (#51)
- force UTF-8 stdout in every printing entry point (#51)

## 1.5.0

### Features
- **Phase 2b nightly automation — headless self-improving loop.** New `synthesize_nightly.py` + `synthesize-nightly` CLI subcommand run the existing deterministic frequency synthesis headlessly across **every** observed project. The nightly steward has no cwd/project context, so the runner iterates `projects/*/observations.jsonl` explicitly rather than resolving the current project (`get_project_id`), and writes one combined report at the data-root (`last_mine_report.json`, project-independent) for the stewardship briefing to consume. No new mining logic — reuses `synthesize` + `write_instincts` unchanged (idempotent, atomic, reinforcing via stable ids). `tests/test_synthesize_nightly.py` (9 tests) + CLI dispatch test. _Note: an LLM tier for the non-frequency signal 2b discards (error clusters, semantic patterns) was deliberately deferred to a future bead, gated on a spike proving it beats this deterministic baseline._

## 1.4.0

### Features
- **Phase 2d — retrospective mining (#19).** New `retro_mine.py` + `/instinct-from-retro` close the previously write-only retrospective loop: the script deterministically parses each retro's `## Friction / bugs` entries (the `*Rule:*` / `*Root cause:*` / `*What happened:*` / `*How caught:*` sub-labels) and emits a JSON friction summary; Claude clusters rules that recur across ≥2 retros and authors candidates, which `--ingest` normalizes into the new `retro-mined` source (capped at `MAX_CONF_DETECTED` = 0.80) and writes via the existing idempotent `write_instincts`. No new storage — retro instincts surface at SessionStart and are evolved/pruned like any machine instinct. New `retro-mine` CLI subcommand and `tests/test_retro_mine.py` (14 tests). `retro-mined` registered in `is_machine_source`.

## 1.3.0

### Features
- add Phase 2c detection + Phase 3 evolve/promote/prune

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
