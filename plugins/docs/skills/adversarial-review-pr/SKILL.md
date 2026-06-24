---
name: adversarial-review-pr
description: Use when you need to adversarially review a pull request for description accuracy, work item consistency, commit message alignment, and cross-document sync obligations. Reviews the PR as a whole — not individual code changes. Complementary to pr-review-toolkit:code-reviewer (code quality) and /reviewer-personas (team-member perspective).
version: 0.1.0
dependencies: []
---

# Adversarial PR Review

A PR description written on day one is often stale by merge day: it describes intent, not what was actually changed. No automated code review tool checks whether the description matches the diff.

Dimension-based adversarial review for pull requests. Checks what automated code review tools miss: whether the PR description accurately reflects the diff, whether work item references resolve to real items of the right type, whether commit messages satisfy the project convention, and whether the PR fulfills any cross-document sync obligations it triggered.

This skill reviews the PR as a whole — scope, framing, and traceability. For code quality review, run `pr-review-toolkit:code-reviewer` and `pr-review-toolkit:silent-failure-hunter` first. For persona-perspective review before creating the PR, use `/reviewer-personas` from `review@garrettmanley`. This skill is complementary to `adversarial-review-doc` — use both for complete PR coverage.

## When to use

- Before merging any PR to verify the description matches the actual diff.
- When a PR touches multiple files or layers and the description was written early in development.
- When the PR references ADO work items that need to match the change type.
- When the repo enforces a commit message convention and manual commits have been added.
- When a PR edits files that carry canonical-home or sync-obligation annotations.

---

## Interface

```
/adversarial-review-pr <pr-url-or-id>
  [--repo <repo>]     # e.g., your-org/your-repo or owner/repo
  [--fix]             # auto-dispatch fixer for description corrections
```

**Arguments:**

| Argument | Default | Description |
|----------|---------|-------------|
| `<pr-url-or-id>` | required | GitHub PR URL or numeric ID |
| `--repo` | inferred from URL or git remote | Repository in `owner/repo` form; required when passing a bare numeric ID |
| `--fix` | off | After consolidation, dispatch a fixer agent that applies description corrections to the PR body. Only description-accuracy findings are auto-fixable; other finding types surface as comments for human action |

---

## Workflow

### Step 1 — Fetch PR data

Collect the following before running any dimension:

- **PR description and title** — via `gh pr view <id> --repo <repo> --json title,body,commits`
- **Git diff** — `gh pr diff <id> --repo <repo>` (full unified diff)
- **Commit list** — each commit's subject line and body from the `commits` JSON field
- **Work item references** — all `AB#NNNN` tokens in the title and body; all URLs matching `dev.azure.com/.*/workItems/NNNN` in the body
- **Commit message rules** — check for `commit-message-rules.yaml` at the workspace root; if present, load the rule set

Fetch all inputs before dispatching dimensions. Do not run dimension checks against incomplete data.

### Step 2 — Dimension checks (parallel)

Run all four dimensions concurrently. Each dimension operates on the data fetched in Step 1.

### Step 3 — Consolidation

After all dimension checks complete:

1. Collect all findings.
2. Deduplicate: identical `<dimension>` + `"current text"` pairs count as one finding; keep the highest severity.
3. Sort by severity: CRITICAL → IMPORTANT → MINOR.
4. Print the consolidated findings list to stdout.

### Step 4 — Fixer dispatch (optional)

If `--fix` was passed, dispatch a fixer agent with:
- The consolidated findings list
- The PR number and repo

The fixer edits only the PR description (via `gh pr edit`). It applies description-accuracy findings only. For all other finding types, it posts a PR comment listing the items that require human action. The fixer does not invent corrections — it applies only what the findings specify. For findings where the required fix is ambiguous, it inserts `<!-- REVIEW: <finding> -->` in the description rather than guessing.

---

## Standard Findings Format

All dimension checks must produce findings in this exact format, one finding per line:

```
[CRITICAL | IMPORTANT | MINOR] — <dimension>: "<current text (≤20 words)>" → "<required fix>"
```

**Severity guidance:**

| Severity | Use when |
|----------|----------|
| CRITICAL | The PR description or commit makes a false claim about the diff; a required work item reference is missing or wrong-typed; a hard-blocked sync obligation is unaddressed |
| IMPORTANT | Inconsistency or omission that degrades PR traceability; a reviewer would flag it |
| MINOR | Style inconsistency, nit, or low-consequence gap that is worth noting but not blocking |

Each finding must be self-contained: a reader of only that line must understand the problem and the required fix.

**Example findings:**

```
[CRITICAL] — description-accuracy: "Adds rate limiting to all API endpoints" → "Diff adds rate limiting only to /api/devices; /api/users is unmodified — correct the scope claim"
[IMPORTANT] — work-item-consistency: "AB#4821 referenced but resolves to a Bug" → "PR implements a new feature; link to a User Story work item instead, or confirm the fix classification with the team"
[IMPORTANT] — commit-message-alignment: "feat(auth): Add token rotation" → "Commit body is missing required Tested: section per commit-message-rules.yaml"
[MINOR] — cross-document-sync: "appsettings.Production.json modified" → "File carries canonical-home annotation pointing to SaaS config wiki page; verify the wiki is up to date"
```

---

## Dimensions

### 1. Description accuracy

Compare every claim in the PR title and description against the actual git diff.

**Check for:**

- **Overclaims** — the description says a change was made but the diff does not contain it. Common patterns: "Updates all X," "Refactors the Y module," "Removes deprecated Z."
- **Underclaims** — the diff contains a significant change not mentioned in the description. Threshold: any change to a file not in the same directory tree as the **stated focus** (the file path pattern or directory named in the PR title or description), or any deletion of more than 5 lines (heuristic; adjust judgment based on file type — a 5-line deletion in a config file is significant; in a generated file it may not be).
- **Wrong file paths** — the description names a specific file or directory that does not appear in the diff.
- **Incorrect scope statements** — "minimal change," "no behavior change," "only affects tests" when the diff contradicts the claim.

Produce one finding per discrepancy. Quote the exact claim from the description and specify what the diff shows instead.

### 2. Work item consistency

For every `AB#NNNN` reference found in the PR title and description:

1. Resolve the work item using `az boards work-item show --id NNNN`.
2. Check that the work item **exists** (finding: CRITICAL if the ID resolves to nothing).
3. Check that the work item **type matches the change**:
   - Bug fix PR (type prefix `fix:` in commits, or "fixes," "resolves," "bug" in description) → work item should be a Bug or a Task under a Bug.
   - Feature or new-capability PR → work item should be a User Story, Feature, or Task under a User Story.
   - Chore / maintenance PR → Task or work item type is less constrained, but should not be a Bug.
4. Check that every `Issue:` URL in the description resolves to a real work item.

Flag type mismatches as IMPORTANT. Flag non-resolving references as CRITICAL.

### 3. Commit message alignment

For each commit in the PR:

1. Check the **subject line** for the required `<type>(<scope>): <summary>` format. If `commit-message-rules.yaml` is present at the workspace root, use its `types` and `scopes` lists as the allowed values.
2. Check for a **body** — a blank line followed by at least one non-empty line after the subject. Flag commits with a subject-only message as IMPORTANT.
3. Check for a **`Tested:` section** — if `commit-message-rules.yaml` requires it (key `required-sections` includes `Tested`), flag its absence as IMPORTANT.
4. Check that the **type** matches the nature of the change: `fix:` commits should address a defect, `feat:` commits should add capability, `chore:` commits should not touch production code.

Produce one finding per non-conforming commit. Quote the commit subject.

### 4. Cross-document sync obligations

Inspect every modified file in the diff for sync obligation annotations. The canonical forms to look for:

- `# Canonical home: <reference>` (Python, YAML, shell)
- `// Canonical home: <reference>` (C#, JavaScript, C)
- `<!-- Canonical home: <reference> -->` (Markdown, HTML)
- `Canonical home:` anywhere in a file's first 20 lines

For each annotation found:

1. Extract the referenced document from the annotation.
2. Check whether the PR description or linked work items mention updating that document.
3. If no mention exists, flag it as IMPORTANT (the PR may have left the canonical source out of sync).

Also check for files with well-known sync pairs. The following are built-in defaults; projects can extend this list via workspace config:

- `appsettings.*.json` → look for a paired wiki page reference in the PR description
- `*.proto` → look for a mention of the generated code or consumer updates
- Any file whose path contains `ssot`, `canonical`, or `single-source`

The list above is not exhaustive. When in doubt, check whether the modified file's first 20 lines carry a `Canonical home:` annotation.

Flag each unaddressed sync obligation with the file name, the annotation text, and the referenced document.

---

## Cross-references

- **Code quality:** run `pr-review-toolkit:code-reviewer` and `pr-review-toolkit:silent-failure-hunter` before this skill. This skill does not review code changes — it reviews the PR as a whole.
- **Persona perspective:** use `/reviewer-personas` from `review@garrettmanley` for team-member-perspective review before creating the PR. This skill is complementary: `adversarial-review-pr` finds factual and traceability problems; `/reviewer-personas` surfaces how a reviewer would react.
- **Document integrity:** if the PR modifies a design document or wiki page, also run `/adversarial-review-doc` on that document. `adversarial-review-pr` checks sync obligations at the PR level; `adversarial-review-doc` checks the document's internal integrity.
- **Commit message convention:** the commit-message-alignment dimension reads `commit-message-rules.yaml` from the workspace root. If no file is found, the dimension checks only the `<type>(<scope>): <summary>` format and the presence of a body.
- **Prose quality:** when `--fix` edits the PR description, the resulting prose is governed by `/tech-writing` (`docs@garrettmanley`) universal rules and `/writing-style` (project-specific voice, e.g., `your-style@your-org`). Run both on the edited description if prose quality matters.
