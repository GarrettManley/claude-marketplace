---
name: deliver
description: Drive one body of work end-to-end through the delivery lifecycle — plan, adversarial plan review, subagent execution, completion gate, adversarial code review, land, retrospective — binding project-specific steps from .claude/delivery.local.md.
argument-hint: [<work-target>]
---

# /deliver

Deliver **$ARGUMENTS** (a directory like `@./some-app`, an issue reference, or a prose description;
if empty, ask the user what the body of work is) through the full delivery lifecycle.

Invoke the `deliver` skill and follow it exactly. It will:

0. If the work-target is too vague or exploratory for `writing-plans` to work from (see the skill's
   Phase 0 trigger), first run `retrospective:pre-plan-brief` then dispatch `superpowers:brainstorming`
   to produce an approved design spec, stopping there rather than auto-handing off into
   `writing-plans` — skip this step when a spec already exists or the work-target is already concrete.
1. Read `<repo>/.claude/delivery.local.md`, resolve the project slots, and **print the resolved-slot
   table** before anything else — then check for an existing SDD ledger
   (`.superpowers/sdd/progress.md`); if one exists with incomplete tasks, resume Phase B execution
   directly instead of re-running plan authoring and review.
2. Run the lifecycle: pre-plan brief → write plan (+ project plan-writer) → doc cluster → adversarial
   plan review (gated: CRITICAL/IMPORTANT resolved or deferred) → approval → subagent execution (with
   a worktree-freshness guard and an instruction telling subagent-driven-development to stop after its
   final review rather than auto-handing off) → edit checklist → completion gate (positive-evidence
   only — fresh command output and exit code, not a clean terminal state) → whole-branch adversarial
   code review (wider scope, no down-routed model) → land (Hybrid: `finishing-a-development-branch`'s
   menu when no `land-policy` is set, the inline policy verbatim when set to a recognized verb, halt
   and surface when set to an unrecognized value) → retrospective.

There are no flags — project behavior binds from the config file, not the command line. See the
`deliver` skill for the slot table, the gate checklists, the config schema, and the landing policy.
