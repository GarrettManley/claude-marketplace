---
name: instinct-detect
description: Claude-driven detection of correction and preference instincts from the transcript + observations (Phase 2c)
---

# /instinct-detect

Detect **correction patterns** (where the user redirected or rejected an approach) and **preference signals** (a tool or approach chosen repeatedly) that pure frequency synthesis (`/instinct-synthesize`) cannot see, and turn them into `claude-detected` instincts. The intelligence here is *yours* — you read the live transcript and the observation summary, then propose candidates; the script only dumps context and validates/writes what you author.

This is Path A (Claude-driven). A headless local-LLM backend (Path B) is deferred.

## Implementation

**1. Dump the observation summary** (sequences, tool frequency, Bash prefixes, likely-error samples):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" detect --dump-observations --scope project
```

**2. Reason over it.** Read the JSON above **and this session's transcript**. Identify:
- **Correction patterns** — the user said "no, use X instead", reverted your change, or steered you off an approach. Encode the *learned* behavior (prefer X when Y).
- **Preference signals** — an approach/tool chosen ≥5 times where alternatives existed.
- **Tool-outcome patterns** — a command in `error_samples` that repeatedly failed until corrected.

**3. Author candidates** as a multi-instinct YAML file (same shape as `/instinct-import` accepts — `id`, `trigger`, `confidence`, `domain`, `source`, then `## Action` / `## Evidence`). Write it to a temp path, e.g. `"$TMPDIR/instinct-candidates.yaml"`. Set evidence to the concrete transcript moment. Source and confidence are normalized for you (forced to `claude-detected`, capped at 0.80).

**4. Review (dry-run), then persist:**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" detect --ingest "$TMPDIR/instinct-candidates.yaml" --scope project
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/instinct_cli.py" detect --ingest "$TMPDIR/instinct-candidates.yaml" --scope project --apply
```

## Notes

If `--dump-observations` reports `record_count: 0`, capture is off — enable it and run some sessions first (`export LEARNING_HOOK_PROFILE=strict; export LEARNING_OBSERVE=on`). Detected instincts land in the scope's `personal/` store and are reinforced/decayed like other machine instincts; run `/instinct-status` to review.
