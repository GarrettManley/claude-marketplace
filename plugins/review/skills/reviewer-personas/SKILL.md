---
name: reviewer-personas
description: Use when reviewing design documents, PRs, operational docs, work items, wiki pages, or skill files with sub-agent reviewer personas. Provides a reusable library of archetype personas with dispatch protocol and incremental self-improvement.
version: 0.1.0
dependencies: []
---

# Reviewer Personas

A library of reviewer archetypes for sub-agent-based document and PR review. Each archetype ships as an agent definition at `agents/<name>.agent.md` — that file **is** the persona. This skill is the index, selection table, dispatch protocol, and post-cycle update protocol.

## When to use

Reach for this skill when an artifact warrants multi-lens scrutiny before it lands: a design document, a PR, an operational runbook, a work item, a wiki page, or a Claude Code skill file. Match the artifact to the selection table below, then dispatch the named archetype agents as sub-agents and consolidate their findings into one report.

The shipped library has 16 archetype agents. To add a real teammate persona (with its own pushback triggers grounded in feedback they actually gave), create a new `agents/<name>.agent.md` using `templates/persona-stub.md` as the shape — keep those additions in your project-local `.claude/agents/` rather than upstreaming.

---

## Selection Table

Each cell names the plugin-scoped `subagent_type` — pass it verbatim. The bare `<name>` (e.g. `security-auditor`) also resolves when unambiguous per the Claude Code sub-agents docs, but the scoped `review:<name>` form is recommended: these archetype names are generic and can collide with other installed plugins' agents.

| Artifact | Default archetype set (`subagent_type`) |
|---|---|
| Design documents (pre-implementation) | `review:architect`, `review:security-auditor`, `review:data-architect`, `review:new-engineer`, `review:ecosystem-context-reviewer` |
| Design documents (post-implementation / live system) | Add `review:incident-commander`, `review:observability-champion` |
| Operational docs / runbooks | `review:incident-commander`, `review:new-engineer` |
| Security-sensitive changes | `review:security-auditor` |
| Regulated data flows / audit trails / cert lifecycles | Add `review:compliance` |
| Features introducing or depending on a new data model | Add `review:data-architect` |
| Features with auto-refresh / polling / ops surfaces | Add `review:incident-commander`, `review:observability-champion` |
| Migrations / rotation runbooks / slot swaps | `review:migration-safety`, `review:incident-commander` |
| API endpoints / route or schema changes | Add `review:api-contract` |
| Config defaults / identity-access / external contract surfaces | Add `review:contract-surface` |
| Multi-step flows with external dependencies | Add `review:error-handling` |
| Latency / throughput / cost claims | Add `review:performance-scalability` |
| Test approach (explicit or implied) | Add `review:test-strategy` |
| Interactive UI / layout / color / dynamic content | Add `review:accessibility` |
| PRs touching interfaces used by external systems | Add `review:ecosystem-context-reviewer` |
| Services with diagnosability gaps (limited logging/metrics) | Add `review:observability-champion` |
| Skill files (SKILL.md, REGRESSION.md, agent/persona files) | `review:skill-craft-reviewer` |
| Onboarding / first-time-reader docs | `review:new-engineer` |

To bias the selection for your team or domain, fork this skill into `.claude/skills/reviewer-personas/` and edit the table, and add project-local archetypes under `.claude/agents/`. Archetypes are starting points — they get sharper as you record real review-catches against them.

---

## Dispatch Protocol

1. **Selection.** Match artifact type to the selection table to get the set of `subagent_type` values.

2. **Dispatch.** For each selected archetype, call the `Agent` tool with:
   - `subagent_type: review:<name>` — the plugin-scoped value from the selection table (e.g., `review:security-auditor`). The bare `<name>` also resolves when unambiguous, but the scoped form is collision-safe and recommended. **The agent definition is the persona** — its system prompt carries the full pushback triggers, NOT-covered boundary, and severity rubric, so do not paste any persona text into the prompt.
   - `description`: short persona label (e.g., "Security Auditor — Trust boundaries")
   - `prompt`: the template below with only the artifact reference filled in

3. **Parallelism.** Call up to 4 concurrent agents. Batch into waves for larger sets.

4. **Context.** Pass artifact by reference (absolute path or `gh pr diff <n>` instruction). The sub-agent reads the artifact itself — do not paste inline.

5. **Aggregate.** Collect all YAML findings. Build a consolidated report (format below).

6. **Triage.** Classify each finding: **Act on** / **Noted** / **Dismiss**.

7. **Run Post-Cycle Update Protocol.**

### Dispatch prompt template

The persona comes from the dispatched agent. The prompt only carries the artifact reference and the output contract:

```
ARTIFACT: <absolute path | gh pr diff <n> | wiki URL>

Review the artifact through your archetype's lens. Stay silent on items outside your NOT-covered boundary.

OUTPUT: YAML only. No prose outside the YAML block.

persona: <your archetype name>
findings:
  - severity: blocker|must_fix|nit|signal|praise
    location: <section / line / thread ref>
    finding: <one sentence>
    rationale: <one sentence tied to a pushback trigger>
    trigger_ref: <which pushback trigger fired>
```

### Fallback (sub-agents unavailable)

When the `Agent` tool is unavailable, read the selected `agents/<name>.agent.md` files directly, role-play each archetype inline **sequentially**, and emit: `[REVIEW MODE: inline — sub-agent dispatch unavailable]`. Output format unchanged.

---

## Consolidated Report Format

```
# Review: <artifact>  (<N> personas, <date>)

## Blockers and Must-fix (cross-persona amplified)
Same location flagged by ≥2 personas → severity escalates one step.

## By severity
### Blockers  /  Must-fix  /  Nits  /  Signal  /  Praise

## Disagreements
Locations where personas contradict. Flag; author decides.

## Per-persona findings
Full YAML from each persona.

## Triage
- Act on: ...
- Noted: ...
- Dismiss: ...
```

---

## Post-Cycle Update Protocol

After each review cycle, before committing, run this for each participating persona:

1. **Caught** — what did this persona flag that was acted on?
2. **Missed** — what did human review or another persona catch that this persona should have flagged?
3. **Hallucinated** — what did this persona flag that was inapplicable? Classify as Dismiss.
4. **Update** — if missed or hallucinated findings were notable, adjust pushback triggers.

Then: "Was there a class of issue this cycle that no current archetype would catch? If so, draft a new archetype as `agents/<name>.agent.md` using `templates/persona-stub.md` for the persona body."

Update the relevant `agents/<name>.agent.md` file. Set the `Last updated` line with a one-line reason. Commit alongside the artifact you just reviewed.

---

## Completion Tokens (pairs with the SessionStart hook)

This plugin ships with `session-start-review-nag.sh`, which surfaces markers in `.claude/reviews/pending/` at session start. When a review cycle completes, write a completion token at `.claude/reviews/completed/<slug>.json`:

```json
{
  "slug": "<artifact-slug>",
  "reviewed_at": "<ISO8601 timestamp>",
  "personas": ["Security Auditor", "Data Architect"]
}
```

The marker mechanism is project-defined (you decide when an artifact becomes review-triggering). The skill plus hook only handles the back half: surfacing pending markers and acknowledging completion.
