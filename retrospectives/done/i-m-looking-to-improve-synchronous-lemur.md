# Retrospective: Triage the `deliver` adversarial plan review

**Plan:** `~/.claude/plans/i-m-looking-to-improve-synchronous-lemur.md`
**Commit:** `faaa086` (`feat(delivery): triage the adversarial plan review (#28)`)
**Date:** 2026-07-01

## Outcome

`deliver` step 5 no longer dispatches all 9 adversarial-plan-review subagents (6 dimensions + 3
archetypes) unconditionally. It now runs a built-in triage (5a: effort/complexity/uncertainty axes
plus a plan-format self-check) and dispatches by posture (5b): `SKIP` (0 agents, still commits a
triage record), `SCALED` (feasibility-auditor only, ~3-4 agents — the common case once Phase 0
brainstorming already vetted the plan's premise), or `FULL` (unchanged 9-agent review, for any
high-risk axis). Added a `plan-review-policy` (`auto`/`always`/`never`) config key as an escape hatch,
and a `--archetypes` selector on `docs:adversarial-review-plan` as the reusable scaling mechanism
`SCALED` uses. Landed via two Conventional-Commit-scoped commits (`feat(docs)`, `feat(delivery)`), PR
#28, all 9 CI checks green, squash-merged to `main`. Tracker: `hb-w61.12` (closed), under epic
`hb-w61`.

## What worked

- **Three parallel Explore agents before any design decision.** Dispatching them to independently
  read the `deliver` lifecycle, count `adversarial-review-plan`'s exact agent dispatch, and check for
  an existing complexity/format-validation signal grounded the whole design in verified facts (9-agent
  count, zero existing gating, discipline's `plan_issue_check.py` already enforcing a machine-checked
  `impact*confidence/effort` block) before writing a single line of plan — no guessing about what
  already existed.
- **`AskUserQuestion` on the three genuine design forks** (triage mechanism: rubric vs. structured
  block; escape-hatch config key: yes/no; scope: plan-review only vs. plan+code) before drafting the
  plan. Kept the plan tightly scoped to what the user actually wanted instead of guessing and
  re-planning.
- **Reading `ci/release.py` mid-implementation, not during planning**, caught that CHANGELOG.md
  sections are machine-generated from Conventional Commit subjects at `--apply` time
  (`_prepend_changelog`) — hand-writing a `## 0.3.0` section as the plan's file list originally called
  for would have conflicted with that mechanism (duplicate section, possible H1-count abort). Deviating
  from the approved plan here was the right call, not scope creep.
- **Splitting the change into two Conventional-Commit-scoped commits** (`feat(docs)`, `feat(delivery)`)
  so `release.py`'s per-plugin commit-scope filtering (`_commits_for`) gives both plugins correct
  future version bumps, instead of only the plugin named in a single combined commit.
- **Running the contract tests and `scripts/verify.sh` locally before pushing** caught a real bug (see
  Friction) before it would have failed CI — cheaper and faster than a red PR check.

## Friction / bugs

- **Contract-test substring match broke on markdown's hard-wrap**
  - *What happened:* `TestReviewTriage.test_skip_is_conditioned_on_the_format_self_check` checked for
    the literal substring `"format self-check"` in the SKILL.md prose I'd just written. The prose
    itself hard-wraps at ~100 chars, so the actual text was `"format\n     self-check"` (a newline +
    indentation between the two words) — the naive check failed on first run.
  - *Root cause:* assumed a full-phrase substring search against prose would just work, without
    checking whether the phrase could straddle a line wrap.
  - *How caught:* ran `pytest` locally before pushing, per verification-before-completion discipline,
    rather than assuming a newly-written test would pass.
  - *Fix:* `re.sub(r"\s+", " ", ...)` to collapse whitespace before the substring check.
  - *Rule:* any contract test doing a full-phrase substring match against hard-wrapped markdown prose
    (as opposed to a short bracket/backtick token, which this file's existing helpers already handle
    safely) must collapse whitespace first — a new test class can't assume a phrase never crosses a
    wrap boundary.
- **The plan's own tracker instruction was skipped during execution, not caught until the retro.**
  - *What happened:* the plan's Context/Retrospective sections said "create a sub-bead `hb-w61.N`" and
    "on completion, create and close the tracking sub-bead" — this was never done during
    implementation; the PR merged with no tracked bead at all until this retrospective step created
    and closed `hb-w61.12` retroactively.
  - *Root cause:* the plan-writing step correctly named the obligation, but nothing in the execution
    flow (contract tests, `verify.sh`, completion gate) checks for it — it's a prose instruction with
    no mechanical enforcement, easy to lose track of across a long multi-step session.
  - *Fix:* created `hb-w61.12` and closed it with a citation to the merged PR, after the fact.
  - *Rule:* when a plan names a tracker obligation ("create bead X"), treat it as part of the
    completion gate's checklist, not a detail to remember unaided — surface it explicitly at the point
    of landing, not only when writing the retrospective.

## Concrete improvements

- **`plan-review-policy` triage (SKIP/SCALED/FULL)** — live in `deliver`'s `SKILL.md` on `main`
  (version bump to the plugin pending a future `ci/release.py --apply` run against the two
  already-landed Conventional Commits).
- **`docs:adversarial-review-plan --archetypes` selector** — a reusable scaling primitive; any future
  skill wanting partial-archetype dispatch can reuse it rather than inventing its own.
- **Open follow-up, not yet resolved:** whether the objective thresholds (≤2/≥5 `## Task` headings,
  ≤3/≥8 files touched) need tuning against real plans, and whether `SCALED` (feasibility-only) ever
  misses something a `FULL` run would have caught — to be observed over the next several `/deliver`
  runs that hit `SCALED`.
- **Pending:** `ci/release.py --dry-run` (after `git fetch --tags`) to formalize the `delivery` (feat →
  minor) and `docs` (feat → minor) version bumps and auto-generated CHANGELOG entries from the two
  commits already on `main`.
