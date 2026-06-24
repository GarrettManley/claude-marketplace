---
name: adversarial-review-plan
description: Use when you need to adversarially review an implementation or work plan BEFORE executing it — to challenge its premise, test feasibility, and cut scope. Dispatches dimension agents plus three plan-reviewer archetypes (plan-skeptic, plan-feasibility-auditor, plan-scope-cutter) in parallel, consolidates findings into CRITICAL / IMPORTANT / MINOR severity buckets, and optionally auto-dispatches a fixer. Complements /adversarial-review-doc, which checks document integrity rather than plan soundness.
version: 0.1.0
dependencies: []
---

# Adversarial Plan Review

A plan that reads well can still be the wrong plan: solving a problem not worth solving, hiding complexity behind "just," shipping speculative scope, or changing live state with no way back. Reviewing your own plan rarely catches these — you wrote it because you already believe it.

Dimension-based adversarial review for any markdown implementation or work plan, run **before** execution. Dispatches one agent per dimension in parallel, **plus** three signature plan-reviewer archetypes that attack the plan's premise, feasibility, and scope. Consolidates all findings with deduplication and severity sorting, and optionally auto-dispatches a fixer.

This skill checks whether a plan is worth executing and survivable. For document-integrity review (broken cross-references, stale claims, terminology drift), use `/adversarial-review-doc`. For persona-perspective review of a finished artifact, use `/reviewer-personas` from `review@garrettmanley`. These are complementary.

## When to use

- Before executing any implementation or work plan, especially a multi-step or multi-day one.
- After writing a plan yourself — you are the worst reviewer of your own premise.
- When a plan is large enough that a human reviewer is likely to miss a hidden dependency or a speculative phase.
- When you want a go/no-go signal and a list of what to cut before committing effort.

---

## Interface

```
/adversarial-review-plan <plan-path>
  [--dimensions dim1,dim2,...]   # override active dimensions; defaults to all 6
  [--fix]                        # auto-dispatch fixer after consolidation
  [--output <path>]              # findings file path; defaults to <plan-path>.review.md
```

**Arguments:**

| Argument | Default | Description |
|----------|---------|-------------|
| `<plan-path>` | most recent `~/.claude/plans/*.md` | Absolute or repo-relative path to the markdown plan. Any plan works (e.g., `~/.claude/plans/*.md`, `docs/engineering/plans/*.md`, or an explicit path). If omitted, defaults to the most recently modified file in `~/.claude/plans/`. |
| `--dimensions` | all 6 | Comma-separated subset: `feasibility`, `value-justification`, `clarity`, `completeness`, `risk-rollback`, `scope-cut` |
| `--fix` | off | After consolidation, dispatch a fixer agent that reads the findings file and applies changes to the plan |
| `--output` | `<plan>.review.md` | Path where the consolidated findings file is written |

---

## Workflow

### Step 1 — Resolve the plan path and workspace dimensions

If no `<plan-path>` is given, select the most recently modified `~/.claude/plans/*.md` file. Report which file was chosen before proceeding.

Then check for additional dimension files at:

```
<workspace-root>/.claude/adversarial-dimensions/plan/
```

Any `.md` files found there are loaded as additional dimensions, each getting its own parallel agent. **Conflict rule:** a workspace dimension file with the same base name as a built-in dimension (e.g., `feasibility.md`) **overrides** the built-in for this run. A different name **augments** the built-in set.

This is the extension point: domain-specific plugins drop dimension files here to extend plan review without modifying this skill.

### Step 2 — Parallel dispatch (dimensions + archetype agents)

Launch all of the following concurrently. Do not wait for one before starting the next.

**Dimension agents** — one per active dimension (built-in, minus any overridden by workspace files, plus any workspace additions). Pass each:
- The plan path
- Its dimension prompt from `dimensions/<name>.md` (or the workspace dimension file path)
- A scratch output path for its raw findings: `<output-dir>/<dimension-name>.raw.md`, where `<output-dir>` is the directory of the `--output` file. Scratch files are deleted after consolidation.

**Plan-reviewer archetype agents** — dispatched alongside the dimensions for adversarial depth. Call the `Agent` tool with the plugin-scoped `subagent_type`:

| Agent (`subagent_type`) | Lens |
|-------------------------|------|
| `docs:plan-skeptic` | Should this be done at all? Is there a materially simpler path? Is the premise wrong? |
| `docs:plan-feasibility-auditor` | Hidden complexity, unrealistic effort/sequencing, missing dependencies, unverifiable steps, untested assumptions |
| `docs:plan-scope-cutter` | YAGNI, what to cut, over-engineering, premature abstraction |

The agent definition **is** the persona — its system prompt carries the full pushback triggers, NOT-covered boundary, and severity rubric. Do not paste any persona text into the prompt. Pass each archetype the plan path (by reference) and instruct it to emit findings in the Standard Findings Format below, written to its own scratch path `<output-dir>/<agent-name>.raw.md`. The archetypes' native severity vocabulary (`blocker` / `must_fix` / `nit` / `signal` / `praise`) maps to the consolidated buckets as: `blocker` to CRITICAL, `must_fix` to IMPORTANT, `nit` / `signal` to MINOR (`praise` is dropped from the findings file).

### Step 3 — Consolidation

After all agents complete:

1. Collect all raw findings files.
2. Deduplicate: identical `<Step/section>` + `"current text"` pairs from different agents count as one finding; keep the highest severity.
3. Sort by severity: CRITICAL → IMPORTANT → MINOR.
4. Write the consolidated findings file to `--output`.

### Step 4 — Fixer dispatch (optional)

If `--fix` was passed, dispatch a **single** fixer agent that receives:
- The consolidated findings file path
- The original plan path

The fixer applies CRITICAL and IMPORTANT findings, in CRITICAL-first order. MINOR findings are not applied — they remain in the findings file for human review. It does not invent fixes — it applies only what the findings specify. For findings where the required fix is ambiguous, it inserts a `<!-- REVIEW: <finding> -->` comment rather than guessing. A premise-level CRITICAL (e.g., "the plan should not be done") is surfaced at the top of the fixed plan as a `<!-- BLOCKER: <finding> -->` comment for the author to resolve — the fixer does not silently rewrite the plan's goal.

To run a fixer-only pass against an existing findings file without re-running dimensions, call the fixer agent directly with the findings file and plan paths.

---

## Standard Findings Format

All dimension agents and archetype agents must produce findings in this exact format, one finding per line:

```
[CRITICAL | IMPORTANT | MINOR] — <Step/section>: "<current text (≤20 words)>" → "<required fix>"
```

**Severity guidance:**

| Severity | Use when |
|----------|----------|
| CRITICAL | Executing the plan as written would waste the effort, stall, or do harm: wrong premise, impossible step, irreversible action with no rollback, or a missing prerequisite without which the goal is unreachable |
| IMPORTANT | A gap that degrades the plan's reliability — a reviewer would block on it: unverified load-bearing assumption, missing acceptance criterion, premature abstraction, absent lifecycle phase |
| MINOR | Low-consequence improvement worth making but not blocking: optimistic estimate, minor gold-plating, recoverable ambiguity |

Agents must not output prose summaries, only the structured finding lines. Each finding must be self-contained: a reader of only that line must understand the problem and the fix.

**Example findings:**

```
[CRITICAL] — § Goal: "Build a plugin registry to load reviewers dynamically" → "Premise unverified: only one reviewer exists; a static list meets the goal — justify the registry or cut it"
[CRITICAL] — Step 4 Migrate data: "Drop the old table after the backfill" → "No rollback path if backfill is wrong; add a verification gate and retain the old table for one release"
[IMPORTANT] — Step 2: "Just wire up the new auth flow" → "the word 'just' hides token-refresh and session-migration steps; add them as explicit steps with acceptance criteria"
[MINOR] — § Phase 3: "Add a --format flag for future output types" → "No requirement asks for alternate output; defer the flag until a second format is needed"
```

---

## Dimensions

The six built-in dimensions live in `dimensions/` alongside this file:

| Dimension file | Focus |
|----------------|-------|
| `feasibility.md` | Hidden complexity, sequencing, missing dependencies, unverifiable steps, untested assumptions |
| `value-justification.md` | Do-nothing baseline, named consumer, effort/value proportionality, problem-vs-solution framing |
| `clarity.md` | Ambiguous instructions, undefined referents, implicit decisions, missing acceptance criteria |
| `completeness.md` | Placeholders, missing lifecycle phases, untouched touchpoints, missing final verification |
| `risk-rollback.md` | Irreversible steps, non-idempotency, blast radius, mid-flow failure handling, cutover windows |
| `scope-cut.md` | YAGNI, premature abstraction, speculative flexibility, gold-plating, deferrable phases |

To use only a subset, pass `--dimensions feasibility,risk-rollback`.

To add a dimension without modifying this skill, create a `.md` file at:

```
<workspace-root>/.claude/adversarial-dimensions/plan/<dimension-name>.md
```

Follow the same prompt format as the built-in dimension files: state the focus, specify the output format, instruct the agent to report only (no fixes).

---

## Cross-references

- **Complementary:** `/adversarial-review-doc` (`docs@garrettmanley`) — document integrity review (structure, cross-references, stale claims, terminology). Use for a finished markdown document rather than a plan awaiting execution.
- **Complementary:** `/adversarial-review-code` (`docs@garrettmanley`) — correctness review of a code diff. Use after a plan is executed, on the resulting changes.
- **Complementary:** `/reviewer-personas` (`review@garrettmanley`) — persona-perspective review. Use to layer team-member reactions onto the structural plan findings.
- **Archetype agents:** `docs:plan-skeptic`, `docs:plan-feasibility-auditor`, `docs:plan-scope-cutter` — dispatched by this skill; each can also be invoked directly for a single-lens pass.
- **Fixer-only pass:** dispatch a fixer agent with the consolidated findings file path and plan path directly, bypassing dimension and archetype re-dispatch.
