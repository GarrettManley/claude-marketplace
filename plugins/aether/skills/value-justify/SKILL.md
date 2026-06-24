---
name: value-justify
description: Generate the exact-format Value Justification block required by .claude/hooks/plan_issue_check.py. Use when writing a plan under docs/engineering/plans/ to avoid the regex-format friction documented in CLAUDE.md.
version: 0.1.0
dependencies: []
disable-model-invocation: true
---

# Value Justification

## When to use

Use when writing a plan under `docs/engineering/plans/` and you need a
`## Value Justification` block that passes the hook regex on the first
try. Invoke explicitly (for example `/value-justify 3 5 6`).

Output a hook-passing `## Value Justification` section for an engineering
plan. The PostToolUse hook (`plan_issue_check.py`) validates four numbers
plus a score field with a strict regex; the wrong format silently fails
the regex and blocks the plan write.

## Inputs

Ask the user for three numbers (or accept them as args):

- **Impact** (1–5): how big is the gain if this lands successfully?
- **Confidence** (1–5): how sure are we the approach works as planned?
- **Effort** (hours, ≥1): honest estimate of total time to land.

If the user provides rationale strings, use them. Otherwise prompt for
each in one short sentence.

## Compute

```
score = impact × confidence / effort
```

Round to 2 decimal places. The hook tolerates ±5% rounding.

## Output

Emit exactly this block (the hook regex anchors on `**Field**`-with-closed-asterisks-BEFORE-the-colon):

```markdown
## Value Justification

`score = impact × confidence / effort` (per spec 036 / hook #54)

- **Impact** (1-5): N — <one-sentence rationale>
- **Confidence** (1-5): N — <one-sentence rationale>
- **Effort** (hours): N — <one-sentence rationale>
- **Score**: N.NN  (impact × confidence / effort = I × C / E)

<one-sentence interpretation: "Solid debt-closure slice", "High-leverage feature work", "Speculative refactor — defer if shipping pressure rises", etc.>
```

## What the hook regex actually checks

From `.claude/hooks/plan_issue_check.py`:

```python
impact_m = re.search(r"\*\*Impact\*\*[^:]*:\s*([0-9.]+)", body)
conf_m   = re.search(r"\*\*Confidence\*\*[^:]*:\s*([0-9.]+)", body)
eff_m    = re.search(r"\*\*Effort\*\*[^:]*:\s*([0-9.]+)", body)
score_m  = re.search(r"\*\*Score\*\*\s*:\s*([0-9.]+)", body)
```

The asterisks must close BEFORE the colon. `**Impact: 3**` will silently
fail. `**Impact** (1-5): 3` will pass.

The arithmetic check enforces `|expected - score| / max(score, 0.01) ≤ 0.05`.
Two-decimal rounding stays inside that tolerance for the integer ranges
plans actually use.

## Calibration anchors

Use these reference scores to keep impact/effort claims honest:

| Plan kind | Typical score |
|---|---|
| Bug fix that closes a P1 issue | 4.0–6.0 |
| Coverage close-out (T3.5-style) | 2.0–3.0 |
| New feature, mid-confidence | 1.5–3.0 |
| Speculative refactor | 0.3–1.0 |
| Documentation / harness improvement | 1.0–2.5 |

If your score lands far outside these ranges, sanity-check the inputs
before writing the plan. The hook accepts the math, but the user reads
the rationale.

## Example session

User: `/value-justify 3 5 6`

Output:

```markdown
## Value Justification

`score = impact × confidence / effort` (per spec 036 / hook #54)

- **Impact** (1-5): 3 — Closes the three named coverage gaps and finishes the T3 Wild Shape arc.
- **Confidence** (1-5): 5 — Zero architectural risk; mirrors existing test patterns exactly.
- **Effort** (hours): 6 — 3 integration tests × ~1h, scenario + harness ~2h, retro + push ~1h.
- **Score**: 2.50  (impact × confidence / effort = 3 × 5 / 6)

Solid debt-closure slice. Lower-impact than feature work but high-confidence and low-effort.
```
