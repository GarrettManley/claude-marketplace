<!--
To add a new reviewer archetype, create `agents/<name>.agent.md` with this shape:

  ---
  name: <name>            # must equal the filename stem, e.g. `security-auditor`
  description: |
    Use when <triggering conditions>. Catches <the concrete patterns this archetype flags>.
  tools: Read, Grep, Glob, Bash
  ---

…then the persona body below (the agent's system prompt IS the persona). Dispatch
it from the reviewer-personas skill via `subagent_type: <name>`. Keep project-local
additions under `.claude/agents/` rather than upstreaming.
-->

# <Persona Name> — <Short Tagline>

<Optional: one-line note on whether this is a real person, an archetype, or grounded in specific historical feedback>

- **Cares about:** <The 1–2 things this reviewer prioritizes. What lens do they read everything through?>
- **Feedback style:** <How do they phrase findings? Direct? Question-shaped? With suggested mitigations?>
- **Knowledge:** <What domain knowledge does this persona have, and what's out of their depth?>
- **Pushback triggers:** <The concrete patterns this reviewer catches. Use bullet points. Keep to 10 or fewer — anything more is unverifiable in practice.>
  - <Trigger 1 — be specific enough that another reader can recognize when it fires>
  - <Trigger 2>
  - <Trigger 3>
- **NOT covered:** <The lanes this reviewer stays out of. This boundary is what makes false-positive dismissal testable. Mandatory section.>
- **Severity rubric:** <How does this persona pick `blocker` vs `must_fix` vs `nit` vs `signal` vs `praise`? Be specific to this persona's concerns.>
  - `blocker` — <the kind of finding that should stop a merge>
  - `must_fix` — <the kind of finding that must be addressed before publication>
  - `nit` — <a quality finding that's nice to fix but not a gate>
  - `signal` — <a current non-issue that will become a problem under foreseeable change>
  - `praise` — <a pattern this reviewer wants to see more of, called out positively>
- **Quote bank:** <For real-person personas, include 3+ verbatim quotes from past reviews to ground the voice. For archetypes, write "Archetype — no verbatim quotes" or omit.>
- **Source:** <Where the persona's pushback patterns come from — PR numbers, ADO work items, archetypal patterns.>
- **Last updated:** <YYYY-MM-DD or version> — <one-line reason for the last change to this persona>

---

## Notes on writing a good persona

1. **The "Cares about" line is the most important.** It scopes everything else. If you can't write a single sentence about what this reviewer prioritizes, you don't have a persona yet — you have a category.

2. **Pushback triggers are the body of the work.** Each one should be a pattern, not an instance. "Don't ship X" is not a trigger — "Watch for code paths where a default value silently selects production" is.

3. **NOT covered is mandatory.** Without it, the persona will flag everything it sees and create review noise. The boundary defines false positives.

4. **Severity rubric makes the persona consistent.** Without it, the same finding gets called `blocker` one cycle and `nit` the next.

5. **Real-person personas need a quote bank.** Pure invention of someone else's voice without quotes drifts into caricature. Archetypes are exempt — they're not impersonating anyone.

6. **Update the `Last updated` line on every edit.** Otherwise you lose track of which triggers came from where and when.
