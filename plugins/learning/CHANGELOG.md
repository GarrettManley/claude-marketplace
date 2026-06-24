# Changelog

All notable changes to the **learning** plugin are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres
to [Semantic Versioning](https://semver.org/).

## 1.1.0 — 2026-06-24

- Fixed `observe.py` phase detection: it now reads `hook_event_name` from the stdin event JSON (the only reliable production signal), so PreToolUse observations are recorded as `pre` instead of always falling through to `post`. argv/env paths retained as test/direct-invocation fallbacks.
- Added `tests/test_observe.py` covering the corrected phase-detection logic.
- Manifest enriched with `$schema`, `homepage`, `repository`, `license`, `keywords`, and category metadata.

## 1.0.0 — initial public release

First public release. Continuous-learning toolkit: atomic instinct storage plus project-scoped observation hooks (default-off) and an /analyze-observations review report.
