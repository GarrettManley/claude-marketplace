# Fix run_with_flags.py shell/python spawn bugs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two confirmed, real bugs in the canonical `run_with_flags.py` hook-runtime-controls wrapper (`plugins/discipline/scripts/run_with_flags.py`, vendored byte-identical into `plugins/{learning,stewardship}/scripts/`): (1) wrapped shell hooks using `${BASH_SOURCE[0]}` for self-location break under the current `bash -c <content>` spawn strategy, and (2) wrapped Python hooks whose `main(argv=None)` falls back to `sys.argv` receive the wrapper's own process argv instead of an empty list.

**Why this, why now:** Bug 1 is empirically reproduced and live-broken **right now** for `plugins/discipline/hooks/inject_issues.sh` (discipline's actual, currently-deployed SessionStart hook that surfaces open GitHub issues): `bash -c "$(cat inject_issues.sh)"` → `bash: line 27: BASH_SOURCE[0]: unbound variable` → a wrong-path spawn error → exit 2. The wrapper's own code comment claiming this is safe ("none uses $0/BASH_SOURCE/dirname \"$0\"") is factually false — this script does exactly that. Bug 2 is confirmed by code-reading, not a live reproduction (the specific hook it was diagnosed against, `plugins/retrospective/hooks/plan_completion_check.py`, is not currently wrapped by any gated plugin) — **but the fix's correctness has an equally-live stake in the opposite direction**: `plugins/discipline/hooks/hooks.json` currently wraps at least 5 hooks with bare `def main():` signatures (`todo_issue_hook.py`, `memory_tracker_check.py`, `frontmatter_lint.py`, `pitfalls_pointer.py`, `spec_companion_check.py`), firing on nearly every PreToolUse/PostToolUse edit — these work fine under today's `main_fn()` zero-arg call. A naive fix to Bug 2 (always call `main_fn([])`) would raise `TypeError` in all five, silently swallowed by the wrapper's own `except Exception` handler — silently disabling five currently-working, actively-used hooks. The fix must handle both calling conventions correctly, not trade one live bug for five new ones.

**Architecture:** Both fixes are isolated to two functions in one file. `_spawn_shell` changes from reading file content and piping it via `bash -c <text>` to passing the real file path directly as bash's script argument — this preserves `BASH_SOURCE[0]` as the genuine source path. `_import_and_run_python` inspects `main_fn`'s signature once: if it takes a parameter, call `main_fn([])` (an explicit, deliberate empty list — never let a hook accidentally read the wrapper's own `sys.argv`); if it takes none, call `main_fn()` exactly as before. Signature introspection failure falls back to the zero-arg call (matching today's behavior); the actual invocation's own exceptions are never silently reinterpreted as a signature mismatch (see Task 2's exact code — this is a real double-invocation risk if the except scoping is wrong). Fix once in the canonical `plugins/discipline/scripts/run_with_flags.py`, then propagate via `ci/check-vendored-sync.py --fix` (never hand-edit the vendored copies) — matching the exact "fix canonical, then sync" pattern already established for this file family (commit `d03fd12`).

**Tech Stack:** Python 3.12+/3.13, `subprocess`, `importlib.util`, `inspect`, pytest.

## Global Constraints

- **This dev clone (`C:\Users\Garre\Workspace\claude-marketplace`) is separate from the live installed plugin cache** (`~/.claude/plugins/marketplaces/garrettmanley`) that actually executes discipline/learning/stewardship hooks in any currently-running Claude Code session, including this one. Every edit in this plan is inert for live sessions until the user runs `/plugin` to reinstall from this clone. "Live-reproduce" steps (Task 1 Step 5, Task 3 Step 4) validate the **dev-clone copy only**, invoked directly via `python3 .../run_with_flags.py ...` — not the live installed one. Do not claim or imply this fix is "deployed" until the user has explicitly reinstalled.
- Fix the canonical copy at `plugins/discipline/scripts/run_with_flags.py` only — never hand-edit `plugins/{learning,stewardship}/scripts/run_with_flags.py`; propagate via `ci/check-vendored-sync.py --fix`.
- On Windows, `_resolve_bash()` already prefers Git Bash (`C:\Program Files\Git\bin\bash.exe` / `...\usr\bin\bash.exe`) over a bare `bash` PATH lookup specifically to avoid the WSL launcher stub — this fix relies on that existing preference; it does not change `_resolve_bash()` itself.
- No version bump, no CHANGELOG hand-edit — `ci/release.py` derives per-plugin bumps from `fix:` commits at release time.
- Stage files explicitly per commit — never `git add -A`.
- **Work happens in an isolated git worktree** (via the native `EnterWorktree` tool if available, else `superpowers:using-git-worktrees`'s fallback) — never commit directly to `master`/`main` without explicit consent, matching every other delivery this session.
- Landing: `.claude/delivery.local.md` sets `land-policy: pr` — this autonomous session does not push or open a PR without the repo owner's explicit go-ahead (same standing rule as every other delivery tonight). **Commits themselves ARE executed** as each task completes (local, reversible, matching every other delivery this session) — it is specifically `git push`/`gh pr create` that stay proposed-only, never executed.
- Existing tests must stay green: `python3 -m pytest ci/tests -q && for d in plugins/discipline/tests plugins/learning/tests plugins/stewardship/tests; do python3 -m pytest "$d" -q; done` and `bash scripts/verify.sh`. **Never combine multiple plugin test directories into one `pytest` invocation** — `discipline/scripts/snapshot.py` and `learning/scripts/snapshot.py` (same basename, no `__init__.py`, importlib mode) collide when collected together, confirmed reproducible in both this worktree and the main checkout; `.github/workflows/ci.yml` runs each plugin's tests in its own separate `pytest` process for exactly this reason — match that convention, not a combined command.
- Do not fix any individual hook script (`inject_issues.sh`, `plan_completion_check.py`, `observe.py`, `todo_issue_hook.py`, etc.) — the wrapper fix alone corrects behavior for all of them uniformly, once vendored-synced.
- If any verification step (test run, `bash scripts/verify.sh`) fails **after** a task's commit has already landed, the default resolution is fix-forward with a new commit (never `git commit --amend`, per repo convention) — only fall back to `git revert` if the failure indicates the whole approach in that commit was wrong, not merely incomplete.

---

## File Structure

- **Modify `plugins/discipline/scripts/run_with_flags.py`** — fix `_spawn_shell` and `_import_and_run_python`.
- **Modify `plugins/discipline/tests/test_run_with_flags.py`** — add regression tests for both bugs, using fixtures that actually exercise `BASH_SOURCE` and `argv=None` fallback (the existing fixtures don't, which is why neither bug was ever caught).
- **Propagate (via `ci/check-vendored-sync.py --fix`, not hand-edited)** — `plugins/learning/scripts/run_with_flags.py`, `plugins/stewardship/scripts/run_with_flags.py`.
- **Modify (per-plugin tests not covered by vendored-sync)** — `plugins/learning/tests/test_coverage_gaps.py`, `plugins/stewardship/tests/test_run_with_flags.py` (hardcode assertions on the OLD `bash -c`/`read_text` implementation shape; these break once the vendored copies are updated and must be fixed to match the new behavior).
- **Modify** — `docs/architecture.md` (stale paragraph describing the old `bash -c`-inlining rationale).

---

## Task 1: Fix Bug 1 — `_spawn_shell` breaks `BASH_SOURCE`-dependent scripts

**Files:**
- Modify: `plugins/discipline/scripts/run_with_flags.py` (`_spawn_shell`, lines ~114-126)
- Test: `plugins/discipline/tests/test_run_with_flags.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `_spawn_shell(script_path: Path, stdin_text: str) -> int` — same signature, corrected implementation. Task 3's vendored-sync step depends on this and Task 2's changes both landing in the canonical file first.

- [ ] **Step 1: Write the failing test**

Append to `plugins/discipline/tests/test_run_with_flags.py`, inside `class TestInvokeWhenEnabled` (matching the existing class's convention — read the class's other tests first if unsure of indentation/style):

```python
    def test_shell_hook_bash_source_self_location_works(self, tmp_path):
        """Regression: a real-world pattern (dirname "${BASH_SOURCE[0]}" to locate a
        sibling file) must survive being wrapped. The existing
        test_shell_hook_invoked_via_subprocess fixture doesn't reference BASH_SOURCE at
        all, which is exactly why this class of bug went uncaught (see
        plugins/discipline/hooks/inject_issues.sh:27 for the real pattern this mirrors)."""
        sibling = tmp_path / "sibling.txt"
        sibling.write_text("sibling-content")
        hook = tmp_path / "self_locating_hook.sh"
        hook.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
            'cat "$dir/sibling.txt"\n'
        )
        hook.chmod(0o755)
        result = run_wrapper(
            [str(hook), "discipline:test:self-locating", "standard"],
            stdin="",
        )
        assert result.returncode == 0, result.stderr
        assert "sibling-content" in result.stdout
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd plugins/discipline/tests && python3 -m pytest test_run_with_flags.py -v -k bash_source_self_location`
Expected: FAIL — `bash: line 3: BASH_SOURCE[0]: unbound variable`, non-zero return code, "sibling-content" not found in stdout.

- [ ] **Step 3: Fix `_spawn_shell` in `plugins/discipline/scripts/run_with_flags.py`**

Replace:
```python
def _spawn_shell(script_path: Path, stdin_text: str) -> int:
    # Passing a Windows path as a bash argument fails on Windows regardless of
    # whether bash resolves to Git Bash (MSYS mangles the path) or WSL bash
    # (path is inaccessible from the Linux side).  Reading the script content
    # and using `bash -c` avoids the argument entirely.  This is safe for the
    # gated shell hooks because none uses $0/BASH_SOURCE/dirname "$0" --
    # they resolve directories via `git rev-parse --show-toplevel`.
    try:
        script_content = script_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        print(f"run_with_flags: cannot read shell script {script_path.name}: {e}", file=sys.stderr)
        return _passthrough(stdin_text)
    result = subprocess.run(
        [_resolve_bash(), "-c", script_content],
        input=stdin_text,
        capture_output=True,
        text=True,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode
```

with:
```python
def _spawn_shell(script_path: Path, stdin_text: str) -> int:
    # Pass the real script path directly rather than reading its content into
    # `bash -c <text>`. The prior approach broke any script using
    # `dirname "${BASH_SOURCE[0]}"` for self-location (BASH_SOURCE is unset
    # under `bash -c`) -- confirmed live-broken for
    # plugins/discipline/hooks/inject_issues.sh. Git Bash (which _resolve_bash()
    # already prefers on Windows) handles a Windows-style path passed as the
    # script argument correctly -- confirmed empirically with a real
    # backslash-separated str(Path) value (not just a hand-typed forward-slash
    # path): dirname "${BASH_SOURCE[0]}" resolves correctly and the script's
    # own sibling-file lookup succeeds. On POSIX there was never a
    # path-translation concern to begin with.
    result = subprocess.run(
        [_resolve_bash(), str(script_path)],
        input=stdin_text,
        capture_output=True,
        text=True,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode
```

(No `is_file()` check here — `main()`'s caller already checks `script_path.is_file()` once before dispatching to `_spawn_shell`/`_import_and_run_python`/`_spawn_generic`; a redundant re-check here guards a TOCTOU race outside the scope of these two bugs and was flagged as unnecessary by review. The old try/except around `read_text` is gone entirely since there's no file read in this function anymore.)

- [ ] **Step 4: Run the test to verify it passes, plus the full existing shell-hook test**

Run: `cd plugins/discipline/tests && python3 -m pytest test_run_with_flags.py -v`
Expected: all PASS, including the new test and the pre-existing `test_shell_hook_invoked_via_subprocess` (unaffected — its synthetic fixture never referenced `BASH_SOURCE`, so it passed before and passes now for the same reason, just via the new code path).

- [ ] **Step 5: Reproduce the original real-world failure is now fixed, through the actual wrapper**

Run this via the Bash tool (Git Bash) specifically — the `<<<` here-string syntax is not valid in PowerShell — from the repo root:
```bash
python3 plugins/discipline/scripts/run_with_flags.py plugins/discipline/hooks/inject_issues.sh discipline:session-start:inject-issues standard <<< '{}'
```
Expected: exit 0, valid JSON hook output (either real open-issues content or a clean "no open issues" message) — no `BASH_SOURCE` error, no "Failed to spawn" error. This is the exact manual reproduction from planning (`bash -c "$(cat inject_issues.sh)"` → unbound-variable error), now run through the actual fixed wrapper code path instead of a raw manual `bash -c`.

- [ ] **Step 6: Commit**

```bash
git add plugins/discipline/scripts/run_with_flags.py plugins/discipline/tests/test_run_with_flags.py
git commit -m "fix(discipline): pass real script path to bash instead of piping content, fixing BASH_SOURCE-dependent hooks"
```

---

## Task 2: Fix Bug 2 — `_import_and_run_python` calls `main_fn()` with the wrapper's own argv

**Files:**
- Modify: `plugins/discipline/scripts/run_with_flags.py` (`_import_and_run_python`, lines ~157-176)
- Test: `plugins/discipline/tests/test_run_with_flags.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `_import_and_run_python(script_path: Path, stdin_text: str) -> int` — same signature, corrected implementation.

**Confirmed constraint driving this task's design (do not simplify away):** `plugins/discipline/hooks/hooks.json` currently wraps at least 5 hooks with bare `def main():` signatures (`todo_issue_hook.py`, `memory_tracker_check.py`, `frontmatter_lint.py`, `pitfalls_pointer.py`, `spec_companion_check.py`), firing on nearly every PreToolUse/PostToolUse edit. These work correctly today under `main_fn()` (zero args exactly matches their signature). A fix that unconditionally calls `main_fn([])` would raise `TypeError` in all five — silently swallowed by the existing `except Exception` handler, silently disabling five currently-working, actively-used hooks. The fix MUST detect which calling convention a given `main_fn` expects and use the right one — this is not optional scope, it is required to avoid trading one live bug for five new ones.

- [ ] **Step 1: Write the failing tests**

Append to `plugins/discipline/tests/test_run_with_flags.py`, inside `class TestInvokeWhenEnabled`:

```python
    def test_python_hook_receives_empty_argv_not_wrapper_own_argv(self, tmp_path):
        """Regression: a hook using the standard `main(argv: list[str] | None = None)`
        idiom, falling back to sys.argv[1:] when argv is None, must see an empty list --
        not run_with_flags.py's own process argv (hook_script_path, hook_id,
        profile_csv). Mirrors the real pattern in
        plugins/retrospective/hooks/plan_completion_check.py:300-312, which would
        misinterpret its own script path as a CLI positional argument if this broke."""
        hook = tmp_path / "argv_fallback_hook.py"
        hook.write_text(
            "import sys\n"
            "def main(argv=None):\n"
            "    args = sys.argv[1:] if argv is None else argv\n"
            "    print('argv-was:' + repr(args))\n"
            "    return 0\n"
        )
        result = run_wrapper(
            [str(hook), "discipline:test:argv-fallback", "standard"],
            stdin="{}",
        )
        assert result.returncode == 0
        assert "argv-was:[]" in result.stdout

    def test_python_hook_zero_param_main_still_works(self, tmp_path):
        """Regression: real, currently-wrapped discipline hooks (todo_issue_hook.py,
        memory_tracker_check.py, frontmatter_lint.py, pitfalls_pointer.py,
        spec_companion_check.py) use bare `def main():` with no parameters at all --
        the fix for the argv-leak bug above must not break these. This mirrors the
        pre-existing test_python_hook_main_called_with_stdin/
        test_python_hook_exit_code_propagated fixtures but asserts explicitly on the
        zero-param case so a regression here fails with a clear name, not just
        collateral failures in unrelated tests."""
        hook = tmp_path / "zero_param_hook.py"
        hook.write_text(
            "def main():\n"
            "    print('zero-param-ran')\n"
            "    return 0\n"
        )
        result = run_wrapper(
            [str(hook), "discipline:test:zero-param", "standard"],
            stdin="{}",
        )
        assert result.returncode == 0
        assert "zero-param-ran" in result.stdout
```

- [ ] **Step 2: Run the tests to verify the first fails and the second currently passes**

Run: `cd plugins/discipline/tests && python3 -m pytest test_run_with_flags.py -v -k "receives_empty_argv or zero_param_main_still_works"`
Expected: `test_python_hook_receives_empty_argv_not_wrapper_own_argv` FAILS (stdout contains the wrapper's own argv, e.g. `argv-was:['<tmp_path>/argv_fallback_hook.py', 'discipline:test:argv-fallback', 'standard']`, not `argv-was:[]`). `test_python_hook_zero_param_main_still_works` PASSES already (this is the pre-fix baseline this task must not break).

- [ ] **Step 3: Fix `_import_and_run_python` in `plugins/discipline/scripts/run_with_flags.py`**

Change:
```python
    main_fn = getattr(module, "main", None)
    if not callable(main_fn):
        # No main(); module top-level already ran (and didn't exit). Treat as success.
        return 0
    try:
        result = main_fn()
        return int(result) if result is not None else 0
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0
    except Exception as e:  # noqa: BLE001
        print(f"run_with_flags: runtime error in {script_path.name}: {e}", file=sys.stderr)
        return 0  # don't break the chain
```
to:
```python
    main_fn = getattr(module, "main", None)
    if not callable(main_fn):
        # No main(); module top-level already ran (and didn't exit). Treat as success.
        return 0
    # Detect the calling convention BEFORE invoking -- some currently-wrapped hooks
    # (todo_issue_hook.py, memory_tracker_check.py, frontmatter_lint.py,
    # pitfalls_pointer.py, spec_companion_check.py) use bare `def main():` with no
    # parameters; others (plan_completion_check.py and the standard idiom generally)
    # use `def main(argv: list[str] | None = None)`. Calling the latter with zero
    # args leaks this process's own sys.argv (hook_script_path, hook_id,
    # profile_csv) into the hook when it falls back from argv=None -- calling the
    # former with one arg raises TypeError. Introspection failure (e.g. a
    # C-extension callable) falls back to the zero-arg call, matching prior
    # behavior. This check is intentionally OUTSIDE the try/except below: a
    # genuine runtime error raised by the hook's own body during the real call
    # must never be reinterpreted as a signature mismatch and retried --
    # double-invoking a hook with side effects would be silent data corruption.
    try:
        takes_argv = bool(inspect.signature(main_fn).parameters)
    except (TypeError, ValueError):
        takes_argv = False
    try:
        result = main_fn([]) if takes_argv else main_fn()
        return int(result) if result is not None else 0
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0
    except Exception as e:  # noqa: BLE001
        print(f"run_with_flags: runtime error in {script_path.name}: {e}", file=sys.stderr)
        return 0  # don't break the chain
```

Also add `import inspect` to the file's import block at the top (alongside the existing `io`, `importlib.util`, `os`, `shutil`, `subprocess`, `sys`).

- [ ] **Step 4: Run the tests to verify both pass, plus the full existing python-hook tests**

Run: `cd plugins/discipline/tests && python3 -m pytest test_run_with_flags.py -v`
Expected: all PASS — the two new tests, and every pre-existing test (`test_python_hook_main_called_with_stdin`, `test_python_hook_exit_code_propagated`, `test_python_hook_runtime_error_does_not_break_chain` in particular — that last one's fixture `raise ValueError('boom')` from inside a zero-param `def main():` must still be caught and reported as `"runtime error"` in stderr with exit 0, NOT silently reinterpreted as a signature issue and retried).

- [ ] **Step 5: Commit**

```bash
git add plugins/discipline/scripts/run_with_flags.py plugins/discipline/tests/test_run_with_flags.py
git commit -m "fix(discipline): detect main() calling convention so wrapped python hooks get correct argv, not the wrapper's own sys.argv"
```

---

## Task 3: Propagate the vendored fix, fix downstream test assumptions, verify, update docs

**Files:**
- Propagate (via `--fix`, not hand-edited): `plugins/learning/scripts/run_with_flags.py`, `plugins/stewardship/scripts/run_with_flags.py`
- Modify (NOT covered by `check-vendored-sync.py`, which only syncs the two `scripts/` files, never test files): `plugins/learning/tests/test_coverage_gaps.py`, `plugins/stewardship/tests/test_run_with_flags.py`
- Modify: `docs/architecture.md`

**Interfaces:**
- Consumes: Task 1 + Task 2's fixed canonical `plugins/discipline/scripts/run_with_flags.py`.
- Produces: nothing new — this is the plan's final task.

- [ ] **Step 1: Propagate the fix to the vendored copies**

Run: `python3 ci/check-vendored-sync.py --fix`
Expected: reports `check-vendored-sync: fixed plugins/learning/scripts/run_with_flags.py` and `check-vendored-sync: fixed plugins/stewardship/scripts/run_with_flags.py` (exact message includes the `scripts/` path segment — don't mistake its absence for a failure if you see the full path). Confirm with `git status --porcelain plugins/learning/scripts/run_with_flags.py plugins/stewardship/scripts/run_with_flags.py` that both files now show as modified.

- [ ] **Step 2: Find and fix any per-plugin tests that hardcode the OLD implementation**

`check-vendored-sync.py` only syncs the two `scripts/*.py` files — it does not touch each plugin's own `tests/` directory, and `learning`/`stewardship` each have their own test files that may assert on internals of the pre-fix implementation. Run:
```
grep -rln "read_text\|-c.*script_content\|cmd\[1\] == .-c.\|cannot read shell script" plugins/learning/tests/ plugins/stewardship/tests/
```
For each match, read the specific test and determine whether it asserts on the OLD `_spawn_shell`'s `bash -c <content>` invocation shape or its `read_text`-failure error message (`"cannot read shell script"`) — both of these are gone in the new implementation. Update any such test's assertions to match the new behavior (direct path invocation; a missing/unreadable script now surfaces as a subprocess failure from `bash` itself, not a `run_with_flags`-authored "cannot read" message — check what `bash <nonexistent-path>` actually prints to stderr and assert on that instead, or on the resulting non-zero exit code if the exact message isn't stable). Run each affected test file individually after updating: `cd plugins/learning/tests && python3 -m pytest test_coverage_gaps.py -v` and the equivalent for `plugins/stewardship/tests/test_run_with_flags.py` — confirm green before moving on.

- [ ] **Step 3: Update `docs/architecture.md`**

Find the paragraph (around lines 135-137) stating shell hooks are spawned via `bash -c` with script content inlined "to dodge Windows path-mangling" — this is now false. Update it to describe the new direct-path invocation and note (briefly, one sentence) that the prior approach broke `BASH_SOURCE`-dependent hooks, which is why it changed.

- [ ] **Step 4: Full verification**

Run: `python3 -m pytest ci/tests -q && for d in plugins/discipline/tests plugins/learning/tests plugins/stewardship/tests; do python3 -m pytest "$d" -q; done`
Expected: all PASS, no regressions.

Run: `bash scripts/verify.sh`
Expected: all checks report `[verify] OK` / clean, including `check-vendored-sync` and `check-doc-links`.

- [ ] **Step 5: Live-reproduce the original bug is fixed, end to end**

Run via the Bash tool (not PowerShell):
```bash
python3 plugins/discipline/scripts/run_with_flags.py plugins/discipline/hooks/inject_issues.sh discipline:session-start:inject-issues standard <<< '{}'
```
Expected: exit 0, JSON output on stdout (either real open-issues content or a clean "no open issues" message) — no `BASH_SOURCE` error, no "Failed to spawn" error. Record the actual output in the retrospective as positive evidence. (This duplicates Task 1 Step 5's check intentionally — that one confirms Bug 1's fix in isolation right after landing it; this one re-confirms after vendored-sync propagation and the doc update haven't regressed it.)

- [ ] **Step 6: Commit**

```bash
git add plugins/learning/scripts/run_with_flags.py plugins/stewardship/scripts/run_with_flags.py plugins/learning/tests/test_coverage_gaps.py plugins/stewardship/tests/test_run_with_flags.py docs/architecture.md
git commit -m "chore(ci): propagate run_with_flags.py spawn-bug fixes to vendored copies, update downstream tests and docs"
```

(If Step 2 found no test files needing changes, or Step 3's doc paragraph turns out already accurate, adjust the `git add` list to whatever actually changed — but the vendored `scripts/run_with_flags.py` files in learning/stewardship will always have changed here.)

---

## Verification

- [ ] `python3 -m pytest ci/tests -q && for d in plugins/discipline/tests plugins/learning/tests plugins/stewardship/tests; do python3 -m pytest "$d" -q; done` — full suite green, no regressions.
- [ ] `bash scripts/verify.sh` — full pre-merge gate clean, including `check-vendored-sync` and `check-doc-links`.
- [ ] `python3 plugins/discipline/scripts/run_with_flags.py plugins/discipline/hooks/inject_issues.sh discipline:session-start:inject-issues standard <<< '{}'` (via Bash tool) — exits 0 with valid JSON output (the original, real-world reproduction of Bug 1, now fixed).
- [ ] Manual read-through: `git diff main..HEAD` shows changes only to `plugins/discipline/scripts/run_with_flags.py`, `plugins/discipline/tests/test_run_with_flags.py`, the two vendored copies, any updated learning/stewardship test files, and `docs/architecture.md` — no edits to any individual hook script (`inject_issues.sh`, `plan_completion_check.py`, `observe.py`, `todo_issue_hook.py`, etc.).
- [ ] Confirm the five currently-wrapped bare-`def main():` discipline hooks (`todo_issue_hook.py`, `memory_tracker_check.py`, `frontmatter_lint.py`, `pitfalls_pointer.py`, `spec_companion_check.py`) still fire correctly post-fix — the full discipline test suite (already run above) covers this; if any of them lack direct test coverage, note that gap explicitly in the retrospective rather than assuming coverage exists.
- [ ] Confirm explicitly in the retrospective: this fix is applied to the dev clone only; it is inert for any currently-running Claude Code session until the user runs `/plugin` to reinstall from this clone.

## Retrospective

_(To be completed after execution via `retrospective:plan-retrospective`.)_

Tracker: discovered during hb-w61.8's adversarial plan review; not itself a beads item — file one if useful for cross-session tracking, or note this as a direct fix with no separate tracker.
