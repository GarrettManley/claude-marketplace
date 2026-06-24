---
name: session-handoff
description: Write a thorough end-of-session handoff document using a structured 8-section schema (What We're Building / What WORKED / What Did NOT Work / What Has NOT Been Tried Yet / Current State of Files / Decisions Made / Blockers & Open Questions / Exact Next Step). Use when closing a work cluster, before hitting context limits, or anytime a future session needs to resume with zero re-learning. The heavyweight authoring depth for the same auto-injected `.remember/remember.md` that `remember` writes lightly — reach for it on high-stakes handoffs.
version: 0.6.0
dependencies: []
---

> Adapted from `affaan-m/everything-claude-code` at commit [`4774946d`](https://github.com/affaan-m/everything-claude-code/blob/4774946db57a072f9b878f233a80f2ec6f5ac342/commands/save-session.md) (MIT licensed). The "What Did NOT Work" section is the load-bearing piece — without it, a resumed session re-attempts known failures.

# Session Handoff

Capture the full state of a work session — what was built, what worked, what failed, what's left — and write it to the **auto-injected handoff file** (`.remember/remember.md`) so the next session picks up exactly where this one left off, with zero manual re-reading. This is the deep authoring depth of the *same* handoff channel `remember` writes lightly — not a separate file.

## When to Use

- End of a focused work cluster (a feature, a bug fix, a multi-day arc) before closing the session
- Before hitting context limits — save first, then start fresh
- After solving a non-trivial problem worth remembering
- Anytime you need to hand context to a future session and `remember`'s streaming notes feel too thin

**Not for:** Quick reminders ("remind me X tomorrow") — use `remember` instead. Lightweight breadcrumbs — use `remember`. Same file either way; this is just the heavyweight depth — reach for it when the cost of forgetting is high.

## Process

### 1. Gather context

Before writing the file, collect:

- Files modified this session (`git diff --stat` or recall from conversation)
- What was attempted, what worked, what failed (with exact error messages)
- Test/build status if relevant
- Any decisions made and why

### 2. Write the file

**Path:** Write to the **auto-injected handoff file** — use the path from the most recent `=== HANDOFF ===` block in this session's context (e.g., `Write next handoff to: ~/.remember/remember.md`, or a project-slug subdir like `~/.remember/<slug>/remember.md`). Fall back to `{project_root}/.remember/remember.md` if no `=== HANDOFF ===` block is present. This is the **same file `remember` writes** — `session-handoff` is just the deeper authoring depth. Read it first (a 1-line Read satisfies the write-check), then **overwrite** it with the handoff below; the latest handoff wins.

Because this file is **injected verbatim** at the next SessionStart, keep it focused — every line is re-read next session, so prune anything the next session won't act on.

Use this format. Do **not** skip sections — write "Nothing yet" or "N/A" if a section has no content. An incomplete file is worse than an honest empty section.

```markdown
# Session Handoff: <topic>

**Project:** <project name or path>
**Started:** <approx start time if known>
**Closed:** <current time>

## What We Are Building

<1-3 paragraphs. The goal, why it matters, how it fits into the larger system.
Enough context that someone with zero memory of this session understands the
intent.>

## What WORKED (with evidence)

<Only list things confirmed working. For each, name the evidence — test passed,
manual repro succeeded, deploy went through. Without evidence, demote to
"Not Tried Yet".>

- **<thing>** — confirmed by: <specific evidence>
- **<thing>** — confirmed by: <specific evidence>

## What Did NOT Work (and why)

<This is the most important section. Every failed approach with the EXACT reason
so the next session doesn't retry it. "Threw X error because Y" is useful;
"didn't work" is not.>

- **<approach>** — failed because: <exact reason / error message>
- **<approach>** — failed because: <exact reason / error message>

## What Has NOT Been Tried Yet

<Approaches that seem promising but weren't attempted. Specific enough that the
next session knows what to try.>

- <approach>
- <approach>

## Current State of Files

<Every file touched this session. Be precise about state.>

| File | Status | Notes |
| --- | --- | --- |
| `path/to/file.ts` | Complete | <what it does> |
| `path/to/file.ts` | In Progress | <what's done, what's left> |
| `path/to/file.ts` | Broken | <what's wrong> |
| `path/to/file.ts` | Not Started | <planned but not touched> |

## Decisions Made

<Architecture choices, tradeoffs accepted, approaches chosen. Prevents
relitigating settled decisions in the next session.>

- **<decision>** — reason: <why this over alternatives>

## Blockers & Open Questions

<Anything unresolved. Questions that came up. External dependencies waiting on.>

- <blocker / open question>

## Exact Next Step

<If known: the single most important thing to do when resuming. Specific enough
that resuming requires zero thinking about where to start.>

<If not known: "Next step not determined — review 'What Has NOT Been Tried Yet'
and 'Blockers' before deciding direction.">
```

### 3. Show the file to the user

After writing, display the full contents and ask:

```
Session handoff saved to <path>.

Does this look accurate? Anything to correct or add before we close?
```

Wait for confirmation before considering the handoff complete.

## Reading a handoff

The handoff **auto-injects** at the next SessionStart (in the `=== MEMORY === / --- remember.md ---` block) — no manual retrieval needed. To resume:

1. Re-read the injected handoff fully — do not summarize-then-act
2. Reconstruct context out loud: project / what we were doing / what worked / what NOT to retry / next step
3. Ask the user to confirm before touching any files
4. Lead with the "What Did NOT Work" section — it's the most likely thing a fresh session will accidentally retry

## When NOT to use

- Quick reminders or lightweight breadcrumbs — use `remember`
- Mid-task save before a context-window pressure event — `remember` is lighter; reach for handoff only if the cluster is closing
- Documenting a single decision — use `discipline:council` for the decision itself, then if the outcome is durable, add a one-line entry to `remember`

## Related

- `remember` — the lighter authoring depth for the *same* auto-injected `.remember/remember.md` handoff file; quick notes vs. this skill's full 8-section capture
- `discipline:checkpoint` — git-state delta detection mid-work
- `discipline:council` — when the next decision is itself the open question
- `superpowers:writing-plans` — when the handoff reveals enough scope for a real plan
