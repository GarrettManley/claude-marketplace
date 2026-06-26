# Changelog

All notable changes to this marketplace are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/).

This is the **aggregated** changelog across all plugins and repo-level tooling. Each
plugin also keeps its own `plugins/<name>/CHANGELOG.md` with per-plugin release notes;
this file summarizes the program-level picture. See `docs/adr/0008-root-changelog.md`.

## [Unreleased]

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
