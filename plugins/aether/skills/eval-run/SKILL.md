---
name: eval-run
description: Run the classifier golden eval suite against the local llama-server classifier. Use after any edit to classifier_prompt.ts, gemini.ts, llamacpp.ts, or schemas.ts to catch regressions before committing.
version: 0.1.0
dependencies: []
---

# Run Classifier Eval

## When to use

Use after editing `classifier_prompt.ts`, `gemini.ts`, `llamacpp.ts`, or
`schemas.ts`, before committing, to catch classifier regressions.

Run the classifier golden eval suite and report results.

## Steps

### 1. Run the eval (gate mode)

```bash
EVAL_REQUIRE_LLM=1 npm run eval:classifier
```

`eval:classifier` runs `scripts/eval-gate.mjs`, which drives the vitest
classifier suite (`vitest.classifier.config.ts`) against the local
**llama-server** classifier (`LLAMACPP_CLASSIFIER_MODEL`, default `gemma4:e4b`,
`LLAMACPP_SEED=42`). `EVAL_REQUIRE_LLM=1` makes the gate **fail on any skipped
case** — without it the suite silently reports a green run when the model is
unreachable (issue #158). Make sure llama-server is already serving `gemma4:e4b`.

If the gate fails with skips or a connection error, **stop and report it** — a
green run without the LLM up means nothing.

### 2. Read the scorecard line

`eval-gate.mjs` prints a one-line summary and appends it to
`docs/engineering/model-eval/scorecards.jsonl`:

```
[eval-gate] <passed>/<total> passed, <failed> failed, <skipped> skipped (model=gemma4:e4b) → scorecard appended to …
```

Do **not** assume a fixed test count — report the `total` / `passed` / `skipped`
the gate actually emits. Under `EVAL_REQUIRE_LLM=1` any `skipped > 0` has already
failed the gate.

### 3. Report

State:

- passed / total (from the scorecard line)
- failing count, with each failing test name + received vs expected intent type
- skipped count (must be 0 in gate mode)

If clean: "Eval clean — no classifier regressions."
If any fail: list regressions with their input text and misclassification.

## Context

- Command: `npm run eval:classifier` → `scripts/eval-gate.mjs` (gate mode:
  `EVAL_REQUIRE_LLM=1 npm run eval:classifier`)
- Suite config: `vitest.classifier.config.ts`
- Runtime: local **llama-server** (Ollama was retired 2026-06-12)
- Default classifier model: `gemma4:e4b` (override via `LLAMACPP_CLASSIFIER_MODEL`)
- Scorecard trend: `docs/engineering/model-eval/scorecards.jsonl`
- Full multi-model study: `node scripts/model-study/run-all.mjs` (manifest-driven
  lifecycle across the classifier/prose model slate)
