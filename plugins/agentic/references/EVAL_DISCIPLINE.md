# Eval Discipline

Templates and conventions for evaluating Claude-powered apps.

## The minimum viable eval

Before shipping any AI app, you need:

1. **Golden test set**: ≥ 20 input/output pairs. Each pair has:
   - Input (user prompt, conversation context, tool inputs).
   - Expected output (exact match for structured, rubric-scored for prose).
   - Rationale (why this case matters — edge case? regression? happy path?).
2. **Eval runner**: a script that runs all cases, captures actual outputs, scores them.
3. **Regression gate**: CI step that fails when scores drop > X% from main.

## Test-set structure

```
src/evals/
├── README.md                # what this set covers, how to grow it
├── golden/                  # the cases
│   ├── 001-happy-path.json
│   ├── 002-empty-input.json
│   ├── 003-conflicting-tools.json
│   └── ...
├── runner.py                # or runner.ts
└── results/                 # historical eval runs (gitignored or LFS)
```

Each case file:

```json
{
  "id": "001-happy-path",
  "category": "happy-path",
  "rationale": "User asks a clear question that fits one tool's domain.",
  "input": {
    "messages": [{"role": "user", "content": "What's the weather in Tokyo?"}]
  },
  "expected": {
    "tool_calls": [{"name": "get_weather", "args": {"city": "Tokyo"}}],
    "response_contains": ["Tokyo", "weather"]
  }
}
```

## Scoring strategies

### Structured outputs (tool calls, JSON)
Exact match on tool name + arg keys. Fuzzy match on string args (use `Levenshtein` or LLM-judge).

### Prose outputs
Three scoring tiers, in order of cost:

1. **String contains**: cheapest. Use for "did it mention the right facts."
2. **Rule-based**: regex / structural checks. Use for format compliance.
3. **LLM-judge**: send the response + rubric to a smaller model (`claude-haiku-4-5`) for a 1-5 score. Use sparingly — judge stochasticity adds noise.

Never use LLM-judge as the SOLE scorer for a regression gate — pair with at least one rule-based check.

## Running evals

Local development:

```bash
python src/evals/runner.py --suite golden --model claude-sonnet-4-6
# Output: pass-rate per category, regression vs last run, full per-case results
```

CI:

```yaml
# .github/workflows/eval.yml
- name: Run golden evals
  run: |
    python src/evals/runner.py --suite golden --model claude-sonnet-4-6 --json > eval-results.json
    python src/evals/check_regression.py --baseline main --threshold 0.05
```

## Growing the test set

Every bug report should add a case. Workflow:

1. User reports unexpected behavior.
2. Reproduce locally; capture the input.
3. Decide expected behavior.
4. Add a case file with `category: regression-<issue>` and `rationale: closes #N`.
5. Confirm the new case fails on current code; ship the fix; confirm it passes.

This grows your test set in lockstep with real-world failures, not just the imagined cases.

## Frameworks

For batch eval at scale, consider:

- **`inspect-ai`** (Anthropic's eval framework): structured + judge support, good ecosystem.
- **`lighteval`**: lighter weight, good for benchmark-style suites.
- **Custom Python harness**: best for app-specific shape.

For quick iteration, custom is usually enough until you have > 100 cases or > 3 model variants to compare.

## What NOT to do

- **Don't eval on production traffic without consent** (PII leak, GDPR risk).
- **Don't ship an AI feature without ≥ 1 case for it.**
- **Don't gate on a single model's output** — eval across models when you can. Hedges against per-model regressions.
- **Don't trust eval scores from the same model you're evaluating** (LLM-judge bias). Use a different family.
