# Adversarial Plan Review — 2026-07-20-ci-subprocess-robustness

**Posture:** SCALED (deliver plan-review-policy `auto`; triage: Effort MID, Complexity MID, Uncertainty LOW — no HIGH axis, format self-check clean).
**Dispatched:** dimensions feasibility, risk-rollback, completeness + archetype `docs:plan-feasibility-auditor`.
**Outcome:** 3 CRITICAL, 2 IMPORTANT, several MINOR. The review + controller-run empirical reproduction **de-scoped hb-lv9** and corrected hb-duz's test isolation. All CRITICAL/IMPORTANT resolved or de-scoped below.

## CRITICAL

- **[C1] hb-lv9 root cause disputed / unverifiable RED (feasibility dim + feasibility-auditor).** Two agents disagreed on whether the pre-fix helper fails under a deleted cwd. **Controller resolution (empirical, not adjudicated):** ran the real reproduction — (a) minimal WSL git 2.43 repro: `git init <abspath>` under a deleted process cwd returns rc=0, no OSError; (b) full `pytest ci/tests/ plugins/delivery/tests/` in WSL: 100% green; (c) no `chdir`-leaker exists (all `chdir` is auto-restoring `monkeypatch.chdir`, none in delivery tests). The flake does not reproduce as diagnosed. **Resolution: hb-lv9 de-scoped** from this run; bead updated with findings; a fix with no obtainable RED would be theater.
- **[C2] hb-duz test isolation — ambient home repo (risk-rollback + feasibility-auditor).** `tmp_path` (`%TEMP%`) sits inside the `C:\Users\Garre` home git repo, so `git grep` ascends into it and exits 0/1, not ≥2 → the test never raises on the Windows host. **Verified true** (`git -C <tmp> grep` → exit 1 without ceiling; exit 128 with `GIT_CEILING_DIRECTORIES=tmp_path.parent`). **Resolution: Task 1 test sets `GIT_CEILING_DIRECTORIES=tmp_path.parent`** (same guard as `test_init.py:34-37`).
- **[C3] Scope undercount — production git calls also cwd-less (completeness).** `check-notice.py:27` and `check-doc-links.py:75` run cwd-less git via `main()`. **Resolution: moot** — this was a completeness argument for fully closing hb-lv9, which is now de-scoped. The hb-duz fix (exit-code check) is independent of cwd and unaffected.

## IMPORTANT

- **[I1] WSL has no pytest; PEP 668 blocks pip (feasibility dim).** Confirmed (WSL python3 3.12.3, no pytest). **Resolution:** the revised plan is fully cross-platform and needs no WSL path — reproduction used a throwaway `/tmp/mktvenv` venv (controller-side, not a plan step). Moot for execution.
- **[I2] hb-4d1 grep can't confirm multi-line calls (completeness + feasibility-auditor).** The `stdin=` kwarg lands on a different line than `subprocess.run(`. **Resolution: Task 2 Step 2 uses `grep -c 'stdin=subprocess.DEVNULL'` expecting `3`**, cross-checked against the `subprocess.run(` count.

## MINOR (accepted, noted in plan — not applied as blocking changes)

- `main()` contract widens to "may raise" — an uncaught traceback on a git error is the intended fail-loud; documented in Task 1 Interfaces.
- Widened failure surface: any future git-grep error mode now hard-fails legs that previously silently passed — intended direction, noted.
- hb-4d1 "11 green tests prove nothing about stdin closure" — acknowledged; the grep is the real acceptance gate, stated in Task 2 Step 1.
- Test docstring mechanism ("Popen would raise OSError") — obviated by de-scoping hb-lv9 (that test is removed).

## Gate status

CRITICAL: C1 de-scoped (documented), C2 fixed, C3 moot. IMPORTANT: I1 moot, I2 fixed. **Gate passes** — proceed to approval.
