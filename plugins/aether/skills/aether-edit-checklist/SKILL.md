---
name: aether-edit-checklist
description: Use when finishing a logical chunk of edits and before declaring work done, or when the user asks "what should I check before committing?". Walks the per-edit checklist (graphs, JSDoc, eval, harness, TODO format) so nothing is forgotten before the diff lands.
version: 0.1.0
dependencies: []
---

# Aether per-edit checklist

## When to use

Use after a logical chunk of edits and before declaring work done or
committing. Most items have hooks that fire automatically, but this
checklist is the ground truth — walk it to catch what the hooks miss.

## 1. Diagrams (auto-regenerated, but verify)

| Trigger | Command |
| --- | --- |
| Changed `src/**/*.ts` | `npm run docs:graphs:ts && git add docs/engineering/diagrams/ts-module-graph.mmd` |
| Changed `core/src/**/*.rs` | `npm run docs:graphs:rust && git add docs/engineering/diagrams/rust-module-graph.dot` |

The graph-regen hook in `settings.local.json` runs `docs:graphs:ts`
automatically on `src/*.ts` writes; verify the diff is staged.

## 2. Doc comments on public API

- Added a public TypeScript export → JSDoc above the export.
- Added a public Rust item → `///` doc comment above the item.

## 3. Tests + evals

| Touched | Run |
| --- | --- |
| Classifier code (`src/llm/classifier_prompt.ts`, `gemini.ts`, `ollama.ts`, `schemas.ts`) | `npm run eval:classifier` (or invoke the `eval-run` skill) |
| State-sync prompt or schema | `npm run eval:state-sync` |
| Gameplay-affecting source (`src/dm.ts`, `src/llm/*`, `src/bus.ts`, `src/server.ts`, `src/actor.ts`, `src/roll-proposal.ts`, `src/state-sync.ts`) | `node scripts/run-gameplay-tests.mjs` (live Ollama; scenarios 01-03 baseline + area-specific) |
| Anything else in `src/` or `core/src/` | `npm run check` |

Don't run `eval:classifier` or `eval:state-sync` concurrently with
`run-gameplay-tests.mjs` — all three hit the same Ollama instance and
hit the 14 s timeout. Serialize them.

## 4. TODOs need issue refs

Any `TODO`, `FIXME`, `XXX`, or `HACK` comment in `.ts`/`.js`/`.rs`
must cite a GitHub issue: `TODO(#NNN): note`. The
`todo_issue_hook.py` PreToolUse hook BLOCKS un-cited TODOs. If the
work isn't tracked yet, file the issue first:

```bash
gh issue create --title "..." --label "type:..." --body "..."
```

## 5. README + module-level docs

If you changed the public surface of a `src/<module>/`, update its
`README.md` if one exists.

## 6. Plan + retrospective

If this work was scoped under a plan in `docs/engineering/plans/`,
add a Retrospective on completion with `Closes #N` (or `Updates #N`
for in-progress placeholder). See the `aether-plan-writer` skill.

## 7. Final gate

```bash
npm run check
```

This chains typecheck + smoke + unit. Mirrors CI. Don't ship without
it green.

## 8. Branch hygiene

Feature branches are short-lived. After a task cluster lands commits,
invoke `superpowers:finishing-a-development-branch` to handle the
rebase + review + FF-merge workflow. Project policy: merge via
`git merge --ff-only` only — never `--squash` (the user values
`git log` granularity).

## See also

- `docs/engineering/conventions.md` — canonical per-edit rules
- `docs/engineering/ci-and-guards.md` — full guard stack
- `docs/engineering/pitfalls/tests-and-tooling.md` — eval/harness gotchas
- `.claude/hooks/` — the hooks that automate parts of this checklist
