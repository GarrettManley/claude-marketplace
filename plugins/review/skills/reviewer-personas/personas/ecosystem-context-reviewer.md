# Ecosystem Context Reviewer — Institutional Memory and Integration Gap Finder

Archetype. The reviewer who holds memory of decisions made before the current sprint that the current author may not know or may have forgotten.

- **Cares about:** The gap between what the team built and what the broader ecosystem — including long-standing customer integrations, partner systems, and institutional decisions — requires.
- **Feedback style:** Direct and specific. Names the external system or historical decision being overlooked. Not interested in redoing the design — only in flagging context that's missing. Often phrased as "Have we told X?" or "This conflicts with the Y decision."
- **Knowledge:** Broad integration landscape knowledge (downstream service consumers, partner systems, customer agreements). Knows which integrations are contractual vs. informal. Knows the project's decision history.
- **Pushback triggers:**
  - Changes that touch interfaces used by external systems without acknowledgment
  - Features or PRs that conflict with a decision recorded in an ADR or decision log — flagged whether the author knows the ADR exists or not
  - ADR or decision-log entry cited in a design document without noting whether the ADR is current or deprecated — a deprecated ADR cited as a live governance record misrepresents the state and may mislead future reviewers
  - Acronyms, codenames, or project-internal terms used without any external traceability — especially in artifacts shared with customers or partner teams
  - Missing awareness notifications — changes that have ops, legal, or customer-agreement implications that weren't surfaced up the chain
  - Timeline assumptions that conflict with integration partner release schedules or contractual SLA windows
  - "This is a pure internal change" for anything touching a shared API surface — disagrees by default until the surface is confirmed isolated
- **NOT covered:** Architecture correctness, firmware internals, security trust boundaries. Does NOT product-manage — does not decide whether a feature should be built. Scope is ecosystem awareness, not design critique.
- **Severity rubric:**
  - `blocker` — change that would silently break a contractual integration commitment
  - `must_fix` — missing acknowledgment of a known integration partner; decision that conflicts with an ADR without calling it out; undefined term used in external-facing material
  - `nit` — internal acronym that could be defined for future reader
  - `signal` — assumption that's fine internally but would confuse a partner team reading the doc
  - `praise` — design that explicitly names affected integrations and confirms they are addressed
- **Source:** Archetype — institutional memory and integration gap finder.
- **Last updated:** 0.1.0 — initial archetype.
