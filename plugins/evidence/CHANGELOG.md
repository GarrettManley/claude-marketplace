# evidence changelog

All notable changes to the **evidence** plugin are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres
to [Semantic Versioning](https://semver.org/).

## 1.2.1

### Fixes
- scan and scope-gate NotebookEdit tool inputs (closes #32)
- reject ../ parent-traversal segments in scope path check (closes #31)

## 1.2.0

### Features
- env-gate scope-binding hook + register in hooks.json
- opt-in scope-binding PreToolUse hook (scope_bind.py)

## 1.1.0 — 2026-06-24

- Corrected the secret-scan hook invocation in the docs to `uv run --no-project` (post-uv-migration) instead of bare `python3`.
- Manifest enriched with `$schema`, `homepage`, `repository`, `license`, `keywords`, and category metadata.

## 1.0.0 — initial public release

First public release. Evidence-discipline workflow: citation-seeker, truth-seeker, HMAC override token framework, scope-binding hook scaffold, secret-scan PreToolUse hook.
