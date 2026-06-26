# Changelog

All notable changes to this marketplace are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/).

This is the **aggregated** changelog across all plugins and repo-level tooling. Each
plugin also keeps its own `plugins/<name>/CHANGELOG.md` with per-plugin release notes;
this file summarizes the program-level picture. See `docs/adr/0008-root-changelog.md`.

## [Unreleased]

### Changed

- Release tooling (`ci/release.py`): tags are now created on `main` after the
  squash-merge via a new `--tag` mode (`--apply` no longer tags on the branch),
  so the squash can never orphan a release tag. A dry-run/apply guard refuses with
  a re-point hint if a plugin's last tag is not an ancestor of HEAD. Runbook updated;
  see `docs/adr/0012-tag-after-merge.md`.

### Added

- `review` plugin: `/review-evolve` command automating the post-cycle update
  protocol — derives per-persona Caught/Missed/Hallucinated catches from the
  in-context review report and turns the notable signals into validated,
  full-persona rewrites of `agents/<name>.agent.md` (dry-run by default,
  project-local `.claude/agents/` target, git as the snapshot). Backed by the
  plugin's first `scripts/` (`persona.py`, `review_cli.py`) + `tests/`.
  New-archetype scaffolding is deferred. See `docs/adr/0009-review-persona-evolution.md`.
- `stewardship` plugin: nightly steward now runs a third step,
  `horizon_scan_schedule.py` — a deterministic cadence tracker that surfaces a
  "horizon-scan DUE" reminder monthly (state in
  `~/.claude/stewardship/horizon-scan-state.json`, `--interval-days`, `--mark-done`).
  It reminds rather than executes: `orchestration:horizon-scanning` needs an
  interactive session (web search, VRAM judgment, load tests) and cannot run
  headless. Wired into the Windows/cron/launchd schedulers; adds a
  `{{HORIZON_SCAN_SECTION}}` briefing token. See
  `docs/adr/0010-horizon-scan-cadence-reminder.md`.
- `stewardship` plugin: `/morning-briefing` command + `render_briefing.py` fill
  `templates/morning-briefing.md` from live data — invoking the three source
  scripts via `--json` (added `--json` to `auto_memory_housekeep.py` for parity),
  deriving a status line + rule-based suggested actions, and writing
  `~/.claude/stewardship/briefing/<date>.md`. Delivered both on-demand and as the
  steward's 4th nightly step. See `docs/adr/0011-morning-briefing-renderer.md`.

### Fixed

- `stewardship` `render_briefing.py`: force UTF-8 stdout so `/morning-briefing`
  (`--stdout`) no longer crashes printing non-ASCII glyphs (the `→` in
  broken-pointer lines) on a Windows cp1252 console.

## [evidence 1.2.0] — 2026-06-25

### Added

- `evidence` plugin: opt-in scope-binding PreToolUse hook (`scope_bind.py`) —
  confines `WebFetch` (when the manifest declares `hosts`) and
  `Edit`/`Write`/`MultiEdit` (when it declares `path_prefixes`) to
  `.claude/evidence-scope.yaml`, with a `scope_binding` HMAC override valve.
  Registered but **off by default**: a no-op unless `EVIDENCE_SCOPE_ENFORCE` is
  on and a manifest is loaded (the `learning`-plugin env-gated opt-in idiom).

## [1.3.0] — 2026-06-25

### Added

- `learning` plugin (1.3.0): Phase 2c Claude-driven correction/preference
  detection (`/instinct-detect`, Path A) and Phase 3 instinct lifecycle —
  `/prune` (30-day half-life confidence decay), `/promote` (project→global,
  `--auto` for cross-project high-confidence), `/evolve` (cluster + merge
  near-duplicate instincts, archive to `evolved/`). Adds
  `Instinct.last_reinforced` and `is_machine_source()`; machine-owned instincts
  are now reinforced in place and written atomically. The headless llama-server
  detection backend (Path B) is deferred until a concrete headless consumer
  exists.

## [1.1.1] — 2026-06-25

### Changed

- `aether` plugin (1.1.1): migrated the `eval-run` skill and
  `classifier-regression-checker` agent from the retired Ollama runtime to
  llama-server (`npm run eval:classifier` / `scripts/eval-gate.mjs`, `gemma4:e4b`
  via `LLAMACPP_CLASSIFIER_MODEL`, provider schema in `src/llm/llamacpp.ts`);
  replaced the hardcoded eval test count with the eval-gate scorecard's dynamic
  `passed/total/skipped`.

## [1.1.0]

### Added

- OSS governance and discoverability files: structured GitHub issue forms
  (`bug_report.yml`, `feature_request.yml`), an enriched pull-request template,
  `CITATION.cff`, an inert `.github/FUNDING.yml`, `.github/dependabot.yml`
  (github-actions, weekly), and an analysis-only `.github/workflows/codeql.yml`
  (Python). CI status and license badges on the root README.
- `review` plugin now dispatches its 16 archetype agents (previously the dispatch path
  was incomplete).
- `docs` plugin: new `adversarial-review-plan` skill plus 3 supporting agents.
- `retrospective` plugin: new plan-completion skill plus a completion gate hook.
- This root `CHANGELOG.md` (per `docs/adr/0008-root-changelog.md`).

### Changed

- Manifest schema and category metadata enrichment across plugin manifests.

### Fixed

- Audit-driven fixes from the v1.1 quality pass.

## [1.0.0]

### Added

- Initial public release: 12 capability-bundled plugins — `aether`, `agentic`,
  `discipline`, `docs`, `evidence`, `git`, `learning`, `orchestration`,
  `retrospective`, `review`, `stewardship`, `windows` — with verify-only CI across a
  tri-OS matrix and a ≥90% Python line-coverage gate.
