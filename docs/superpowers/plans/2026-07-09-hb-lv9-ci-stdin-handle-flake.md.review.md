# Adversarial plan review — hb-lv9 CI stdin-handle flake

**Posture:** SCALED (triage: Effort LOW, Complexity MEDIUM [5 files], Uncertainty LOW; `plan-review-policy: auto`, no axis HIGH → SCALED). Dimensions: feasibility, risk/rollback, completeness. Archetype: `docs:plan-feasibility-auditor`. Constitution: unbound (not separately checked).

**Verdict:** Executable as written, no CRITICAL. Two IMPORTANT + four MINOR, all resolved before landing.

## Findings and resolutions

### IMPORTANT 1 — Regression guard covered only 1 of 6 fixed sites (RESOLVED, design changed)
The original meta-test's chosen inner node `test_check_notice_real_repo_is_clean` calls only `cn.main()` (git grep) — it never touches `_git_repo_with_trigger`, and the delivery module spawns no subprocesses. So the guard exercised exactly one fixed site; a future revert of the helper fixes would stay green.
**Resolution:** Empirical probing then showed the flake's pytest-collection trigger is pathologically finicky (`--ignore=test_ci_scanners.py` *stops* it reproducing; `--ignore=test_release.py` doesn't), so *any* `--ignore=<self>` meta-test is an unreliable guard. Replaced the whole approach with a **deterministic** guard: reproduce the exact `STD_INPUT_HANDLE` stale-handle state via `SetStdHandle`, then exercise the two real gate-script functions (`triggering_files()`, `tracked_markdown()`) plus a non-vacuous control. Verified RED (`2 failed, 1 passed`) → GREEN (`3 passed`).

### IMPORTANT 2 — Step 2 expected-output wrong + no RED-didn't-fire fallback (RESOLVED)
The minimal 2-module pair can produce at most 1 failure, not the "18" the plan stated; and the plan gave no instruction if RED unexpectedly passed.
**Resolution:** Moot under the new deterministic design (RED is not collection-dependent). Step 2 now records the actual observed RED (`2 failed, 1 passed in 0.12s`, both `OSError [WinError 6]`), which is deterministic and reproducible.

### MINOR 3 — Stale scope claim about test_release.py (RESOLVED)
Plan listed `test_release.py` as an unfixed out-of-scope site; it (and `ci/release.py`) already carry `stdin=subprocess.DEVNULL`.
**Resolution:** Scope-boundary section rewritten — the pattern is now correctly framed as an *established in-repo precedent*; the one genuinely-unfixed site (`plugins/git/tests/test_init.py:18,26`) is named, and a follow-up bead is filed.

### MINOR 4 — verify.sh path (RESOLVED)
Gate is `scripts/verify.sh`, not `verify.sh`.
**Resolution:** Verification section corrected to `bash scripts/verify.sh`; run confirmed `EXIT: 0`.

### MINOR 5 — no timeout on inner pytest subprocess (RESOLVED, obsolete)
**Resolution:** Obsolete — the deterministic guard spawns only a fast `git --version` control and calls in-process functions; no long-lived inner pytest to bound.

### MINOR 6 — plan ended at commit, PR landing unstated (RESOLVED)
**Resolution:** Landing is `land-policy: pr` (delivery config), handled by the deliver lifecycle Phase C — a PR is opened and left for maintainer merge on green checks; not pushed to `main`.

## Risk/rollback (auditor assessment, accepted)
`stdin=subprocess.DEVNULL` on the two production gate scripts is behaviorally inert: `git grep`/`git ls-files` never read stdin, both already use `capture_output=True`, and the identical pattern already ships in `ci/release.py` without incident. GitHub CI (runs the scripts via `scripts/verify.sh` outside pytest) sees no change. Rollback is a two-line revert per file. Confirmed empirically: `scripts/verify.sh` runs both patched scripts clean (`EXIT: 0`).

## Signal (accepted, no action)
The auditor's original SIGNAL (delivery suite running twice per CI cell) applied only to the abandoned meta-test design; the deterministic guard adds no cross-suite coupling.
