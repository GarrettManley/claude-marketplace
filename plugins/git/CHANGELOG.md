# Changelog

All notable changes to the **git** plugin are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres
to [Semantic Versioning](https://semver.org/).

## 1.1.0 — 2026-06-24

- `validate.sh` now provisions PyYAML via `uv run --no-project --with pyyaml`, so the real YAML parser always runs on the standard path (the minimal-fallback warning only appears when `validate.py` is invoked directly without PyYAML).
- README troubleshooting and cross-platform notes updated to reflect the `uv`-based validator (needs `uv` on PATH, not a standalone `python3`).
- Manifest enriched with `$schema`, `homepage`, `repository`, `license`, `keywords`, and category metadata.

## 1.0.0 — initial public release

First public release. Git workflow: Conventional Commits formatting that resists the common CI-guard failure modes, and PR creation that detects the remote host (GitHub / Azure DevOps Repos / GitLab) instead of hardcoding one.
