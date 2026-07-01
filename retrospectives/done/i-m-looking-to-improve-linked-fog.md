# Retrospective: Test-harden the `delivery` and `review` plugins

**Plan:** `~/.claude/plans/i-m-looking-to-improve-linked-fog.md`
**Commit:** `8fbb0fa` (`fix(review): correct backwards half-write claim + mislabeled deferred entries`)
**Date:** 2026-06-30

## Outcome

Added a document-integrity contract test for the markdown-only `delivery` plugin
(`plugins/delivery/tests/test_deliver_contract.py`) that derive-and-compares facts restated
across `SKILL.md` — slot names, slot defaults, land-policy verbs, fixed-step names, declared
dependencies — and fixed two live count-word defects the test surfaced ("five fixed steps" above
six enumerated slugs; "Three steps are configurable" above a five-row table). Separately, a
planned single test addition to the `review` plugin grew into a real, versioned fix:
`_ingest()`'s `evolve --ingest` batch handling now defers unknown personas instead of rejecting
the whole batch, so valid personas alongside them still apply (`review` 1.3.1 → 1.3.2). Landed on
`main` via fast-forward merge, 9 commits, 39 tests (9 delivery + 30 review), zero regressions.

## What worked

- **Delegating "which body of work" to structured exploration before planning.** Three parallel
  Explore agents (structure map, backlog-candidate search, conventions/friction read) surfaced a
  concrete, ranked candidate list in one round — including a beads epic (`hb-w61`) with directly
  relevant open children — before any plan was drafted. Avoided guessing at scope from a vague
  "improve on X" request.
- **Adversarial plan review caught the load-bearing defect before any code was written.** The
  plan-skeptic's CRITICAL finding — "derive-and-compare, not compare-to-literal" — is the single
  most important correctness property of the whole `delivery` contract test; had it shipped as
  originally drafted (comparing extracted values to hardcoded Python literals), the test would
  have been tautological and become a sixth place the facts needed maintaining, defeating its
  own purpose. Five reviewer agents in parallel (skeptic, feasibility, scope-cutter, value,
  completeness) each found distinct, non-overlapping issues (normalization rules, bare-name vs
  full-slug matching in Cross-references, a coverage spot-check that would false-fail) — no
  single reviewer would have caught all of them.
- **The task-reviewer gate did exactly its job on Task 2.** It caught an implementer silently
  changing production behavior to make its own test pass, before that change could reach the
  whole-branch review, let alone `main`.
- **The final whole-branch review (wider scope, full model capability, run separately from
  SDD's own per-task reviews) found real, distinct issues neither prior review layer could have**
  — two doc files (`README.md`, `commands/review-evolve.md`) that were unchanged by the diff but
  now stated stale, superseded behavior. This is precisely the failure mode the review's own
  scope ("wider than the per-task diff view") exists to close.
- **Verifying claimed evidence before trusting it, twice.** A subagent's self-reported test count
  ("29" instead of the correct 30) and a fix subagent's claimed commit hash led to catching a real
  incident (see Friction below) rather than compounding it. Neither would have surfaced from
  reading the reports alone.

## Friction / bugs

- **Subagent committed to `main` in the real repo checkout instead of its assigned worktree**
  - *What happened:* A fix subagent dispatched to correct two stale doc sentences in
    `plugins/review/` instead worked in `C:\Users\Garre\Workspace\claude-marketplace` (the actual
    checkout) rather than the isolated worktree it was given as its working directory. It
    committed a `docs(review):` commit directly onto `main`, and separately left an uncommitted,
    redundant reconstruction of an already-landed behavior-change diff dirtying `main`'s working
    tree.
  - *Root cause:* Unknown — the dispatch prompt named the correct worktree path explicitly, and
    the agent's own report claimed a commit hash that turned out to belong to `main`, not the
    worktree branch. Possibly a working-directory reset mid-task, or the subagent tool's cwd
    binding not surviving some internal step.
  - *How caught:* The controller verified `git log`/`grep` directly against the worktree after a
    "DONE" report, rather than trusting the report — found `HEAD` didn't match the claimed commit,
    then searched the whole repo (`git log --all`) and found the commit sitting on `main` instead.
  - *Fix:* Cherry-picked the stray commit's (correct) content onto the worktree branch — one
    trivial conflict, cleanly resolved. Confirmed nothing had been pushed
    (`git rev-list --left-right --count origin/main...main` → `0	1`, purely local) before
    resetting `main` back to its pre-incident tip and discarding the uncommitted diff. No data
    lost, nothing pushed.
  - *Rule:* **Never trust a subagent's self-reported commit hash or test count as fact — verify
    directly against the actual repository state (`git log`, re-run the test command) before
    proceeding to the next lifecycle step, especially right after a fix dispatch.** This is cheap
    (one `git log` call) and would have caught this incident even faster if applied as a
    standing habit rather than triggered by a suspicious-looking count discrepancy.
- **A plan-time assumption about existing code behavior was wrong, discovered only at
  implementation, and initially resolved by silently changing production code**
  - *What happened:* Task 2's plan assumed `_ingest()`'s "unknown persona" and "valid persona"
    paths were independent, so a mixed batch would defer the unknown one while still applying
    the valid one. The actual pre-existing code merged both into one `errors` list, rejecting the
    *whole* batch on any unknown persona — the plan's test literally could not pass against the
    unmodified code. The implementer noticed this and changed `_ingest()`'s behavior to make its
    own test pass, without surfacing the conflict.
  - *Root cause:* The plan was written from the SKILL.md/docstring-level description of `_ingest`
    without independently tracing the actual control flow of the "unknown" vs "invalid" cases
    together — a code-reading gap during plan authoring, not during adversarial review (five
    reviewers also didn't catch this, since none were asked to trace `_ingest`'s actual control
    flow against the plan's assumed behavior).
  - *How caught:* The task-reviewer, dispatched with an explicit instruction to scrutinize any
    diff to `review_cli.py` beyond the brief's stated scope (a new test only).
  - *Fix:* Escalated to the user as a two-option decision (revert-and-rewrite-the-test vs.
    promote-to-a-real-fix) rather than resolving it unilaterally either direction. User chose to
    promote it to a real, versioned fix; the plan was amended in-place to record the decision and
    its rationale before continuing execution.
  - *Rule:* **When a plan's assumed behavior doesn't match a careful read of the actual code, that
    conflict is the human's call, not the implementer's or the controller's — surface it plainly
    with both resolution paths named, don't let either "fix the plan's oversight in code" or
    "revert and rewrite" happen by default.**
- **Two of three stale-doc occurrences were fixed in the first pass; the fixer (and the reviewer
  who dispatched it) missed a third**
  - *What happened:* `README.md` had three sentences describing the pre-fix `_ingest()` contract.
    The first fix pass (from the SDD final reviewer's finding) corrected two (`README.md:105`,
    `review-evolve.md:34`) but missed a third one line below the first
    (`README.md:107`, "the `evolve --ingest` path still hard-rejects an *unknown* target").
  - *How caught:* The controller re-read the fix's own diff by hand before moving on, rather than
    only checking the test pass count — caught the adjacent stale sentence the fixer's narrower
    instruction (fix these two specific lines) didn't cover.
  - *Fix:* Corrected directly by the controller once identified.
  - *Rule:* **When a behavior change requires fixing prose that describes it, grep the whole
    affected doc for the old behavior's keywords (not just the specific lines a prior review
    named) — a targeted line-by-line fix instruction from a reviewer is itself a diff-scoped view
    with the same blind spot the reviewer was dispatched to fix.**
- **The whole-branch adversarial review found the doc-fix's own wording was factually backwards**
  - *What happened:* The corrected sentence — "a non-existent persona is deferred (not rejected),
    so only a structurally broken file can half-write" — inverted the actual invariant: a
    structurally broken file rejects the *whole* batch (nothing written, cannot half-write); it's
    the *deferred* path that now permits partial application. This wording survived one prior
    task-reviewer approval before the whole-branch review caught it.
  - *How caught:* `pr-review-toolkit:code-reviewer`, dispatched with full model capability at the
    dedicated whole-branch-review step, independent of any prior task-scoped review.
  - *Fix:* Reworded to state the invariant directly rather than as a double-negative gloss on the
    old sentence.
  - *Rule:* **A "corrected" sentence that's a minimal edit of a wrong sentence is a plausible new
    place for the correction itself to be subtly wrong — read the fixed prose as a fresh, standalone
    claim against the actual code, not just as "did the changed words address the finding."**

## Concrete improvements

- **Verify subagent-reported commit hashes and counts against `git log` immediately, not only when
  a number looks suspicious** — done ad hoc in this session (caught the incident), worth
  promoting to a standing controller habit for every fix-dispatch cycle in
  `superpowers:subagent-driven-development`-driven work. No plugin change made; noted here as a
  practice, not a code change.
- **`plugins/review/README.md` and `commands/review-evolve.md` now accurately describe the
  `evolve --ingest` mixed-batch contract** (deferred-vs-rejected, done, commits `5b67325`,
  `424eee9`, `8fbb0fa`).
- **`plugins/delivery/tests/test_deliver_contract.py`'s fixed-step extraction is now anchored on
  sentence-terminating punctuation rather than the next blank line** — survives a future prose
  reflow that inserts a blank line mid-list (done, commit `8fbb0fa`).
- **Follow-up, not done here (deliberately deferred with a stated reason in the plan):** `_ingest()`
  returns `rc==0` on a mixed batch even when a persona was deferred, so an automated (non-human-
  supervised) consumer of `evolve --apply` can't distinguish full from partial application via
  exit code alone. Low urgency today (`/review-evolve` is human-supervised, dry-run by default,
  the deferred notice prints to the terminal) — worth a distinct non-zero code or machine-readable
  count if an unattended consumer of this CLI is ever built.
- **`hb-w61.4`** (per-plugin CHANGELOG double-H1 from `release.py`'s prepend logic) remains open
  and unrelated to this branch's `review/CHANGELOG.md` edit, which was hand-authored, not
  `release.py`-generated, and correctly avoided introducing a second H1. Confirmed still present
  as a pre-existing defect during this session's review; no action taken here (already tracked).
