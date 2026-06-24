---
name: adversarial-review-doc
description: Use when you need to adversarially review any markdown document for structural problems, broken cross-references, stale claims, terminology drift, or placeholder text. Runs dimension agents in parallel, consolidates findings into CRITICAL / IMPORTANT / MINOR severity buckets, and optionally auto-dispatches a fixer. Complementary to /reviewer-personas, which checks team-member perspectives rather than document integrity.
version: 0.1.0
dependencies: []
---

# Adversarial Document Review

Documents edited in multiple passes accumulate silent errors: headings drift, cross-references break, defined terms get renamed mid-document, and placeholder text ships. No single reviewer catches all of these consistently.

Dimension-based adversarial review for any markdown document. Dispatches one agent per dimension in parallel, consolidates findings with deduplication and severity sorting, and optionally auto-dispatches a fixer agent.

This skill checks structural and technical document integrity. For persona-perspective review (what a team member would think), use `/reviewer-personas` from `review@garrettmanley` instead or in addition. These are complementary: `adversarial-review-doc` finds internal inconsistencies and broken references; `/reviewer-personas` surfaces how a reader would react.

## When to use

- Before publishing any design document, wiki page, or specification.
- After a document has been edited in multiple passes — terminology drifts and cross-references break without anyone noticing.
- When a document has grown large enough that a human reviewer is likely to miss completeness gaps.
- When you want machine-speed coverage before sending to human reviewers.

---

## Interface

```
/adversarial-review-doc <document-path>
  [--dimensions dim1,dim2,...]   # override active dimensions; defaults to all 5
  [--calibration "issue1; issue2"]  # known issues for coverage scoring
  [--fix]                        # auto-dispatch fixer after consolidation
  [--output <path>]              # findings file path; defaults to <document-path>.review.md
```

**Arguments:**

| Argument | Default | Description |
|----------|---------|-------------|
| `<document-path>` | required | Absolute or repo-relative path to the markdown file to review |
| `--dimensions` | all 5 | Comma-separated subset: `structural`, `cross-reference`, `stale-text`, `terminology`, `completeness` |
| `--calibration` | none | Semicolon-separated list of known issues. Used to score coverage: if a calibration issue is NOT found, it surfaces as an uncaught finding |
| `--fix` | off | After consolidation, dispatch a fixer agent that reads the findings file and applies changes to the source document |
| `--output` | `<doc>.review.md` | Path where the consolidated findings file is written |

---

## Workflow

### Step 1 — Auto-discovery of workspace dimensions

Before dispatching any agents, check for additional dimension files at:

```
<workspace-root>/.claude/adversarial-dimensions/<doc-type>/
```

`<doc-type>` is determined as follows (in priority order):

1. **`type:` frontmatter key** — if the document has a YAML frontmatter block with a `type:` field, use its value verbatim (e.g., `type: threat-model` → `threat-model`).
2. **First-level heading** — normalize the H1 text to a slug: lowercase, spaces to hyphens, all other punctuation stripped. Examples: `# Key Vault Threat Model 2026` → `key-vault-threat-model-2026`; `# Design Document` → `design-document`.

Built-in recognized slugs: `design-document`, `threat-model`, `adr`, `wiki-page`, `runbook`. Any slug is valid — the built-in list is for documentation, not validation.

Any `.md` files found in the directory are loaded as additional dimensions, each getting its own parallel agent. **Conflict rule:** if a workspace dimension file has the same base name as a built-in dimension (e.g., `structural.md`), the workspace file **overrides** the built-in for this run. A different name **augments** the built-in set.

This is the extension point: domain-specific plugins (e.g., `your-org-security`) drop dimension files here to extend the review for their document types without modifying this skill.

### Step 2 — Dimension dispatch (parallel)

Launch one agent per active dimension (built-in dimensions, minus any overridden by workspace files, plus any workspace additions from Step 1). Pass each agent:
- The document path
- Its dimension prompt from `dimensions/<name>.md` (or the workspace dimension file path)
- A scratch output path for its raw findings: `<output-dir>/<dimension-name>.raw.md`, where `<output-dir>` is the directory of the `--output` file. Scratch files are deleted after consolidation in Step 3.

Run all dimension agents concurrently. Do not wait for one before starting the next.

### Step 3 — Consolidation

After all agents complete:

1. Collect all raw findings files.
2. Deduplicate: identical `<Section/heading>` + `"current text"` pairs from different agents count as one finding; keep the highest severity.
3. Sort by severity: CRITICAL → IMPORTANT → MINOR.
4. Compute calibration score: for each calibration issue, check whether a finding with matching section or text exists. Report matches as "caught" and gaps as "UNCAUGHT CALIBRATION ISSUE."
5. Write the consolidated findings file to `--output`.

### Step 4 — Fixer dispatch (optional)

If `--fix` was passed, dispatch a fixer agent that receives:
- The consolidated findings file path
- The original document path

The fixer applies CRITICAL and IMPORTANT findings, in CRITICAL-first order. MINOR findings are not applied by the fixer — they remain in the consolidated findings file for human review. It does not invent fixes — it applies only what the findings specify. For findings where the required fix is ambiguous, it inserts a `<!-- REVIEW: <finding> -->` comment rather than guessing.

To run a fixer-only pass against an existing findings file without re-running dimensions, call the fixer agent directly with the findings file and document paths.

---

## Standard Findings Format

All dimension agents must produce findings in this exact format, one finding per line:

```
[CRITICAL | IMPORTANT | MINOR] — <Section/heading>: "<current text (≤20 words)>" → "<required fix>"
```

**Severity guidance:**

| Severity | Use when |
|----------|----------|
| CRITICAL | A reader acting on this content would get a wrong result; or a required field is missing/placeholder |
| IMPORTANT | Inconsistency or gap that degrades document reliability; a reviewer would block on it |
| MINOR | Style, nit, or low-consequence inconsistency that is worth fixing but not blocking |

Agents must not output prose summaries, only the structured finding lines. Each finding must be self-contained: a reader of only that line must understand the problem and the fix.

**Example findings:**

```
[CRITICAL] — § 3.2 Key Vault secrets: "Secret name is TBD" → "Populate with actual secret name before publication"
[IMPORTANT] — § 5 References: "[1] See Appendix B" → "Appendix B does not exist in this document; remove or add it"
[MINOR] — § 2 Overview: "YARP" used without definition → "Introduce as 'YARP (Yet Another Reverse Proxy)' on first use"
```

---

## Dimensions

The five built-in dimensions live in `dimensions/` alongside this file:

| Dimension file | Focus |
|----------------|-------|
| `structural.md` | Heading hierarchy, section ordering, numbering, duplicate labels |
| `cross-reference.md` | Internal links, section references, named items (e.g., OQ-3, KV-001) |
| `stale-text.md` | Present-tense claims contradicted by other content in the same document |
| `terminology.md` | Defined-term consistency, capitalization drift, abbreviation inconsistency |
| `completeness.md` | TBD, TODO, Pending, and placeholder markers |

To use only a subset, pass `--dimensions structural,completeness`.

To add a dimension without modifying this skill, create a `.md` file at:

```
<workspace-root>/.claude/adversarial-dimensions/<doc-type>/<dimension-name>.md
```

Follow the same prompt format as the built-in dimension files: state the focus, specify the output format, instruct the agent to report only (no fixes).

---

## Cross-references

- **Complementary:** `/reviewer-personas` (`review@garrettmanley`) — runs named or archetype reviewers who react as a team member would. Use after `adversarial-review-doc` to layer perspective onto structural findings.
- **Complementary:** `/tech-writing` (`docs@garrettmanley`) — prose discipline rules for a writing pass. Run before or after this skill depending on whether you want to fix style before or after structural issues.
- **Complementary:** `/writing-style` (project-specific voice calibration, e.g., `your-style@your-org`) — applies project voice and naming conventions. Run alongside `/tech-writing` when the document is a team-facing artifact.
- **Complementary:** `/design-document` (`docs@garrettmanley`) — provides the canonical section structure that `structural.md` uses as its reference for ordering checks.
- **Fixer-only pass:** dispatch a fixer agent with the consolidated findings file path and document path directly, bypassing dimension re-dispatch.
