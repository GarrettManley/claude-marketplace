# retrospective changelog

## 1.2.0

### Features
- add /pre-plan-brief to surface prior retro findings

# Changelog

All notable changes to the **retrospective** plugin are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres
to [Semantic Versioning](https://semver.org/).

## 1.1.0 — 2026-06-24

- Added **plan-completion** skill: structured plan-completion verification that gates a plan as done only when its acceptance criteria are met.
- Added a soft completion-gate SessionStart hook (`plan_completion_check.py`) that surfaces incomplete plans at session open without hard-blocking.
- Manifest enriched with `$schema`, `homepage`, `repository`, `license`, `keywords`, and category metadata.

## 1.0.0 — initial public release

First public release. Plan retrospective discipline: a self-contained cycle of marker-drop (exit plan mode), session-start nag, and a retro-authoring skill.
