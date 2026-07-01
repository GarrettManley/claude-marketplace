# Retrospective: claude-marketplace Wholesale Engineering Audit

**Plan:** `~/.claude/plans/a-wholesale-audit-of-frolicking-sun.md`
**Commit:** `0bb6176` (`docs: link audit backlog to filed issues (#27, #30-#43)`)
**Date:** 2026-07-01

## Outcome

Delivered a consultant-grade wholesale audit of claude-marketplace via the full `/deliver` lifecycle. Shipped `docs/audits/2026-07-01-engineering-audit.md` (8-section gaps+possibilities report), 5 quick-win doc fixes, and 14 backlog issues (#30–#43, plus pre-existing #27 for F10) on branch `audit/2026-07-wholesale` → PR #29. The audit itself found 26 findings (3 CRITICAL, 12 IMPORTANT, 11 MINOR), of which 2 CRITICALs are real fail-open bugs in the repo's own gating code (completion-gate `TODO:` bypass; `scope_bind` `../` traversal). 8 commits, docs-only, `verify.sh` green.

## What worked

- **Read-only finder + refute-lens + orchestrator re-verification (3 layers).** The refute-lens killed 4 of 26 findings and the orchestrator re-verification reproduced 14/15 CRITICAL-IMPORTANT with fresh commands — the discipline caught a real explorer hallucination ("CodeQL inert", refuted because the repo is public) before it reached the report.
- **Dedupe-before-file in Task 5.** `gh issue list` surfaced pre-existing #27 = finding F10, preventing a duplicate; F10 was recorded as `#27 (pre-existing)` instead of double-filed.
- **Workflow tool for the fan-out.** 6 dimensions × find→verify pipeline in one background workflow (17 agents) kept main context lean; findings came back as one structured JSON blob parsed into the ledger programmatically rather than pasted.
- **Parallel Task 1 (audit) + Task 2 (quick-wins).** The two independent workstreams ran concurrently; quick-wins were reviewed and merged while the audit workflow was still running.
- **Stage-before-gate discovery.** Both `check-doc-links.py` and `verify.sh` were run only after `git add`, because the plan (from the plan-review) knew `check-doc-links` scans `git ls-files` and skips untracked files.
- **Adversarial plan review paid for itself.** The 9-agent plan review caught 2 CRITICALs (issues-before-PR ordering; report structure missing the sections downstream tasks consumed) and two vacuous acceptance gates *before* execution — cheap insurance that would have been expensive rework.

## Friction / bugs

- **Root-level `pytest` fails at collection in this repo**
  - *What happened:* the plan's Task 4 specified `python3 -m pytest -q` at repo root; it exited 2 with "Plugin already registered under a different name."
  - *Root cause:* `--import-mode=importlib` + multiple `plugins/*/tests/conftest.py` all resolving to the same `tests.conftest` module name collide. Structural, pre-existing, unrelated to the docs-only branch.
  - *How caught:* running the command per the plan; recognized the error as a collection (not test) failure and confirmed the branch adds no conftest.
  - *Fix:* ran the CI-equivalent per-directory loop (`pytest ci/tests` + `for d in plugins/*/tests`), all `[100%]`. Recorded the corrected command in the plan's Verification block.
  - *Rule:* in this repo, "run the tests" means per-directory, never root-level pytest — the plan-writer should copy the CI invocation, not assume `pytest -q` works.

- **Pending-retro marker written inside the worktree, not the main checkout**
  - *What happened:* the `ExitPlanMode` marker hook wrote `retrospectives/pending/<slug>.marker` into `.worktrees/audit-2026-07-wholesale/`, not the main checkout — the exact recurrence the `i-m-looking-to-deliver-glimmering-honey` retro already recorded.
  - *Root cause:* the marker hook resolves the workspace root from `$PWD`, which was the worktree during plan mode.
  - *How caught:* checked both `retrospectives/pending/` locations at retro time.
  - *Fix:* wrote the done file into the worktree (so it lands atomically with PR #29) and deleted the worktree marker.
  - *Rule (known, still unfixed):* the marker hook should resolve to the main checkout, not the active worktree — worth a discipline/retrospective-plugin follow-up.

## Concrete improvements

- **Audit backlog is now tracked** — issues #30–#43 (label `audit-2026-07`) + #27; the 2 CRITICAL code bugs (F01 completion-gate bypass #30, F02 scope_bind traversal #31) are the highest-value follow-ups for the next marketplace cycle.
- **Plan-writer note (follow-up):** for this repo, hardcode the per-directory pytest invocation in any plan's Verification section — the root `pytest -q` collision will trip every future plan that copies the generic command.
- **Marker-in-worktree recurrence (follow-up):** second occurrence of the same hook bug across deliveries — candidate for an actual fix in the marker hook's workspace-root resolution, not just per-retro cleanup.
- **Report authored by orchestrator, not a subagent** — synthesis over 26 findings + 3 inventories was correctly kept in main context; the accuracy reviewer (fresh subagent) then independently reproduced evidence and caught one severity-labeling inconsistency (F03 residual). This find→author→independently-verify split worked well for a report deliverable.
