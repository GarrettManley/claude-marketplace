---
name: reviewer-personas
description: Use when reviewing design documents, PRs, operational docs, work items, wiki pages, or skill files with sub-agent reviewer personas. Provides a reusable library of archetype personas with dispatch protocol and incremental self-improvement.
version: 0.1.0
dependencies: []
---

# Reviewer Personas

A library of reviewer archetypes for sub-agent-based document and PR review. Each archetype lives in `personas/<slug>.md`. This file is the index, selection table, dispatch protocol, and post-cycle update protocol.

## When to use

Reach for this skill when an artifact warrants multi-lens scrutiny before it lands: a design document, a PR, an operational runbook, a work item, a wiki page, or a Claude Code skill file. Match the artifact to the selection table below, then dispatch the named archetypes as sub-agents and consolidate their findings into one report.

The shipped library has 7 archetype personas. To add real teammate personas (with their own pushback triggers grounded in feedback they actually gave), copy `templates/persona-stub.md` and fill in the blanks — keep those forks in your project-local `.claude/skills/reviewer-personas/personas/` rather than upstreaming.

---

## Selection Table

| Artifact | Default archetype set |
|---|---|
| Design documents (pre-implementation) | Security Auditor, Data Architect, New Engineer, Ecosystem Context Reviewer |
| Design documents (post-implementation / live system) | Add Incident Commander, Observability Champion |
| Operational docs / runbooks | Incident Commander, New Engineer |
| Security-sensitive changes | Security Auditor |
| Features introducing or depending on a new data model | Add Data Architect |
| Features with auto-refresh / polling / ops surfaces | Add Incident Commander, Observability Champion |
| PRs touching interfaces used by external systems | Add Ecosystem Context Reviewer |
| Services with diagnosability gaps (limited logging/metrics) | Add Observability Champion |
| Skill files (SKILL.md, REGRESSION.md, personas/*.md) | Skill-Craft Reviewer |
| Onboarding / first-time-reader docs | New Engineer |

To bias the selection for your team or domain, fork this skill into `.claude/skills/reviewer-personas/` and edit the table. Archetypes are starting points — they get sharper as you record real review-catches against them.

---

## Dispatch Protocol

1. **Selection.** Match artifact type to the selection table. Read only the targeted `personas/<slug>.md` files.

2. **Dispatch.** For each selected persona, call the `Agent` tool with:
   - `subagent_type: general-purpose`
   - `description`: short persona label (e.g., "Security Auditor — Trust boundaries")
   - `prompt`: the template below with the persona definition and artifact reference filled in

3. **Parallelism.** Call up to 4 concurrent agents. Batch into waves for larger sets.

4. **Context.** Pass artifact by reference (absolute path or `gh pr diff <n>` instruction). The sub-agent reads the artifact itself — do not paste inline.

5. **Aggregate.** Collect all YAML findings. Build a consolidated report (format below).

6. **Triage.** Classify each finding: **Act on** / **Noted** / **Dismiss**.

7. **Run Post-Cycle Update Protocol.**

### Dispatch prompt template

```
You are reviewing <artifact_ref> through the lens of <Persona Name>.

PERSONA DEFINITION (verbatim — do not paraphrase):
<paste full contents of personas/<slug>.md>

ARTIFACT: <absolute path | gh pr diff <n> | wiki URL>

OUTPUT: YAML only. No prose outside the YAML block.

persona: <name>
findings:
  - severity: blocker|must_fix|nit|signal|praise
    location: <section / line / thread ref>
    finding: <one sentence>
    rationale: <one sentence tied to a pushback trigger>
    trigger_ref: <which pushback trigger fired>
```

Silence on items this persona does NOT cover.

### Fallback (sub-agents unavailable)

Role-play personas inline **sequentially** and emit: `[REVIEW MODE: inline — sub-agent dispatch unavailable]`. Output format unchanged.

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

Then: "Was there a class of issue this cycle that no current persona would catch? If so, draft a new persona using `templates/persona-stub.md`."

Update the relevant `personas/<slug>.md` file. Set the `Last updated` line with a one-line reason. Commit alongside the artifact you just reviewed.

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
