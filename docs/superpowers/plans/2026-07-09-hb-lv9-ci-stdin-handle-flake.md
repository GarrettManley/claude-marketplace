# hb-lv9 — CI subprocess stdin-handle flake fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the combined local pytest invocation (`pytest ci/tests/ plugins/delivery/tests/`) pass on Windows by stopping the CI gate scripts and their git test-helpers from inheriting a pytest-mangled stdin handle into `subprocess.run`.

**Architecture:** The six affected `subprocess.run(..., capture_output=True)` calls leave `stdin=None`, so subprocess resolves `GetStdHandle(STD_INPUT_HANDLE)` and duplicates it. Under pytest's default fd-level capture, certain multi-module collections leave that Windows std-input handle invalid, so `DuplicateHandle` raises `OSError: [WinError 6] The handle is invalid`. None of these git subprocesses read stdin, so the fix is to pass `stdin=subprocess.DEVNULL` explicitly at each call site — a fresh, always-valid handle that never touches the inherited one. A meta-test that runs the exact failing sub-invocation as a subprocess and asserts a clean exit guards the regression.

**Tech Stack:** Python 3.12+ (CI matrix 3.12/3.13 tri-OS; 3.14 local), pytest with `--import-mode=importlib`, `subprocess`, git.

## Global Constraints

- Target Python: **3.12+** (CI matrix ubuntu/windows × 3.12/3.13; local dev on 3.14). No 3.13-only syntax.
- CI runs tests **per-directory** (`ci.yml`: `pytest ci/tests -q`, then each plugin dir separately) — GitHub CI is already green; this bug only affects the combined *local* invocation. The fix must keep both invocation shapes green.
- pytest config is repo-root `pytest.ini` with `addopts = --import-mode=importlib -q`; inner/meta pytest invocations must run with **cwd = repo root** so that config and testpaths apply.
- Source files must be **ASCII-only** where practical (Windows cp1252 console); any non-ASCII literal uses a `\uXXXX` escape. (All edits in this plan are ASCII.)
- Landing is **PR-gated** (`.claude/delivery.local.md` `land-policy: pr`; `main` requires 5 status checks). Do not push to `main`.
- Do not use destructive git (`git checkout --`, `git rm`) — the Fact-Forcing gate blocks them; stage explicit files with `git add <path>`.
- Tracker: **hb-lv9** (beads).

**Root-cause correction (carry-forward from `retrospectives/done/our-next-highest-value-modular-map.md`):** hb-lv9 was filed with a *cwd-contamination* hypothesis ("a sibling test `os.chdir`s into a torn-down `tmp_path`; give `_git_repo_with_trigger` an explicit `cwd=tmp_path` / find the chdir-leaking test"). That hypothesis is **falsified**: `grep -rn 'os.chdir\|chdir(' ci/tests plugins/delivery/tests` returns nothing, and the actual error is `WinError 6 invalid handle` inside `_make_inheritable` on the *stdin* handle — not a `FileNotFoundError`/`WinError 267` from a stale cwd. Disabling capture (`pytest -s`) makes all tests pass, proving it is a capture/stdin-handle interaction. The phantom deleted-clone path the original triage read as the "tell" was a red herring (a display artifact, not the failure mechanism). Do **not** implement the `cwd=tmp_path` fix — it would not fix the proven cause.

---

### Task 1: Pass `stdin=subprocess.DEVNULL` at the six affected call sites + regression guard

**Files:**
- Create: `ci/tests/test_combined_invocation_regression.py`
- Modify: `ci/check-notice.py:27` (the `git grep` in `triggering_files()`)
- Modify: `ci/check-doc-links.py:75` (the `git ls-files` in `tracked_markdown()`)
- Modify: `ci/tests/test_ci_gates.py:122,125,159,162` (`git init` / `git add` in `_git_repo_with_trigger` and its plain-file sibling)
- Modify: `ci/tests/test_check_doc_links.py:32,39` (`git init` / `git add` in the doc-links repo helper)

**Interfaces:**
- Consumes: none (terminal single-task fix; no earlier task).
- Produces: none consumed by a later task. The behavioral contract established is: every `subprocess.run` in the two CI gate scripts and their git test-helpers passes `stdin=subprocess.DEVNULL`, so a co-collected module that invalidates the process stdin handle cannot make them raise `OSError` at Popen.

- [x] **Step 1: Write the failing regression test** — **deterministic design (revised after plan review)**

The original design ran the combined invocation as a pytest subprocess and asserted exit 0. Plan review + empirical probing killed that approach: the flake's trigger is *pathologically finicky* — `pytest ci/tests/ --ignore=ci/tests/test_ci_scanners.py plugins/delivery/tests/` **stops** reproducing (226 passed) while ignoring `test_release.py` keeps it (18 failed). A meta-test that must `--ignore` itself could silently drop below the trigger threshold and go permanently green. Instead the guard reproduces the exact *handle state* deterministically via `SetStdHandle`, independent of pytest collection, and exercises the two real gate-script functions plus a control that proves the condition is active (non-vacuous).

Create `ci/tests/test_combined_invocation_regression.py` with three Windows-only tests: `test_stale_stdin_handle_is_actually_broken` (control — a bare inherited-stdin `subprocess.run(capture_output=True)` raises `OSError` under a stale `STD_INPUT_HANDLE`), `test_check_notice_survives_stale_stdin_handle` (calls `cn.triggering_files()` — the real `git grep`), and `test_check_doc_links_survives_stale_stdin_handle` (calls `cd.tracked_markdown()` — the real `git ls-files`). Scripts are loaded via the same `importlib.util.spec_from_file_location` `_load` helper the existing tests use (dash-named files aren't importable normally). A `_StaleStdin` context manager saves `STD_INPUT_HANDLE`, points it at a closed-but-non-null handle, and restores it on exit. See the committed file for the full source.

- [x] **Step 2: Run the regression test to verify it fails** — **DONE, evidence recorded**

Run: `python -m pytest ci/tests/test_combined_invocation_regression.py -v`
Expected: the two `*_survives_*` tests FAIL with `OSError: [WinError 6]`, control PASSES.
**Actual (RED):** `2 failed, 1 passed in 0.12s` — `test_check_notice_survives_stale_stdin_handle` and `test_check_doc_links_survives_stale_stdin_handle` failed with `OSError: [WinError 6] The handle is invalid`; `test_stale_stdin_handle_is_actually_broken` passed. Confirms the guard detects the bug and is not vacuous.

- [x] **Step 3: Fix the production `git grep` call in `check-notice.py`**

In `ci/check-notice.py`, the `subprocess.run` in `triggering_files()` (starts line 27). Add `stdin=subprocess.DEVNULL,` after `text=True,`, with a one-line constraint comment:

```python
    out = subprocess.run(
        # Exclude NOTICE (its own enumeration of the phrase) and this gate script
        # (its TRIGGER constant) so neither self-triggers the requirement.
        ["git", "-C", str(ROOT), "grep", "-l", TRIGGER, "--",
         ".", ":(exclude)NOTICE", ":(exclude)ci/check-notice.py"],
        capture_output=True,
        text=True,
        # git grep never reads stdin; pin it to DEVNULL so a pytest-capture-mangled
        # inherited stdin handle can't fail Popen on Windows (hb-lv9).
        stdin=subprocess.DEVNULL,
    )
```

- [x] **Step 4: Fix the production `git ls-files` call in `check-doc-links.py`**

In `ci/check-doc-links.py`, the `subprocess.run` in `tracked_markdown()` (starts line 75). Add `stdin=subprocess.DEVNULL,` after `check=True,`:

```python
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "*.md"],
        capture_output=True,
        text=True,
        check=True,
        # git ls-files never reads stdin; pin to DEVNULL (hb-lv9 — see check-notice.py).
        stdin=subprocess.DEVNULL,
    )
```

- [x] **Step 5: Fix the four git test-helper calls in `test_ci_gates.py`**

In `ci/tests/test_ci_gates.py`, add `stdin=subprocess.DEVNULL` to all four helper `subprocess.run` calls (lines 122, 125, 159, 162). Each currently reads `subprocess.run([...], capture_output=True, check=True)`; make each:

```python
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True, stdin=subprocess.DEVNULL)
```
```python
    subprocess.run(["git", "-C", str(tmp_path), "add", "ported.py"], capture_output=True, check=True, stdin=subprocess.DEVNULL)
```

Apply the same `stdin=subprocess.DEVNULL` addition to the two sibling calls at lines 159 (`git init`) and 162 (`git add "plain.py"`). Verify `import subprocess` is already at the top of the file (it is, line 12) — no new import needed.

- [x] **Step 6: Fix the two git test-helper calls in `test_check_doc_links.py`**

In `ci/tests/test_check_doc_links.py`, add `stdin=subprocess.DEVNULL` to the two helper calls (lines 32, 39):

```python
    subprocess.run(["git", "init", str(root)], capture_output=True, check=True, stdin=subprocess.DEVNULL)
```
```python
    subprocess.run(["git", "-C", str(root), "add", rel], capture_output=True, check=True, stdin=subprocess.DEVNULL)
```

Confirm `import subprocess` is present at the top of the file — if absent, add it.

- [x] **Step 7: Run the regression test to verify it now passes** — **DONE.** `3 passed in 0.05s` (GREEN — all three tests pass with the fix in place).

- [x] **Step 8: Run the full combined invocation directly to confirm zero failures** — **DONE.** `python -m pytest ci/tests/ plugins/delivery/tests/` → `319 passed in 8.21s`, **0 failed** (previously 18 failed).

- [x] **Step 9: Run the per-directory CI shape to confirm no regression there** — **DONE.** `python -m pytest ci/tests/` → `296 passed` (was 293; +3 regression tests); `python -m pytest plugins/delivery/tests/` → `23 passed`.

- [x] **Step 10: Commit** — staged explicitly (per repo CLAUDE.md "never `git add -A`"):

```bash
git add ci/check-notice.py ci/check-doc-links.py ci/tests/test_ci_gates.py ci/tests/test_check_doc_links.py ci/tests/test_combined_invocation_regression.py
git commit -m "fix(ci): pin stdin=DEVNULL on gate-script git subprocesses (hb-lv9)"
```

---

## Completion

**Done.** All six `subprocess.run` sites that the combined-invocation flake hit now pass `stdin=subprocess.DEVNULL` (2 production gate scripts + 4 git test-helpers), and a deterministic Windows-only regression guard reproduces the exact stale-`STD_INPUT_HANDLE` state via `SetStdHandle` and asserts the real gate functions survive it. The bead repro `pytest ci/tests/ plugins/delivery/tests/` went from **18 failed → 319 passed, 0 failed**; per-directory CI shape stays green; `scripts/verify.sh` exits 0. Landed on branch `fix/hb-lv9-ci-cwd-contamination` (commits `a99be52` fix, `be6e40d` plan+review) for PR (`land-policy: pr`). The bead's original cwd-contamination hypothesis was falsified during diagnosis (no `os.chdir` exists in the suites; error is a stdin-handle `WinError 6`, not a cwd error) — recorded so the fix doesn't get "corrected" back to the wrong root cause. Tracker: **hb-lv9**. One out-of-scope follow-up (`plugins/git/tests/test_init.py`) filed as a bead.

## Verification

Positive evidence required (fresh command output + exit code, not a clean terminal state):

- [x] **Regression test fails before the fix, passes after.** Evidence: Step 2 RED = `2 failed, 1 passed in 0.12s` (both `*_survives_*` tests raise `OSError: [WinError 6]`, control passes); Step 7 GREEN = `3 passed in 0.05s`.
- [x] **Combined invocation is fully green.** `python -m pytest ci/tests/ plugins/delivery/tests/` → `319 passed in 8.21s`, `0 failed` (was 18 failed).
- [x] **Per-directory CI shape stays green.** `python -m pytest ci/tests/` → `296 passed`; `python -m pytest plugins/delivery/tests/` → `23 passed`.
- [x] **`scripts/verify.sh` passes** (the dev clone's pre-merge gate — path confirmed via repo CLAUDE.md, `bash scripts/verify.sh`, not a bare `verify.sh`). Output: all gates `[verify] OK`, including `check-notice: clean` and `check-doc-links: clean (170 markdown file(s) scanned)` — the two patched production scripts run clean in the real gate path. `EXIT: 0`.
- [x] **No `os.chdir` / `cwd=tmp_path` change was made** — the fix targets the proven stdin-handle cause, not the falsified cwd hypothesis. The diff touches only `stdin=subprocess.DEVNULL` additions + the new regression test.

## Scope boundary (logged, not silently dropped)

The `stdin=subprocess.DEVNULL` pattern is **already established in-repo**: `ci/release.py` (lines 125-128, 150-153) and `ci/tests/test_release.py` (lines 233-236, 729-730, 737-739) ship it with the identical rationale — so this fix extends a proven precedent, not a novel approach. (An earlier draft of this plan wrongly listed `test_release.py` as an unfixed out-of-scope site; corrected during plan review.)

One genuinely unfixed site remains outside this repro: `plugins/git/tests/test_init.py` (lines 18, 26) still runs `git init`/`git add` without `stdin=subprocess.DEVNULL` and fails when paired directly with a check-notice test. It is **out of scope** for hb-lv9, whose stated repro is `ci/tests/ plugins/delivery/tests/` — an invocation that does not collect the git-plugin suite. Follow-up: apply the same one-line treatment there (or, if this class recurs across suites, adopt a repo-root conftest session-fixture that repairs `STD_INPUT_HANDLE` once — a larger, riskier change deliberately not taken here). **Filed as bead `hb-4d1`.**
