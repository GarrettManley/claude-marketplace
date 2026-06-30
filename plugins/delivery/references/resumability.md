# Phase B resumability

`deliver` rides entirely on `superpowers:subagent-driven-development`'s own resume mechanism — it does
not invent a new ledger or hook into any crash-recovery infrastructure. This doc states exactly what
that buys you, and what it deliberately doesn't.

## What gets resumed

**Phase B (execute) task-level progress, and only that.** SDD's "Durable Progress" behavior is native
to the skill: at skill start it checks `"$(git rev-parse --show-toplevel)/.superpowers/sdd/progress.md"`
for a ledger; tasks already marked complete there are not re-dispatched, and execution resumes at the
first incomplete task. `deliver`'s step 0 checks for that same file before doing anything else — if it
exists with incomplete tasks, step 0 skips straight to step 7 (the `subagent-driven-development`
dispatch) instead of re-running Phase A, and SDD takes it from there using its own native logic.
`deliver` does not parse the ledger or duplicate SDD's resume mechanics in any way.

## What does not get resumed

**Phase A (plan) and Phase C (verify and land) are not resumable.** Both are short and already
idempotent in practice — re-running pre-plan-brief, plan authoring, doc-cluster, and plan review costs
little, and the completion gate / code review / land steps are meant to be re-run anyway each time
Phase B produces a new diff. No separate resume tracking is built for either phase. If a run is
interrupted during Phase A or Phase C, just start `/deliver` again from the top.

## How to tell a run is resuming vs. starting fresh

The step-0 echo is the only signal, and it's printed every run, right after the resolved-slot table:

- **No `.superpowers/sdd/progress.md` found** (the common case) — nothing extra is printed; the run
  proceeds through Phase A as normal.
- **Ledger found with incomplete tasks** — a one-line note: "Found an in-progress SDD ledger with N
  incomplete task(s) — resuming Phase B from the first incomplete task rather than starting fresh,"
  followed by skipping directly to step 7.

There is no other indicator and no separate status command — the echo at the top of the run is the
whole contract.

## Deliberately out of scope: `/recover` and session-crash recovery

This does **not** integrate with `/recover` or any session-crash-recovery infrastructure. That
infrastructure (a personal `recover` skill plus `SessionStart` sentinel hooks) lives entirely outside
this plugin, in user-level config, and is specific to one operator's machine setup — it has no business
being a dependency of a portable plugin. SDD's ledger needs none of it to be useful: it's a plain file
committed in the worktree, recoverable the same way SDD's own "Durable Progress" section describes —
`git log` plus reading the file — independent of whatever recovery tooling (or lack of it) the operator
has installed.
