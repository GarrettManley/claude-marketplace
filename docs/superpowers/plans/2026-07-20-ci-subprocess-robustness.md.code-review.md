# Whole-Branch Adversarial Code Review — fix/ci-subprocess-robustness

**Scope:** `git diff main..HEAD -- ci/ plugins/` (Python only). Agents: `pr-review-toolkit:code-reviewer`, `pr-review-toolkit:silent-failure-hunter` (session model, no down-routing). No `.ts`/`.cs` → type-design-analyzer not dispatched.

## Findings & resolutions

- **[IMPORTANT] check-notice.py `triggering_files` — `returncode >= 2` misses negative signal codes.** A signal-killed `git grep` (SIGKILL/SIGTERM on OOM/timeout) returns a negative code < 2, falls through, and silently returns `[]` — re-opening the exact hb-duz silent-pass class. **FIXED:** guard changed to `if out.returncode not in (0, 1):`. (Both reviewers confirmed `>=2` is otherwise correct for git's documented error codes; no legitimate scenario — shallow clone, worktree, submodule, `:(exclude)` pathspec magic — returns ≥2.)
- **[IMPORTANT] test_init.py `_git_init_repo` commit call omits `check=True`.** A failed initial commit would be swallowed, leaving a commitless repo that masks setup breakage. **FIXED:** added `check=True`. (The `_run` helper's omission of `check=True` is correct — callers assert on `returncode` directly — so it was left as-is.)
- **[MINOR] test_ci_gates.py git calls lack `stdin=subprocess.DEVNULL`** — inconsistent with the hb-4d1 hygiene added to `test_init.py` in the same PR. **FIXED:** added `stdin=subprocess.DEVNULL` to all four git calls (parity; `stdin` hygiene is orthogonal to the de-scoped hb-lv9 `cwd=` question).
- **[MINOR] check-notice.py RuntimeError message opaque when stderr empty.** **FIXED:** message now includes `ROOT` for diagnosability on a stderr-less git failure.

## Cleared vectors (no finding)

- The `not in (0, 1)` raise fully closes the silent-pass hole; `main()` has no try/except so it propagates to a nonzero exit; `FileNotFoundError` (git absent) also propagates.
- `git grep` exit 0 always means real matches with complete output — no partial-output-with-success case.
- `stdin=subprocess.DEVNULL` hides nothing: `capture_output` still captures stderr; DEVNULL only prevents interactive-prompt hangs.

**Gate:** all CRITICAL/IMPORTANT resolved. Post-fix: `pytest ci/tests/` + `pytest plugins/git/tests/test_init.py` + `bash scripts/verify.sh` all green, exit 0.
