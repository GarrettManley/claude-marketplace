---
status: active
author: Garrett Manley
created: 2026-06-30
diataxis: reference
---

# 0013. `/deliver` lands via PR so required checks gate the merge decision

## Status

Accepted

## Context

`main` is protected by GitHub ruleset `18094698`, which requires **5 status checks**
(`verify` on ubuntu-latest and windows-latest × Python 3.12/3.13, plus
`claude plugin validate (--strict)`) and **1 approval** before a normal PR merge.
`delivery:deliver`'s Hybrid landing mode, with `land-policy` unset, fell back to
`finishing-a-development-branch`'s "merge locally" behavior: merge the branch locally
and `git push origin main` directly.

That local push *does* trigger CI — `.github/workflows/ci.yml` triggers on
`push: [main]` as well as `pull_request` — but the checks run **post-hoc and
non-blocking**: the code is already on `main` by the time they run, and the push only
succeeds at all because the repo-owner role carries `bypass_mode=always` on the
ruleset. The failure mode is not "checks never run"; it is that the merge decision is
made before the checks are visible, and a red result — if one occurs — surfaces on
`main` after the fact rather than gating anything.

`scripts/verify.sh`, the local pre-merge gate mirrored by `.githooks/pre-commit`, is a
strict subset of what CI enforces: single OS (the maintainer's Windows box), a single
local Python (3.14, outside the CI-required 3.12/3.13 matrix), and no
`claude plugin validate --strict` or pytest+coverage step. Passing it locally does not
prove what the ruleset actually requires.

Because the repo has exactly one maintainer, the "1 approval" requirement can never be
satisfied by self-approval — some form of owner-bypass is structurally unavoidable for
the merge step, regardless of which landing approach is chosen.

## Decision

`/deliver` lands via a real pull request. `.claude/delivery.local.md` sets
`land-policy: pr`, which routes the skill's landing step to open a PR and stop there,
rather than merging locally and pushing directly to `main`. The 5 required status
checks then run **on the PR, before the merge decision**, instead of on `main`
afterward. The maintainer merges deliberately once the PR shows 5/5 green (owner-bypass
still supplies the unattainable solo self-approval).

### Rejected alternatives

1. **Local `pre-land.sh` mirror script reproducing the CI checks.** Rejected as
   infeasible, not merely lower-effort. CI's ≥90% coverage gate is met only by
   *combining* the ubuntu and windows coverage runs; several branches are POSIX-only
   (e.g. `plugins/learning/scripts/storage.py`,
   `plugins/discipline/scripts/run_with_flags.py`,
   `plugins/stewardship/scripts/stop_format_typecheck.py`) and never execute on the
   maintainer's Windows-only box. A local gate built this way would never reach 90%
   coverage and would always need an override to pass — recreating the exact
   bypass-by-default pattern this decision exists to fix. It also can't reproduce the
   py3.12/3.13 matrix from a local Python 3.14 install.
2. **A `.githooks/pre-push` hook enforcing local checks before any push to `main`.**
   Rejected: it hard-fails pushes on any machine that lacks the full dev toolchain, has
   no audit trail for an override, no kill-switch, and would self-block the very branch
   introducing it (its own first push to land this change would trip the hook it adds).
3. **Removing the ruleset's owner-bypass and dropping required approvals to 0** so
   GitHub enforces the checks natively without any bypass path. Rejected: a solo owner
   cannot self-approve a PR, so *some* bypass mechanism is unavoidable for a one-person
   repo to ever merge anything. Dropping approvals to 0 would loosen governance
   (removing the approval gate entirely) rather than tightening it, which runs counter
   to the goal.

## Consequences

- The maintainer no longer merges unverified code to `main` by default: `/deliver`
  opens a PR, the 5 required checks run and are visible, and the merge is taken
  deliberately on green.
- **Residual (by design, not oversight):** the merge step still requires owner-bypass,
  because a solo maintainer structurally cannot self-approve. This decision does not
  remove that bypass and does not try to — it changes *when* the bypass is exercised,
  from "before the checks are known" to "after they are visibly green." The win is
  checks-green-before-the-decision, not bypass-eliminated.
- No new executable surface is introduced — no `pre-land.sh`, no `pre-push` hook, no new
  pytest module. This is a configuration + documentation change
  (`.claude/delivery.local.md`), so it carries no coverage-gate impact and needs no new
  test.
- A direct `git push origin main` remains technically possible (owner-bypass permits
  it) but is now discouraged in `CONTRIBUTING.md`: it bypasses the PR-gated checks,
  which then only run post-hoc and non-blocking on `main`, reintroducing the exact
  problem this ADR fixes.
