---
name: design-document
description: Use when creating a new design document for a component, feature, or system. Provides a pluggable structure (intro, scope, system overview, design details, dependencies, references, history) and an opinionated skeleton you can extend per project.
version: 0.1.0
dependencies: []
---

# Design Document Creation

Generate design documents that read like a senior engineer wrote them. This skill provides a project-agnostic skeleton; for project-specific section requirements, fork into `.claude/skills/design-document/` and adjust.

For prose guidance, follow `/tech-writing`. For diagrams, follow `/mermaid-diagram`.

## When to use

- Creating a new design document for a component, feature, or system from scratch.
- Deciding which sections a draft needs and which to omit (sections 1–4, 7, 12, 16, 17 are required).
- Running the pre-publish checklist before circulating a design doc for review.

## Required Inputs

- **Component/feature name** — becomes the document title
- **Author(s)** — full name(s) for the header and history table
- **Scope** — what the document covers and what it does NOT cover
- **Key design decisions** — architectural choices, trade-offs, selected approaches

## Skeleton

A generic starter template ships at `templates/generic-design-doc-template.md` in this plugin. The recommended structure:

| # | Heading | Level | Required in draft? |
|---|---------|-------|--------------------|
| 1 | Introduction | `#` | Yes |
| 1a | Purpose | `##` | Yes |
| 1b | Scope (in / out) | `##` | Yes |
| 1c | Definitions and Acronyms | `##` | Only if 3+ project-specific terms |
| 2 | Overview | `#` | Yes |
| 3 | System Overview | `#` | Yes (include diagram) |
| 4 | Architecture / Design Details | `#` | Yes |
| 5 | Data Models | `#` | Optional |
| 6 | Interfaces and APIs | `#` | Optional |
| 7 | Execution Flow | `#` | Yes |
| 8 | Error Handling and Edge Cases | `#` | Optional |
| 9 | Testing and Validation | `#` | Optional |
| 10 | Performance Considerations | `#` | Optional |
| 11 | Security Considerations | `#` | Optional |
| 12 | Dependencies | `#` | Yes |
| 13 | Configuration | `#` | Optional |
| 14 | Future Enhancements | `#` | Optional |
| 15 | Troubleshooting | `#` | Optional |
| 16 | References | `#` | Yes |
| 17 | Document History | `##` | Yes (below `---` rule) |

**Required in early draft:** sections 1–4, 7, 12, 16, 17. Other sections may be omitted entirely (don't include empty sections with "None" or "N/A").

**Troubleshooting scope:** Keep this section as a diagnostic reference (symptoms, likely causes, commands to check). Repair procedures, escalation paths, and step-by-step recovery belong in an operational runbook, not the design doc.

## Header Block

```
Date: <YYYY-MM-DD>
Author(s): <Name(s)>
Version: 0.1 (Draft)
```

Version status values: **Draft**, **Engineering Team Review**, **Final**.

## Diagrams

Use Mermaid for system overviews, sequence diagrams, and component graphs. Check `/mermaid-diagram` for palette, fencing, and common mistakes.

The fencing depends on your renderer. GitHub/GitLab/most Markdown: triple-backtick. Azure DevOps Wiki: `:::mermaid` / `:::`.

## Scope Statement

Both halves matter equally:

> **In scope:** `<list of components, behaviors, environments covered>`
>
> **Out of scope:** `<list of items reviewers might expect but won't find here>`

The out-of-scope half prevents wasted reading and misplaced frustration. Reviewers learn early that a topic lives elsewhere.

## Document History Table

End every document with a horizontal rule and version table:

```
---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | <YYYY-MM-DD> | <Author> | Initial draft |
```

## Pre-Publish Checklist

1. Pair this skill with `/tech-writing` for prose discipline.
2. If you have a `review` plugin enabled, run `/reviewer-personas` for a multi-lens review before publication.
3. Confirm the scope statement names what's out-of-scope, not just in-scope.
4. Confirm every diagram fences correctly for the target renderer.
5. Confirm references section cites authoritative sources (specs, ADRs, prior design docs) — not random commits.

## Forking This Skill for Project-Specific Conventions

Different projects have different design-doc cultures. If your project requires specific sections (e.g., "Compliance Review" or "Hardware BOM"), copy this skill into your project's `.claude/skills/design-document/` and add the sections there. Keep the universal skeleton intact so the upstream guidance still applies.
