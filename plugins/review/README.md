# review@garrettmanley

Multi-lens artifact review using a library of sub-agent reviewer archetypes. Hand it a design document, PR, operational runbook, work item, wiki page, or Claude Code skill file and it dispatches the appropriate personas as parallel sub-agents, consolidates their YAML findings into a single severity-ranked report, and surfaces unreviewed artifacts at session start. For teams and individuals who want structured, multi-perspective scrutiny on artifacts before they land — without assembling a review panel by hand.

## Install

```
/plugin marketplace add garrettmanley/claude-marketplace
/plugin install review@garrettmanley
```

## Components

### Skills

| Skill | Description |
|-------|-------------|
| `reviewer-personas` | Archetype selection table, sub-agent dispatch protocol, consolidated report format, and post-cycle update protocol for incremental persona improvement |

### Agents

Sixteen reviewer archetypes ship as `.agent.md` files. Each runs as a sub-agent dispatched by the `reviewer-personas` skill.

| Agent | Scope |
|-------|-------|
| `accessibility` | WCAG compliance, ARIA semantics, keyboard navigation, and color contrast for browser-rendered UI surfaces |
| `api-contract` | Idempotency guarantees, versioning discipline, breaking-change detection, and error response consistency for API surfaces |
| `architect` | Progressive disclosure, mental-model completeness, undefined concepts, and unverified quantitative claims in design documents |
| `compliance` | Auditable evidence of controls, data residency boundaries, and audit trail integrity for regulated data flows |
| `contract-surface` | Operational invariants, fail-closed defaults, and contract precision for configuration and external integration surfaces |
| `data-architect` | Schema design, referential integrity, multi-tenant isolation, and data lifecycle for features that introduce or modify data models |
| `ecosystem-context-reviewer` | Institutional memory gaps, ADR conflicts, and missing integration acknowledgments for changes touching external systems |
| `error-handling` | Failure mode completeness, recovery path specification, and error propagation boundaries at design time |
| `incident-commander` | Operational clarity — repair steps, alerting callouts, escalation paths, and thundering-herd patterns in runbooks and live-system docs |
| `migration-safety` | Rollback paths, idempotency, mixed-version windows, and partial-failure blast radius for migrations and rotation procedures |
| `new-engineer` | Onboarding clarity — undefined terms, assumed context, and missing prerequisite steps for any first-time-reader audience |
| `observability-champion` | Design-time instrumentation gaps: structured logging, trace IDs, heartbeat events, and alert-level correctness |
| `performance-scalability` | Claim precision, capacity modeling, cost-at-scale visibility, and adjective-only performance assertions |
| `security-auditor` | Trust boundaries, least-privilege violations, missing input validation, and defense-in-depth gaps |
| `skill-craft-reviewer` | Triggering accuracy, Iron Law compliance, token efficiency, and description quality for Claude Code skill files |
| `test-strategy` | Risk-appropriate test level selection, mock contract fidelity, and boundary condition coverage |

### Hooks

| Hook | Event | Behavior |
|------|-------|----------|
| `session-start-review-nag.sh` | `SessionStart` | Lists artifacts in `.claude/reviews/pending/` that completed without a reviewer-personas completion token; silent when the directory is absent or empty |

## Usage

Invoke the skill with an artifact reference. The skill selects archetypes from the built-in selection table, dispatches up to 4 agents in parallel, and consolidates findings into a single report.

```
Use the reviewer-personas skill to review docs/engineering/designs/2026-07-01-cache-layer.md
```

```
Use reviewer-personas on PR #47 — focus on security-auditor and data-architect
```

```
Review this runbook: docs/ops/cert-rotation.md
```

The consolidated report groups findings by severity (blocker / must_fix / nit / signal / praise), escalates findings flagged by two or more personas, and surfaces disagreements between personas for author triage.

### Selection table (built-in)

| Artifact type | Default archetypes |
|---|---|
| Design documents (pre-implementation) | Security Auditor, Data Architect, New Engineer, Ecosystem Context Reviewer |
| Design documents (live system) | Add Incident Commander, Observability Champion |
| Operational docs / runbooks | Incident Commander, New Engineer |
| Security-sensitive changes | Security Auditor |
| Features with a new data model | Add Data Architect |
| Features with polling / ops surfaces | Add Incident Commander, Observability Champion |
| PRs touching external-system interfaces | Add Ecosystem Context Reviewer |
| Services with diagnosability gaps | Add Observability Champion |
| Skill files (`SKILL.md`, `personas/*.md`) | Skill-Craft Reviewer |
| Onboarding / first-time-reader docs | New Engineer |

Override the table for your team by forking the skill into `.claude/skills/reviewer-personas/` in your project and editing the selection table there.

### Post-cycle update protocol

After each review, record what each persona caught, missed, or hallucinated. Update the relevant `personas/<slug>.md` with refined pushback triggers and commit it alongside the reviewed artifact. This is how the library sharpens over time.

## Configuration

### Completion token contract

The hook and skill share a file-based marker contract under `.claude/reviews/`:

| Path | Purpose |
|------|---------|
| `.claude/reviews/pending/<slug>.marker` | Marks an artifact as needing review; file contents become the human-readable label in the nag |
| `.claude/reviews/completed/<slug>.json` | Written by the skill after a successful cycle; clears the pending nag |
| `.claude/reviews/skip/<slug>.marker` | Paper-trail bypass — moves a marker out of pending without completing a cycle |

The project decides when an artifact becomes review-triggering (a separate hook, a manual `touch`, or a CI step that writes the marker). The `review` plugin handles only the back half: surfacing pending markers and acknowledging completion.

**Recommended `.gitignore` entry:**

```
.claude/reviews/pending/
```

Keep `.claude/reviews/completed/` tracked — it is the audit trail showing reviews actually happened.

### Completion token format

```json
{
  "slug": "<artifact-slug>",
  "reviewed_at": "<ISO8601 timestamp>",
  "personas": ["Security Auditor", "Data Architect"]
}
```

### Adding real-person personas

The shipped library is archetypes only. To add personas grounded in actual teammate feedback:

1. Fork this skill into `.claude/skills/reviewer-personas/` in your project.
2. Copy `templates/persona-stub.md` into `personas/<teammate-slug>.md`.
3. Fill in pushback triggers from real PR comments or review threads. The quote bank needs at least 3 verbatim quotes for grounding.
4. Add a selection-table row in the forked `SKILL.md` naming the new persona for the artifact types they should review.

Keep these forks in your project. The upstream library stays archetype-only.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Session-start nag fires for an artifact you don't intend to review | Move the marker to `.claude/reviews/skip/<slug>.marker` for a paper-trail bypass, or delete it if no audit trail is needed |
| Nag fires but the pending directory looks empty | The hook uses `find -maxdepth 1 -name '*.marker'`; verify the file extension is exactly `.marker` and the file is directly in `.claude/reviews/pending/` (not a subdirectory) |
| Sub-agents are unavailable (no `Agent` tool) | The skill falls back to inline sequential role-play and prepends `[REVIEW MODE: inline — sub-agent dispatch unavailable]` to the output; report format is unchanged |
| A persona flags items outside its documented scope | Run the post-cycle update protocol: classify the finding as `Dismiss` (hallucinated), then narrow the persona's pushback triggers and update `Last updated` in `personas/<slug>.md` |

## Cross-platform

The `session-start-review-nag.sh` hook is a POSIX shell script. On Windows it requires a Bash-compatible shell in PATH (e.g. Git Bash). The Claude Code hook runner invokes it via `bash "${CLAUDE_PLUGIN_ROOT}/hooks/session-start-review-nag.sh"`, so Git Bash on Windows is sufficient — no WSL required.

The marker file contract (`.claude/reviews/pending/*.marker`) is path-based and cross-platform. Paths inside marker files should use forward slashes or be relative to the project root for portability.
