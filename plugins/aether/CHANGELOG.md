# Changelog

All notable changes to the **aether** plugin are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres
to [Semantic Versioning](https://semver.org/).

## 1.1.0 — 2026-06-24

- Corrected cross-platform docs for the `uv` migration: hooks run via `uv run --no-project`, so `uv` on PATH is the only runtime requirement (no separate `python3`).
- Updated `eval-run` skill and `aether-edit-checklist` to cite `schemas.ts` instead of the retired `verb_lexicon.ts` as a classifier-eval trigger.
- Manifest enriched with `$schema`, `homepage`, `repository`, `license`, `keywords`, and category metadata.

## 1.0.0 — initial public release

First public release. Aether Engine TTRPG/narrative framework support: domain-specific hooks (cd_core_guard, ledger truncation, classifier/harness/Rust-rebuild reminders), 6 skills (doc-cluster, edit-checklist, plan-writer, ledger-doctor, eval-run, value-justify), classifier-regression-checker agent.
