# learning@garrettmanley

Continuous-learning toolkit for Claude Code: atomic instinct storage with YAML+markdown files, project-scoped tool-use observation hooks (default-off), and a pattern-review report. Lets you build a personal library of learned behaviors that persist across sessions and machines.

Adapted from [`affaan-m/everything-claude-code`](https://github.com/affaan-m/everything-claude-code/tree/4774946db57a072f9b878f233a80f2ec6f5ac342/skills/continuous-learning-v2) at `4774946d` (MIT licensed). The original ships all three phases as one 706-line script; this port splits them into phased, reviewable pieces.

## Install

```
/plugin marketplace add garrettmanley/claude-marketplace
/plugin enable learning@garrettmanley
```

Enabling the plugin alone records nothing. The observation hook is gated off until you set the environment variables described in [Configuration](#configuration).

## Components

| Component | Type | Trigger / Default state |
|-----------|------|------------------------|
| `scripts/observe.py` via `run_with_flags.py` | PreToolUse + PostToolUse hook | **Off** — requires `LEARNING_HOOK_PROFILE=strict` AND `LEARNING_OBSERVE=on` |
| `/analyze-observations` | Command | Available; reads `observations.jsonl` |
| `/instinct-export` | Command | Available; takes `<output-path>` argument |
| `/instinct-import` | Command | Available; takes `<file-path>` argument |
| `/instinct-status` | Command | Available; no arguments |

### Commands

| Command | Description |
|---------|-------------|
| `/analyze-observations` | Report tool-use patterns from the current project's `observations.jsonl`; user decides which patterns to codify as instincts |
| `/instinct-export <output-path> [--scope=global\|project]` | Export the union of `personal/` and `inherited/` instincts to a single YAML file |
| `/instinct-import <file-path> [--scope=global\|project]` | Import a YAML instinct file into the `inherited/` directory of a scope |
| `/instinct-status` | Show all instincts grouped by domain, with confidence bars |

## Usage

**Check what instincts are active:**

```
/instinct-status
```

**Export instincts for backup or transfer:**

```
/instinct-export ~/my-instincts.yaml --scope=global
```

**Seed instincts from a file (another machine, a teammate, or your own backup):**

```
/instinct-import ~/my-instincts.yaml --scope=global
```

Imported instincts land in `inherited/`. The `personal/` directory is reserved for Phase 2 auto-creation.

**Enable observation capture, then review patterns:**

```bash
export LEARNING_HOOK_PROFILE=strict
export LEARNING_OBSERVE=on
# ... run your Claude Code session ...
```

Then run:

```
/analyze-observations
```

Read the report, decide which patterns warrant an instinct, write the YAML file manually, and import it via `/instinct-import`.

## Storage layout

```
%LOCALAPPDATA%\claude-marketplace\learning\     (Windows)
~/.local/share/claude-marketplace/learning/     (POSIX)
├── instincts/
│   ├── personal/      (auto-learned — Phase 2, not yet implemented)
│   └── inherited/     (manual /instinct-import)
├── evolved/           (Phase 3, not yet implemented)
└── projects/
    └── <12-char-hash>/
        ├── instincts/
        │   ├── personal/
        │   └── inherited/
        └── observations.jsonl   (written when LEARNING_OBSERVE=on)
```

The 12-character project hash is derived in priority order:

1. `CLAUDE_PROJECT_DIR` env var (hashed)
2. `git remote get-url origin` (hashed — same repo on different machines maps to the same ID)
3. `git rev-parse --show-toplevel` (machine-specific)
4. CWD hash
5. Literal `"global"`

Override the entire data root with `LEARNING_DATA_ROOT=<path>`.

## Instinct file format

Each instinct is a YAML-frontmatter + Markdown file:

```yaml
---
id: prefer-edit-over-write
trigger: editing an existing file
confidence: 0.9
domain: file-editing
source: manual
---

# Prefer Edit over Write for existing files

## Action

Use the Edit tool for targeted changes to existing files rather than rewriting
the full file, unless the file is new or under 100 lines.

## Evidence

Reduces diff noise and lowers the risk of accidentally clobbering unrelated content.
```

Required frontmatter fields: `id`, `trigger`, `confidence` (0.0–1.0), `domain`, `source`. Optional: `source_repo`.

A multi-instinct export file concatenates individual instinct blocks separated by `---` lines.

## Observation schema

When observation is enabled, each tool invocation appends one JSON line to `observations.jsonl`:

```json
{
  "timestamp": 1717977600.123,
  "phase": "pre|post",
  "tool_name": "Edit",
  "tool_input": {"file_path": "/foo/bar.py"},
  "session_id": "...",
  "tool_use_id": "toolu_01abc...",
  "tool_response": {}
}
```

`tool_use_id` and `tool_response` are optional. `tool_response` only appears on `post` records.

## Configuration

| Variable | Values | Effect |
|----------|--------|--------|
| `LEARNING_HOOK_PROFILE` | `minimal` \| `standard` (default) \| `strict` | `strict` is required for observation hooks to fire |
| `LEARNING_OBSERVE` | `on` \| `1` \| `true` \| `yes` \| `enabled` | Must be set to actually write observations; no-op otherwise |
| `LEARNING_DISABLED_HOOKS` | comma-separated hook IDs | Silently disables named hooks regardless of profile |
| `LEARNING_DATA_ROOT` | path | Override the default data directory |

The observation hook is gated by two independent controls that must both be open:

1. `LEARNING_HOOK_PROFILE=strict` — allows the `run_with_flags.py` wrapper to invoke `observe.py`
2. `LEARNING_OBSERVE=on` — tells `observe.py` to write records; without this it exits 0 immediately

Either gate alone keeps the plugin completely silent.

### Disabling hooks individually

```bash
# Disable both observation hooks for one session
export LEARNING_DISABLED_HOOKS=learning:pre-tool:observe,learning:post-tool:observe

# Disable via profile (wrapper short-circuits before observe.py loads)
export LEARNING_HOOK_PROFILE=standard

# Runtime no-op even if profile is strict
export LEARNING_OBSERVE=off
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `/analyze-observations` reports "0 records" | Set `LEARNING_HOOK_PROFILE=strict` and `LEARNING_OBSERVE=on`, then run a Claude Code session before analyzing |
| `/instinct-import` fails with "Missing required field" | Check the YAML file has all required frontmatter: `id`, `trigger`, `confidence`, `domain`, `source` |
| `/instinct-status` shows no instincts | No instincts have been imported yet; use `/instinct-import` to seed from a YAML file |
| Observation hook fires but `/analyze-observations` shows the wrong project's data | `CLAUDE_PROJECT_DIR` is not set; the project ID fell back to a git or CWD hash. Set `LEARNING_DATA_ROOT` to a fixed path to avoid ambiguity |

## Cross-platform notes

- **Windows:** data root is `%LOCALAPPDATA%\claude-marketplace\learning\`. The hook wrapper (`run_with_flags.py`) uses `importlib` for in-process Python dispatch (no extra process spawns). Shell scripts (`.sh`, `.bash`) fall back to `bash -c` via subprocess — Git Bash must be on `PATH`.
- **macOS / Linux:** data root is `~/.local/share/claude-marketplace/learning/`. No platform-specific differences in behavior.
- This plugin ships **no** `init.sh` / `init.ps1` — no scaffolding step is required. The data directory is created on first use.

## What ships in future phases

- **Phase 2b:** automated instinct creation from frequency-based patterns in `observations.jsonl`
- **Phase 2c:** LLM-driven pattern detection (correction patterns, preference signals)
- **Phase 3:** `/evolve` clustering, `/promote` (project→global), `/prune` (confidence-decay)
