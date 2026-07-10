# Retrospective: hb-lv9 — CI subprocess stdin-handle flake

**Plan:** `docs/superpowers/plans/2026-07-09-hb-lv9-ci-stdin-handle-flake.md`
**Commit:** `9c43d13` (`fix(ci): harden hb-lv9 regression test per code review`); fix proper at `a99be52`
**Date:** 2026-07-09
**Tracker:** `hb-lv9`

## Outcome

The combined local pytest invocation `pytest ci/tests/ plugins/delivery/tests/` went from **18 failed → 319 passed** on Windows. Root cause: pytest's fd-level capture can leave the Windows `STD_INPUT_HANDLE` holding a stale (closed but non-null) handle; any `subprocess.run(capture_output=True)` that lets stdin inherit then fails `DuplicateHandle` with `OSError: [WinError 6] The handle is invalid`. Fix: pass `stdin=subprocess.DEVNULL` at the six affected git subprocess sites (2 production gate scripts + 4 test-helpers) — none of which read stdin. A deterministic Windows-only regression test reproduces the exact stale-handle state via `ctypes.SetStdHandle` and asserts the real gate functions survive it. Two orthogonal follow-ups were surfaced and filed rather than folded in (`hb-4d1`, `hb-duz`). Lands via PR (`land-policy: pr`).

## What worked

- **Reproduce-and-verify before fixing (systematic-debugging) falsified the tracker's own root cause.** hb-lv9 was filed (by the `our-next-highest-value-modular-map` retro) with a confident *cwd-contamination* hypothesis: "a sibling test `os.chdir`s into a torn-down `tmp_path`; give `_git_repo_with_trigger` an explicit `cwd=tmp_path`." A `grep` for `os.chdir` across both suites returned nothing, the actual error was a stdin-handle `WinError 6` (not a `FileNotFoundError`/`WinError 267` a stale cwd would produce), and `pytest -s` made it vanish — three independent signals that the filed fix would have "validated nothing." Implementing the filed hypothesis directly would have been wasted work on the wrong mechanism.
- **A cheap non-destructive spike proved the fix before a line of plan was written.** Patching one call with `stdin=DEVNULL` in a Python block that captured-restored the file (no `git checkout`) turned 18 failures into 24 passes — the fix was known-good before planning, so the plan documented a proven change rather than a bet.
- **The plan-review + empirical probing killed a plausible-but-unreliable regression test.** The first guard design ran the combined invocation as a pytest subprocess. The feasibility auditor flagged it covered only 1 of 6 sites; probing then showed the trigger is *pathologically finicky* (`--ignore=test_ci_scanners.py` makes it stop reproducing; `--ignore=test_release.py` doesn't) — so a meta-test that must `--ignore` itself could silently fall below the trigger threshold and go permanently green. That pushed the redesign to a deterministic `SetStdHandle` reproducer independent of pytest collection.
- **Whole-branch code review caught a vacuous-control bug at full model tier.** Both reviewers independently flagged that `pytest.raises(OSError)` would accept a `FileNotFoundError` (git absent), so the control could pass without the stale-handle firing — fixed by asserting `winerror == 6`. The same review confirmed the trickiest part (the ctypes handle save/restore signatures) was correct, which is exactly the reassurance an adversarial pass is for.
- **Deferring orthogonal findings instead of scope-creeping.** Code review surfaced a real pre-existing silent failure (`check-notice.py` swallows `git grep` exit ≥2 as "no matches"). It was filed as `hb-duz` and explicitly deferred — changing a gate's exit-code semantics is a distinct behavioral change deserving its own test, not a rider on a flake fix.

## Friction / bugs

- **The tracker's filed root cause was wrong, and its "tell" was a red herring.**
  - *What happened:* hb-lv9 (and the retro that filed it) attributed the flake to a stale process cwd, citing a phantom deleted-clone path in the traceback as the "tell."
  - *Root cause:* The phantom path was just the display of a subprocess arg / process cwd, not the failure mechanism — the `Popen` failed during handle duplication (`_make_inheritable`), before cwd is even consulted. The real cause is pytest fd-capture leaving `STD_INPUT_HANDLE` stale.
  - *How caught:* Reproducing first, then reading the actual `WinError 6` frame (stdin handle, not cwd), grepping for the hypothesized `os.chdir` (absent), and observing `pytest -s` fixes it.
  - *Fix:* Fixed the proven cause (`stdin=DEVNULL`); recorded the falsified hypothesis prominently in the plan's Global Constraints so a future reader doesn't "correct" the fix back to the wrong mechanism.
  - *Rule:* A tracker's stated root cause is a hypothesis, not a fact — reproduce and read the actual failure frame before implementing the filed fix, especially when the filer noted they didn't fully confirm it.

- **First regression-test design was plausible but fundamentally unreliable.**
  - *What happened:* The initial guard shelled out to `pytest` over the combined invocation and asserted exit 0, using `--ignore=<self>` to avoid recursion.
  - *Root cause:* The flake's trigger depends on the *exact set* of co-collected modules (removing `test_ci_scanners.py` suppresses it), so `--ignore`-ing even one file — including the guard itself — can drop below the trigger threshold, yielding a test that passes vacuously forever.
  - *How caught:* Feasibility auditor flagged the coverage gap; empirical `--ignore` probing then proved the fragility quantitatively.
  - *Fix:* Replaced with a deterministic `_StaleStdin` context manager (`SetStdHandle` → stale handle → restore) that reproduces the *mechanism*, not the finicky *collection*, and exercises the real gate functions plus a non-vacuous control.
  - *Rule:* When guarding a heisenbug, reproduce the underlying mechanism deterministically — don't pin a regression test on the fragile emergent condition that first surfaced it.

## Concrete improvements

- **`stdin=subprocess.DEVNULL` at the six git subprocess sites** (`ci/check-notice.py`, `ci/check-doc-links.py`, `ci/tests/test_ci_gates.py`, `ci/tests/test_check_doc_links.py`) — done, landed. Extends the pattern already shipping in `ci/release.py`.
- **`ci/tests/test_combined_invocation_regression.py`** — deterministic Windows-only guard (`SetStdHandle` stale-handle reproduction, real-function survival + non-vacuous `winerror==6` control, `SetStdHandle`-return checked). Done, landed. Reusable pattern for any future stdin-handle-inheritance guard.
- **`hb-4d1`** (follow-up) — `plugins/git/tests/test_init.py` has the same unfixed stdin-inheritance in `git init`/`git add`, outside hb-lv9's repro. Filed, P3.
- **`hb-duz`** (follow-up, bug) — `check-notice.py`'s `triggering_files()` swallows `git grep` exit ≥2, so the NOTICE gate falsely passes on a real git error. Pre-existing, found in review. Filed, P3.
