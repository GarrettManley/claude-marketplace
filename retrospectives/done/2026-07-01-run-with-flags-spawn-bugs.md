# Retrospective: Fix run_with_flags.py shell/python spawn bugs

**Plan:** `docs/superpowers/plans/2026-07-01-run-with-flags-spawn-bugs.md`
**Commits:** see `git log main..worktree-fix-run-with-flags-spawn-bugs` for the exact, current
hash list — not pinned here by hash, since this branch was rebased onto `main` after this
retrospective's first draft, which stale-dated a prior hardcoded hash list (caught by whole-branch
adversarial review). By subject: Bug 1 fix (`_spawn_shell` direct-path invocation), a
learning/stewardship test update for the new bash invocation shape, Bug 2 fix (`_import_and_run_python`
calling-convention detection), the Task 3 tail (`docs/architecture.md` + a double-invoke regression
guard), this plan + retrospective, completion-gate evidence, and a whole-branch-review fix-round
(signature-detection robustness — see "Update" below).
**Date:** 2026-07-01

## Outcome

Fixed two confirmed, real bugs in the canonical `run_with_flags.py` hook-runtime-controls
wrapper (vendored into discipline/learning/stewardship): (1) `_spawn_shell` broke any wrapped
shell hook using `dirname "${BASH_SOURCE[0]}"` for self-location — confirmed live-broken for
discipline's actual, currently-deployed `inject_issues.sh` — fixed by passing the real script
path to bash instead of piping its content via `bash -c`. (2) `_import_and_run_python` called
wrapped Python hooks' `main_fn()` with zero args, leaking the wrapper's own `sys.argv` into any
hook using the `argv: list[str] | None = None` idiom — fixed via signature detection, carefully
scoped so a genuine hook exception is never reinterpreted as a signature mismatch and retried
(the double-invocation risk an adversarial reviewer caught and I fixed before landing). Both
fixes were caught, sharpened, and independently empirically verified through 9-agent plan review
plus two thorough per-task reviews. The vendored propagation to learning/stewardship happened
incidentally via the repo's own pre-commit hook on Tasks 1-2's commits — confirmed byte-identical
across all three plugins.

**Not completed due to running out of session time (discovered wall-clock had advanced far
faster than tracked during a long background review wait):** Task 3's `docs/architecture.md`
update (a stale paragraph describing the old `bash -c`-inlining rationale) and the final
whole-suite `bash scripts/verify.sh` re-run. Also left uncommitted: a valuable-but-optional
regression test (counter-based, proving no double-invocation) that a reviewer recommended — the
file is staged in the worktree but the commit itself hung on the pre-commit hook past a 5-minute
timeout with time nearly exhausted, so it was left uncommitted rather than risk further delay.

## What worked

- **Discovering this bug as a byproduct of a different plan's adversarial review**, rather than
  going looking for it — the hb-w61.8 retrofit plan's feasibility-auditor independently reproduced
  a live production failure while checking an unrelated claim. This was the single best-grounded
  target of the whole night (empirically reproduced, not hypothetical), in contrast to two other
  P3 items deferred earlier for weak value justification.
- **9-agent adversarial plan review caught a plan-breaking premise reversal**: my first draft's
  fix for Bug 2 would have silently disabled 5 real, currently-wrapped discipline hooks
  (`todo_issue_hook.py` and 4 others with bare `def main():`) — an independent reviewer traced
  actual `hooks.json` wiring to find this, not a hypothetical. The plan's design (signature
  detection, not a blanket fix) exists entirely because of that finding.
- **Two-tier per-task review with real empirical verification**, not just diff-reading — the
  Task 1 reviewer independently diffed all three vendored copies byte-for-byte; the Task 2
  reviewer wrote scratch hooks with counter files to empirically prove no double-invocation
  occurs, rather than trusting the code's structure alone.
- **Reacting immediately to a reviewer-caught regression** (Task 1's premature vendoring broke
  two pre-existing stewardship/learning tests asserting the old `read_text`-based error path) —
  fixed directly in the same working session rather than deferring, since a broken test in the
  tree is a real, if small, harm.

## Friction / bugs

- **Wall-clock tracking failure during a long background wait**
  - *What happened:* A per-task reviewer took ~24 minutes of reported agent duration, but actual
    wall-clock time advanced by roughly 2+ hours during that same wait — repeated `ScheduleWakeup`
    calls with ~270-280s delays did not reliably correspond to that much real elapsed time between
    checks, and I did not check absolute wall-clock time frequently enough during the wait to
    notice the drift until only ~40 minutes remained before the loop's stated 7AM MT cutoff
    (discovered at 06:16, again at 07:20 — past the deadline by then).
  - *Root cause:* Treated the sequence of `ScheduleWakeup` calls as a reliable proxy for elapsed
    time without cross-checking absolute time often enough during a single long wait.
  - *How caught:* An explicit `Get-Date`-style check, prompted by the "next wakeup" timestamp
    jumping further forward than a single delay should explain.
  - *Rule:* during any single wait longer than a couple of `ScheduleWakeup` cycles, check absolute
    wall-clock time at least once every few cycles — don't rely on the wakeup scheduler's own
    stated delay as a substitute for checking the actual clock, especially when approaching a
    hard external deadline.
- **Pre-commit hook hung past a 5-minute timeout on the final small commit**
  - *What happened:* A trivial test-only addition (one new test method, no production code
    change) failed to commit twice — once at a 2-minute timeout, once at 5 minutes — with the
    hook stuck somewhere after `lint-no-bare-python`'s first line of output.
  - *Root cause:* Not determined — likely resource contention from the many concurrent background
    bash commands and subagents run over the course of the session, or a genuinely slow check
    (`ruff`, `hook-runtime-controls`, or `vendored-sync`) under load. Not investigated further
    given the time remaining.
  - *Fix:* Left the file staged, uncommitted, with this retrospective documenting it explicitly
    rather than forcing through with `--no-verify` (never bypass hooks without explicit
    authorization) or burning more of an already-exhausted time budget.
  - *Rule:* if a `git commit` hangs unexpectedly on a trivial change close to a hard deadline,
    stop retrying immediately and hand off the staged-but-uncommitted state clearly, rather than
    repeating the same command hoping for a different result.

## Concrete improvements

- **Both real bugs fixed and landed** (`621af6d`, `e5629db`, `9486241`) on
  `worktree-fix-run-with-flags-spawn-bugs`, kept unpushed/unmerged pending the user's review —
  same standing rule as every delivery tonight (autonomous session does not push/land without
  explicit authorization).
- **Follow-up, done in a subsequent `/deliver` session (the "Task 3 tail" commit, see header):**
  1. ~~Commit the staged `test_python_hook_runtime_error_never_double_invokes` addition~~ — done;
     verified passing in isolation (`pytest -k double_invokes`) before committing.
  2. ~~Update `docs/architecture.md`'s stale `bash -c`-inlining paragraph~~ — done; now describes
     direct-path invocation and states in one sentence why the old approach broke.
  3. ~~Re-run `bash scripts/verify.sh` fresh at the final state~~ — done, clean (ran automatically
     as this repo's pre-commit hook; all 11 checks OK).
  4. **Not investigated:** why the pre-commit hook hung in the original session. No repro attempted
     in the follow-up session (it committed cleanly in ~seconds this time) — left as an open
     unknown rather than assumed-resolved; if it recurs, treat as a fresh report.
- **Confirmed explicitly:** this fix is applied to the dev clone only (`C:\Users\Garre\Workspace\claude-marketplace`),
  separate from the live installed plugin cache — inert for any running Claude Code session
  (including the one that did this work) until the user runs `/plugin` to reinstall.

## Update — whole-branch adversarial code review (same follow-up `/deliver` session)

Ran `docs:adversarial-review-code` (`code-reviewer` + `silent-failure-hunter`, session-tier model,
no down-routing) against the full `main..HEAD` diff before PR landing, per `deliver`'s Phase C step
10. Findings and dispositions:

**Fixed:**
- `_import_and_run_python`'s signature-detection `except (TypeError, ValueError)` was narrower than
  the "introspection failure" the code comment claimed to cover — widened to `except Exception` so
  any pathological `__signature__` degrades the same way every other failure path in this file does
  (fail-open), rather than crashing the wrapper.
- `takes_argv = bool(inspect.signature(main_fn).parameters)` misclassified a keyword-only-only
  signature (e.g. `def main(*, flag=None)`) as argv-taking, which would raise `TypeError` on
  `main_fn([])` — replaced with an explicit parameter-*kind* check
  (`POSITIONAL_ONLY`/`POSITIONAL_OR_KEYWORD`/`VAR_POSITIONAL`). No currently-wrapped hook has this
  shape, but the fix is cheap and directly on-topic for Task 2's own bug class.
- This retrospective's own hardcoded commit-hash list went stale the moment the branch was rebased
  onto `main` (git rebase rewrites hashes) — replaced with a by-subject description and a pointer to
  `git log`, so it can't drift out of sync with the branch again.

**Reviewed and deliberately not changed (with reason):**
- *"`_spawn_shell` dropped the old `read_text` try/except's passthrough fallback for exec
  failures."* On inspection this mischaracterizes the change: the old try/except caught
  `UnicodeDecodeError`/`OSError` from **Python reading the script's content** — a failure mode that
  no longer exists now that the script's content is never read in Python (the path is passed
  directly to `bash`). `subprocess.run` does not raise on a nonzero exit code (permission-denied or
  bad-interpreter surfaces as bash's own nonzero `result.returncode`, handled normally); the one
  path that *could* raise (`_resolve_bash()` returning a nonexistent literal `"bash"`) is a
  pre-existing gap unrelated to this diff (see next item). No actual regression here.
- *`_resolve_bash()`'s fallback to the literal `"bash"` risking an uncaught `FileNotFoundError`,
  and `sys.exit(str)` raising `ValueError` in the `int(e.code)` conversion.* Both pre-existing,
  unchanged by this diff — out of scope for this fix, which is scoped to the two named spawn bugs.
  Left as-is; worth a separate follow-up if they ever surface in practice.
- *The `main_fn([])` fix is a no-op for hooks using the `argv = argv or sys.argv` idiom (as opposed
  to `argv is None`), since an empty list is falsy — confirmed real for `plugins/learning/scripts/observe.py`,
  a currently-wrapped hook.* Traced `observe.py`'s `_detect_phase`: it treats `event["hook_event_name"]`
  (always present in real Claude Code stdin JSON) as the canonical signal and only falls back to
  `argv[1]` when that's absent — a path the code's own comment confirms only fires in
  direct-invocation tests, never in production. Confirmed benign; not fixed, since generalizing to
  every possible argv-fallback idiom is scope creep beyond this plan's two named bugs. Documented
  here rather than silently ignored.
- *Regression test coverage for the `or` idiom.* Follows from the above — not added, same reasoning.
- *Locale-dependent string assertion (`"no such file or directory"`) in the updated vendored tests.*
  Reviewer's own assessment was "acceptable" (errno strerror is stable); left as-is.
