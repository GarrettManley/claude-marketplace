# Retrospective: Fix release.py double-H1 CHANGELOG bug + add single-H1 lint gate

**Plan:** `~/.claude/plans/i-m-looking-to-improve-noble-candle.md`
**Commit:** `a526247` (`fix(ci): harden release.py changelog split + lint-changelog BOM handling`)
**Date:** 2026-06-30

## Outcome

Fixed `ci/release.py::_prepend_changelog`, which always prepended a fresh H1 on release,
producing a double-H1 CHANGELOG on any hand-authored file and wedging intro prose between
version sections. Cleaned the 5 plugin CHANGELOGs already broken (the tracked backlog item
undercounted — it listed 4, missing `evidence`). Added `ci/lint-changelog.py` as a new hard
CI gate enforcing exactly one H1 per plugin CHANGELOG. A whole-branch adversarial review
then found the fix itself had a residual gap (naive regex split-point could be hijacked by
a `## ` line inside a fenced code example) and two hardening opportunities, all fixed in a
follow-up commit. PR #23 opened; land-policy `pr` stops there pending the 5 required checks.

## What worked

- **Value-probe survey before planning** — three parallel Explore agents (delivery v0.2.0
  status, hook-gating gap, general repo-health scan) surfaced that the backlog's own count
  (4 broken plugins) was wrong before a single line of the plan was written; the true count
  (5) only came from reading all 13 CHANGELOGs directly rather than trusting the tracked item.
- **9-agent adversarial plan review caught two real bugs before code was written**: a
  headerless-CHANGELOG data-loss regression (the naive 3-case draft would have silently
  discarded a legacy file's body) and a scope-inflation (the draft implicitly required
  renaming 8 healthy files and title-canonicalizing them, driven by a title-equality lint
  check nobody asked for). Both caught at the plan stage, at zero implementation cost.
- **Convergent multi-agent YAGNI cutting**: 4-5 of 9 review agents independently flagged the
  same over-scope items (title check, 8-file rename, fence-awareness, self-heal). When
  independent agents converge on the same cut without prompting, that's a strong signal —
  cut with confidence rather than treating it as one opinion among many.
- **Workflow-tool `isolation: 'worktree'` for genuinely parallel implementers**: once the
  false premise (see Friction below) was corrected, 4 disjoint-file dispatches ran truly
  concurrently in separate git worktrees with zero merge conflicts, cutting wall-clock
  substantially versus serial dispatch.
- **Controller-level severity calibration on cross-agent findings**: a whole-branch reviewer
  flagged two findings as CRITICAL; independently verifying against the actual code showed
  one was a real, worth-fixing gap and the other was a scope suggestion the plan's own
  adversarial review had already deliberately rejected for the analogous case. Calibrating
  rather than blindly implementing both prevented undoing a deliberate scope decision.
- **Verifying subagent-reported commit hashes and counts immediately** — done twice (after
  the initial 4-dispatch Workflow run, and after the whole-branch-review fix pass) via
  `git cat-file -t <sha>` and a fresh `pytest`/`verify.sh` run, per a prior retro's explicit
  rule. Cheap insurance; caught nothing wrong this time, but the discipline is what matters.

## Friction / bugs

- **False belief that SDD's "don't dispatch implementers in parallel" is a blanket rule**
  - *What happened:* The first Phase B attempt dispatched one plain `Agent`-tool implementer
    (no isolation) and treated the SDD skill's parallel-dispatch caution as categorical,
    serializing 4 fully-disjoint-file dispatches that had no real dependency edge.
  - *Root cause:* Misread the SDD skill's rationale. The actual hazard is concurrent git
    mutations racing `.git/index`/`HEAD` in one *shared* working tree — not disjoint-file
    parallelism in general. `Workflow`'s `isolation: 'worktree'` exists precisely to remove
    that hazard by giving each implementer its own worktree.
  - *How caught:* User interrupted mid-dispatch and corrected the framing directly.
  - *Fix:* Killed the in-flight dispatch (RED-phase test edits only, no commits — safe to
    discard), re-planned Phase B execution as a `Workflow` script with 4 `parallel()`
    isolated-worktree implementers + a `pipeline()` review stage, re-entered plan mode to
    record the corrected strategy and get explicit sign-off before resuming.
  - *Rule:* Before serializing agent dispatches "for safety," name the actual shared
    resource that would be corrupted by parallelism. If the answer is "nothing — the files
    are disjoint," the real fix is isolation (worktree/sandbox), not serialization.

- **A `Workflow` `isolation: 'worktree'` agent committed directly to the real local `main`**
  - *What happened:* Of 4 parallel isolated-worktree implementers, 3 correctly reported
    fresh worktree paths and branches. The 4th (haiku-tier, single-file docs task) reported
    `branch: "main"` and `worktreePath: <actual repo root>` — its commit landed on the
    real, non-worktree `main` checkout.
  - *Root cause:* Unconfirmed — the model tier and task size both differ from the other 3,
    but no direct causal link was established; worth flagging if it recurs.
  - *How caught:* The controller cross-checked every dispatch's reported `branch` field
    against its `worktreePath` before trusting either, per this repo's own prior retro
    finding on exactly this failure class (subagent committing to `main` instead of its
    assigned worktree) — the mismatch (a plain repo-root path where a `.claude/worktrees/…`
    path was expected) was visible immediately in the structured output, not discovered
    later.
  - *Fix:* Verified the commit was local-only (absent from `origin/main`) before touching
    anything. Cherry-picked the commit onto the feature branch, then user-confirmed
    `git reset --hard` on `main` back to `origin/main`'s tip. Zero external blast radius.
  - *Rule:* This is the **second** occurrence of this exact failure class across two
    unrelated deliveries (previously with plain `Agent` dispatch, now with `Workflow`
    `isolation: 'worktree'`). Two occurrences across different dispatch mechanisms suggests
    checking `branch`/`worktreePath` fields against expected shape is worth a standing habit
    (or a schema `enum`-style hint discouraging `"main"`/`"master"` as a valid isolated
    branch value) rather than a one-off catch. Flagging as a fast-follow candidate rather
    than fixing in this delivery, which is out of scope for a docs/CI bugfix.

- **A whole-branch review found a residual gap the fix's own author didn't anticipate**
  - *What happened:* The `release.py` rewrite fixed the double-H1 bug but used a plain
    `re.compile(r"^## ", re.MULTILINE)` search for the split point — itself vulnerable to
    being hijacked by a `## `-shaped line inside a fenced code example in the intro, which
    would silently wedge new content at the wrong position with zero error.
  - *Root cause:* The task-scoped implementer and its task reviewer both verified the 3-case
    algorithm against the plan's literal spec, which didn't call out fence-awareness for the
    *split-point* search (only the *lint*'s H1-counting fence-awareness had been explicitly
    discussed and cut). The two are different code paths with different risk profiles
    (read-only count vs. mutate-on-write), and that distinction wasn't drawn during planning.
  - *How caught:* `pr-review-toolkit:silent-failure-hunter` at deliver's step 10 (wider
    scope, non-down-routed model) — exactly the review tier this two-tier review structure
    (down-routed task reviews + a broader final pass) exists to catch.
  - *Fix:* Fence-aware line scan replacing the regex; added a pre-commit validation guard in
    `release.py --apply` itself (abort before commit on an unexpected H1 count) as
    belt-and-suspenders; one-line BOM defense in the lint's counter.
  - *Rule:* When a plan explicitly discusses and cuts a hardening measure (e.g.,
    fence-awareness) for one code path, don't assume the decision transfers to a
    superficially similar but functionally different code path (read vs. write) without
    re-examining it. The two-tier review structure (cheap task reviews, one non-down-routed
    final pass) is specifically insurance against exactly this kind of gap.

## Concrete improvements

- **`ci/release.py::_prepend_changelog`** — fence-aware split-point detection +
  abort-before-commit validation. Landed in this PR, `a526247`.
- **`ci/lint-changelog.py`** — new gate, BOM-defended H1 counter. Landed in this PR.
- **hb-w61.4** — scope corrected from 4 to 5 broken plugins; should be updated/closed
  against this PR once merged.
- **hb-w61.9** (DISCIPLINE_HOOK_PROFILE docstring) — surfaced as a likely no-op during the
  value-probe survey: the vendored `hook_flags.py` files across discipline/learning/
  stewardship are byte-identical by design (enforced by `check-vendored-sync.py`), and the
  "discipline" wording in the docstring is deliberate illustrative example text, not a
  copy-paste bug. Follow-up: verify with the bead's original filer before closing, but this
  delivery's research suggests it's a misread rather than a real defect — pending, not done.
- **hb-w61.8** (hook-gating retrofit) — the value-probe survey found it embeds a genuine
  security design decision (evidence's `secret_scan`/`scope_bind` must not gain a weak
  env-var disable bypass) that the original bead didn't flag. Follow-up: worth a design note
  before someone picks it up expecting pure mechanical retrofit work — pending.
- **Fast-follow candidate**: a standing check (hook or convention) for `Workflow`
  `isolation: 'worktree'` agents reporting `branch: "main"`/`"master"` or a non-worktree
  `worktreePath` — this is the second occurrence of the same failure class. Not filed as a
  bead in this delivery (out of scope for a docs/CI bugfix), but worth raising if it recurs
  a third time.
- **`docs/architecture.md:270-272` and `docs/testing-strategy.md:159-162`** — both enumerate
  `verify.sh`'s gate list in prose and now omit `lint-changelog` (pre-existing drift in kind;
  both already omitted `check-doc-links` before this change). Noted in the plan's Phase B
  outcomes as a deferred Minor; not fixed in this PR (out of its stated Task 3/6 scope) —
  pending, worth a one-line fast-follow.
