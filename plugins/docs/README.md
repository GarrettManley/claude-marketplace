---
status: active
author: Garrett Manley
created: 2026-06-23
diataxis: reference
---

# docs@garrettmanley

Six skills for documentation craft: writing rules for technical prose, consistent Mermaid diagram authoring, a structured design-document skeleton, and three adversarial review skills that find problems automated code review misses — in documents, PRs, and code diffs. Aimed at engineers who write design docs, run PR workflows, or want machine-speed coverage before sending work to human reviewers.

## Install

```
/plugin marketplace add garrettmanley/claude-marketplace
/plugin enable docs@garrettmanley
```

No init scripts. No configuration files. Enable and use.

## Components

| Skill | Description |
|-------|-------------|
| `tech-writing` | Universal prose rules grounded in [Google Technical Writing](https://developers.google.com/tech-writing). Active voice, strong verbs, pronoun distance, paragraph structure, self-check. |
| `mermaid-diagram` | Mermaid diagrams with a semantic three-role color palette (Enforcement / Processing / Infrastructure), renderer-agnostic fencing, and a common-mistakes table. |
| `design-document` | Structured design-doc skeleton with 17 numbered sections; 8 are required in early draft (sections 1-4, 7, 12, 16, 17). Ships a starter template at `templates/generic-design-doc-template.md`. |
| `adversarial-review-doc` | Parallel dimension-agent review for any markdown document. Catches structural problems, broken cross-references, stale claims, terminology drift, and placeholder text. Optional `--fix` fixer dispatch. |
| `adversarial-review-pr` | PR-level adversarial review: description accuracy vs. the actual diff, work item consistency, commit message alignment, and cross-document sync obligations. |
| `adversarial-review-code` | Coordination layer over `pr-review-toolkit` agents. Dispatches `code-reviewer`, `silent-failure-hunter`, and (for TypeScript / C# diffs) `type-design-analyzer` in parallel, then consolidates and deduplicates findings. |

This plugin ships no hooks, agents, or commands.

## Usage

### tech-writing

Invoke before publishing any technical prose — documentation, design docs, PR descriptions, wiki pages, or work items. The skill applies the rules from the Google Technical Writing courses: active voice, strong verbs, one idea per sentence, audience modeling, scope statements, list/table discipline, and punctuation. A 10-point self-check is included.

```
/tech-writing
```

Pair with `mermaid-diagram` and `design-document` for full document authoring coverage.

### mermaid-diagram

Invoke when embedding a diagram in any document. The skill provides:

- **Fencing** — GitHub/GitLab/most Markdown uses triple-backtick; Azure DevOps Wiki uses `:::mermaid` / `:::`.
- **Palette** — three semantic roles with exact hex values:

  | Role | Fill | Stroke | Use for |
  |------|------|--------|---------|
  | Enforcement | `#fce4cc` | `#c0570d` | Security gates, rejection/acceptance nodes |
  | Processing | `#dae8cd` | `#38571a` | Application logic, validation, transformations |
  | Infrastructure | `#cbebfa` | `#144c8f` | Stores, caches, routing, shared services |

- **Per-node `style` directives** — the skill uses these rather than `classDef`/`:::className` for portability.
- **Sequence diagrams** — leave unstyled; the skill explains why.

To use a project-specific color palette, fork the skill into your project's `.claude/skills/mermaid-diagram/` and replace the role rows with your brand tokens.

### design-document

Invoke when creating a new design document from scratch. Required inputs: component/feature name, author(s), scope (in and out), and key design decisions. The skill produces a document with the required sections pre-populated and optional sections omitted unless they are needed.

Required sections in an early draft: Introduction (1), Overview (2), System Overview (3), Architecture / Design Details (4), Execution Flow (7), Dependencies (12), References (16), Document History (17). Optional sections (Data Models, Interfaces and APIs, Error Handling, Testing, Performance, Security, Configuration, Future Enhancements, Troubleshooting) are included only when the content is present.

A generic starter template is available at `templates/generic-design-doc-template.md` in this plugin. Copy it to start a document manually.

```
/design-document
```

The skill's pre-publish checklist points at `/tech-writing` for prose and `/mermaid-diagram` for any diagrams.

### adversarial-review-doc

```
/adversarial-review-doc <document-path>
  [--dimensions dim1,dim2,...]   # default: all 5
  [--calibration "issue1; issue2"]
  [--fix]
  [--output <path>]              # default: <document-path>.review.md
```

Dispatches one agent per dimension in parallel. After all agents complete, findings are deduplicated (same section + current-text from different agents → one finding, highest severity kept), sorted CRITICAL → IMPORTANT → MINOR, and written to the output file.

**Five built-in dimensions:**

| Dimension | Focus |
|-----------|-------|
| `structural` | Heading hierarchy, section ordering, numbering, duplicate labels |
| `cross-reference` | Internal links, named items (e.g., OQ-3), section references |
| `stale-text` | Present-tense claims contradicted elsewhere in the same document |
| `terminology` | Defined-term consistency, capitalization drift, abbreviation inconsistency |
| `completeness` | TBD, TODO, Pending, and placeholder markers |

Use `--dimensions` to run a subset. Use `--calibration` to inject known issues and score whether the skill catches them.

**Custom dimensions** (extension point): drop `.md` files under `<workspace-root>/.claude/adversarial-dimensions/<doc-type>/`. A file with the same base name as a built-in dimension overrides it; a different name augments the set.

If `--fix` is passed, a single fixer agent applies CRITICAL and IMPORTANT findings to the source document. MINOR findings remain in the output file for human review. For ambiguous findings, the fixer inserts `<!-- REVIEW: <finding> -->` rather than guessing.

**Standard findings format** (all dimensions):

```
[CRITICAL | IMPORTANT | MINOR] — <Section/heading>: "<current text (≤20 words)>" → "<required fix>"
```

### adversarial-review-pr

```
/adversarial-review-pr <pr-url-or-id>
  [--repo owner/repo]
  [--fix]
```

Fetches PR title, body, commits, and diff (via `gh`), then runs four dimension checks concurrently:

1. **Description accuracy** — overclaims, underclaims, wrong file paths, incorrect scope statements.
2. **Work item consistency** — `AB#NNNN` references resolve to real items of the right type.
3. **Commit message alignment** — `<type>(<scope>): <summary>` format, body presence, required sections. Reads `commit-message-rules.yaml` from the workspace root if present.
4. **Cross-document sync obligations** — modified files with `Canonical home:` annotations that the PR description does not mention updating.

If `--fix` is passed, a fixer agent edits the PR description via `gh pr edit` for description-accuracy findings; other finding types are posted as PR comments for human action.

**Standard findings format:**

```
[CRITICAL | IMPORTANT | MINOR] — <dimension>: "<current text (≤20 words)>" → "<required fix>"
```

### adversarial-review-code

```
/adversarial-review-code <diff-path-or-pr-ref>
  [--fix]
  [--output <path>]   # default: <diff-path>.review.md
```

Before dispatching, inspects the diff for file extensions: `.ts`, `.tsx`, `.cs`, `.d.ts` → includes `type-design-analyzer`. Always dispatches `code-reviewer` and `silent-failure-hunter`. All agents run concurrently.

After agents complete, findings are deduplicated by `<file>:<line>` (higher severity wins), sorted CRITICAL → IMPORTANT → MINOR, and written to the output file.

If `--fix` is passed, a single fixer agent receives the entire consolidated findings list and applies CRITICAL and IMPORTANT findings in one pass, CRITICAL-first. For ambiguous findings it inserts `// REVIEW: <finding>` rather than guessing.

**Prerequisite:** `pr-review-toolkit` from `claude-plugins-official` must be installed. This skill dispatches its agents directly.

**Standard findings format:**

```
[CRITICAL | IMPORTANT | MINOR] — <file>:<line-or-symbol>: "<current behavior (≤20 words)>" → "<required fix>"
```

## Skill composition

The three adversarial-review skills and the three authoring skills are complementary, not overlapping:

| Goal | Skills to use |
|------|--------------|
| Write a new design doc | `design-document` → `tech-writing` → `mermaid-diagram` |
| Review a document before publishing | `adversarial-review-doc` |
| Review a PR before merging | `adversarial-review-pr` + (if code changed) `adversarial-review-code` |
| Full PR coverage | `adversarial-review-code` → `adversarial-review-pr` → `adversarial-review-doc` (for any docs in the diff) |

For persona-perspective review ("how would a team member react"), pair with `/reviewer-personas` from `review@garrettmanley` — it surfaces reader reactions rather than structural findings.

## Configuration

No environment variables or config files. The skills have no opt-in/opt-out knobs at the plugin level.

**Per-project customization is done by forking:**

- `tech-writing` — fork into `.claude/skills/tech-writing/` to add project voice, banned phrases, or brand vocabulary.
- `mermaid-diagram` — fork into `.claude/skills/mermaid-diagram/` to replace the default palette with brand tokens.
- `design-document` — fork into `.claude/skills/design-document/` to add project-specific required sections.
- `adversarial-review-doc` dimensions — add `.md` files under `<workspace-root>/.claude/adversarial-dimensions/<doc-type>/` without modifying the plugin.

**`commit-message-rules.yaml`** (workspace root): if present, `adversarial-review-pr` reads `types`, `scopes`, and `required-sections` from it to validate commit messages. Without the file, the skill checks only `<type>(<scope>): <summary>` format and body presence.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `adversarial-review-code` fails with "agent not found" | Install `pr-review-toolkit` from `claude-plugins-official` — it is a required dependency that does not ship with this plugin. |
| `adversarial-review-pr` returns "not found" for work items | The `az` CLI must be authenticated and `az boards work-item show` must resolve the referenced IDs. The skill does not authenticate on your behalf. |
| Dimension agents find no issues in a document known to have problems | Use `--calibration "known-issue-1; known-issue-2"` to inject known issues and score whether the skill catches them. A gap in calibration coverage surfaces as an UNCAUGHT finding in the output. |
| A Mermaid diagram renders as raw code | The fencing is wrong for the target renderer. GitHub/GitLab/most Markdown: triple-backtick. Azure DevOps Wiki: `:::mermaid` / `:::`. Swap and re-publish. |

## Cross-platform

The plugin is pure-skill (no hooks, no shell scripts, no init). It runs identically on Windows, macOS, and Linux. The only external tool dependencies are:

- `gh` CLI — required by `adversarial-review-pr` to fetch PR data and post comments.
- `az` CLI — required by `adversarial-review-pr`'s work-item-consistency dimension to resolve Azure DevOps work items. If your project does not use Azure DevOps, that dimension produces no findings.
- `pr-review-toolkit` plugin — required by `adversarial-review-code`.
