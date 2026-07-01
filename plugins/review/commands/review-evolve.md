---
name: review-evolve
description: Automate the reviewer-personas Post-Cycle Update Protocol — turn a cycle's Caught/Missed/Hallucinated catches into refined archetype persona files.
---

# /review-evolve <slug>

Refine the archetype personas that participated in a review cycle, so the library sharpens over time. The intelligence is *yours*: you read the cycle's catches and each participating persona, then author a refined full-persona body. The script only validates and writes what you author. New-archetype scaffolding is **out of scope** (deferred) — this command only refines existing personas.

## Steps

**1. Recover the cycle's catches from the review report in this conversation.** The `reviewer-personas` cycle for `<slug>` just produced a consolidated report in context (per-persona YAML findings + a Triage section). From it, derive per participating persona:
- **Caught** = findings under Triage **Act on**.
- **Hallucinated** = findings under Triage **Dismiss** (inapplicable to this artifact).
- **Missed** = what human review or another persona caught that this persona should have flagged.

If no such report is in context, run `reviewer-personas` on the artifact first. (The participating personas are also listed in `.claude/reviews/completed/<slug>.json` if you need to confirm the set.)

**2. For each persona with a Missed catch, or a Hallucinated catch that recurred**, read its current definition at `plugins/review/agents/<name>.agent.md` and author a refined full rewrite:
- **Missed** → add a precise pushback trigger so the gap is caught next time.
- **Hallucinated** → tighten or qualify the trigger that misfired (or add a fact-check caveat), and sharpen the NOT-covered boundary if the persona strayed out of lane.
- Preserve the frontmatter (`name`, `description`, `tools`) and all required sections (`**Pushback triggers:**`, `**NOT covered**`, `**Severity rubric:**`, `**Last updated:**`).
- **Bump** the `- **Last updated:**` line with a one-line reason citing the slug, e.g. `- **Last updated:** 1.2.0 — added telemetry-encoding trigger (missed in <slug> cycle).` (The ingester warns if you forget.)

Write each rewritten file to a temp dir — `$TMPDIR/review-evolve/` (POSIX) / `$env:TEMP\review-evolve\` (Windows) / the session scratchpad — naming each file `<name>.agent.md`.

**3. Review (dry-run), then apply** on a **clean git tree** — `--apply` overwrites tracked source, so uncommitted persona edits would be lost. As the marketplace maintainer sharpening the shipped library, target `plugins/review/agents/` explicitly; as an adopter, omit `--agents-dir` to refine your project-local `.claude/agents/`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/review_cli.py" evolve --ingest "$TMPDIR/review-evolve" --agents-dir plugins/review/agents
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/review_cli.py" evolve --ingest "$TMPDIR/review-evolve" --agents-dir plugins/review/agents --apply
```

The dry-run prints a unified diff per persona; `--apply` atomic-writes them. The ingester rejects the whole batch if any file is structurally invalid; a non-existent persona is deferred (not rejected) — so only a structurally broken file can half-write. Restore is `git checkout -- <agents-dir>`.

**4. Commit** the refined personas alongside the artifact you reviewed (scope `docs(review):` — persona-content edits do not bump the plugin version).

## Notes

If a cycle surfaces a **coverage gap** — a class of issue *no* current archetype would catch — scaffold a new archetype instead of refining an existing one:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/review_cli.py" scaffold <name> --agents-dir plugins/review/agents
# review the printed skeleton, then re-run with --apply
```

`scaffold` writes a structurally-valid `agents/<name>.agent.md` skeleton (real frontmatter + the required sections with `<placeholders>`); it refuses to clobber an existing persona. Fill its pushback triggers from the catch, then commit. As the maintainer, target `plugins/review/agents`; adopters omit `--agents-dir` to scaffold into project-local `.claude/agents/`. See `skills/reviewer-personas/templates/persona-stub.md` for the full guidance on writing a good persona.
