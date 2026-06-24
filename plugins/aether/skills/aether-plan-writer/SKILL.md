---
name: aether-plan-writer
description: Use when writing a new plan file under docs/engineering/plans/ or when the user invokes /plan. Wraps the issue-citation, value-justification, and retrospective rules so plan_issue_check.py won't reject the write.
version: 0.1.0
dependencies: []
---

# Aether plan writer

## When to use

Use before writing a new plan file under `docs/engineering/plans/`, or
when the user invokes `/plan`. Following these rules first stops the
enforcing hook from bouncing the write.

Plan files at `docs/engineering/plans/YYYY-MM-DD-NNN-<slug>-plan.md`
must satisfy three rules. The PostToolUse hook
`.claude/hooks/plan_issue_check.py` enforces all three on every Write.
Use this skill before writing the plan to avoid the hook bouncing
your edit.

## Rule 1 — Cite at least one GitHub issue with `#N`

Before writing the plan, find or file the tracking issue.

```bash
gh issue list --state open
# or, if none fits:
gh issue create --title "..." --label "type:..." --body "..."
```

The plan body must reference the issue at least once with the `#N`
shape (for example `#91`).

## Rule 2 — Include a `## Value Justification` section

Format requirements (the regex is exact — asterisks close BEFORE the
colon, not around the value):

```
## Value Justification

- **Impact** (1-5): 4 — rationale grounded in concrete user/system effect
- **Confidence** (1-5): 5 — rationale (proven pattern, scope clarity, etc.)
- **Effort** (hours): 5 — rationale (P1 ~2h, P2 ~1h, P3 ~2h)
- **Score**: 4.00  (impact × confidence / effort)
```

Common formatting failures the hook catches:

- `**Impact: 3**` — closes the asterisks AROUND the value (regex
  fails)
- Missing the `Score` line
- Score arithmetic wrong (`4 × 5 / 5` must be `4.00`, not
  `4` or `5.00`)
- Not enough decimals: `Score: 4` is rejected; use `4.00`

The hook auto-grandfathers completed plans (those with a
`## Retrospective` section already present), so legacy plans don't
need the block.

## Rule 3 — Add a Retrospective on completion

The Retrospective section must include `Closes #N`, `Updates #N`, or
`Follows up #N`. The hook auto-triggers `gh issue close` when it sees
`Closes #N` in a Retrospective.

**Pitfall:** during in-progress drafts, use `Updates #N` to avoid
prematurely closing the issue. Only flip to `Closes #N` when you're
ready to actually close it. (If you accidentally trigger
auto-close, run `gh issue reopen <N>` and switch the line back to
`Updates #N`.)

## Suggested template

Start from `docs/engineering/templates/plan-template.md` then add the
`## Value Justification` block. The plan structure that matches
project precedent:

```markdown
---
status: Draft
author: <name>
created: YYYY-MM-DD
diataxis: how-to
---

# NNN — <Title> — Plan (YYYY-MM-DD)

One paragraph on what this plan delivers and why. Tracks #N.

## Context

Why now. Constraints. Dependencies on other specs.

## Value Justification

- **Impact** (1-5): N — ...
- **Confidence** (1-5): N — ...
- **Effort** (hours): N — ...
- **Score**: X.YY  (impact × confidence / effort)

## Critical files to read before starting

1. `<path>` — why
...

## Task 1 — <name>

**Why.** ...
**Files.** ...
**Steps.**
1. ...

## Verification

**Plan complete when:** ...

## Retrospective

*Required. Fill in before marking this plan done.*

Updates #N (placeholder; flip to `Closes #N` on completion).

- What went as expected?
- What was harder than anticipated?
- ...
```

## See also

- `docs/engineering/conventions.md` — canonical engineering conventions
- `docs/engineering/templates/plan-template.md` — base template
- `docs/engineering/issues-workflow.md` — issue label taxonomy
- `.claude/hooks/plan_issue_check.py` — the enforcing hook
