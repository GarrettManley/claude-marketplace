---
name: aether-doc-cluster
description: Use before starting a substantial piece of work — new feature, subsystem, or rework — to determine which engineering documents must land in the same PR. Walks the trigger taxonomy (spec / ADR / threat model / runbook / user guide / plan / retrospective) and points at the templates so nothing critical ships undocumented.
version: 0.1.0
dependencies: []
---

# Aether documentation cluster

Aether Engine work that crosses architectural, operational, or
security boundaries is held to an engineering-grade documentation
standard: code lands together with the docs an operator, reviewer,
or future contributor needs. This skill produces that cluster.

## When to invoke this skill

- Right after the brainstorming phase, before writing the spec.
- When triaging a fresh GitHub issue and deciding scope.
- When a user says "land an engineering-grade rework" — that phrase
  triggers the full cluster (#34 auth rework precedent).
- Before a PR review, to verify the cluster is complete.

If the work is a one-line bug fix, skip to the bug-fix branch below.

## The trigger taxonomy

Walk the tree top-down. Stop at the first match per branch.

```
1. Bug fix with no architectural change?
   YES -> commit message; maybe update a pitfalls/<area>.md file. STOP.
   NO  -> continue.

2. Trivial (1–3 files touched, no tests beyond unit, no public API
   change)?
   YES -> plan optional; commit message + retrospective comment in the
          commit body. STOP.
   NO  -> continue.

3. Introduces a numbered-spec-track design (new feature or subsystem)?
   YES -> Spec REQUIRED at docs/engineering/NNN-<slug>.md.
          NNN = next free number (max+1 across NNN-*.md). Continue (4).
   NO  -> Plan REQUIRED at docs/engineering/plans/YYYY-MM-DD-<slug>-plan.md.
          Skip to (8).

4. Two or more viable architectural alternatives with long-term
   consequences (transport, identity, runtime model, persistence
   layer)?
   YES -> ADR REQUIRED per non-trivial decision at
          docs/engineering/adrs/ADR-NNNN-<slug>.md (four-digit,
          monotonic).
   NO  -> Spec body's Decisions section absorbs rationale; no separate
          ADR.

5. Security-adjacent (auth, OIDC, TLS, secrets, audit logs, access
   control, transport, file permissions, sandbox boundaries)?
   YES -> Threat model REQUIRED at
          docs/engineering/security/<spec-number>-<component>-threat-model.md
          (full STRIDE). Optional companion security analysis at
          docs/engineering/security/<spec-number>-<component>-security-analysis.md.
   NO  -> Skip threat model.

6. Operators run this in production (start, monitor, stop, recover)?
   YES -> Runbook REQUIRED at docs/runbooks/<feature>.md.
   NO  -> Skip runbook.

7. End users (players, GMs, integrators) interact directly?
   YES -> User guide REQUIRED at docs/user/<feature>.md.
   NO  -> Skip user guide.

8. Plan REQUIRED for any non-trivial work. Must reference the spec
   (if any) and contain Value Justification + Retrospective per the
   plan-writing rules. Use the aether-plan-writer skill.

9. Retrospective REQUIRED before declaring done. Lives in the plan's
   ## Retrospective section. Must include `Closes #N`, `Updates #N`,
   or `Follows up #N`. The plan_issue_check.py hook enforces.
```

## Required cluster shapes

| Trigger answer | Required docs |
| --- | --- |
| Bug fix | commit message; pitfall update if knowledge gained |
| Enhancement (non-trivial, no spec) | plan + retrospective |
| Spec-track feature | spec + plan + retrospective; ADR(s) per (4); runbook per (6); user guide per (7) |
| Spec-track + security-adjacent | all of the above + threat model (and usually a security analysis) |

## Template index

All under `docs/engineering/templates/`:

| Template | Use for |
| --- | --- |
| `spec-template.md` | Numbered specs (`NNN-<slug>.md`) |
| `plan-template.md` | Plans (`YYYY-MM-DD-NNN-<slug>-plan.md`) — start here, then add the Value Justification block via `aether-plan-writer` |
| `arch-doc-template.md` | Architecture docs (subsystem-level) |
| `runbook-template.md` | Operational MOPs (`docs/runbooks/`) |
| `tutorial-template.md` | Tutorials (`docs/user/tutorial-<slug>.md`) |
| `readme-template.md` | Module READMEs |
| `glossary-entry-template.md` | Glossary additions |

ADRs and threat models do not have committed templates yet; copy
shape from `docs/engineering/adrs/ADR-0008-manual-provider-composition.md`
and `docs/engineering/security/manual-gm-threat-model.md` respectively.

## Worked example — spec 041 (Manual GM Mode)

Spec 041 is a new `LLMProvider` (subsystem-level), security-adjacent
(file permissions on operator I/O channel), operator-run (Monitor
stream), and user-facing (Claude operating as GM). Full cluster:

```
docs/engineering/041-manual-gm-mode.md                            # spec
docs/engineering/adrs/ADR-0008-manual-provider-composition.md     # ADR — provider selection
docs/engineering/adrs/ADR-0009-manual-gm-io-channel.md            # ADR — I/O channel design
docs/engineering/security/manual-gm-threat-model.md               # threat model
docs/engineering/plans/2026-05-07-041-manual-gm-plan.md           # plan + retrospective
docs/runbooks/manual-gm-operations.md                             # operator MOP
docs/user/gm-manual.md (updated)                                  # user-facing GM guide
```

Rationale per file:

- **Spec.** Numbered design doc — new subsystem.
- **ADR-0008.** Provider-selection alternatives had real long-term
  consequences (composition vs subclass vs flag).
- **ADR-0009.** I/O channel had multiple viable shapes (file polling,
  socket, stdin pipe).
- **Threat model.** File-based I/O on a multi-tenant host is
  security-adjacent (see auth rework #34 precedent).
- **Plan.** Value Justification + Retrospective + tracks issue #108.
- **Runbook.** Operators need a MOP for start/monitor/stop/recover.
- **User guide.** GMs interact with manual mode directly.

The auth rework (#34) cluster is the other canonical example and is
referenced by `feedback_engineering_grade_default.md` in user memory.

## PR checklist

Copy this into the PR description. Strike the rows that don't apply
based on the taxonomy walk above. Don't delete rows — leave them
struck so reviewers can see the deliberate decision.

```markdown
Documentation cluster:

- [ ] Spec — `docs/engineering/NNN-<slug>.md`
- [ ] ADR(s) — `docs/engineering/adrs/ADR-NNNN-<slug>.md`
- [ ] Threat model — `docs/engineering/security/<spec>-<component>-threat-model.md`
- [ ] Runbook — `docs/runbooks/<feature>.md`
- [ ] User guide — `docs/user/<feature>.md`
- [ ] Plan — `docs/engineering/plans/YYYY-MM-DD-NNN-<slug>-plan.md`
- [ ] Retrospective filled in — `Closes #N` / `Updates #N` / `Follows up #N`
```

## See also

- `aether-plan-writer` — plan-file rules (issue cite, Value
  Justification regex, retrospective close-tag).
- `aether-edit-checklist` — per-edit gates (graphs, JSDoc, eval,
  harness, TODO format) before declaring done.
- `docs/engineering/conventions.md` — canonical engineering
  conventions; per-edit checklist; plan-writing rules.
- `docs/engineering/doc-conventions.md` — frontmatter schema,
  filename rules, ADR block shape, directory map.
- `docs/engineering/issues-workflow.md` — issue label taxonomy.
- `docs/engineering/security/README.md` — threat-model and
  security-analysis filename + content conventions.
- `docs/engineering/adrs/ADR-0000-adopt-adr-convention.md` — ADR
  lifecycle (Proposed → Accepted → Superseded).
