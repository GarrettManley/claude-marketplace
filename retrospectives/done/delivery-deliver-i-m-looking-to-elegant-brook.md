# Retrospective: Route `/deliver` landings through PR-gated checks (hb-w61.10)

**Plan:** `~/.claude/plans/delivery-deliver-i-m-looking-to-elegant-brook.md`
**Commit:** `fa56a07` (`docs(delivery): route /deliver landings through PR-gated checks (hb-w61.10) (#22)`)
**Date:** 2026-06-30

## Outcome

`/deliver` now lands via PR by default in this repo (`.claude/delivery.local.md`,
`land-policy: pr`), so the 5 status checks required by ruleset `18094698` run and go
green *before* the merge decision instead of post-hoc on `main` after a local push.
Recorded as `docs/adr/0013-pr-gated-landing.md`, with three rejected alternatives
documented for cause. Dogfooded end-to-end: PR #22 opened, all 9 checks (5 required +
2 extra + 2 `continue-on-error` macOS legs) went green, merged via `--admin` (the
documented residual — a solo owner cannot self-approve). `bd close hb-w61.10`.

## What worked

- **Exploration-before-target-selection paid off.** Two parallel Explore agents (repo
  structural map + backlog/retro mining) converged independently on the same top
  candidate (hb-w61.10) before any plan was written — high confidence the target was
  actually the highest-value item, not just the first one found.
- **7-agent adversarial plan review caught an infeasible design before any code was
  written.** The originally-approved "Hybrid" (PR-gating + local `pre-land.sh` mirror +
  `pre-push` hook + drift-guard test) looked reasonable on paper. The review's
  feasibility/skeptic/scope-cutter agents independently converged on the same fatal
  flaw — see Friction below — and the plan was reshaped *before* any implementation
  effort was spent on the infeasible half. This is exactly the value proposition of
  reviewing the plan, not just the diff.
- **Re-verifying subagent claims with fresh commands caught nothing wrong, but was
  cheap insurance.** Both the implementer subagent's report and the code-review
  agents' claims (ruleset facts via a second independent `gh api` call) were
  independently re-checked rather than trusted — per the "no fabrication" rule and the
  standing controller habit from a prior retro (`linked-fog`). Zero discrepancies
  found this time, but the check is what makes that a fact rather than an assumption.
- **Deferring one review finding with a stated reason, instead of scope-creeping back
  in, held the line.** The silent-failure-hunter's IMPORTANT finding (no validation of
  `land-policy`'s value against the skill's accepted verb set) would have required
  adding new executable surface — exactly what the plan reshape had just cut for
  infeasibility elsewhere. Deferring it with a written reason (candidate follow-up
  against `plugins/delivery` itself, not this repo's config) kept the change
  proportionate instead of re-inflating scope one finding at a time.

## Friction / bugs

- **Original plan target (local CI-mirror script) was infeasible, not just over-scoped**
  - *What happened:* The approved "Hybrid" plan included `scripts/pre-land.sh`, a local
    script reproducing CI's pytest+coverage+`claude plugin validate --strict` checks
    before allowing a `main` push.
  - *Root cause:* CI's ≥90% coverage gate is met only by *combining* ubuntu+windows
    coverage runs; several production code paths are POSIX-only
    (`plugins/learning/scripts/storage.py`, `plugins/discipline/scripts/run_with_flags.py`,
    `plugins/stewardship/scripts/stop_format_typecheck.py`) and never execute on the
    maintainer's Windows-only box. A local coverage gate built this way could never
    reach 90% and would always need an override — recreating the exact
    bypass-by-default the plan existed to fix. Local Python was also 3.14, outside the
    CI-required 3.12/3.13 matrix.
  - *How caught:* Adversarial plan review — the `feasibility` dimension agent traced
    the actual coverage-combining mechanics in `.coveragerc` and CI's job definition;
    `plan-skeptic` independently flagged the weaker but related point that CI already
    runs (non-blocking) on `push: [main]`, so the bead's framing ("checks never run")
    was itself overstated.
  - *Fix:* Reshaped the plan from 5 tasks to 3 before any implementation: dropped the
    local mirror, the `pre-push` hook, and the drift-guard test; kept only
    `land-policy: pr` + governance docs (ADR + CHANGELOG + CONTRIBUTING note).
  - *Rule (if generalizable):* When a plan proposes reproducing a CI gate locally,
    check whether that gate's pass condition depends on *combining* results across a
    matrix (OS, language version) the local machine cannot itself produce. A
    single-machine mirror of a matrix-combined gate is not a weaker version of the
    real check — it is structurally incapable of passing, which is worse than not
    having the check at all (it manufactures a permanent-override habit).

- **A solo repo owner cannot self-approve — the "eliminate the bypass" framing was
  always unreachable**
  - *What happened:* The bead (hb-w61.10) and the initial plan implicitly framed the
    goal as "stop landings from bypassing the ruleset." The final merge of this very
    PR still required `gh pr merge --admin` because GitHub's 1-approval requirement
    cannot be satisfied by the PR author approving their own PR.
  - *Root cause:* The ruleset's required-approval count and the repo's single-maintainer
    reality are structurally in tension; no landing-policy change can resolve it
    without either adding a second reviewer (not available) or dropping the approval
    requirement (a governance regression, considered and rejected in ADR-0013).
  - *How caught:* `plan-feasibility-auditor` flagged it explicitly during plan review,
    before landing was attempted — not discovered live at merge time, though the merge
    attempt (`gh pr merge --squash --delete-branch` failing with "base branch policy
    prohibits the merge") independently confirmed the same fact in practice.
  - *Fix:* Reframed the plan's stated goal from "eliminate the bypass" to "checks green
    before the decision, not bypass eliminated" — an honest, achievable target — and
    documented the residual explicitly in three places (config file, ADR, CLAUDE.md)
    rather than letting the gap go unstated.
  - *Rule (if generalizable):* When a plan's success criterion implies eliminating a
    platform-level escape hatch (owner bypass, admin override, force-push allowance),
    check whether the repo's *governance shape* (solo maintainer, no second reviewer)
    makes that escape hatch structurally load-bearing rather than incidental. If so,
    redefine success as "used deliberately on green" rather than "removed," and say so
    explicitly — don't let the plan silently promise something the org chart can't
    support.

## Concrete improvements

- **`plugins/delivery/skills/deliver/SKILL.md`'s Landing policy section has no defined
  behavior for an unrecognized `land-policy` value** — status: not filed as a bead this
  session (surfaced by the code-review's silent-failure-hunter, deferred in the PR
  description with a stated reason: fixing it would add new executable surface to a
  config-only change, and it's a gap in the `delivery` plugin itself, not specific to
  this repo). Worth filing as a follow-up bead against `plugins/delivery` if it
  recurs — a typo in `land-policy:` (e.g. `PR` instead of `pr`) currently has
  undocumented fallback behavior.
- **ADR frontmatter convention (`status`/`author`/`created`/`diataxis`) is not gated
  by any lint** — status: caught only by the code-reviewer agent noticing ADR-0013
  initially lacked it, not by `lint-frontmatter` (which apparently doesn't scope to
  `docs/adr/*.md`, or scopes to a different frontmatter shape). Confirmed and fixed
  inline this session; not filed as a bead — small enough to flag here for whoever
  writes the next ADR without this retro's context.
- **CHANGELOG double-H1 bug (hb-w61.4)** — unrelated to this session's scope but
  re-confirmed still open via the harness-backlog mining agent during target
  selection; still the best small-effort/high-payoff pick for a future session.
