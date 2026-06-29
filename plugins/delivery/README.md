# delivery@garrettmanley

End-to-end value-delivery lifecycle in one orchestrated pass. The `/deliver` command + `deliver`
skill run a fixed spine — pre-plan brief → write plan → adversarial plan review → approval →
subagent execution → completion gate → adversarial code review → land → retrospective — composing
existing `superpowers`, `docs`, and `retrospective` skills instead of reimplementing them.

The spine is project-agnostic. The few steps that differ per repo — how a plan is authored, which
companion docs must ship, the pre-commit checklist — are **slots** that bind from a per-repo
`<repo>/.claude/delivery.local.md` config. A repo with its own plan/doc/checklist skills gets full
rigor; a bare repo gets generic defaults. Same skill, no edits, no project-internal names committed
here.

Intended for engineers who run Claude Code in plan mode and want the whole deliver arc driven
consistently rather than retyped — and varied per project from a local config rather than per-repo
forks of the skill.

## Install

```
/plugin marketplace add garrettmanley/claude-marketplace
/plugin install delivery@garrettmanley
```

No init scripts. The `docs` and `retrospective` plugins are the composed dependencies;
`superpowers` (external) is used best-effort with built-in fallbacks when it is absent.

## Components

| Component | Type | Trigger / Purpose |
|-----------|------|-------------------|
| `deliver` | Skill | The lifecycle playbook: resolves project slots from config, echoes the resolved-slot table, then runs the plan → execute → review → land → retrospect arc. |
| `/deliver` | Command | Thin entry that takes an optional `<work-target>` and defers to the `deliver` skill. |

## Usage

```
/deliver @./some-app
/deliver "#42 — add rate limiting to the gateway"
/deliver                      # asks what the body of work is
```

Every run first prints a **resolved-slot table** showing exactly which path it will take — the
project-specific bindings (or generic defaults) for `plan-writer`, `doc-cluster`, `edit-checklist`,
and `land-policy`.

### Per-project binding

Create `<repo>/.claude/delivery.local.md` to slot in a repo's own steps. The skill's `## Configuration`
section documents the exact frontmatter keys and the 2-level resolution rule
(`delivery.local.md` > generic default). Bindings are best-effort: a bound skill that is not
installed is announced and skipped, never fatal.

## Configuration

Project bindings live in `<repo>/.claude/delivery.local.md` — schema and example are in the `deliver`
skill's `## Configuration` section (kept there so there is one source of truth). The plugin itself has
no env vars or global config.

## What this is not

- **Not an automated runner.** The approval and landing gates are deliberately human; the skill
  proposes commands and lands only on explicit authorization.
- **Not a replacement** for the skills it composes — invoke `pre-plan-brief`, `adversarial-review-plan`,
  `plan-completion`, `adversarial-review-code`, or `plan-retrospective` directly when you want just
  that one step.
