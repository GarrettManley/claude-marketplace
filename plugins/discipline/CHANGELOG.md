# Changelog

All notable changes to the **discipline** plugin are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres
to [Semantic Versioning](https://semver.org/).

## 1.1.0 — 2026-06-24

- SessionStart shell hooks no longer require a bare `python3`: `inject_issues.sh` runs its helper via `uv run --no-project` (needs `uv` on PATH), and `inject_branch_state.sh` dropped its Python check entirely since it is pure bash + git.
- Documented the gateguard profile split: the fact-forcing edit gate is `strict`-only (as of 0.7.1) while the destructive-Bash gate still fires under both `standard` and `strict`; README profile table and migration notes corrected.
- Manifest enriched with `$schema`, `homepage`, `repository`, `license`, `keywords`, and category metadata.

## 1.0.0 — initial public release

First public release. Generic dev hygiene: TODO+issue enforcement, frontmatter lint, plan validation (issue+value+retrospective), spec-code drift checker, finish-and-push workflow, and pitfalls-pointer routing, plus a fact-forcing edit gate, git-state checkpoint/snapshot tooling, and council + session-handoff skills.
