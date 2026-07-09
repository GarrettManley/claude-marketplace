# Adversarial Plan Review — hb-168 tool_input cap

**Plan:** `2026-07-09-hb-168-tool-input-cap-plan.md`
**Posture:** FULL (6 dimensions + 3 archetypes = 9 agents), chosen because Phase 0 was skipped (premise/scope never independently approved) and `observe.py` is a hot-path hook (runs on every tool call).
**Date:** 2026-07-09

All findings below are dispositioned. The plan was **revised** (single-task, redesigned cap) to resolve every CRITICAL and IMPORTANT before execution.

## CRITICAL

- **[CRITICAL] risk-rollback — RecursionError crashes the observation hook.** `cap_tool_input` recurses on payload nesting depth; MCP tool_input is arbitrary/unbounded JSON. >~1000 nested levels raises `RecursionError` (not `OSError`), which propagates uncaught out of `_build_observation` → `main()` (only the file write is `try/except OSError`), crashing the Pre/PostToolUse hook on that call while `LEARNING_OBSERVE=on`. The current verbatim capture has no such path — the change *introduces* it.
  → **RESOLVED:** added a `_depth` guard (`_MAX_DEPTH = 40`) that collapses beyond-limit values instead of recursing. Surgical (no broad `except` that would mask real bugs); a hook consuming arbitrary tool payloads is a system boundary, so a bound here is boundary-validation, not over-engineering.

- **[CRITICAL] scope-cutter — Cut Task 2 (nightly re-cap) entirely.** Corroborated by value-justification (IMPORTANT) and scope-cut dimension (IMPORTANT/defer). The 75.5 MB that motivated hb-168 was already rotated to `observations.rotated-20260707.jsonl` — a file `compact_observations` never touches — so Task 2 cannot shrink it. It only re-caps records written between rotation and landing, which the existing **30-day retention drop already self-purges** with zero code. Its new `truncated_input` counter has **no reader** (`render_briefing.py` never surfaces it). Bead mandate is "at capture."
  → **RESOLVED:** Task 2 cut. Plan is now single-task (capture only). `synthesize_nightly.py` untouched. Removes the wider signature, the reader-less counter, the import change, 2 tests, and the nightly-recursion risk on unvalidated pre-fix records.

## IMPORTANT

- **[IMPORTANT] plan-skeptic — `command` preserved verbatim is a bloat leak.** `bash_command_prefixes` reads only `tokens[:2]`, yet the original `_PRESERVE_KEYS` kept multi-MB heredoc / `python -c` commands uncapped by design.
  → **RESOLVED via redesign (see below):** head-cap *every* over-length string; `command`'s head keeps `tokens[:2]` intact for `analyze.py`.

- **[IMPORTANT] plan-skeptic — simpler allowlist projection never ruled out.** Storing only `command`/`file_path`/`edits[].file_path` is ~8 lines, no recursion.
  → **RESOLVED:** kept the recurse-and-cap shape (not lossy projection) so record structure survives for future mining, and the recursion is justified for `edits[]` + unknown MCP nesting (scope-cutter's own KEEP verdict). Redesign drops the marker/preserve-set machinery, so the surviving code is close to the projection's size anyway.

- **[IMPORTANT] value-justification / plan-skeptic / completeness — the "~50 MB / 75.5 MB residual" claim is unquantified and already rotated out.** The live file is ~KB; the cap is forward-looking, not a shrink of existing bloat.
  → **RESOLVED:** Architecture rewritten to an honest forward-looking framing (bounds every future record so the live file can't re-accumulate multi-MB payloads); no claim to fix the rotated-out file.

- **[IMPORTANT] feasibility-auditor — landing tag-repoint is unconditional but this PR cuts no release.** Literal execution would force-move the live `learning-v*` tag `release.py` keys off.
  → **RESOLVED:** landing constraint softened — this PR ships `fix(learning):` commits that release in learning's *next* `release.py` run; do **not** move tags as part of landing.

- **[IMPORTANT] completeness — `plugins/learning/README.md` goes stale.** Its "Observation growth is bounded twice" section (185-190) and `tool_input` schema example (164) describe only `tool_response` capping.
  → **RESOLVED:** README update folded into the task (Files + a step); reworded to describe capture-time capping of both `tool_response` and oversized `tool_input` string values.

- **[IMPORTANT] completeness / plan-skeptic — Verification is entirely synthetic.** No end-to-end / real-data acceptance that the cap actually bounds a stored record.
  → **RESOLVED:** added an E2E smoke to Verification — enable capture in a temp data-root, feed an oversized Write `tool_input`, read the stored JSONL, confirm `content` head-capped and `file_path`/`command` intact.

- **[IMPORTANT] clarity / feasibility-auditor — combined-coverage command is Bash-only + drops CI's `set -euo pipefail`; no coverage baseline; post-commit `git status` is empty.**
  → **RESOLVED:** Verification commands marked "run via the Bash tool / Git Bash," given `set -euo pipefail`; dropped the unobservable "≥ prior" (kept "new lines covered"); artifact check switched to `git show --name-only` per commit + empty porcelain.

## MINOR

- **[MINOR] INPUT_MAX_CHARS=2000 asserted, not derived** → added a rationale comment (2000-char head is ample for the only structural read, `command`'s first two tokens; mirrors `RESPONSE_MAX_CHARS`).
- **[MINOR] risk-rollback — marker `{truncated,text}` collision at any depth** → **eliminated by redesign** (no marker dict; over-length strings become plain string heads).
- **[MINOR] clarity / feasibility-auditor — stale line-number cues after in-file insertions** → rely on quoted before/after anchors, not line numbers.
- **[MINOR] clarity — run-on sentence in Architecture** → reworded.
- **[MINOR] plan-skeptic — per-record aggregate still unbounded (a 50-edit MultiEdit ≈ 200 KB of heads)** → **ACCEPTED, not fixed**: bounded and rare (large MultiEdits are uncommon), and vastly better than multi-MB; capping list length would be over-engineering against a non-problem. Noted in the plan.
- **[MINOR] completeness — `detect.py` reads `command` indirectly via `analyze.bash_command_prefixes`** → clarified in the preserve-behavior comment so a future editor doesn't treat `detect.py` as tool_input-independent.
- **[MINOR] feasibility-auditor — Step 2 `-k` filter deselects the multiedit test; ImportError names the first missing symbol** → Step 2 now runs the whole test file (no fragile `-k`); expected message loosened to "ImportError (cap_tool_input / INPUT_MAX_CHARS not defined)."

## Net redesign (resolves I1, I2, M2, M7 together)

Drop the marker dict **and** `_PRESERVE_KEYS`. Head-cap every over-length string to a plain string (`value[:max_chars]`); recurse `dict`/`list`; depth-guard. `file_path` (short) and `command` (head preserves `tokens[:2]`) survive naturally for `analyze.py` with zero special-casing — simpler, and no consumer reads a truncation signal on `tool_input`. Single file changed for the core (`observe.py`), plus its test and the README.

**Gate:** all CRITICAL + IMPORTANT resolved in the revised plan. Proceeding to approval.
