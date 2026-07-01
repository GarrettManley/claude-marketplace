# Fix hb-w61.8: Retrofit run_with_flags disable pattern onto 4 more plugins — Implementation Plan

> **STATUS: NOT EXECUTED — deferred after adversarial plan review, 2026-07-01.** The design
> split (retrofit aether/orchestration/retrospective/review; document evidence's secret-scan
> hooks as a deliberate exception) holds up. But 2 independent reviewers (plan-skeptic,
> value-justification dimension) found the retrofit's value doesn't clear scrutiny for most of
> the 10 target hooks: orchestration and review each ship exactly one hook, so a per-hook disable
> is redundant with the already-existing whole-plugin disable; most of the remaining hooks are
> non-blocking reminders/nags a user can already just ignore; even `cd_core_guard.py`'s one real
> blocking gate already documents a correct workaround for every case it would block. No concrete
> incident or named consumer motivates this work — see `bd show hb-w61.8`'s comment for the full
> disposition. Kept as a reusable draft (exact hook IDs, mechanical steps, the design split) for
> whenever a real need surfaces — do not treat it as approved-for-execution as written.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `aether`, `orchestration`, `retrospective`, and `review` gain the same per-hook disable escape hatch (`<PREFIX>_HOOK_PROFILE` / `<PREFIX>_DISABLED_HOOKS`) already proven in `discipline`/`learning`/`stewardship`, closing the asymmetry hb-w61.7 deferred. `evidence`'s 2 security hooks are deliberately excluded and documented as a permanent exception, not retrofitted.

**Architecture:** Every gated plugin vendors byte-identical copies of `plugins/discipline/scripts/{run_with_flags.py,hook_flags.py}` (kept in sync by `ci/check-vendored-sync.py --fix`) and routes every hook command in its `hooks.json` through `run_with_flags.py <hook_script> <plugin>:<event>:<hook-name> <profile_csv>`. `hook_flags.py` derives its env-var prefix from the hook id's own namespace, so the file works unmodified for any plugin name. `ci/verify_hook_runtime_controls.py` is the CI gate that proves every gated plugin's hooks actually route through the wrapper — widening its `GATED_PLUGINS` tuple first (before any retrofit work) gives a true TDD red state, since the 4 target plugins don't have wrappers on disk yet.

**Tech Stack:** Python 3.12+/3.13 (repo CI matrix), `uv run --no-project`, pytest (`ci/tests/`, `python3 -m pytest`), no new dependencies.

## Global Constraints

- Profile CSV for every one of the 10 hooks retrofitted here is `minimal,standard,strict` — this preserves today's exact behavior (every hook currently always runs, in every profile) while adding *only* the ability to disable a specific hook id via `<PREFIX>_DISABLED_HOOKS`. Do not redesign which profile each hook defaults to — that's a separate, un-asked-for product decision.
- `evidence`'s `secret_scan.py`/`scope_bind.py` are NOT retrofitted — they are genuine security controls (defense-in-depth secret-scanning and scope-binding), documented as a permanent exception instead, citing the established precedent in the sibling `sec-research/` workspace (`C:\Users\Garre\Workspace\sec-research\CLAUDE.md`), which documents its own secret-scan hook (PT-6) and git pre-commit secret gate (G-2) as `override: NONE` by design. Cite this precedent verbatim; don't invent new reasoning.
- Stage files explicitly per commit — never `git add -A` (repo `CLAUDE.md`).
- No version bump, no CHANGELOG hand-edit anywhere — `ci/release.py` derives per-plugin bumps from `fix:`/`feat:` commits at release time.
- Each modified plugin gets its own commit scope (`fix(aether):`, `fix(orchestration):`, `fix(retrospective):`, `fix(review):`, `fix(ci):` for the gate-list widening) — matching the precedent commit `ff35831 fix(ci): widen hook-runtime-controls gate to learning + stewardship` and ensuring `release.py`'s per-plugin commit-range analysis attributes each change to the right plugin.
- Landing: this repo's `.claude/delivery.local.md` sets `land-policy: pr` — this session does not push or open a PR without the repo owner's explicit go-ahead (autonomous overnight session; same standing rule applied to every other delivery tonight). Work lands on a local branch/worktree and stays there, commands proposed, not executed.
- Existing tests must stay green: `python3 -m pytest ci/tests/ plugins/discipline/tests/ -q` and `bash scripts/verify.sh`.

## File Structure

- **Modify `ci/check-vendored-sync.py`** — extend `CONSUMER_PLUGINS` and the module docstring.
- **Modify `ci/verify_hook_runtime_controls.py`** — extend `GATED_PLUGINS`.
- **Create** (via `check-vendored-sync.py --fix`, not hand-copied) `plugins/{aether,orchestration,retrospective,review}/scripts/{run_with_flags.py,hook_flags.py}`.
- **Modify** `plugins/{aether,orchestration,retrospective,review}/hooks/hooks.json` — route every command through the wrapper.
- **Modify `plugins/evidence/hooks/hooks.json`** — add a `description`-field note; **modify `plugins/evidence/README.md`** — add a short paragraph on the exception.

---

## Task 1: Widen the two CI gate plugin lists (expect RED)

**Files:**
- Modify: `ci/check-vendored-sync.py`
- Modify: `ci/verify_hook_runtime_controls.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `CONSUMER_PLUGINS` and `GATED_PLUGINS` tuples that name all 4 target plugins — Tasks 2-5 make these lists' assertions true.

- [ ] **Step 1: Widen `CONSUMER_PLUGINS` in `ci/check-vendored-sync.py`**

Change:
```python
Vendored consumers: learning, stewardship.
```
to:
```python
Vendored consumers: learning, stewardship, aether, orchestration, retrospective, review.
```
And change:
```python
CONSUMER_PLUGINS = ("learning", "stewardship")
```
to:
```python
CONSUMER_PLUGINS = ("learning", "stewardship", "aether", "orchestration", "retrospective", "review")
```

- [ ] **Step 2: Widen `GATED_PLUGINS` in `ci/verify_hook_runtime_controls.py`**

Change:
```python
GATED_PLUGINS = ("discipline", "learning", "stewardship")
```
to:
```python
GATED_PLUGINS = ("discipline", "learning", "stewardship", "aether", "orchestration", "retrospective", "review")
```

- [ ] **Step 3: Run both scripts directly to confirm RED**

Run: `python3 ci/check-vendored-sync.py`
Expected: exit 1, reports drift for `plugins/aether/scripts/hook_flags.py`, `plugins/aether/scripts/run_with_flags.py`, and the same pair for orchestration/retrospective/review (8 missing files total) — none exist on disk yet.

Run: `python3 ci/verify_hook_runtime_controls.py`
Expected: exit 1, reports each of the 4 plugins as "listed in GATED_PLUGINS but has no scripts/run_with_flags.py", plus every one of their 10 hook commands as bypassing the wrapper.

- [ ] **Step 4: Run the existing CI-scanner tests to confirm no regression from this step alone**

Run: `python3 -m pytest ci/tests/test_ci_scanners.py -q`
Expected: all PASS — these tests monkeypatch `GATED_PLUGINS`/`CONSUMER_PLUGINS` to fixture values, so widening the real tuples doesn't affect them.

- [ ] **Step 5: Commit**

```bash
git add ci/check-vendored-sync.py ci/verify_hook_runtime_controls.py
git commit -m "fix(ci): widen hook-runtime-controls + vendored-sync gates to aether, orchestration, retrospective, review (hb-w61.8)"
```

---

## Task 2: Retrofit `aether`

**Files:**
- Create (via `--fix`): `plugins/aether/scripts/run_with_flags.py`, `plugins/aether/scripts/hook_flags.py`
- Modify: `plugins/aether/hooks/hooks.json`

**Interfaces:**
- Consumes: `ci/check-vendored-sync.py --fix` (Task 1's widened `CONSUMER_PLUGINS`).
- Produces: nothing new for later tasks — each plugin's retrofit is independent.

- [ ] **Step 1: Vendor the wrapper files**

Run: `python3 ci/check-vendored-sync.py --fix`
Expected: creates `plugins/aether/scripts/run_with_flags.py` and `plugins/aether/scripts/hook_flags.py` (and the same pair for orchestration/retrospective/review — this single command fixes all 4 plugins at once since Task 1 already widened `CONSUMER_PLUGINS` to include all of them; Tasks 3-5 do not need to re-run this command).

- [ ] **Step 2: Rewrite `plugins/aether/hooks/hooks.json`**

Replace the entire file with:
```json
{
    "description": "aether plugin hooks: Aether Engine TTRPG/narrative framework safety + reminder gates. Path-pattern-matched, so they no-op in non-Aether repos.",
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": "uv run --no-project \"${CLAUDE_PLUGIN_ROOT}/scripts/run_with_flags.py\" \"${CLAUDE_PLUGIN_ROOT}/hooks/cd_core_guard.py\" aether:pre-tool:cd-core-guard minimal,standard,strict",
                        "timeout": 5
                    },
                    {
                        "type": "command",
                        "command": "uv run --no-project \"${CLAUDE_PLUGIN_ROOT}/scripts/run_with_flags.py\" \"${CLAUDE_PLUGIN_ROOT}/hooks/ledger_truncation_hook.py\" aether:pre-tool:ledger-truncation minimal,standard,strict",
                        "timeout": 5
                    }
                ]
            }
        ],
        "PostToolUse": [
            {
                "matcher": "Edit|Write|MultiEdit",
                "hooks": [
                    {
                        "type": "command",
                        "command": "uv run --no-project \"${CLAUDE_PLUGIN_ROOT}/scripts/run_with_flags.py\" \"${CLAUDE_PLUGIN_ROOT}/hooks/classifier_eval_reminder.py\" aether:post-tool:classifier-eval-reminder minimal,standard,strict",
                        "timeout": 5
                    },
                    {
                        "type": "command",
                        "command": "uv run --no-project \"${CLAUDE_PLUGIN_ROOT}/scripts/run_with_flags.py\" \"${CLAUDE_PLUGIN_ROOT}/hooks/gameplay_harness_reminder.py\" aether:post-tool:gameplay-harness-reminder minimal,standard,strict",
                        "timeout": 5
                    },
                    {
                        "type": "command",
                        "command": "uv run --no-project \"${CLAUDE_PLUGIN_ROOT}/scripts/run_with_flags.py\" \"${CLAUDE_PLUGIN_ROOT}/hooks/rust_rebuild_reminder.py\" aether:post-tool:rust-rebuild-reminder minimal,standard,strict",
                        "timeout": 5
                    }
                ]
            }
        ]
    }
}
```

- [ ] **Step 3: Verify aether's portion of both gates is now clean**

Run: `python3 ci/check-vendored-sync.py`
Expected: no drift reported for `plugins/aether/*` (orchestration/retrospective/review still show drift until Tasks 3-5 rewrite their hooks.json — wait, their wrapper *files* are already vendored by Step 1's single `--fix` run, so `check-vendored-sync.py` should report clean for ALL 4 plugins' scripts already; only `verify_hook_runtime_controls.py`'s hooks.json-command check remains red for orchestration/retrospective/review until their own tasks land).

Run: `python3 ci/verify_hook_runtime_controls.py`
Expected: no more violations listed under `aether:` — violations for orchestration/retrospective/review remain until Tasks 3-5.

- [ ] **Step 4: Commit**

```bash
git add plugins/aether/scripts/run_with_flags.py plugins/aether/scripts/hook_flags.py plugins/aether/hooks/hooks.json
git commit -m "fix(aether): add per-hook disable escape hatch via run_with_flags (hb-w61.8)"
```

---

## Task 3: Retrofit `orchestration`

**Files:**
- Modify: `plugins/orchestration/hooks/hooks.json` (wrapper files already vendored by Task 2 Step 1)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new.

- [ ] **Step 1: Confirm the wrapper files already exist**

Run: `ls plugins/orchestration/scripts/run_with_flags.py plugins/orchestration/scripts/hook_flags.py`
Expected: both files exist (vendored by Task 2 Step 1's single `--fix` run across all 4 plugins). If either is missing, re-run `python3 ci/check-vendored-sync.py --fix` before continuing.

- [ ] **Step 2: Rewrite `plugins/orchestration/hooks/hooks.json`**

Replace the entire file with:
```json
{
    "description": "orchestration plugin hooks: inject the agent/Workflow orchestration defaults at session start.",
    "hooks": {
        "SessionStart": [
            {
                "matcher": "*",
                "hooks": [
                    {
                        "type": "command",
                        "command": "uv run --no-project \"${CLAUDE_PLUGIN_ROOT}/scripts/run_with_flags.py\" \"${CLAUDE_PLUGIN_ROOT}/hooks/inject_orchestration_context.py\" orchestration:session-start:inject-context minimal,standard,strict",
                        "timeout": 5
                    }
                ]
            }
        ]
    }
}
```

- [ ] **Step 3: Verify orchestration's portion is clean**

Run: `python3 ci/verify_hook_runtime_controls.py`
Expected: no more violations listed under `orchestration:`.

- [ ] **Step 4: Commit**

```bash
git add plugins/orchestration/scripts/run_with_flags.py plugins/orchestration/scripts/hook_flags.py plugins/orchestration/hooks/hooks.json
git commit -m "fix(orchestration): add per-hook disable escape hatch via run_with_flags (hb-w61.8)"
```

(Task 2 Step 1's single `--fix` run created wrapper files for all 4 plugins at once, but Task 2's own commit only staged `plugins/aether/**` — so `plugins/orchestration/scripts/{run_with_flags.py,hook_flags.py}` are still untracked on disk at this point. This step's `git add` explicitly includes them alongside orchestration's `hooks.json` — they were never committed until now.)

---

## Task 4: Retrofit `retrospective`

**Files:**
- Modify: `plugins/retrospective/hooks/hooks.json` (wrapper files already vendored by Task 2 Step 1)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new.

- [ ] **Step 1: Confirm the wrapper files already exist**

Run: `ls plugins/retrospective/scripts/run_with_flags.py plugins/retrospective/scripts/hook_flags.py`
Expected: both exist. If missing, re-run `python3 ci/check-vendored-sync.py --fix`.

- [ ] **Step 2: Rewrite `plugins/retrospective/hooks/hooks.json`**

Replace the entire file with:
```json
{
    "description": "retrospective plugin hooks: drop a marker when exiting plan mode; nag at SessionStart about outstanding retrospectives; soft completion-gate nag at SessionStart for pending plans that are not yet done.",
    "hooks": {
        "PostToolUse": [
            {
                "matcher": "ExitPlanMode",
                "hooks": [
                    {
                        "type": "command",
                        "command": "uv run --no-project \"${CLAUDE_PLUGIN_ROOT}/scripts/run_with_flags.py\" \"${CLAUDE_PLUGIN_ROOT}/hooks/exit-plan-mode-marker.sh\" retrospective:post-tool:exit-plan-mode-marker minimal,standard,strict",
                        "timeout": 5
                    }
                ]
            }
        ],
        "SessionStart": [
            {
                "matcher": "*",
                "hooks": [
                    {
                        "type": "command",
                        "command": "uv run --no-project \"${CLAUDE_PLUGIN_ROOT}/scripts/run_with_flags.py\" \"${CLAUDE_PLUGIN_ROOT}/hooks/session-start-retro-nag.sh\" retrospective:session-start:retro-nag minimal,standard,strict",
                        "timeout": 5
                    },
                    {
                        "type": "command",
                        "command": "uv run --no-project \"${CLAUDE_PLUGIN_ROOT}/scripts/run_with_flags.py\" \"${CLAUDE_PLUGIN_ROOT}/hooks/plan_completion_check.py\" retrospective:session-start:plan-completion-check minimal,standard,strict",
                        "timeout": 15
                    }
                ]
            }
        ]
    }
}
```

(Both `.sh` hooks now go through the wrapper the same way `discipline`'s `inject_issues.sh` already does — `run_with_flags.py` detects the `.sh` suffix and spawns bash internally; the outer command is always `uv run --no-project .../run_with_flags.py` regardless of the wrapped script's own language. `plan_completion_check.py` keeps its original `timeout: 15` — the wrapper adds negligible overhead, no timeout change needed.)

- [ ] **Step 3: Verify retrospective's portion is clean**

Run: `python3 ci/verify_hook_runtime_controls.py`
Expected: no more violations listed under `retrospective:`.

- [ ] **Step 4: Commit**

```bash
git add plugins/retrospective/scripts/run_with_flags.py plugins/retrospective/scripts/hook_flags.py plugins/retrospective/hooks/hooks.json
git commit -m "fix(retrospective): add per-hook disable escape hatch via run_with_flags (hb-w61.8)"
```

---

## Task 5: Retrofit `review`

**Files:**
- Modify: `plugins/review/hooks/hooks.json` (wrapper files already vendored by Task 2 Step 1)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new.

- [ ] **Step 1: Confirm the wrapper files already exist**

Run: `ls plugins/review/scripts/run_with_flags.py plugins/review/scripts/hook_flags.py`
Expected: both exist. If missing, re-run `python3 ci/check-vendored-sync.py --fix`.

- [ ] **Step 2: Rewrite `plugins/review/hooks/hooks.json`**

Replace the entire file with:
```json
{
    "description": "review plugin hooks: nag at SessionStart about review-triggering artifacts that completed without a reviewer-personas review completion token.",
    "hooks": {
        "SessionStart": [
            {
                "matcher": "*",
                "hooks": [
                    {
                        "type": "command",
                        "command": "uv run --no-project \"${CLAUDE_PLUGIN_ROOT}/scripts/run_with_flags.py\" \"${CLAUDE_PLUGIN_ROOT}/hooks/session-start-review-nag.sh\" review:session-start:review-nag minimal,standard,strict",
                        "timeout": 5
                    }
                ]
            }
        ]
    }
}
```

- [ ] **Step 3: Verify review's portion is clean, and confirm ALL 4 plugins now pass both gates entirely**

Run: `python3 ci/verify_hook_runtime_controls.py`
Expected: `verify_hook_runtime_controls: clean.` — every plugin (discipline, learning, stewardship, aether, orchestration, retrospective, review) now passes.

Run: `python3 ci/check-vendored-sync.py`
Expected: `check-vendored-sync: clean.`

- [ ] **Step 4: Commit**

```bash
git add plugins/review/scripts/run_with_flags.py plugins/review/scripts/hook_flags.py plugins/review/hooks/hooks.json
git commit -m "fix(review): add per-hook disable escape hatch via run_with_flags (hb-w61.8)"
```

This is the last of the 4 retrofits — run `git status` afterward and confirm a fully clean tree (no untracked/unstaged files remain from any of the vendored-file creation across Tasks 2-5).

---

## Task 6: Document `evidence`'s exception + full verification

**Files:**
- Modify: `plugins/evidence/hooks/hooks.json`
- Modify: `plugins/evidence/README.md`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — this is the plan's final task.

- [ ] **Step 1: Add a note to `plugins/evidence/hooks/hooks.json`'s description**

Change:
```json
    "description": "evidence plugin hooks: secret-scan + scope-binding PreToolUse defense-in-depth.",
```
to:
```json
    "description": "evidence plugin hooks: secret-scan + scope-binding PreToolUse defense-in-depth. Deliberately NOT retrofitted with the run_with_flags disable pattern (unlike discipline/learning/stewardship/aether/orchestration/retrospective/review, hb-w61.8) -- these are security controls, not workflow reminders, and must not have an easy per-hook disable switch. See plugins/evidence/README.md for the full rationale.",
```

- [ ] **Step 2: Add a paragraph to `plugins/evidence/README.md`**

First read the current file to find an appropriate insertion point (likely near a "Hooks" or "How it works" section — do not guess the structure; insert after the section that describes `secret_scan.py`/`scope_bind.py`, or at the end of the file if no better fit exists). Add:

```markdown
## Why these hooks have no disable switch

Most `garrettmanley` marketplace plugins (`discipline`, `learning`, `stewardship`,
`aether`, `orchestration`, `retrospective`, `review`) support a per-hook disable
escape hatch via `<PREFIX>_HOOK_PROFILE` / `<PREFIX>_DISABLED_HOOKS`
(`run_with_flags.py`). `evidence`'s two hooks — `secret_scan.py` and
`scope_bind.py` — are deliberately excluded from this pattern. They are
defense-in-depth security controls, not workflow reminders, and an easy disable
switch would defeat their purpose.

This mirrors the established posture in the sibling `sec-research/` workspace,
whose own `CLAUDE.md` documents its secret-scan hook (PT-6) and git pre-commit
secret gate (G-2) as `override: NONE` by design — secret-scanning must never be
casually disabled, in either project. (hb-w61.8)
```

- [ ] **Step 3: Run the full verification suite**

Run: `python3 -m pytest ci/tests/ plugins/discipline/tests/ -q`
Expected: all PASS, no regressions (discipline's tests exercise the shared `hook_flags.py`/`run_with_flags.py` logic the 4 new plugins now also depend on byte-for-byte).

Run: `bash scripts/verify.sh`
Expected: all checks report `[verify] OK` / clean, including `check-vendored-sync` and `verify_hook_runtime_controls` (already confirmed individually in Task 5 Step 3, but this is the full pre-merge gate — lint, version drift, hook-runtime checks together).

- [ ] **Step 4: Commit**

```bash
git add plugins/evidence/hooks/hooks.json plugins/evidence/README.md
git commit -m "docs(evidence): document secret-scan hooks as a deliberate exception to the run_with_flags pattern (hb-w61.8)"
```

---

## Verification

- [ ] `python3 -m pytest ci/tests/ plugins/discipline/tests/ -q` — full suite green, no regressions.
- [ ] `bash scripts/verify.sh` — full pre-merge gate clean.
- [ ] `python3 ci/verify_hook_runtime_controls.py` and `python3 ci/check-vendored-sync.py` — both report clean, independently.
- [ ] `git log --oneline` on the working branch shows 6 commits, each scoped to the plugin(s) it actually touches (`fix(ci):`, `fix(aether):`, `fix(orchestration):`, `fix(retrospective):`, `fix(review):`, `docs(evidence):`).
- [ ] Manual spot-check: pick any one retrofitted hook id (e.g. `aether:pre-tool:cd-core-guard`) and confirm `AETHER_DISABLED_HOOKS=aether:pre-tool:cd-core-guard` actually suppresses it — this is the literal capability hb-w61.8 asks for; don't just trust the CI gates, exercise the real behavior once.
- [ ] Confirm hb-w61.8's own bead text is satisfied and close it (`bd close hb-w61.8`) once landed — note the evidence exception explicitly in the close reason so it isn't re-litigated later.

## Retrospective

_(To be completed after execution via `retrospective:plan-retrospective`.)_

Tracker: `hb-w61.8`, under epic `hb-w61`.
