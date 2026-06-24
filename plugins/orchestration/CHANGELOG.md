# Changelog

All notable changes to the **orchestration** plugin are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres
to [Semantic Versioning](https://semver.org/).

## 1.1.0 — 2026-06-24

- Documented the `uv` prerequisite: the SessionStart hook runs via `uv run --no-project`, which bootstraps its own Python, so `uv` on PATH replaces the prior bare-`python3` requirement (README install + cross-platform notes corrected).
- Manifest enriched with `$schema`, `homepage`, `repository`, `license`, `keywords`, and category metadata.

## 1.0.0 — initial public release

First public release. Local LLM tier handoff: Reasoning + Tooling tier model defs (llama-server), local-orchestrator skill (when to hand off to local), horizon-scanning skill (track SOTA <=14B models), hardware-profile awareness via ~/.claude/context/hardware-profile.md.
