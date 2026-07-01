# Retrospective: Fix run_with_flags.py shell/python spawn bugs

**Plan:** `docs/superpowers/plans/2026-07-01-run-with-flags-spawn-bugs.md`
**Commits:** `621af6d`, `e5629db`, `9486241` (Tasks 1-2), `8948cdc` (Task 3 tail, closed in a
follow-up `/deliver` session — see "Update" below)
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
- **Follow-up, done in a subsequent `/deliver` session (commit `8948cdc`):**
  1. ~~Commit the staged `test_python_hook_runtime_error_never_double_invokes` addition~~ — done;
     verified passing in isolation (`pytest -k double_invokes`) before committing.
  2. ~~Update `docs/architecture.md`'s stale `bash -c`-inlining paragraph~~ — done; now describes
     direct-path invocation and states in one sentence why the old approach broke.
  3. ~~Re-run `bash scripts/verify.sh` fresh at the final state~~ — done, clean (ran automatically
     as this repo's pre-commit hook on `8948cdc`; all 11 checks OK).
  4. **Not investigated:** why the pre-commit hook hung in the original session. No repro attempted
     in the follow-up session (it committed cleanly in ~seconds this time) — left as an open
     unknown rather than assumed-resolved; if it recurs, treat as a fresh report.
- **Confirmed explicitly:** this fix is applied to the dev clone only (`C:\Users\Garre\Workspace\claude-marketplace`),
  separate from the live installed plugin cache — inert for any running Claude Code session
  (including the one that did this work) until the user runs `/plugin` to reinstall.
