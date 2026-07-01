# Wholesale Engineering Audit — claude-marketplace

**Date:** 2026-07-01 · **Scope:** documentation, tests, implementation, CI/release, security posture, process/governance · **Method:** read-only multi-agent fan-out with adversarial verification (see Methodology) · **Commit audited:** branch point `37d163b`.

This is a consultant-style audit: an outside read of the whole engineering solution, framed as a gaps **and** possibilities analysis. It is deliberately critical — the strengths section is real, but the body is weighted toward what to fix and what is now possible, because that is what an audit is for.

## Executive summary

claude-marketplace is a **well-governed, above-average** plugin marketplace: 13 plugins, ~1,630 tests across 72 files with **zero skipped/xfailed**, an 11-gate pre-merge verification suite, 13 ADRs, a dual-changelog model, and a public-repo CI matrix spanning three OSes and two Python versions. The engineering discipline visible in the *process* layer (ADRs, gates, conventional-commit release automation) is genuinely strong and would pass most professional bars.

The gap between that process discipline and the *correctness* of the code the process guards is the audit's central finding. Two CRITICAL logic bugs sit in the exact machinery the repo sells — an agent-discipline gate whose completion check passes an unfilled plan (`TODO: …` slips through), and a scope-confinement hook defeated by a one-line path-traversal. A repo whose thesis is "disciplined gating" has two gates that don't hold. Neither is exploitable-by-attacker in the classic sense (these are agent-guidance tools, not security boundaries — the repo says so), but both silently fail open in precisely the case they exist to catch.

None of the CRITICAL/IMPORTANT findings block the repo's current use; all are fixable and most are small. This audit landed five trivial documentation fixes directly (see Quick wins applied) and files the substantive findings as a tracked backlog (see Backlog).

| Area | Grade | One-line rationale |
|------|-------|--------------------|
| Implementation | **Adequate** | Clean, small, readable modules — but two CRITICAL fail-open bugs in gating code plus three correctness gaps (eviction non-determinism, non-atomic release, frontmatter mis-parse). |
| Tests | **Adequate** | Excellent breadth and zero skips, undercut by coverage-padding suites, a vacuous conditional assertion, and two shipped modules with zero coverage. |
| CI & release | **Adequate** | Strong 5-check matrix; weakened by a non-atomic release path, an incorrect never-tagged-plugin bump, unpinned Actions, and no local test gate. |
| Documentation | **Adequate** | Strong ADR discipline and per-plugin READMEs; visible changelog drift (partially fixed — the missing `delivery` entry is fixed here; the aggregation gate + full catch-up remain backlog) and one README that omits a shipped command. |
| Security posture | **Needs attention** | For a repo that *ships security hooks*, a path-traversal escape, a NotebookEdit scan bypass, and mutable-tag supply chain are the sharpest cluster. |
| Process & governance | **Strong** | ADRs, dual changelog, retrospectives, gate suite, release automation — above bar; the completion-gate bug is the one crack. |

## Methodology

**Fan-out.** Six read-only finder agents (implementation, tests, CI/release, docs, security, possibilities) swept the repo in parallel, each required to attach `file:line` plus a reproducing command to every finding. Three read-only exploration agents mapped the surface first (inventory, not conclusions).

**Verification protocol (two layers).**
1. Every MINOR finding was passed to an independent **refute-lens** agent instructed to *disprove* it and default to "refuted" on any doubt.
2. Every CRITICAL/IMPORTANT finding was **re-verified by the orchestrator** with a fresh command run in the audit worktree — not trusted from the finder's report.

**Ledger counts:** 26 raw findings (3 CRITICAL, 12 IMPORTANT, 11 MINOR). The refute-lens **killed 4** MINOR findings. Of the 15 CRITICAL/IMPORTANT findings, **14 reproduced live** under orchestrator re-verification; 1 (macOS-CI promotion) is a lower-confidence possibility that needs CI run history to confirm and is flagged as such.

**Killed claims (recorded honestly).** A first-pass exploration agent reported CodeQL as "inert" (guarded by `!repository.private`); re-verification refuted this — the repo *is* public, so `codeql.yml` is live. Four MINOR findings (IDs F20, F21, F25, F26) were dropped by the refute-lens (ADR status-vocabulary split, release.py H1 perpetuation, missing devcontainer, skill-index discoverability) as either non-defects or overstated — which is why the MINOR list below skips those four IDs. These are listed so the reader can see the filter working, not hidden.

**Limits — what this audit did NOT cover.** Live runtime behavior of hooks inside a real Claude Code session (only static + unit-level reproduction); the actual behavior of external consumers of the marketplace; performance/load; and the corporate/private repos deliberately out of scope. Findings are code-level and reproducible, not field-observed.

## Strengths

These are real and above-bar, verified during the sweep:

- **Verification gate breadth.** `scripts/verify.sh` chains 11 independent gates (bare-python ban, ruff, version-drift, manifest validation, hook-runtime routing, vendored byte-identity, frontmatter, changelog H1, skill-index freshness, NOTICE attribution, doc-link integrity). Most repos have 2-3.
- **Test breadth with zero skips.** ~1,630 tests, and `grep` for `@pytest.mark.skip/xfail/skipif` returns **nothing** — the suite exercises both OS branches via `monkeypatch` rather than skipping (`plugins/learning/tests/test_storage.py`). That is a deliberate, disciplined choice.
- **ADR discipline.** 13 ADRs record the load-bearing decisions (per-plugin subtrees, vendored-hook byte-identity, releases-stay-local, tag-after-merge, PR-gated landing) with rejected alternatives. This is the artifact most repos never write.
- **Deliberate, gate-enforced duplication.** The `hook_flags.py`/`run_with_flags.py` triple-copy is a DRY "violation" that is actually correct — it is forced by the per-version plugin-cache install model and *enforced byte-identical* by `ci/check-vendored-sync.py` (ADR 0002). Documented trade-off, not an accident.
- **Release automation.** `ci/release.py` derives per-plugin conventional-commit bumps and writes changelogs mechanically, keeping `marketplace.json` a derived-and-checked duplicate of the per-plugin `plugin.json` source of truth.
- **Self-honest config.** `.claude/delivery.local.md` documents that PR-gated landing does *not* eliminate owner-bypass — it names its own residual limitation instead of overclaiming.

## Gaps

Ranked CRITICAL → IMPORTANT → MINOR. Dispositions: `fixed-here` (landed on this branch), `quick-win` (a trivial `fixed-here`), `issue` (filed post-PR — see Backlog), `report-only` (recorded, no action proposed), `accepted-risk` (acknowledged, deliberately not fixed).

### CRITICAL

| # | Finding | Evidence | Impact | Disposition |
|---|---------|----------|--------|-------------|
| F01 | Completion-gate placeholder check fails open on `TODO: <prose>` | `plugins/retrospective/hooks/plan_completion_check.py:96-137`. `check_text()` on a plan whose entire Retrospective is `TODO: fill in the details…` returns **`complete=True`**. `_is_placeholder_body()` strips the keyword then checks for leftover text; trailing prose survives and reads as "real content". `check_verification_addressed()` avoids this only via a redundant second guard the completion check lacks. | The one mechanism meant to stop retrospecting an unfinished plan silently passes the most natural form of an unfilled section. Defeats the completion-discipline workflow (`/plan-completion`, the `ExitPlanMode` enforcement in CLAUDE.md) with no error. | issue |
| F02 | `scope_bind` path confinement defeated by traversal | `plugins/evidence/scripts/scope_binding.py:181-184`. `check_path('/opt/data/engagement-2026/../../../../etc/passwd', scope)` returns `(True, "matches prefix")`. Prefix check runs on the raw string; `..` segments are not normalized, and the "not-yet-existing path" branch (normal Write-new-file case) never resolves them. | The scope-confinement control (SECURITY.md advertises it confining `WebFetch`/writes to declared paths) can be walked out of with a literal `../`. It is opt-in and self-described as defense-in-depth, but it fails open exactly where confinement matters. | issue |
| F03 | Root CHANGELOG drift with no automation | `CHANGELOG.md:11-59` vs per-plugin releases; ADR 0008 predicted exactly this. The `delivery` plugin was never recorded; multiple plugin bumps unaggregated. | The public program-level changelog understates the project. ADR 0008 flagged the risk; it is now realized. | one-line entry **fixed-here** (`112fb69`); full catch-up + gate → issue |

### IMPORTANT

| # | Finding | Evidence | Impact | Disposition |
|---|---------|----------|--------|-------------|
| F04 | GateGuard eviction is hash-seed random, not recency | `plugins/discipline/scripts/gateguard.py:147-196`. Three identical runs evict three different sets — `save_state()` unions `checked` into a `set`, whose str iteration order depends on the (unset, randomized) `PYTHONHASHSEED`, then keeps a trailing slice. | On sessions touching >500 files, cleared files re-fire the fact-forcing gate at random — silent, non-reproducible friction contradicting the "first touch per file" contract. | issue |
| F05 | `release.py --apply` is non-atomic, no rollback | `ci/release.py:327-341`. `_set_version()` + `_prepend_changelog()` write to disk *inside* the loop; a later plugin's H1 check can `return 1` after earlier plugins are already mutated — while printing "refusing to commit". | A failed multi-plugin release leaves earlier plugins version-bumped on disk with no commit/tag; a re-run double-applies. Corrupts changelog/semver state. | issue |
| F06 | `_parse_frontmatter` treats prose as config when the fence never closes | `plugins/discipline/scripts/discipline_config.py:125-151`. A doc opening with `---` and no closing fence yields bogus `key: value` pairs from ordinary prose (docstring promises `{}`). | A project doc starting with `---` + a `key:`-shaped prose line can silently override discipline config (gh target, main branch, bd auto-close). | issue |
| F07 | Vacuous conditional assertion | `plugins/discipline/tests/test_coverage_boost.py:1256-1257`: `if result: assert _is_block(result)`. If the block path emits nothing, the assertion is skipped and the test passes without verifying anything. | A test that can pass without exercising its target — false coverage signal. | issue |
| F08 | Two shipped modules have zero coverage | `plugins/discipline/hooks/todo_issue_hook.py`, `plugins/discipline/scripts/_inject_issues.py` — no test imports either (not even the catch-all suites). | Untested hook logic ships in a 1.1.0 plugin. | issue |
| F09 | `env_flags.is_on()` undertested | `plugins/learning/scripts/env_flags.py:14-16` accepts 5 on-values; tests exercise 1, no dedicated test. | Flag-parsing regressions (case, `enabled`/`yes`) would pass CI. | issue |
| F10 | `release.py` cannot compute a correct bump for a never-tagged plugin | `ci/release.py:132-193,264-274`. `delivery` has no `delivery-v*` tag; `--dry-run` proposes `0.2.1 → 0.3.0` over the plugin's **entire** history (no baseline), so the delta is not incremental. Confirms the `velvet-nygaard` retro claim. | The one un-released plugin cannot be released correctly through the standard path without a manual seed tag. | issue |
| F11 | retrospective README omits a shipped command | `plugins/retrospective/README.md` — 0 hits for `pre-plan-brief`, though `commands/pre-plan-brief.md` and `skills/pre-plan-brief/` ship. | A shipped command is undiscoverable from its plugin's own docs. | issue |
| F12 | `secret_scan` / `scope_bind` ignore `NotebookEdit` | `plugins/evidence/hooks/secret_scan.py:55-73`. `extract_text('NotebookEdit', {'new_source': '…AKIA…'})` returns `''` — notebook cell writes are never scanned. | Credentials written via `NotebookEdit` bypass the secret-scan hard block entirely. | issue |
| F13 | Supply chain uses mutable tags / unpinned tooling | `.github/workflows/ci.yml:30-99`: `actions/*@v6`/`@v7`, `Install-Module PSScriptAnalyzer` unpinned, `npm install -g @anthropic-ai/claude-code` unpinned. | A compromised or shifted upstream tag changes CI behavior with no lockfile; standard hardening (SHA-pin) absent. | issue |
| F14 | macOS CI leg still `continue-on-error` | `.github/workflows/ci.yml:16-19`; workflow-reported green streak (not orchestrator-re-verified — needs run history). | A now-stable leg provides no signal; a real macOS regression would pass silently. | issue (verify streak first) |
| F15 | Local gate runs no tests | `scripts/verify.sh` (0 pytest); `.githooks/pre-commit:11` comment confirms pytest is CI-only. | A committer passes the full local gate while breaking tests; the 90% coverage gate is invisible until CI. | issue |

### MINOR (report-only unless a backlog item absorbs them)

- **F16** `_is_destructive_rm` requires both `-r` and `-f`, missing plain `rm -r` (`gateguard.py:281-299`).
- **F17** 6 `.ps1` scripts (5× `init.ps1`, `register_nightly.ps1`) have zero behavioral coverage — only their bash siblings are tested.
- **F18** 5 `test_init.py` files hardcode the Git-for-Windows bash path with no `shutil.which` fallback/skip.
- **F19** ADR 0013's coverage-gate rationale wording doesn't match the current combine mechanism.
- **F22** `plugin-authoring.md` basename collision: `docs/plugin-authoring.md` vs `plugins/delivery/references/plugin-authoring.md` — same name, drift risk, no gate.
- **F23** `requirements-dev.txt` floor-only bounds, no lockfile, no Dependabot pip coverage.
- **F24** No gate verifies a `plugin.json` bump has a matching entry in that plugin's own CHANGELOG.

## Quick wins applied

Five trivial, confirmed, doc-level fixes landed on this branch, each its own conventional commit:

| Commit | Change |
|--------|--------|
| `776c3d1` | Drop the unmaintainable `CITATION.cff` `version` field (optional in CFF 1.2; per-plugin `plugin.json` is the SoT), normalize repo URL owner casing. |
| `52e2ed7` | Make pre-1.0 plugin support status explicit in `SECURITY.md` (policy unchanged — honest clarification, owner-decided). |
| `f6e5238` | Drop the stale "most thorough" superlative in `README.md:28` (it wasn't). |
| `932d093` | Add the majority-convention frontmatter to ADRs 0003-0006 (matches the other 9). |
| `112fb69` | Record the `delivery` plugin's addition in the root `CHANGELOG.md` (was never listed). |

## Backlog

Filed as GitHub issues after this PR opens (so bodies link a real commit permalink). Ranked by severity; the two CRITICALs first.

| Severity | Title | Finding |
|----------|-------|---------|
| CRITICAL | Completion-gate placeholder check fails open on `TODO: <prose>` | F01 |
| CRITICAL | `scope_bind` path confinement defeated by `../` traversal | F02 |
| IMPORTANT | secret-scan/scope-bind ignore `NotebookEdit` tool inputs | F12 |
| IMPORTANT | `release.py --apply` is non-atomic; partial writes on abort | F05 |
| IMPORTANT | `release.py` can't compute a correct bump for a never-tagged plugin | F10 |
| IMPORTANT | `_parse_frontmatter` parses prose as config with no closing fence | F06 |
| IMPORTANT | GateGuard checked-file eviction is hash-seed random | F04 |
| IMPORTANT | Pin CI Actions/tooling by SHA (mutable tags today) | F13 |
| IMPORTANT | Local gate runs no tests; decide the local pytest story | F15 |
| IMPORTANT | Zero coverage: `todo_issue_hook.py`, `_inject_issues.py` | F08 |
| IMPORTANT | Vacuous conditional assertion in coverage-boost suite | F07 |
| IMPORTANT | `env_flags.is_on()` undertested (1 of 5 spellings) | F09 |
| IMPORTANT | retrospective README omits shipped `/pre-plan-brief` | F11 |
| IMPORTANT¹ | Root-changelog aggregation gate + catch-up | F03 |
| IMPORTANT | Promote macOS CI leg from `continue-on-error` (verify streak first) | F14 |

¹ F03 is CRITICAL in Gaps; its acute part (the missing `delivery` entry) was fixed by quick-win `112fb69`, leaving only the IMPORTANT residual — the aggregation gate + full catch-up — as backlog.

## Possibilities

Each names its consumer and a first concrete step (findings without a named consumer were dropped in triage).

1. **Root-changelog aggregation gate** *(consumer: maintainer)* — a `ci/` check asserting every `plugins/*/plugin.json` version string appears in root `CHANGELOG.md`. First step: a 20-line scanner added to `verify.sh`; it would have caught the `delivery` omission at commit time. (Also closes F03/F24.)
2. **Local test gate parity** *(consumer: maintainer + contributors)* — run the fast, portable pytest suite in `verify.sh`/pre-commit, or explicitly document why not. First step: time the suite (already fast) and add a `pytest -q` step behind a `--fast` opt-out. (Closes F15.)
3. **Promote the macOS CI leg** *(consumer: maintainer)* — flip `continue-on-error: false` once the green streak is confirmed from run history, turning dead signal into real coverage. First step: `gh run list --workflow=ci.yml` audit. (Closes F14.)
4. **SHA-pin the supply chain** *(consumer: external users installing the marketplace)* — pin Actions to commit SHAs + add Dependabot for Actions and pip. First step: `dependabot.yml` with the `github-actions` ecosystem. (Closes F13/F23.)
5. **Behavioral PowerShell coverage** *(consumer: Windows users)* — Pester tests (or subprocess parity tests) for the `.ps1` scripts currently only static-linted. First step: one Pester test for `register_nightly.ps1`. (Closes F17.)
6. **Skill-index as a published page** *(consumer: external readers)* — render `docs/skill-index.md` to a GitHub Pages surface for discoverability. *Lower priority — the refute-lens judged the flat-markdown form adequate for current traffic; listed for completeness, not urgency.*

## Appendix — evidence table

14 confirmed findings, each reproduced by a fresh command in the audit worktree (2026-07-01); F14 is the one lower-confidence entry (workflow-reported, not orchestrator-re-verified — needs CI run history). Full commands and output excerpts are in the audit ledger (`.audit-findings.local.md`, untracked).

| # | Sev | Reproduction (abbreviated) | Verdict |
|---|-----|----------------------------|---------|
| F01 | CRIT | `check_text(<TODO-only Retrospective>)` → `complete=True` | CONFIRMED |
| F02 | CRIT | `check_path('…/../../../../etc/passwd', scope)` → `(True, matches)` | CONFIRMED |
| F03 | CRIT | `sed -n '1,60p' CHANGELOG.md` vs per-plugin releases | CONFIRMED |
| F04 | IMP | 3× `prune_checked_entries(520 files)` → 3 different evicted sets | CONFIRMED |
| F05 | IMP | `sed -n '327,341p' ci/release.py` — write-before-check, no restore | CONFIRMED |
| F06 | IMP | `_parse_frontmatter('---\n<prose>…')` → 5 bogus keys | CONFIRMED |
| F07 | IMP | `test_coverage_boost.py:1256` `if result: assert …` | CONFIRMED |
| F08 | IMP | `grep import (todo_issue_hook|_inject_issues) tests/` → none | CONFIRMED |
| F09 | IMP | `grep is_on plugins/learning/tests/` → none | CONFIRMED |
| F10 | IMP | `git tag --list 'delivery-v*'` empty; `--dry-run` → 0.3.0 over full history | CONFIRMED |
| F11 | IMP | `grep -c pre-plan-brief plugins/retrospective/README.md` → 0 | CONFIRMED |
| F12 | IMP | `secret_scan.extract_text('NotebookEdit', …)` → `''` | CONFIRMED |
| F13 | IMP | `grep 'uses: actions/' ci.yml` → `@v6`/`@v7` | CONFIRMED |
| F14 | IMP | macOS leg `continue-on-error` (streak workflow-reported) | LOWER-CONFIDENCE |
| F15 | IMP | `grep -c pytest scripts/verify.sh` → 0 | CONFIRMED |

**Refuted / killed claims** (checked, not confirmed — recorded for honesty): "CodeQL inert" (repo is public → CodeQL live); ADR status-vocabulary split (non-defect); `release.py` H1 perpetuation (refuted); missing devcontainer (overstated); skill-index discoverability (adequate for current traffic). Refute-lens dropped 4 of 26 raw findings; 1 of 15 verified findings is lower-confidence.
