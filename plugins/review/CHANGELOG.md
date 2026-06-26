# review changelog

## 1.2.0

### Features
- Add /review-evolve command (Post-Cycle protocol automation)
- Add review_cli evolve ingester (validate + diff + apply)
- Add persona parse/validate/diff helpers

# Changelog

All notable changes to the **review** plugin are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres
to [Semantic Versioning](https://semver.org/).

## 1.1.0 — 2026-06-24

- `reviewer-personas` now dispatches the 16 archetype agents directly via the plugin-scoped `subagent_type: review:<name>` (e.g. `review:security-auditor`) instead of pasting persona text into a `general-purpose` agent — the agent definition is now the single source of truth for each persona.
- Removed the duplicate `personas/*.md` files (the persona bodies now live solely in `agents/<name>.agent.md`); selection table expanded to cover all 16 archetypes and the dispatch/update protocol rewritten accordingly.
- Manifest enriched with `homepage` and category metadata.

## 1.0.0 — initial public release

First public release. Multi-lens review: dispatch sub-agent reviewers against design docs, PRs, work items, wiki pages, or skill files using a library of reviewer archetypes (security, observability, data, operations, ecosystem, new-engineer, skill-craft).
