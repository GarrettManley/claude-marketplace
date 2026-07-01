---
name: deliver
description: Use when you want to drive one body of work end-to-end through the full delivery lifecycle in a single orchestrated pass — plan, adversarial plan review, subagent execution, completion gate, adversarial code review, land, and retrospective. Also use when the work-target is too vague or exploratory to plan yet — an optional design phase feeds the resulting approved design spec into the same pass. Composes superpowers + docs + retrospective skills; the project-specific plan-writer / doc-cluster / edit-checklist steps bind per-repo via .claude/delivery.local.md, so the same skill drives a rigor-heavy repo and a bare one without edits.
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
- The work isn't understood well enough to plan yet — `deliver` can start at an optional design phase
  (Phase 0, see Workflow) instead of requiring a plan-ready work-target, and feed the resulting
  approved design spec into plan authoring.

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

The steps below are configurable. Each resolves **2-level**:

> `<repo>/.claude/delivery.local.md` frontmatter  >  generic default (or *skip*)

| Slot | Generic default | Purpose |
|------|-----------------|---------|
| `plan-writer` | `superpowers:writing-plans` only | How the plan is authored. A bound project skill runs **after** `writing-plans` to layer repo-specific rules (issue citation, value justification, etc.). |
| `doc-cluster` | *skip* | Decide which companion docs (spec / ADR / threat model / runbook / user guide) must land in the same change. |
| `edit-checklist` | *skip* | Repo-specific pre-commit ground-truth checklist run before declaring work done. |
| `land-policy` | `finishing-a-development-branch` (Hybrid) | How work lands (see Landing policy) — unset hands the land off to `superpowers:finishing-a-development-branch`; a set value (`ff-only`/`pr`/`direct`/`ask`) is honored inline instead. |
| `constitution` | *skip* | Per-repo governance doc (file path, not a `plugin:skill` slug) treated as binding context for the plan review (step 5) and code review (step 10) gates, in addition to the standard review. |

The fixed steps are not configurable — they are always the same generic skills:
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

The resolve+echo step (Workflow step 1) runs first, every run: read `<repo>/.claude/delivery.local.md`
(if present), resolve all slots, and
**print the resolved-slot table** before doing anything else (except Phase 0's design work, when that
optional phase triggers — see Workflow), e.g.:

```
deliver — resolved slots (myproject):
  plan-writer    = myproject:plan-writer
  doc-cluster    = myproject:doc-cluster
  edit-checklist = myproject:edit-checklist
  land-policy    = ff-only
  constitution   = docs/CONSTITUTION.md
```

or, with no config file:

```
deliver — resolved slots (no delivery.local.md):
  plan-writer    = superpowers:writing-plans
  doc-cluster    = skip
  edit-checklist = skip
  land-policy    = finishing-a-development-branch
  constitution   = skip
```

This echo is the contract: it shows the operator exactly which path the run will take. (Step 1 also
performs the SDD-ledger resume check right after this echo — see Workflow step 1.)

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
constitution: docs/CONSTITUTION.md        # omit -> skip
---
```

`land-policy` accepts a short verb the Landing-policy step understands (e.g. `ff-only`, `pr`,
`direct`, or the explicit `ask` override). Slot values are `plugin:skill` slugs. `constitution` is a
file path (not a `plugin:skill` slug) pointing at a per-repo governance doc — code-quality, testing,
UX, or perf standards, the Spec Kit `constitution.md` pattern for readers who know that prior art.
Because it's a path rather than a slug, the Availability fallback above does not apply to it: if
`constitution` is bound but the path is missing or unreadable, warn and treat the run as if it were
unset rather than silently proceeding as though the constraint were applied. Constitution violations
found while measuring the plan (step 5) or the diff (step 10) against it must be appended to that
step's consolidated findings file, tagged CRITICAL/IMPORTANT/MINOR per the standard format — not left
as free-floating commentary the gate checklist never inspects.

## Workflow

Work the three phases in order. Announce each step as you enter it.

### Phase 0 — Design (optional)

Skip Phase 0 (go straight to Phase A) when any of these hold — the trigger is objective, not a
"well-understood" judgment call:
- A spec or design doc already exists for the work (e.g. the work-target argument points at an
  existing file under `docs/superpowers/specs/` or equivalent, or the user-provided work description
  references one).
- The work-target argument is already a directory or issue reference, or the work-target prose
  names at least one concrete file or function to change.
- The user explicitly states the work is understood and ready to plan (no further design needed).

Run Phase 0 only when **none** of the above hold — i.e. the work-target is vague or exploratory
enough that `writing-plans` would have nothing concrete to work from.

0. **Pre-plan brief, then design.** Run `retrospective:pre-plan-brief` on the work area first —
   its own contract is "run it at the start of planning, not after," and dispatching `brainstorming`
   before this ran would be exactly that mis-order. Then dispatch `superpowers:brainstorming` to
   explore intent, requirements, and design before a plan exists. **Stop `brainstorming` at the
   approved design spec** — instruct it not to trigger its own documented auto-hand-off into
   `superpowers:writing-plans`; Phase A step 3 owns that transition, the same category of
   stop-instruction Phase B gives `subagent-driven-development` before its hand-off into
   `finishing-a-development-branch` (see "Stop SDD before its own hand-off" below). Carry the
   resulting approved design spec forward as the input to Phase A step 3 (plan authoring) —
   `writing-plans` then works from that spec instead of a bare work-target.

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
   unchanged. If the ledger's content cannot be confidently read as well-formed (e.g. truncated or
   garbled mid-write), do not treat it as resumable — surface the ambiguity to the user rather than
   silently choosing skip-to-step-7 or silently ignoring it.
2. **Pre-plan brief** — `retrospective:pre-plan-brief` on the work area, so a known issue from a
   prior cycle does not silently recur. Skip this step if Phase 0 ran — its own first action already
   covered this brief.
3. **Write the plan** — `superpowers:writing-plans`. Then, if the `plan-writer` slot is bound, run
   that skill to layer the repo's plan rules (a project plan-writer that already emits a
   value-justification block makes a separate value step unnecessary). When `constitution` is bound
   (see Configuration), read it and treat it as binding context the plan must satisfy.
4. **Doc cluster** — if the `doc-cluster` slot is bound, run it to determine which companion docs
   must land with this work. Skip cleanly if unbound.
5. **Adversarial plan review** — `docs:adversarial-review-plan` against the plan file. When
   `constitution` is bound (see Configuration), treat it as binding context the plan is measured
   against, in addition to the standard review. The existing `docs:plan-scope-cutter` archetype
   already dispatched by `adversarial-review-plan` is the over-engineering audit — no new audit
   mechanism is needed. **Only proceed when this gate passes:**
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
     post-execution sequence instead. State this in the dispatch so SDD ends at the final review. If
     `finishing-a-development-branch`'s menu or any land/merge action appears before step 9 has
     passed, treat it as a suppression failure — do not act on the menu, halt, and return to step 8.
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
   - the Iron Law evidence (command + output + exit code) recorded inline under each criterion in the
     plan's own `## Verification` section, not asserted separately — that's the artifact
     `plan_completion_check.py`'s "Verification addressed" check actually inspects, so missing
     evidence there is mechanically caught rather than self-attested;
   - no unresolved `<!-- REVIEW -->` markers anywhere in that section — `plan_completion_check.py`'s
     placeholder scan does not reliably catch this (its `<[^>]+>` pattern requires word-boundary
     adjacency, which a marker on its own line or surrounded by whitespace doesn't satisfy), so this
     is verified by the orchestrating agent reading the plan file directly, not mechanically enforced.

   If the gate reports blockers, clear them and re-run; do not proceed on an incomplete plan.
10. **Adversarial code review** — `docs:adversarial-review-code` on the resulting diff, run at
    **wider scope and without a down-routed model** (omit any `model` override so the review inherits
    the session's capability tier) — this is the whole-branch review, distinct from the down-routed
    per-task SDD reviews at step 7. When `constitution` is bound (see Configuration), treat it as
    binding context the diff is measured against, in addition to the standard review. Apply the same
    no-fabrication rule as step 7: a failed or incomplete reviewer subagent is a surfaced failure,
    never a synthesized result. **Only proceed when this gate passes:**
    - all CRITICAL/IMPORTANT findings fixed or explicitly deferred with a stated reason;
    - the whole-branch review actually ran at the wider scope described above, not just the per-task
      diffs already covered in step 7.

    Dispatch a fixer or fix inline, then re-verify.
11. **Land** — see Landing policy (Hybrid). Propose the exact commands; land only on explicit
    authorization.
12. **Retrospective** — `retrospective:plan-retrospective` to capture what worked, the friction, and
    concrete follow-ups, and clear the pending marker.

## Landing policy (Hybrid)

Resolve how work lands. `land-policy` is either unset, set to a recognized verb, or set
to an unrecognized value — three outcomes:

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
- **An unrecognized `land-policy` value** (any value not in the recognized set above) →
  **halt and surface**: announce the literal configured value verbatim and state that it is not one
  of ff-only, pr, direct, or ask, and stop — do not delegate to a land path, present the menu, or
  propose any land. Resolve the misconfiguration first: fix `land-policy`, or tell the operator to
  name the land shape explicitly. Fail-closed by design: an ambiguous landing instruction never
  results in a land.

All existing invariants hold on every path that reaches a landing action: **always propose the exact
commands and land only on explicit user authorization — never auto-push.** The halt path above reaches
no landing action at all, so proposing zero commands there is consistent with this invariant, not an
exception to it. This holds even when `land-policy` is set: the config chooses the *shape* of the
land, the human authorizes the *act*. A multi-step land (rebase → ff-only → push) is non-idempotent;
if a step fails mid-way (e.g. a rebase conflict), stop and surface it rather than forcing through —
the same rule `finishing-a-development-branch` applies to its own merge/discard paths.

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
- `brainstorming` (`superpowers`, external) — optional Phase 0 design exploration; unlike the
  fixed/slot steps above, `deliver` invokes it only conditionally (see Workflow Phase 0), not on
  every run.
- `dependencies` in `plugin.json` (`["docs", "retrospective"]`) is advisory installer metadata, not a
  hard runtime check — an install lacking either plugin keeps working via the Availability
  (best-effort) fallbacks above, just with those steps announced and skipped.
- Project step-skills bind via config — for example a repo's own plan-writer, doc-cluster, and
  edit-checklist skills. Bindings live only in that repo's `delivery.local.md`, never here.
- `references/resumability.md` — what the resolve+echo step's ledger check (Workflow step 1) resumes
  (Phase B only) and what it
  deliberately doesn't (Phase A, Phase C, `/recover` integration).
