---
name: adversarial-review-code
description: Use when you need to adversarially review a code diff or PR for correctness bugs, silent failures, and type design problems. Dispatches pr-review-toolkit agents in parallel, consolidates findings into CRITICAL / IMPORTANT / MINOR severity buckets, and optionally auto-dispatches a single fixer. Complements /adversarial-review-doc, which checks document integrity rather than code.
version: 0.1.0
dependencies: ["pr-review-toolkit"]
---

# Adversarial Code Review

Running multiple code-review agents independently produces overlapping findings in different formats, making it hard to triage what to fix first and causing redundant fixer context-building.

Coordination layer over `pr-review-toolkit` agents. Dispatches code-review, silent-failure-hunter, and (when applicable) type-design-analyzer in parallel, then consolidates their findings into a single severity-sorted file with deduplication. Adds no new review logic — it orchestrates existing agents and normalises their output into a consistent format.

This skill requires `pr-review-toolkit` from `claude-plugins-official`. Install it before use.

## When to use

- Before creating a PR, after implementation is complete and you want machine-speed parallel coverage.
- When a diff spans multiple files or domains and a single-agent review risks missing cross-cutting issues.
- After receiving PR review feedback: run this to verify no related problems remain in the same diff.
- When you need a structured, deduped findings file to hand to a fixer agent or a human reviewer.

---

## Interface

```
/adversarial-review-code <diff-path-or-pr-ref>
  [--fix]             # auto-dispatch a single fixer agent after consolidation
  [--output <path>]   # where to write consolidated findings; defaults to <diff-path>.review.md
```

**Arguments:**

| Argument | Default | Description |
|----------|---------|-------------|
| `<diff-path-or-pr-ref>` | required | Path to a diff file, or a PR reference (`PR #123`, `gh pr view 123`) |
| `--fix` | off | After consolidation, dispatch a single fixer agent with the complete consolidated findings list |
| `--output` | `<diff-path>.review.md` | Path where the consolidated findings file is written |

---

## Workflow

### Step 1 — Inspect the diff

Before dispatching agents, read the diff to determine which file types are present:

- If any `.ts`, `.tsx`, `.cs`, or `.d.ts` files appear in the diff, include `type-design-analyzer` in the dispatch.
- Always include `code-reviewer` and `silent-failure-hunter`.

This check is intentionally lightweight — scan file extensions only, do not parse the diff content.

### Step 2 — Agent dispatch (parallel)

Launch all applicable agents concurrently. Do not wait for one before starting the next. Pass each agent:

- The diff path or PR reference
- A scratch output path for its raw findings

| Agent | Focus |
|-------|-------|
| `pr-review-toolkit:code-reviewer` | Code quality, project guidelines, style adherence |
| `pr-review-toolkit:silent-failure-hunter` | Error handling, catch blocks, silent fallback behavior |
| `pr-review-toolkit:type-design-analyzer` | Type design quality (TypeScript or C# files only) |

### Step 3 — Consolidation

After all agents complete:

1. Collect all raw findings from agent scratch outputs.
2. Deduplicate: findings that share the same `<file> + <line-or-symbol>` from different agents count as one finding; keep the highest severity assigned by any agent. Deduplication key: `<file>:<line>` takes precedence — if two findings share the same file and line number, they deduplicate regardless of differing symbol names. If two findings share the same file and symbol but differ by line number (e.g., a refactored function), deduplicate and keep the higher severity.
3. Sort by severity: CRITICAL → IMPORTANT → MINOR.
4. Write the consolidated findings file to `--output`.

### Step 4 — Fixer dispatch (optional)

If `--fix` was passed, dispatch a **single** fixer agent that receives:

- The consolidated findings file path
- The original diff or PR reference

The fixer processes all CRITICAL and IMPORTANT findings in one pass, in CRITICAL-first order. It does not invent fixes — it applies only what the findings specify. For findings where the required fix is ambiguous, it inserts a `// REVIEW: <finding>` comment rather than guessing.

**One fixer, not one per finding.** A single agent receives the complete consolidated findings list. This avoids redundant context-building and test-suite re-runs that would result from dispatching one agent per finding.

---

## Standard Findings Format

All agents must produce findings in this exact format, one finding per line:

```
[CRITICAL | IMPORTANT | MINOR] — <file>:<line-or-symbol>: "<current behavior (≤20 words)>" → "<required fix>"
```

**Severity guidance:**

| Severity | Use when |
|----------|----------|
| CRITICAL | Correctness bug, security issue, or data-loss risk — a reviewer would block the PR |
| IMPORTANT | Code quality problem that degrades reliability or maintainability; a reviewer would flag it |
| MINOR | Style, naming, or low-consequence inconsistency — worth fixing but not blocking |

Agents must not output prose summaries, only the structured finding lines. Each finding must be self-contained: a reader of only that line must understand the problem and the fix.

**Example findings:**

```
[CRITICAL] — src/auth/token.ts:42: "catch block swallows error silently" → "log error and re-throw or return typed error result"
[IMPORTANT] — src/api/client.cs:AuthResult: "success bool + nullable token as separate fields" → "use discriminated union or sealed class hierarchy"
[MINOR] — src/util/parse.ts:parseDate: "function name is ambiguous" → "rename to parseDateUtc or parseDateLocal to clarify timezone handling"
```

---

## Cross-references

- **Prerequisite:** `pr-review-toolkit` (`claude-plugins-official`) must be installed. This skill dispatches its agents directly.
- **Complementary:** `/adversarial-review-pr` (`docs@garrettmanley`) — structural PR review: description accuracy, work item consistency, scope completeness. Use after code review to layer structural checks onto the same PR.
- **Complementary:** `/adversarial-review-doc` (`docs@garrettmanley`) — document integrity review: structural problems, broken cross-references, stale claims, terminology drift. Use for markdown documents rather than code diffs.
- **Complementary:** `/reviewer-personas` (`review@garrettmanley`) — persona-perspective review: how named or archetype team members would react. Use after this skill to layer human perspective onto mechanical findings.
- **Fixer-only pass:** dispatch the fixer agent directly with an existing consolidated findings file and the original diff, bypassing agent re-dispatch.
