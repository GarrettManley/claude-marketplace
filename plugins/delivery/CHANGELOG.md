# Changelog

All notable changes to the **delivery** plugin are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## 0.1.0 — initial release

First release. End-to-end value-delivery lifecycle:

- `deliver` skill — a project-agnostic plan → adversarial plan review → subagent execution →
  completion gate → adversarial code review → land → retrospective spine, composing `superpowers`,
  `docs`, and `retrospective` skills.
- `/deliver` command — thin entry taking an optional `<work-target>`.
- Per-repo binding of the `plan-writer` / `doc-cluster` / `edit-checklist` / `land-policy` slots via
  `<repo>/.claude/delivery.local.md`, with generic defaults and best-effort availability fallbacks.
- Resolved-slot echo at the start of every run for an observable execution path.
