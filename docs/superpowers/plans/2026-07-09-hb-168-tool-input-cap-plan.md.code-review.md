# Whole-branch Code Review — hb-168 tool_input cap

**Branch:** `fix/hb-168-tool-input-cap` (code diff = commit `bc6eeb1`; fix-wave = `94a5352`)
**Reviewers:** `pr-review-toolkit:code-reviewer` + `pr-review-toolkit:silent-failure-hunter`, full session capability (no down-routed model), parallel. `type-design-analyzer` skipped (Python, no TS/C#).
**Date:** 2026-07-09

Both reviewers independently confirmed the core change is sound: recursion edge cases traced (empty dict/list, int/float/bool/None scalars, exact-2000 kept vs 2001 sliced), `analyze.py`'s `bash_command_prefixes` / `file_hotspots` (incl. MultiEdit `edits[].file_path`) still work on capped records, `cap_tool_input` never mutates the source event, tests pass.

## IMPORTANT

- **code-reviewer — `_MAX_DEPTH` gate didn't make the hook nesting-safe as the docstring claimed; `json.dumps(obs)` could still `RecursionError` on deeply-nested tool_input.**
  → **FIXED (94a5352):** the depth gate now collapses a still-nested container to a `"<capped: nesting too deep>"` marker, so `cap_tool_input` never returns anything deeper than `_MAX_DEPTH` → `obs["tool_input"]` is ≤ `_MAX_DEPTH` deep → `json.dumps(obs)` is safe on the tool_input path. Docstring corrected to state the gate bounds *this function's* recursion, not the whole hook.
  → **DEFERRED (residual):** `json.loads(raw)` in `main()` can still `RecursionError` on >~1000-deep *stdin* (only `JSONDecodeError` is caught). This is **pre-existing** — it predates this change and sits upstream of every line touched here — and out of hb-168's "cap at capture" scope. Real tool_input is 1-2 deep; this needs an adversarial/broken MCP payload. Candidate follow-up bead: broaden `main`'s parse guard to also catch `RecursionError`.

- **silent-failure-hunter — depth-gate returned the subtree verbatim, so a huge string nested past depth 40 was stored uncapped.**
  → **FIXED (94a5352):** same collapse-to-marker change bounds the stored size past the gate. New test `test_cap_tool_input_collapses_beyond_max_depth` buries a 10 KB string 200 levels deep and asserts the capped record serializes to < 1000 bytes (the buried string never leaks in).

## MINOR

- **code-reviewer — README said `command` is "intact"; a >2000-char command is head-capped (only the prefix survives).** → **FIXED (94a5352):** reworded to "preserving `file_path` and the `command` prefix".
- **code-reviewer — the depth test exercises `cap_tool_input` in isolation, not `main`→`json.dumps`.** → **Addressed by the docstring correction.** A test driving deep input through `main()` would hit the *pre-existing* `json.loads` limit and fail for a reason this change doesn't own, so adding it would be misleading. The isolation test correctly asserts the function's own safety; the new collapse test asserts the size bound.
- **silent-failure-hunter — `main` catches only `JSONDecodeError` around `json.loads`.** → **DEFERRED** (same pre-existing/upstream/out-of-scope reason as the IMPORTANT residual above).

**Gate:** all CRITICAL/IMPORTANT findings fixed or explicitly deferred with a stated reason; whole-branch review ran at full capability. Passed → proceed to land.
