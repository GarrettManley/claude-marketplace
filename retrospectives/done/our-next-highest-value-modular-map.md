# Retrospective: Implementer cwd/worktree Confirmation Guardrail

**Plan:** `~/.claude/plans/our-next-highest-value-modular-map.md`
**Commit:** `8ab1b81` (`fix(delivery): require dispatched subagents to confirm cwd before editing (hb-ice)`) — shipped as PR #54, delivery 0.3.1
**Date:** 2026-07-09

## Outcome

Added a standing "confirm your working directory before editing" guardrail to the `delivery` plugin's Phase B step 7 (`SKILL.md`): every dispatched implementer/task-reviewer must run `git rev-parse --show-toplevel` + `git branch --show-current` and confirm before touching any file. This closes the silent-wrong-checkout failure class that cost a wasted dispatch during PR #26 (the incident the velvet-nygaard retro named as an untracked follow-up; `hb-ice` was that tracker). Guarded by a bullet-scoped structural contract test (`TestImplementerCwdGuardrail`), synced the command précis, and released delivery `0.3.0 → 0.3.1`. Landed as PR #54.

## What worked

- **Feasibility as a hard filter during target selection.** The two higher-priority P2 beads (hb-x91 Defender perf, hb-dzz discovery-loop tasks 2/4) were ruled *out* before proposing them — both need an admin terminal / live external spend / human supervision and cannot land in an autonomous `/deliver` pass. Filtering on "is this actually deliverable end-to-end here?" before ranking avoided planning work that couldn't close.
- **Dogfooding the fix.** Before editing, I ran the very `git rev-parse --show-toplevel` / `git branch --show-current` confirmation the guardrail mandates — catching (had it existed) exactly the wrong-checkout risk in the change that fixes it.
- **The triage SKIP posture matched reality.** All three plan-review axes scored LOW (2 tasks, 6 files, pattern-extending), so the review triage correctly dispatched *zero* plan-review agents instead of a disproportionate 9-agent review on a 3-file doc change — the mechanism the delivery plugin exists to add, working as designed.
- **Adversarial code review earned its keep on a tiny diff.** Even on 138 lines, silent-failure-hunter surfaced two real non-vacuousness gaps (assertions scoped to all of step 7 → cross-bullet false-green risk; an `OR` citation that passes on a gutted one-liner). A single bullet-scoping refactor (`extract_cwd_guardrail_bullet()`, `#26` as a hard `and`-anchor) subsumed both. Both reviewers independently reconstructed RED from `HEAD~2` and mutation-tested the anchors.

## Friction / bugs

- **ci/tests cwd-contamination flake (pre-existing, not this change)**
  - *What happened:* `pytest ci/tests/ plugins/delivery/tests/` failed 8 tests in `check-notice`/`check-doc-links` with `OSError` at `subprocess.run` Popen; scoped runs (`ci/tests/` alone = 293 green; delivery alone = 23 green) and `verify.sh` were all clean.
  - *Root cause:* `_git_repo_with_trigger` (`ci/tests/test_ci_gates.py:122`) runs `git init` with **no explicit `cwd`**, inheriting the process cwd; a sibling test in the combined collection `os.chdir`s into a `tmp_path` that pytest tears down, leaving the process cwd pointing at a deleted directory → Popen fails.
  - *How caught:* Reading the traceback — the phantom path `C:\Users\Garre\source\repos\claude-marketplace` (a *deleted* old clone location) was the tell that cwd, not the code, was the problem; confirmed the failing tests run *before* my additions and my additions do zero chdir/subprocess/fs-writes.
  - *Fix:* Scoped completion evidence to the documented CI form (`pytest ci/tests/`) + `verify.sh`; filed **hb-lv9** for the isolation bug.
  - *Rule:* When a *combined* test run fails but *scoped* runs pass, suspect cwd/`tmp_path` contamination before blaming your own change — verify against the failing test's actual subprocess call site and its cwd, not the pytest-reported file path (which can display a stale/phantom location).

- **The literal fix target was read-only**
  - *What happened:* hb-ice named `implementer-prompt.md`, which lives only in the official superpowers cache (`claude-plugins-official/superpowers/6.1.1/...`) — version-pinned, not editable durably.
  - *Root cause:* The natural home for the guardrail (upstream SDD template) is an external repo we can PR but not merge, and whose cache is overwritten on reinstall.
  - *How caught:* Phase A feasibility check (Glob for the file across our repos vs the cache) before writing the plan.
  - *Fix:* Relocated the durable, in-our-control fix to our delivery plugin's own Phase B dispatch guidance; the upstream PR was explicitly scoped out per user decision (local delivery plugin only).
  - *Rule:* Verify the named target file is writable *and durable* before planning to edit it — an external version-pinned cache needs either an upstream PR or a local-wrapper redirect, and that fork is a design decision worth surfacing to the user early.

## Concrete improvements

- **Delivery plugin guardrail** — `plugins/delivery/skills/deliver/SKILL.md` step 7 + `TestImplementerCwdGuardrail` / `extract_cwd_guardrail_bullet()` in `test_deliver_contract.py`, précis synced, delivery 0.3.1. Done — PR #54 (`8ab1b81` fix, `96ad89e` release, `d1ec0e2` review-fix).
- **hb-lv9** — ci/tests cwd-contamination flake (give `_git_repo_with_trigger` and the doc-links equivalent an explicit `cwd=tmp_path`, and/or find the chdir-leaking test). Follow-up, P3.
- **Upstream superpowers `implementer-prompt.md` guardrail** — deliberately out of scope this pass; a potential future follow-up if non-`/deliver` SDD usage needs the same protection. Not filed (no concrete demand yet).
