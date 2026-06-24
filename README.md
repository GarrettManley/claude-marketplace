# garrettmanley/claude-marketplace

A Claude Code plugin marketplace. Twelve capability-bundled plugins for cross-project use — dev hygiene, evidence-grounded research, local LLM orchestration, Windows tooling, autonomous maintenance, AI app development, documentation craft, multi-lens review, git workflow, continuous learning, and a TTRPG narrative framework.

MIT licensed; portions adapted from [`affaan-m/everything-claude-code`](https://github.com/affaan-m/everything-claude-code) (see [NOTICE](NOTICE)).

## Plugins

| Plugin | Category | Purpose |
|--------|----------|---------|
| `discipline` | Hygiene | TODO+issue enforcement, frontmatter lint, plan validation, spec-code drift checker, fact-forcing edit gate, checkpoint tooling, council + session-handoff skills |
| `evidence` | Research | Citation-seeker, truth-seeker, HMAC override token framework, scope-binding scaffold, secret-scan PreToolUse hook |
| `orchestration` | Local LLM | Reasoning/Tooling tier model defs (llama-server), local-orchestrator handoff skill, horizon-scanning for SOTA small models |
| `windows` | Tooling | PowerShell allowlist patterns, PS5.1 vs PS7 routing tree, common Windows-isms (CRLF, BOM, `$env:`, path separators) |
| `stewardship` | Automation | Drift-check runner, morning-briefing template, Task Scheduler registration helper, auto-memory housekeeping |
| `agentic` | AI apps | Meta-overlay over claude-api / agent-sdk-dev / mcp-server-dev with opinionated defaults: latest model IDs, prompt-caching, eval discipline |
| `aether` | Narrative | TTRPG framework hooks + 6 skills + classifier-regression agent; hooks no-op outside framework-shaped repos, safe to enable globally |
| `docs` | Documentation | tech-writing (Google Tech Writing rules), mermaid-diagram (brand palette, renderer-agnostic fencing), design-document |
| `review` | Review | Dispatch sub-agent reviewers against docs/PRs/work items using sixteen archetype agents; SessionStart nag for un-reviewed artifacts |
| `retrospective` | Discipline | Plan-retrospective cycle — ExitPlanMode marker drop, SessionStart nag, retro-authoring skill |
| `git` | Workflow | Conventional Commits formatting (resists common CI-guard failures) + PR creation that detects remote host (GitHub / Azure DevOps / GitLab) |
| `learning` | Learning | Atomic instinct storage, project-scoped observation hooks (default-off), `/analyze-observations` review report |

Each plugin ships its own README under `plugins/<name>/README.md` with full component, hook, and configuration detail. [`plugins/discipline/README.md`](plugins/discipline/README.md) is the most thorough.

## Install

```bash
# Add this marketplace (in Claude Code)
/plugin marketplace add garrettmanley/claude-marketplace

# Enable the plugins you want
/plugin enable discipline@garrettmanley
```

Or edit `~/.claude/settings.json`:

```json
{
  "enabledPlugins": {
    "discipline@garrettmanley": true
  }
}
```

This is a public marketplace — no authentication is required to add it or install any plugin. `/plugin marketplace add garrettmanley/claude-marketplace` resolves the public GitHub repo over HTTPS with no credentials.

### Requirements

Most plugins ship Python hooks (PreToolUse / PostToolUse / SessionStart) and run them through [**uv**](https://docs.astral.sh/uv/) (`uv run`). uv is therefore the one prerequisite for the Python-backed hooks — and the `git` commit-message validator — to fire. It is the same `uv` command on Windows, macOS, and Linux (sidestepping the `python` vs `python3` vs `py` split) and resolves, or installs, a suitable Python automatically. Install it once: <https://docs.astral.sh/uv/getting-started/installation/>. Shell hooks additionally need `bash` on `PATH` (Git Bash on Windows). Plugins with no Python hooks work without uv.

### Optional dependency

The `git` plugin's commit-message validator parses an optional rules file. If [PyYAML](https://pypi.org/project/PyYAML/) is installed it uses it; otherwise it falls back to a built-in stdlib parser (key/value pairs and single-level lists) and prints a one-line notice. Installing PyYAML (`pip install pyyaml`) is an accelerator, not a requirement — no plugin hard-depends on it.

## Archetype templates

Per-project `.claude/settings.local.json` snippets in `templates/`:

| Template | Enables |
|----------|---------|
| `web-dev.json` | discipline, windows |
| `research.json` | discipline, evidence, orchestration, windows |
| `narrative.json` | discipline, orchestration, aether, windows |
| `scripting.json` | discipline (lite), windows |
| `agentic.json` | discipline, evidence, agentic, windows |

Copy the relevant template into a new project's `.claude/settings.local.json` to inherit the standard plugin combo for that project type.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — marketplace layout, the plugin model, and how hooks/skills/agents compose.
- [`docs/plugin-authoring.md`](docs/plugin-authoring.md) — how to add or modify a plugin in this repo.
- [`docs/testing-strategy.md`](docs/testing-strategy.md) — the test approach and coverage expectations for plugin Python.
- [`docs/release-process.md`](docs/release-process.md) — how versions are cut and released.
- [`docs/adr/`](docs/adr/) — architectural decision records (structure, hook vendoring, orchestration tiers, evidence HMAC, context routing, release policy, launch).
- [`docs/skill-index.md`](docs/skill-index.md) — generated index of every skill and agent across the marketplace (regenerate with `python3 ci/gen-skill-index.py --write`; `verify.sh` fails on drift).
- [`docs/plugin-schema-gotchas.md`](docs/plugin-schema-gotchas.md) — plugin manifest validator gotchas. Read before editing any `plugin.json`.

Repo-level governance:

- [CONTRIBUTING.md](CONTRIBUTING.md) — contributor guide and maintainer pre-merge gate.
- [LICENSE](LICENSE) — MIT.
- [NOTICE](NOTICE) — third-party attributions (adapted from `affaan-m/everything-claude-code`).
- [SECURITY.md](SECURITY.md) — security policy and how to report a vulnerability.
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — community expectations.

## Contributing

After cloning, wire the committed pre-commit hooks:

```bash
git config core.hooksPath .githooks
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contributor guide and maintainer pre-merge gate.

## License

MIT — see [LICENSE](LICENSE). Portions are adapted from [`affaan-m/everything-claude-code`](https://github.com/affaan-m/everything-claude-code) (MIT); attributions are recorded in [NOTICE](NOTICE).
