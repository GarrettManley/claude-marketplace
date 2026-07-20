# CI Gate / Test Subprocess Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the marketplace CI gate `check-notice.py` fail loud on a `git grep` error instead of silently passing (hb-duz), and close inherited-stdin exposure in the git-plugin init tests (hb-4d1).

**Architecture:** Two independent, low-blast-radius edits to gate/test tooling. Task 1 adds a return-code check to one production gate function plus a cross-platform regression that isolates from any ambient git repo. Task 2 adds `stdin=subprocess.DEVNULL` to three subprocess calls in one test file. No plugin behavior changes; no version bump.

**Tech Stack:** Python 3.12/3.13, pytest, `subprocess`, `git`. Gate runner `python3 -m pytest ci/tests/` + `bash scripts/verify.sh`.

**Trackers:** hb-duz (BUG, correctness), hb-4d1 (task, hygiene) — harness beads ledger `C:\Users\Garre\.claude\harness-backlog`.

> **Scope note — hb-lv9 de-scoped after adversarial plan review + empirical reproduction (2026-07-20).** hb-lv9 (cwd-contamination flake) could not be reproduced as diagnosed: a minimal POSIX repro shows `git init <abspath>` under a deleted cwd returns rc=0 (no OSError); the full combined invocation `pytest ci/tests/ plugins/delivery/tests/` is 100% green under WSL git 2.43; and no `chdir`-leaker exists in the suite (every `chdir` is auto-restoring `monkeypatch.chdir`). Shipping `cwd=` edits + a regression that cannot be made RED would be an unverifiable no-op. hb-lv9 stays open with reproduction findings recorded; see its bead comment. The consolidated review is at `<this file>.review.md`.

## Global Constraints

- **Cross-platform.** Both fixes and their tests run on the Windows dev host AND ubuntu/windows CI × Python 3.12/3.13. No WSL-only path.
- **Ambient-repo hazard (review CRITICAL #2).** The dev host home dir `C:\Users\Garre` is itself a git repo and `%TEMP%` sits inside it, so `git -C <tmp> grep` ascends into it and exits 0/1 instead of the intended "not a repo" (exit 128). Task 1's test MUST set `GIT_CEILING_DIRECTORIES` to `tmp_path.parent` to force the error deterministically — the same guard `plugins/git/tests/test_init.py:34-37` uses. Verified: with the ceiling, `git grep` exits 128; without it, 1.
- **Stage files explicitly per commit — never `git add -A`** (marketplace CLAUDE.md).
- **Conventional Commits with scopes.** Task 1 = `fix(ci):`, Task 2 = `test(git):`. `ci/` is not a versioned plugin and `test(...)` commits are not release-worthy, so **`release.py` bumps nothing — do not run a release or `git fetch --tags`.**
- **Do not touch `Duracell*` or `malachite/`.**
- **Land policy: `pr`** — open a PR, never push `main`.
- Gate before declaring done: `python3 -m pytest ci/tests/` and `python3 -m pytest plugins/git/tests/test_init.py` green on the Windows host; `bash scripts/verify.sh` green.

---

### Task 1: check-notice.py fails loud on git-grep error (hb-duz)

**Files:**
- Modify: `ci/check-notice.py:24-35` (`triggering_files`)
- Test: `ci/tests/test_ci_gates.py` (add one test in the check-notice section, after line 164)

**Interfaces:**
- Consumes: `cn` module (`test_ci_gates.py:31`), `cn.triggering_files()`, `_patch_cn` (`test_ci_gates.py:129`).
- Produces: `triggering_files()` raises `RuntimeError` when `git grep` exits ≥2; unchanged `list[str]` return on exit 0/1. `main()`'s contract widens from "always returns int" to "may propagate RuntimeError" — an uncaught traceback on a git error is the intended fail-loud behavior (review MINOR, accepted).

- [x] **Step 1: Write the failing test**

Add to `ci/tests/test_ci_gates.py` (check-notice section; `os`/`pytest`/`cn`/`_patch_cn` — note: add `import os` to the imports block if not already present, it is not currently imported):

```python
def test_check_notice_raises_on_git_error(tmp_path, monkeypatch):
    # tmp_path is not a git repo. The dev host home dir is itself git-tracked and
    # %TEMP% sits inside it, so without a ceiling `git grep` would ascend into that
    # ambient repo and exit 0/1. GIT_CEILING_DIRECTORIES=tmp_path.parent stops the
    # upward walk so the "not a git repository" error (exit 128) fires
    # deterministically — the same guard plugins/git/tests/test_init.py uses. The
    # gate must fail loud on that error, not treat it as "no attribution -> pass".
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    _patch_cn(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match="git grep failed"):
        cn.triggering_files()
```

- [x] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest ci/tests/test_ci_gates.py::test_check_notice_raises_on_git_error -v`
Expected: FAIL — current code ignores the return code, so `triggering_files()` returns `[]` and raises nothing.

- [x] **Step 3: Write minimal implementation**

In `ci/check-notice.py`, replace the body of `triggering_files` (lines 24-35) with:

```python
def triggering_files() -> list[str]:
    """Tracked files carrying the attribution phrase (NOTICE excluded so its own
    enumeration does not self-trigger). `git grep` exit 1 means no matches; exit
    >=2 means an actual git error (e.g. not a repo, bad pathspec) — fail loud
    rather than mistaking an error for 'no matches' (hb-duz)."""
    out = subprocess.run(
        # Exclude NOTICE (its own enumeration of the phrase) and this gate script
        # (its TRIGGER constant) so neither self-triggers the requirement.
        ["git", "-C", str(ROOT), "grep", "-l", TRIGGER, "--",
         ".", ":(exclude)NOTICE", ":(exclude)ci/check-notice.py"],
        capture_output=True,
        text=True,
    )
    if out.returncode >= 2:
        raise RuntimeError(
            f"git grep failed (exit {out.returncode}) while scanning for "
            f"upstream attribution: {out.stderr.strip()}"
        )
    return [line for line in out.stdout.splitlines() if line.strip()]
```

- [x] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest ci/tests/test_ci_gates.py::test_check_notice_raises_on_git_error -v`
Expected: PASS.

- [x] **Step 5: Run the full CI-gates suite to confirm no regression**

Run: `python3 -m pytest ci/tests/test_ci_gates.py -v`
Expected: all PASS — the four existing `test_check_notice_*` still green (real repo + synthetic-repo cases exit 0/1, unaffected; the happy-path `test_check_notice_real_repo_is_clean` runs git in the real marketplace repo → exit 0/1, no raise).

- [x] **Step 6: Commit**

```bash
git add ci/check-notice.py ci/tests/test_ci_gates.py
git commit -m "fix(ci): check-notice fails loud on git grep error instead of false-passing (hb-duz)"
```

---

### Task 2: Close inherited stdin on git-plugin init test subprocesses (hb-4d1)

**Files:**
- Modify: `plugins/git/tests/test_init.py:18,26-30,38-44` (`_git_init_repo`, `_run`)

**Interfaces:**
- Consumes: nothing new.
- Produces: all three git/bash subprocess calls in the test helpers pass `stdin=subprocess.DEVNULL`, so a subprocess can never block reading the parent's stdin. Signatures unchanged.

- [x] **Step 1: Apply the hardening edit**

Note: hb-4d1 is a hygiene hardening — a faithful behavioral test (simulating a git credential/editor prompt that reads stdin) is contrived and platform-fragile, so this task is verified by the existing 11 `TestGitInit` tests staying green PLUS the structural grep in Step 2. The grep is the real acceptance gate for the stdin change; the 11 green tests only prove no regression (review MINOR, accepted).

In `plugins/git/tests/test_init.py`:
- `_git_init_repo` line 18: `subprocess.run(["git", "init", str(path)], capture_output=True, check=True, stdin=subprocess.DEVNULL)`
- `_git_init_repo` lines 26-30 (the commit call): add `stdin=subprocess.DEVNULL,` to the kwargs.
- `_run` lines 38-44 (the bash init.sh call): add `stdin=subprocess.DEVNULL,` to the kwargs.

- [x] **Step 2: Structural check — every git/bash subprocess closes stdin**

The `stdin=` kwarg lands on a different line than `subprocess.run(` for the two multi-line calls, so a bare line-grep can't confirm them (review finding). Count occurrences instead:

Run: `grep -c 'stdin=subprocess.DEVNULL' plugins/git/tests/test_init.py`
Expected: `3`.
Cross-check: `grep -c 'subprocess.run(' plugins/git/tests/test_init.py` also returns `3` (one DEVNULL per call site).

- [x] **Step 3: Run the git-plugin init suite to confirm no regression**

Run: `python3 -m pytest plugins/git/tests/test_init.py -v`
Expected: all 11 PASS.

- [x] **Step 4: Commit**

```bash
git add plugins/git/tests/test_init.py
git commit -m "test(git): close stdin on init.sh subprocess helpers to prevent inherited-stdin hangs (hb-4d1)"
```

---

## Verification

Completion-gate criteria (Iron Law: command + output + exit code recorded inline):

- [x] Task 1 RED→GREEN: `python3 -m pytest ci/tests/test_ci_gates.py::test_check_notice_raises_on_git_error -v` → RED pre-fix (`Failed: DID NOT RAISE <class 'RuntimeError'>`), GREEN post-fix (`1 passed`). Full `python3 -m pytest ci/tests/ -q` → all pass, exit 0.
- [x] Task 2: `grep -c 'stdin=subprocess.DEVNULL' plugins/git/tests/test_init.py` → `3`; `grep -c 'subprocess.run(' …` → `3`. `python3 -m pytest plugins/git/tests/test_init.py -q` → 9 passed, exit 0. (Plan originally said 11 tests; actual count is 9 — harmless miscount, all green.)
- [x] Whole gate: `bash scripts/verify.sh` → `check-notice: clean (14 attributed file(s); NOTICE present)`, `check-doc-links: clean (175 …)`, `[verify] OK`, exit 0. Confirms the hb-duz fix leaves the real-repo happy path intact (git grep exits 0, no raise).
- [x] No version bump: `git diff --stat main` shows only `ci/check-notice.py`, `ci/tests/test_ci_gates.py`, `plugins/git/tests/test_init.py`, and the two plan docs — no `plugin.json`/`marketplace.json` changes.

## Completion

Delivered hb-duz and hb-4d1 on branch `fix/ci-subprocess-robustness` (commits `1066040`, `c3174aa`). hb-duz: `check-notice.py` now raises on `git grep` exit ≥2 instead of silently passing the NOTICE gate on a git error; regression `test_check_notice_raises_on_git_error` uses `GIT_CEILING_DIRECTORIES` isolation and went RED→GREEN cross-platform. hb-4d1: `stdin=subprocess.DEVNULL` on all three subprocess calls in `test_init.py`. Full gate green (`ci/tests/` + git-init suite + `verify.sh`, all exit 0); no version bump. **hb-lv9 de-scoped** — empirically unreproducible as diagnosed (see the scope note above and the bead comment). Whole-branch adversarial code review and PR landing follow.
