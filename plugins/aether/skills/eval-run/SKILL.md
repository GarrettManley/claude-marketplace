---
name: eval-run
description: Run the classifier golden eval suite against the local LLM classifier (Ollama or llama-server). Use after any edit to classifier_prompt.ts, gemini.ts, ollama.ts, or schemas.ts to catch regressions before committing.
version: 0.1.0
dependencies: []
---

# Run Classifier Eval

## When to use

Use after editing `classifier_prompt.ts`, `gemini.ts`, `ollama.ts`, or
`schemas.ts`, before committing, to catch classifier regressions.

Run the classifier golden eval suite and report results.

## Steps

### 1. Preflight — verify Ollama is reachable

```bash
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
if ! curl -sf "${OLLAMA_URL}/api/tags" > /dev/null 2>&1; then
  echo "ERROR: Ollama is not reachable at ${OLLAMA_URL}"
  echo "Start Ollama with: ollama serve"
  echo "Then ensure the classifier model is available: ollama list"
  exit 1
fi
echo "Ollama is up at ${OLLAMA_URL}"
```

If Ollama is unreachable, **stop here and report the error**. Do NOT proceed — the eval silently reports all tests as passing when Ollama is down (see `tests/eval/classifier.eval.ts:41-56`). A green result without this preflight means nothing.

### 2. Run the eval

```bash
OLLAMA_CLASSIFIER_MODEL=gemma3:4b npx vitest run \
  --config vitest.classifier.config.ts \
  --reporter=verbose
```

The standard suite contains **38 tests**. If fewer than 38 tests ran, report: "WARNING: Only N tests ran — possible silent-skip. Check that Ollama stayed responsive throughout the run."

### 3. Report

State:
- Tests run / 38
- Passing count
- Failing tests (name + received type + expected type)
- Whether the silent-skip condition may have fired

If all 38 pass: "Eval clean — no classifier regressions."
If any fail: list regressions with their input text and misclassification.

## Context

- Config: `vitest.classifier.config.ts`
- Eval file: `tests/eval/classifier.eval.ts`
- Default classifier model: `gemma3:4b` (overrideable via `OLLAMA_CLASSIFIER_MODEL` env)
- Full multi-model eval: `npm run eval:run` (runs 5 classifier + 3 prose models, writes summaries to `docs/engineering/model-eval/`)
