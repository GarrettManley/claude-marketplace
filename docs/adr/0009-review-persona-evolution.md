---
status: active
author: Garrett Manley
created: 2026-06-25
diataxis: reference
---

# 0009. Automate the review post-cycle update protocol with `/review-evolve`

## Status

Accepted

## Context

The `review` plugin documents a **Post-Cycle Update Protocol** (`reviewer-personas/SKILL.md`,
`README.md`): after each review cycle, record per participating archetype what it *Caught*,
*Missed*, or *Hallucinated*, then hand-edit the `**Pushback triggers:**` block of the relevant
`agents/<name>.agent.md` and bump its `**Last updated:**` line. Nothing assisted or enforced this,
so in practice it rarely ran — the archetype library did not measurably sharpen over time, despite
that being its stated value.

This mirrors the gap the `learning` plugin closed for instincts with its Claude-driven
`detect`/`synthesize` commands: the durable lesson there is **split the work** — a command markdown
holds the *judgment* (Claude reasons over context and authors candidates), and a small, fully-tested
Python script holds the *mechanical apply* (validate, write). We reuse that split here.

## Decision

Ship `/review-evolve <slug>`, backed by `plugins/review/scripts/review_cli.py` (the `evolve`
subcommand) and `persona.py` (parse/validate/diff helpers).

1. **Derive catches from the in-context report — no ledger.** The participating personas and their
   Caught/Missed/Hallucinated buckets are read from the consolidated review report already present
   in the conversation (its Triage section). An earlier design wrote a per-cycle
   `.claude/reviews/catches/<slug>.json` ledger; it was rejected as ceremony — a second artifact the
   report already supplies.

2. **Full-persona rewrite with mechanical structural validation.** Claude authors a complete
   replacement persona body; `review_cli.py` validates it before writing — frontmatter has
   `name`/`description`/`tools`, the `name` matches the target filename stem, and the four required
   sections (`**Pushback triggers:**`, `**NOT covered**`, `**Severity rubric:**`,
   `**Last updated:**`) are present. The batch is rejected whole if any file fails, so a typo cannot
   half-write. Frontmatter is parsed with stdlib regex (column-0 keys only, so a `description: |`
   block scalar parses correctly) — no PyYAML dependency.

3. **Project-local target by default.** The ingester writes to `.claude/agents/` (cwd-relative) by
   default — adopter-safe, and it never resolves to the read-only plugin install cache. The
   marketplace maintainer passes `--agents-dir plugins/review/agents/` explicitly to sharpen the
   *shipped* library. This honors `reviewer-personas/SKILL.md`'s guidance that adopter refinements
   stay project-local.

4. **Dry-run + git as the safety model — no snapshot.** Dry-run (a unified diff per persona) is the
   default; `--apply` atomic-writes (tempfile + `os.replace`). Because personas are git-tracked repo
   source, `git checkout -- <agents-dir>` *is* the restore — unlike `learning`, whose instinct stores
   live in an untracked data root and therefore need a `.snapshots/` backup. `--apply` must run on a
   clean target tree (a mid-batch I/O failure can leave earlier files written; git recovers them).

5. **New-archetype scaffolding deferred.** When a cycle surfaces a class of issue no archetype would
   catch, that is a coverage gap, not a refinement. Scaffolding a new persona from
   `templates/persona-stub.md` is out of scope; the ingester hard-rejects an ingest targeting a
   non-existent persona, and a follow-up issue tracks the capability.

## Consequences

**Positive**

- The post-cycle protocol now has a single entry point (`/review-evolve`) that both *prompts* the
  judgment to happen and removes the mechanical, error-prone hand-edit — the archetype library can
  actually sharpen across cycles.
- Structural validation makes malformed persona edits impossible to commit through the command.
- This is the `review` plugin's first `scripts/` + `tests/` directory, establishing its testing
  precedent (≥90% coverage, per the repo gate).

**Negative / mitigations**

- The judgment (deciding what to refine from the catches) stays manual — the automation covers the
  apply, not the reasoning. Mitigation: the command markdown encodes the Missed→trigger /
  Hallucinated→narrow heuristics so the reasoning is guided, not unaided.
- Full-persona rewrite carries a larger validation surface than a surgical block edit would.
  Mitigation: the whole-batch-or-nothing validation plus dry-run diff keeps the blast radius
  visible and recoverable.

Cross-references: ADR-0008 (root CHANGELOG — the program-level entry for this work is curated
there, not by `ci/release.py`); the `learning` plugin's `detect`/`synthesize` commands (the
command=judgment / script=mechanical precedent).
