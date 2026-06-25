# Changelog

All notable changes to the **aether** plugin are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres
to [Semantic Versioning](https://semver.org/).

## 1.1.1 — 2026-06-25

- Migrated the `eval-run` skill and `classifier-regression-checker` agent from the retired Ollama runtime to **llama-server**: the eval now runs via `npm run eval:classifier` (`scripts/eval-gate.mjs`, with `EVAL_REQUIRE_LLM=1` gate mode), the classifier model is `gemma4:e4b` via `LLAMACPP_CLASSIFIER_MODEL`, and the provider-schema reference is `src/llm/llamacpp.ts` (the deleted `ollama.ts`). Dropped the hardcoded "38 tests" assertion in favor of the eval-gate scorecard's dynamic `passed/total/skipped` (issue #158).

## 1.1.0 — 2026-06-24

- Corrected cross-platform docs for the `uv` migration: hooks run via `uv run --no-project`, so `uv` on PATH is the only runtime requirement (no separate `python3`).
- Updated `eval-run` skill and `aether-edit-checklist` to cite `schemas.ts` instead of the retired `verb_lexicon.ts` as a classifier-eval trigger.
- Manifest enriched with `$schema`, `homepage`, `repository`, `license`, `keywords`, and category metadata.

## 1.0.0 — initial public release

First public release. Aether Engine TTRPG/narrative framework support: domain-specific hooks (cd_core_guard, ledger truncation, classifier/harness/Rust-rebuild reminders), 6 skills (doc-cluster, edit-checklist, plan-writer, ledger-doctor, eval-run, value-justify), classifier-regression-checker agent.
