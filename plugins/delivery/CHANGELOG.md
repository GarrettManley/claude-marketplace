# Changelog

All notable changes to the **delivery** plugin are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## 0.2.1

Fix for a hand-authoring regression at Phase A step 3, found via real `/deliver` usage.

- **Phase A step 3** ("Write the plan") previously read as a bare label naming
  `superpowers:writing-plans` rather than an explicit invocation, unlike deliver's other two
  composed-skill seams. Agents read it as descriptive prose and hand-authored plans in their own
  style, skipping writing-plans' mandatory header, per-task TDD structure, and self-review gate --
  forcing a manual re-invoke of `/writing-plans` after `/deliver` had already produced a plan. Step 3
  now explicitly invokes `superpowers:writing-plans` and follows its full contract, and carries the
  same "stop before its own execution hand-off" suppression instruction already present at the
  Phase 0 (brainstorming) and Phase B (SDD) seams, so a correctly-invoked writing-plans run doesn't
  skip deliver's own steps 4-6 (doc cluster, plan review, approval).
- **New contract test** `TestComposedHandoffsAreSuppressed` enforces that all three composed-skill
  seams (Phase 0, Phase A step 3, Phase B) carry a Stop + hand-off-suppression instruction in their
  phase text, so a future edit can't silently drop one of the three again.

## 0.2.0

Hardening pass driven by real usage (the dev-clone dogfood loop never having actually run `/deliver`
as a skill) plus a 9-agent adversarial plan review and a 2-round whole-branch code review.

- **Completion gate (step 9)** now requires fresh positive evidence (command + output + exit code,
  recorded inline under each `## Verification` criterion) rather than absence-of-error — wired into
  `superpowers:verification-before-completion`'s Iron Law and the artifact
  `retrospective:plan-completion`'s own check actually inspects.
- **Hardened gate wording** at the plan-review, completion, and code-review gates: "Only proceed when
  this gate passes" plus a concrete checklist per gate, replacing softer "resolve findings" language.
- **Worktree-freshness guard** (step 7): before live-executing in a freshly created worktree, diff its
  branch point against the local working branch and stop-and-warn on staleness rather than silently
  continuing.
- **Two-tier code review**: the whole-branch `docs:adversarial-review-code` pass (step 10) now runs at
  wider scope without a down-routed model, distinct from any down-routed per-task reviews during
  execution. Both step 7 and step 10 now refuse to synthesize a result over a failed subagent's
  missing output.
- **Hybrid landing** (step 11): when no `land-policy` is bound, delegate to the purpose-built
  `superpowers:finishing-a-development-branch` (its 4-option menu + worktree cleanup) instead of
  reinventing landing inline; an explicit `land-policy` value is still honored verbatim, unchanged.
  `subagent-driven-development`'s own internal auto-hand-off into `finishing-a-development-branch` is
  now explicitly suppressed during step 7 so `deliver`'s own steps 8-11 own that sequence, with a
  defined fallback if the suppression instruction doesn't take.
- **Dependency-manifest fix**: `plugin.json` now declares `dependencies: ["docs", "retrospective"]`,
  matching `SKILL.md`'s frontmatter.
- **New reference doc** `references/plugin-authoring.md`: the production "make-it-live" checklist
  (push → marketplace update → install → reload) and a verified, safe local dev-test mechanism
  (`claude --plugin-dir`, session-scoped, zero registry mutation) — including a documented warning
  against `marketplace add`/`remove --scope local` round-tripping on a same-named local path, which
  can delete the live marketplace registration rather than safely restoring it.
- **Phase B resumability**: step 1 now checks for an existing `superpowers:subagent-driven-development`
  ledger (`.superpowers/sdd/progress.md`) and, if found with incomplete tasks, skips straight to step 7
  rather than re-running Phase A — riding entirely on SDD's own native resume mechanism. New reference
  doc `references/resumability.md` documents what is and isn't covered (Phase B only; Phases A/C are
  not resumable; no `/recover` integration).
- **Optional Phase 0 — Design**: when the work-target isn't concrete enough to plan from yet (no
  existing spec, not a directory/issue-reference, prose doesn't name a concrete file/function to
  change, and the user hasn't said it's understood), `deliver` runs `retrospective:pre-plan-brief` and
  `superpowers:brainstorming` first to produce an approved design spec before Phase A. Skip conditions
  are objective/checkable facts, not a subjective "well-understood" judgment call.
- **Optional `constitution` governance key**: a `delivery.local.md` frontmatter key pointing at a
  per-repo governance doc (code-quality/testing/UX/perf standards), fed into plan authoring and both
  review gates as binding context when bound; defaults to skip. Missing/unreadable paths warn and
  fall back to unset rather than silently proceeding as if enforced; violations are required to land
  in the same severity-tagged findings file the review gates already inspect.

## 0.1.0 — initial release

First release. End-to-end value-delivery lifecycle:

- `deliver` skill — a project-agnostic plan → adversarial plan review → subagent execution →
  completion gate → adversarial code review → land → retrospective spine, composing `superpowers`,
  `docs`, and `retrospective` skills.
- `/deliver` command — thin entry taking an optional `<work-target>`.
- Per-repo binding of the `plan-writer` / `doc-cluster` / `edit-checklist` / `land-policy` slots via
  `<repo>/.claude/delivery.local.md`, with generic defaults and best-effort availability fallbacks.
- Resolved-slot echo at the start of every run for an observable execution path.
