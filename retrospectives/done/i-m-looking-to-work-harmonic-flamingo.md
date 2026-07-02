# Retrospective: Fail-Open Gate Fixes (Audit Increment 1)

**Plan:** `~/.claude/plans/i-m-looking-to-work-harmonic-flamingo.md`
**Commit:** `9ff612a` (`docs(retrospective): document leading-keyword rule in _is_placeholder_body`) — branch `worktree-fix-fail-open-gates-30-31-32`, `5883644..9ff612a` (5 commits)
**Date:** 2026-07-02

## Outcome

First increment of the value-ordered walk through the 2026-07-01 wholesale-audit backlog (issues #30–#43): the three fail-open gate bugs closed. #30 — the completion gate now rejects a retrospective whose only content is a `TODO:`-prose line (leading-placeholder detection reusing `_PLACEHOLDER_RE.match()`). #31 — `scope_bind`'s path confinement now rejects any `..` segment before the prefix check. #32 — `NotebookEdit` is scanned/scope-gated by both extractors **and** both `hooks.json` PreToolUse matchers, with a new `test_hooks_json.py` matcher-coverage guard. Suite 200 passing (192 baseline + 8 new); `scripts/verify.sh` 11/11 green. One IMPORTANT pre-existing confinement weakness surfaced by the whole-branch review was deferred and tracked as #47. Lands via PR (`land-policy: pr`).

## What worked

- **Adversarial plan review earned its cost, twice over.** The 9-agent plan review caught the single most important thing in the whole delivery: the original Task 3 fixed only the two Python extractors, but `hooks.json`'s PreToolUse matcher strings didn't include `NotebookEdit` — so the fix would have been **inert in production** while unit tests (which call the extractors directly) passed green. That is the exact fail-open trap the audit exists to catch, reproduced inside its own fix. The completeness agent found it; a matcher-coverage test now guards it permanently.
- **A reviewer's simpler-path finding replaced a fragile fix.** The plan-skeptic argued Task 2's `posixpath.normpath` + boundary-match machinery was half-dedicated to undoing a `/eng`→`/england` regression that normpath's own trailing-slash stripping would introduce. Swapping to a wholesale `..`-segment rejection guard closed #31 in ~2 lines with zero regression surface and dissolved ~6 downstream findings (cross-platform anchoring, boundary matching, stale-test churn, block-message drift). The Windows-CI drive-anchoring hazard (`/eng/a.txt` → `C:\eng\...`) was caught at plan time, not by a red CI run.
- **Current-behavior-first TDD as security-regression proof.** Each fix's first test reproduced the live fail-open (red before, green after); the reviewers independently reconstructed pre-fix code to confirm the red claim rather than trust the report. The matcher tests were empirically shown to return `False` on the pre-fix `hooks.json` and `True` after — a real guard, not a tautology.
- **Two-tier review (down-routed per-task, session-tier whole-branch).** The cheap per-task reviews caught a defanged regression-guard test (Task 1's mid-sentence guard had no keyword in its body); the session-tier whole-branch review caught the pre-existing prefix-boundary fail-open the per-task reviews' narrower scope missed — exactly the split the two tiers exist for.
- **Honest deferral over scope creep.** The IMPORTANT boundary finding was pre-existing and distinct from #31's `..` charter; deferring it to tracked issue #47 (not silent prose) kept the PR tightly scoped while recording the residual.

## Friction / bugs

- **Implementer interrupted mid-task by a machine restart**
  - *What happened:* the Task 3 implementer edited all 7 files but the session was killed before it committed or wrote its report.
  - *Root cause:* external (machine restart), not a process fault.
  - *How caught:* on resume, `git status` showed 7 modified/untracked files with no matching commit in the log and no task-3 report.
  - *Fix:* the controller verified the uncommitted work against the plan file-by-file, ran the full suite (200 passed), ran the exhaustiveness grep, then committed with explicit staging and had the task reviewer independently confirm the red-before claims — rather than trusting or discarding the partial work.
  - *Rule:* the SDD progress ledger + `git status`/`git log` are the recovery map after an interrupt; verify uncommitted subagent work against the plan and re-review before adopting it — never fabricate a completion over the gap, never blindly re-run a task the ledger shows as edited-but-uncommitted.
- **The completion gate blocked on its own fix's vocabulary**
  - *What happened:* `plan-completion` flagged the plan's `## Verification` section as still-placeholder.
  - *Root cause:* the section's evidence lines literally contained `TODO: fill in` (the #30 reproduction input), the word `placeholder` (in the quoted blocker message), and `<!-- REVIEW -->` (matching the `<...>` rule) — all trigger tokens for `check_verification_addressed`.
  - *How caught:* `plan_completion_check.py` returned INCOMPLETE with one blocker.
  - *Fix:* reworded the evidence to describe the reproductions abstractly (no literal marker tokens), keeping the facts.
  - *Rule:* when documenting a fix to a placeholder/marker scanner, the surrounding prose cannot quote the literal tokens the scanner keys on — describe them, don't reproduce them.

## Concrete improvements

- **Matcher/extractor sync guard** — `plugins/evidence/tests/test_hooks_json.py` asserts every hook's `hooks.json` matcher covers the tools its extractor handles. Done. Generalizable: any PreToolUse hook is only as live as its matcher; a unit test on the extractor alone is false confidence.
- **`..`-rejection over lexical normalization for path confinement** — simpler, cross-platform-safe, and stricter (rejects in-scope `..` too). Done in `scope_binding.py`.
- **Deferred: scope_bind confinement hardening** — issue **#47** (prefix path-boundary match, Windows trailing-dot/space segment normalization, symlink-parent resolution when the leaf is absent). Follow-up.
- **Next increments (this backlog):** #33/#27 release.py correctness → #34/#35 discipline logic bugs → #38/#39/#40 test integrity → #36/#37/#43 CI hardening → #41/#42 docs. Value-ordered, one `/deliver` pass each.
