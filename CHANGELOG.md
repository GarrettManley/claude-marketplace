# Changelog

All notable changes to this marketplace are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/).

This is the **aggregated** changelog across all plugins and repo-level tooling. Each
plugin also keeps its own `plugins/<name>/CHANGELOG.md` with per-plugin release notes;
this file summarizes the program-level picture. See `docs/adr/0008-root-changelog.md`.

## [Unreleased]

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
