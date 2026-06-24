# Changelog

All notable changes to the **docs** plugin are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres
to [Semantic Versioning](https://semver.org/).

## 1.1.0 — 2026-06-24

- Added **adversarial-review-plan** skill: parallel review of implementation plans across 6 dimensions (clarity, completeness, feasibility, risk/rollback, scope-cut, value-justification), consolidated into CRITICAL / IMPORTANT / MINOR buckets.
- Added three plan-reviewer agents — `plan-skeptic`, `plan-feasibility-auditor`, `plan-scope-cutter` — dispatched by the new skill.
- Manifest enriched with `$schema`, `homepage`, `repository`, `license`, `keywords`, and category metadata.

## 1.0.0 — initial public release

First public release. Six skills for documentation craft:

- **tech-writing** — universal prose rules from Google Tech Writing.
- **mermaid-diagram** — Mermaid authoring with a configurable brand palette and renderer-agnostic fencing.
- **design-document** — structured design-doc creation with a pluggable template.
- **adversarial-review-doc** — parallel dimension-agent review for any markdown document (structural, cross-reference, stale-text, terminology, completeness).
- **adversarial-review-pr** — PR-level adversarial review of description accuracy, work item consistency, commit message alignment, and cross-document sync obligations.
- **adversarial-review-code** — coordination layer over `pr-review-toolkit` agents (code-reviewer, silent-failure-hunter, type-design-analyzer) with consolidated, deduplicated findings.
