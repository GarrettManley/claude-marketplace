---
land-policy: pr
---

# Delivery config — claude-marketplace

`land-policy: pr` routes every `/deliver` landing in this repo through a real pull
request instead of a local merge + `git push origin main`.

## Why

`main` is protected by GitHub ruleset `18094698`, which requires **5 status checks**
(`verify` on ubuntu-latest and windows-latest × Python 3.12/3.13, plus
`claude plugin validate (--strict)`) and **1 approval** before a PR can merge normally.
`.github/workflows/ci.yml` triggers on `push: [main]` as well as `pull_request`, so a
local `git push origin main` landing still runs the 5 checks — but only *after* the
push has already landed on `main`, and it succeeds at all only because the repo owner
has `bypass_mode=always` on the ruleset. The failure mode isn't "checks never run"; it's
that the merge decision gets made **before** the checks are visible, and a red result
surfaces on `main` after the fact instead of gating the decision.

`land-policy: pr` fixes the ordering: `/deliver` opens a PR, the same 5 required checks
run on the PR, and the maintainer only merges once they are visibly green. Verification
now happens *before* the decision, not after.

## Honest residual

This does **not** eliminate owner-bypass. The ruleset's 1-approval requirement can never
be satisfied by a solo maintainer self-approving their own PR, so the merge step still
requires the owner-bypass path. What changes is *when* the bypass is exercised: with
`land-policy: pr`, the maintainer merges deliberately on a 5/5-green PR; without it, the
maintainer had already merged before knowing whether the checks would pass. The win is
"checks green before the decision," not "bypass eliminated" — that distinction matters
and is documented, not glossed over.

See `docs/adr/0013-pr-gated-landing.md` for the full decision record, including the
rejected alternatives (a local CI-mirror script, a `pre-push` hook, and removing
owner-bypass server-side) and why each was cut for cause rather than convenience.

Tracker: hb-w61.10, under epic hb-w61.
