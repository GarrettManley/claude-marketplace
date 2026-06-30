---
name: deliver
description: Use when you want to drive one body of work end-to-end through the full delivery lifecycle in a single orchestrated pass — plan, adversarial plan review, subagent execution, completion gate, adversarial code review, land, and retrospective. Composes superpowers + docs + retrospective skills; the project-specific plan-writer / doc-cluster / edit-checklist steps bind per-repo via .claude/delivery.local.md, so the same skill drives a rigor-heavy repo and a bare one without edits.
version: 0.2.0
dependencies: ["docs", "retrospective"]
---

# Deliver

Shipping a body of work well is a *sequence*, not a single act: surface what prior retros already
learned, write a plan, prove the plan is worth executing, execute it under review, prove it is
actually done, review the resulting diff, land it the way the repo lands work, and capture what you
learned. Each step already exists as a skill somewhere — but stitched by hand they get retyped,
reordered, or skipped under pressure. `deliver` is the fixed spine that runs them in order.

The spine is project-agnostic. The few steps that differ per repo — *how* a plan is written, *which*
companion docs must ship, *what* the pre-commit checklist is — are **slots** that bind from a per-repo
config file. A repo with rich conventions (its own plan-writer, doc-cluster, edit-checklist skills)
gets full rigor; a bare repo gets sensible generic defaults. Same skill, no edits.

This skill **orchestrates**; it does not reimplement. Every step delegates to a real skill (or a
built-in fallback when that skill is absent). It is a playbook you follow across a session, not an
automated runner — the approval and landing gates are deliberately human.

## When to use

- You are about to take on "the next substantial piece of work" in a repo and want the whole
  plan → execute → review → land → retrospect arc driven in one consistent pass.
- You keep retyping the same chain of `/writing-plans`, `/adversarial-review-plan`,
  `/plan-completion`, `/adversarial-review-code`, `/plan-retrospective` and want it captured once.
- A repo has its own plan/doc/checklist skills and you want them slotted into the standard lifecycle
  automatically rather than remembered by hand.

Do **not** use it for a one-line fix or a quick question — the lifecycle overhead is the point only
when the work is substantial enough to plan.

## Interface

```
/deliver [<work-target>]
```

- **`<work-target>`** (optional) — what to deliver: a directory like `@./some-app`, an issue
  reference, or a prose description. If omitted, ask the user what the body of work is.

There are **no flags.** Project-specific behavior binds from `<repo>/.claude/delivery.local.md`
(see Configuration), not from the command line.

### Slots and resolution

Three steps are configurable. Each resolves **2-level**:

> `<repo>/.claude/delivery.local.md` frontmatter  >  generic default (or *skip*)

| Slot | Generic default | Purpose |
|------|-----------------|---------|
| `plan-writer` | `superpowers:writing-plans` only | How the plan is authored. A bound project skill runs **after** `writing-plans` to layer repo-specific rules (issue citation, value justification, etc.). |
| `doc-cluster` | *skip* | Decide which companion docs (spec / ADR / threat model / runbook / user guide) must land in the same change. |
| `edit-checklist` | *skip* | Repo-specific pre-commit ground-truth checklist run before declaring work done. |
| `land-policy` | `finishing-a-development-branch` (Hybrid) | How work lands (see Landing policy) — unset hands the land off to `superpowers:finishing-a-development-branch`; a set value (`ff-only`/`pr`/`direct`) is honored inline instead. |

The five **fixed** steps are not configurable — they are always the same generic skills:
`retrospective:pre-plan-brief`, `docs:adversarial-review-plan`,
`superpowers:subagent-driven-development` (+ the Workflow tool), `retrospective:plan-completion`,
`docs:adversarial-review-code`, `retrospective:plan-retrospective`.

### Availability (best-effort)

Before invoking any slot or fixed step, confirm its skill is available (it appears in your skill
list / loads via the Skill tool).

- A **bound slot** whose skill is unavailable → print
  `slot <name>: bound to <slug> but unavailable — skipping` and continue.
- A **fixed step** whose skill is unavailable → fall back:
  `superpowers:writing-plans` → author the plan directly in plan mode;
  `superpowers:subagent-driven-development` → dispatch Agent/Workflow directly;
  `superpowers:finishing-a-development-branch` (Hybrid landing, unset `land-policy`) → present the
  same merge/PR/keep/discard menu manually;
  the `docs:*` review and `retrospective:*` steps have no built-in equivalent — announce that the
  step is skipped because its plugin is not installed, and recommend enabling it.

This keeps `deliver` runnable anywhere while staying honest about what it could not run.

### Resolved-slot echo (do this first, every run)

Step 0 of every run: read `<repo>/.claude/delivery.local.md` (if present), resolve all slots, and
**print the resolved-slot table** before doing anything else, e.g.:

```
deliver — resolved slots (myproject):
  plan-writer    = myproject:plan-writer
  doc-cluster    = myproject:doc-cluster
  edit-checklist = myproject:edit-checklist
  land-policy    = ff-only
```

or, with no config file:

```
deliver — resolved slots (no delivery.local.md):
  plan-writer    = superpowers:writing-plans
  doc-cluster    = skip
  edit-checklist = skip
  land-policy    = finishing-a-development-branch
```

This echo is the contract: it shows the operator exactly which path the run will take.

## Configuration

Bind project steps in `<repo>/.claude/delivery.local.md`. Only the YAML frontmatter is read (by this
skill, via the Read tool — there is no hook and no enforcement; this is a best-effort convention, not
a deterministic parser). The body is documentation. Frontmatter keys, all optional:

```yaml
---
# <repo>/.claude/delivery.local.md
# Resolution: this file > generic default. Omit a key to take the default.
plan-writer: myproject:plan-writer        # omit -> superpowers:writing-plans only
doc-cluster: myproject:doc-cluster        # omit -> skip
edit-checklist: myproject:edit-checklist  # omit -> skip
land-policy: ff-only                      # omit -> finishing-a-development-branch (Hybrid)
---
```

`land-policy` accepts a short verb the Landing-policy step understands (e.g. `ff-only`, `pr`,
`direct`, or the explicit `ask` override). Slot values are `plugin:skill` slugs.

## Workflow

Work the three phases in order. Announce each step as you enter it.

### Phase A — Plan (in plan mode)

1. **Resolve + echo.** Read the config, resolve slots, print the resolved-slot table (above). Then
   check for an existing Phase B ledger: `cat "$(git rev-parse --show-toplevel)/.superpowers/sdd/progress.md"`
   (the same path `superpowers:subagent-driven-development` itself reads — see
   `references/resumability.md`). If it exists and lists incomplete tasks, print a note immediately
   after the resolved-slot table, e.g. "Found an in-progress SDD ledger with N incomplete task(s) —
   resuming Phase B from the first incomplete task rather than starting fresh," and skip directly to
   step 7 — Phase A (steps 2-6: pre-plan brief, plan authoring, doc cluster, plan review, approval) was
   already completed in the prior session that produced this ledger. `deliver` does not parse the
   ledger itself or duplicate SDD's resume logic; step 7's dispatch to `subagent-driven-development`
   resumes on its own, natively. If no ledger is found (the common case), proceed through Phase A
   unchanged.
2. **Pre-plan brief** — `retrospective:pre-plan-brief` on the work area, so a known issue from a
   prior cycle does not silently recur.
3. **Write the plan** — `superpowers:writing-plans`. Then, if the `plan-writer` slot is bound, run
   that skill to layer the repo's plan rules (a project plan-writer that already emits a
   value-justification block makes a separate value step unnecessary).
4. **Doc cluster** — if the `doc-cluster` slot is bound, run it to determine which companion docs
   must land with this work. Skip cleanly if unbound.
5. **Adversarial plan review** — `docs:adversarial-review-plan` against the plan file. **Only
   proceed when this gate passes:**
   - all CRITICAL findings resolved;
   - all IMPORTANT findings resolved or explicitly deferred with a stated reason;
   - the findings file committed alongside the plan.
6. **Approval** — present the finalized plan and exit plan mode for the user's sign-off.

### Phase B — Execute

7. **Subagent-driven execution** — `superpowers:subagent-driven-development` for independent tasks;
   reach for the **Workflow tool** when tasks fan out in parallel (per the standing orchestration
   defaults). Keep main context for synthesis and the approval/landing gates.
   - **Worktree-freshness guard.** Before live-executing in a freshly created worktree, run
     `git merge-base --is-ancestor <local-working-branch> <worktree-branch>` (or
     `git log <worktree-branch>..<local-working-branch> --oneline`), where "local working branch" is
     the branch `deliver` was invoked from. If the local branch has commits not yet in the worktree's
     branch point, **stop and warn** — present the missing commits and ask whether to rebase the
     worktree or proceed knowingly. Do not silently continue.
   - **Stop SDD before its own hand-off.** Instruct `subagent-driven-development` to stop after its
     final whole-branch review and **not** trigger its documented auto-hand-off into
     `superpowers:finishing-a-development-branch`. This is a real conflict: SDD's process chains
     straight from the final reviewer into `finishing-a-development-branch`, which would skip
     `deliver`'s own steps 8-11 (edit checklist, completion gate, code review, land) — those own the
     post-execution sequence instead. State this in the dispatch so SDD ends at the final review.
   - **No fabrication on subagent failure.** If a dispatched subagent (implementer, task reviewer, or
     the per-task SDD review) fails or returns partial output, refuse to synthesize a result over the
     gap — surface the failure and its partial progress rather than inferring or fabricating what the
     subagent would have found. (The per-task SDD reviews here are down-routed for cost; the
     whole-branch review at step 10 is not — see step 10.)
8. **Edit checklist** — if the `edit-checklist` slot is bound, run it against the diff before
   declaring the work done. Skip cleanly if unbound.

### Phase C — Verify and land

9. **Completion gate** — `retrospective:plan-completion`, hardened with
   `superpowers:verification-before-completion`'s Iron Law as the mechanism: run the command → read
   the output and exit code → only then claim done. **A clean terminal state is not evidence of a
   correct outcome when any silent-catch-and-continue path exists** — absence of an error is not
   fresh positive evidence. **Only proceed when this gate passes:**
   - every plan checkbox ticked;
   - the Iron Law evidence (command + output + exit code) captured for each verification criterion;
   - no unresolved `<!-- REVIEW -->` markers.

   If the gate reports blockers, clear them and re-run; do not proceed on an incomplete plan.
10. **Adversarial code review** — `docs:adversarial-review-code` on the resulting diff, run at
    **wider scope and without a down-routed model** (omit any `model` override so the review inherits
    the session's capability tier) — this is the whole-branch review, distinct from the down-routed
    per-task SDD reviews at step 7. Apply the same no-fabrication rule as step 7: a failed or
    incomplete reviewer subagent is a surfaced failure, never a synthesized result. **Only proceed
    when this gate passes:**
    - all CRITICAL/IMPORTANT findings fixed or explicitly deferred with a stated reason;
    - the whole-branch review actually ran at the wider scope described above, not just the per-task
      diffs already covered in step 7.

    Dispatch a fixer or fix inline, then re-verify.
11. **Land** — see Landing policy (Hybrid). Propose the exact commands; land only on explicit
    authorization.
12. **Retrospective** — `retrospective:plan-retrospective` to capture what worked, the friction, and
    concrete follow-ups, and clear the pending marker.

## Landing policy (Hybrid)

Resolve how work lands — exactly two cases, both exhaustive over "set" vs "unset":

- **`land-policy` unset** in `delivery.local.md` → delegate to
  `superpowers:finishing-a-development-branch` — its 4-option menu (merge locally / PR / keep as-is /
  discard) plus worktree cleanup, the purpose-built lander that `subagent-driven-development` itself
  terminates in. This is the default when a repo has not opted into an inline policy; the repo's
  stated branch-and-merge convention (its `CLAUDE.md` / `AGENTS.md`), if any, is superseded by this
  delegation rather than consulted separately.
- **`land-policy` set** (`ff-only` / `pr` / `direct` / `ask`) → honor the inline policy verbatim,
  exactly as before: `ff-only` (rebase onto the main branch → `git merge --ff-only` → push → delete
  the branch), `pr` (open a pull request and stop), `direct` (commit to the working branch), `ask`
  (always confirm with the user before proposing a land shape — distinct from the *unset* case above,
  which delegates to `finishing-a-development-branch` instead of asking). This branch's behavior is
  unchanged by the Hybrid update — it preserves existing inline bindings (e.g. a repo pinned to
  `ff-only`) exactly as they already work.

All existing invariants hold regardless of path: **always propose the exact commands and land only on
explicit user authorization — never auto-push.** This holds even when `land-policy` is set: the
config chooses the *shape* of the land, the human authorizes the *act*. A multi-step land (rebase →
ff-only → push) is non-idempotent; if a step fails mid-way (e.g. a rebase conflict), stop and surface
it rather than forcing through — the same rule `finishing-a-development-branch` applies to its own
merge/discard paths.

## Cross-references

`deliver` composes these — it does not replace them; invoke any directly when you want just that step:

- `pre-plan-brief`, `plan-completion`, `plan-retrospective` (`retrospective@garrettmanley`) — the
  lifecycle gates; `deliver` runs them as fixed steps.
- `adversarial-review-plan`, `adversarial-review-code` (`docs@garrettmanley`) — the two review gates;
  `adversarial-review-code` composes `pr-review-toolkit` (external, git-hash-pinned in the official
  marketplace, no semver) internally — also best-effort.
- `writing-plans`, `subagent-driven-development`, `finishing-a-development-branch`,
  `verification-before-completion` (`superpowers`, external) — plan authoring, execution, hybrid
  landing (unset `land-policy`), and the completion-gate Iron Law respectively; best-effort, with
  built-in fallbacks when superpowers is not installed.
- `dependencies` in `plugin.json` (`["docs", "retrospective"]`) is advisory installer metadata, not a
  hard runtime check — an install lacking either plugin keeps working via the Availability
  (best-effort) fallbacks above, just with those steps announced and skipped.
- Project step-skills bind via config — for example a repo's own plan-writer, doc-cluster, and
  edit-checklist skills. Bindings live only in that repo's `delivery.local.md`, never here.
- `references/resumability.md` — what step 0's ledger check resumes (Phase B only) and what it
  deliberately doesn't (Phase A, Phase C, `/recover` integration).
