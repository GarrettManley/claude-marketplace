# Whole-branch Code Review — hb-rap hook-error observability

**Branch:** `fix/hb-rap-hook-error-observability`. Code diff = the 3 `fix(...)` commits + the fix-wave (`1edff9a`/`84d70cd`/`3160ae9`).
**Reviewers:** `pr-review-toolkit:code-reviewer` + `pr-review-toolkit:silent-failure-hunter`, full session capability (no down-route), parallel. `type-design-analyzer` skipped (Python).
**Date:** 2026-07-09

Both reviewers independently confirmed the core mechanism sound: the ring-buffer cap is exact (`prior[-199:] + [rec]` = 200), the `tempfile` + `os.replace` write is atomic, the writer's `_learning_data_root` / reader's `learning_data_root` / real `storage.get_data_root` are byte-identical (no drift), and the isolation fixtures fully cover every swallow-point test (no test writes the real log).

## CRITICAL

- **`_append_hook_error`'s `except Exception: pass` hid every persistence failure** — a silent no-op in a feature built to *end* silent failures; a persistently-unwritable log would make the briefing channel vanish invisibly. → **FIXED (`1edff9a`):** report the failure to stderr (the same channel the swallow points use) while still never raising. (The pre-existing hook-error stderr print was unaffected either way; this makes the *persistence* failure visible too.)

## IMPORTANT

- **`read_hook_errors` caught only `OSError`** — a non-UTF-8 log raises `UnicodeDecodeError` (a `ValueError` subclass, not caught) and crashes the *entire* briefing. → **FIXED (`3160ae9`):** widen to `(OSError, UnicodeDecodeError)`.
- **Unreadable log returned `[]`, rendered as a false "No hook errors logged"** — a silent all-clear. → **FIXED (`3160ae9`):** `read_hook_errors` now returns `None` on unreadable (vs `[]` for absent), and `render_hook_errors_section(None)` renders `_(hook-error log present but unreadable)_`, matching the briefing's existing `_(… unavailable)_` degradation pattern. `build_sections` uses `data.get("hook_errors", [])` to preserve the `None`.
- **The resolver-agreement test only exercised the explicit-env branch** (both resolvers short-circuit at `LEARNING_DATA_ROOT`), so the win32/XDG/home branches — where replica drift would actually hide — were never compared. → **FIXED (`3160ae9`):** parametrized across `win32`/`XDG`/`home` with `sys.platform` mocked and the env cleared.

## MINOR

- **Orphaned `mkstemp` tmp on write/replace failure** (Windows lock) accumulates. → **FIXED (`1edff9a`):** `finally` unlinks the tmp if `os.replace` didn't consume it.
- **Concurrent read-trim-rewrite loses records (last-writer-wins), so the count can undercount during a burst.** → **ACCEPTED, not fixed:** documented as best-effort telemetry; concurrent *errors* are rare, atomicity prevents corruption (only lost updates), and the goal is surfacing-that-errors-happened, not an exact count.
- **`ts` is stored but not surfaced; the log isn't time-windowed.** → **ACCEPTED:** `ts` is kept as log hygiene (scope-cutter endorsed); time-windowing the display is YAGNI for a bounded 200-record ring.

**Gate:** all CRITICAL + IMPORTANT fixed; the two MINORs accepted with stated reasons; whole-branch review ran at full capability. Passed → land.
