---
name: deliver
description: Use when you want to drive one body of work end-to-end through the full delivery lifecycle in a single orchestrated pass — plan, adversarial plan review, subagent execution, completion gate, adversarial code review, land, and retrospective. Composes superpowers + docs + retrospective skills; the project-specific plan-writer / doc-cluster / edit-checklist steps bind per-repo via .claude/delivery.local.md, so the same skill drives a rigor-heavy repo and a bare one without edits.
version: 0.1.0
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
| `land-policy` | read repo policy, else *ask* | How work lands (see Landing policy). |

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
  land-policy    = ask
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
land-policy: ff-only                      # omit -> read repo policy, else ask
---
```

`land-policy` accepts a short verb the Landing-policy step understands (e.g. `ff-only`, `pr`,
`direct`, `ask`). Slot values are `plugin:skill` slugs.

## Workflow

Work the three phases in order. Announce each step as you enter it.

### Phase A — Plan (in plan mode)

1. **Resolve + echo.** Read the config, resolve slots, print the resolved-slot table (above).
2. **Pre-plan brief** — `retrospective:pre-plan-brief` on the work area, so a known issue from a
   prior cycle does not silently recur.
3. **Write the plan** — `superpowers:writing-plans`. Then, if the `plan-writer` slot is bound, run
   that skill to layer the repo's plan rules (a project plan-writer that already emits a
   value-justification block makes a separate value step unnecessary).
4. **Doc cluster** — if the `doc-cluster` slot is bound, run it to determine which companion docs
   must land with this work. Skip cleanly if unbound.
5. **Adversarial plan review** — `docs:adversarial-review-plan` against the plan file. Resolve
   CRITICAL/IMPORTANT findings before proceeding.
6. **Approval** — present the finalized plan and exit plan mode for the user's sign-off.

### Phase B — Execute

7. **Subagent-driven execution** — `superpowers:subagent-driven-development` for independent tasks;
   reach for the **Workflow tool** when tasks fan out in parallel (per the standing orchestration
   defaults). Keep main context for synthesis and the approval/landing gates.
8. **Edit checklist** — if the `edit-checklist` slot is bound, run it against the diff before
   declaring the work done. Skip cleanly if unbound.

### Phase C — Verify and land

9. **Completion gate** — `retrospective:plan-completion`. If it reports blockers, clear them and
   re-run; do not proceed on an incomplete plan.
10. **Adversarial code review** — `docs:adversarial-review-code` on the resulting diff. Resolve
    CRITICAL/IMPORTANT findings (dispatch a fixer or fix inline), then re-verify.
11. **Land** — see Landing policy. Propose the exact commands; land only on explicit authorization.
12. **Retrospective** — `retrospective:plan-retrospective` to capture what worked, the friction, and
    concrete follow-ups, and clear the pending marker.

## Landing policy

Resolve how work lands, in order: the `land-policy` config value → else the repo's stated policy
(its `CLAUDE.md` / `AGENTS.md` branch-and-merge section, or the git default branch) → else **ask**.

Common policies: `ff-only` (rebase onto the main branch → `git merge --ff-only` → push → delete the
branch), `pr` (open a pull request and stop), `direct` (commit to the working branch).

**Always propose the exact commands and land only on explicit user authorization — never auto-push.**
This holds even when `land-policy` is set: the config chooses the *shape* of the land, the human
authorizes the *act*. A multi-step land (rebase → ff-only → push) is non-idempotent; if a step fails
mid-way (e.g. a rebase conflict), stop and surface it rather than forcing through.

## Cross-references

`deliver` composes these — it does not replace them; invoke any directly when you want just that step:

- `pre-plan-brief`, `plan-completion`, `plan-retrospective` (`retrospective@garrettmanley`) — the
  lifecycle gates; `deliver` runs them as fixed steps.
- `adversarial-review-plan`, `adversarial-review-code` (`docs@garrettmanley`) — the two review gates.
- `writing-plans`, `subagent-driven-development` (`superpowers`, external) — plan authoring and
  execution; best-effort, with built-in fallbacks when superpowers is not installed.
- Project step-skills bind via config — for example a repo's own plan-writer, doc-cluster, and
  edit-checklist skills. Bindings live only in that repo's `delivery.local.md`, never here.
