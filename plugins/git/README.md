# git@garrettmanley

Git workflow skills that cover the two most common Claude Code friction points: writing commit
messages that actually pass CI guards the first time, and creating pull requests against whichever
host the repo points at — without hardcoding a CLI.

Both skills follow the [Conventional Commits](https://www.conventionalcommits.org/) spec as the
universal baseline and document the failure modes that most CI guards reject. Neither hook into
git; they write and validate — enforcement stays with your existing tooling (commitlint, pre-commit,
GitHub Actions).

## Install

```
/plugin marketplace add garrettmanley/claude-marketplace
/plugin enable git@garrettmanley
```

No global machine configuration required. The optional project-local rule file (see **Init / Setup**
below) is the only per-project artifact.

## Components

| Component | Type | Trigger / purpose |
|-----------|------|-------------------|
| `commit-message` | Skill | Use when writing, formatting, or fixing a git commit message, or when a commit fails a project's commit-message CI check. Ships a `--validate` mode backed by `validate.sh` + `validate.py`. |
| `pr-create` | Skill | Use when the user asks to create a pull request, open a PR, or submit changes for review. Detects the remote host (GitHub, Azure DevOps Repos, GitLab) and uses the matching CLI. |

No hooks ship with this plugin.

## Init / Setup

The init scripts scaffold an optional project-local rule file
(`.claude/commit-message-rules.yaml`) from the bundled `rules.example.yaml`. Run from inside
a git repo.

**macOS / Linux:**

```bash
bash ~/.claude/plugins/cache/garrettmanley/git/1.0.0/scripts/init.sh
```

**Windows (PowerShell 7+):**

```powershell
pwsh ~/.claude/plugins/cache/garrettmanley/git/1.0.0/scripts/init.ps1
```

Both scripts are idempotent: a second run does nothing if `.claude/commit-message-rules.yaml`
already exists. Use `--force` to overwrite, `--quiet` to suppress output.

```bash
# Force overwrite
bash .../init.sh --force

# Silent (for scripted environments)
bash .../init.sh --quiet
```

The scaffolded file is an annotated starting point — edit `header.pattern` and any
`trailers` to match your project's CI guard regex before committing.

**Note:** running outside a git repo is a no-op; the scripts exit 0 with a `skipped` message.

## Usage

### commit-message

Invoke the skill by describing what changed and why; the skill assembles a Conventional Commits
header and body.

Ask Claude:
```
/commit-message  — what changed and why...
```

Or simply describe the work in natural language; the skill triggers on commit-message intent.

**Validate an existing commit:**

```bash
# Validate HEAD (default rule resolution: project-local → bundled example)
bash ~/.claude/plugins/cache/garrettmanley/git/1.0.0/skills/commit-message/scripts/validate.sh HEAD

# Validate a specific SHA
bash ~/.claude/plugins/cache/garrettmanley/git/1.0.0/skills/commit-message/scripts/validate.sh abc1234

# Use an explicit rule file
bash ~/.claude/plugins/cache/garrettmanley/git/1.0.0/skills/commit-message/scripts/validate.sh HEAD \
  --rules .claude/commit-message-rules.yaml
```

**Rule resolution order (validator):**

1. `--rules <path>` if provided
2. `<git-root>/.claude/commit-message-rules.yaml` (project-local)
3. `rules.example.yaml` bundled with the skill (Conventional Commits defaults only)

**Exit codes:** `0` = valid, `1` = validation failed (diagnostic on stderr), `2` = usage / infrastructure error.

**Rule file format:**

```yaml
header:
  pattern: "^(feat|fix|docs|...)\\([^)]+\\)?: [A-Z]"  # anchors are implicit
  max_length: 72

body:
  required: true
  min_lines_before_trailer: 1

trailers:
  Tested:
    required: true
    must_contain:
      - "- How:"
      - "- Hardware:"
      - "- Test Equipment:"
```

All fields are optional; omit any section to skip that check.

### pr-create

Invoke the skill when opening a PR. The skill:

1. Runs `git remote get-url origin` to detect the host.
2. Selects the matching CLI (`gh` / `az repos pr create` / `glab mr create`).
3. Walks through a pre-flight checklist (branch pushed, no stray uncommitted changes, commit message
   passes the project's CI guard).
4. Emits the exact CLI command to run.

If the detected CLI is not installed, the skill surfaces that before proceeding — it does not fall
back silently.

| Remote URL pattern | Host | CLI |
|--------------------|------|-----|
| `github.com` | GitHub | `gh` |
| `dev.azure.com` / `visualstudio.com` | Azure DevOps Repos | `az repos pr create` |
| `gitlab.com` (or self-hosted GitLab) | GitLab | `glab mr create` |
| Other | Unsupported | Manual / web UI |

## Configuration

This plugin has no environment variables or global config files. The only per-project knob is
the optional rule file scaffolded by init:

| File | Purpose |
|------|---------|
| `<git-root>/.claude/commit-message-rules.yaml` | Project-local rule set for the commit-message validator. Overrides the bundled defaults. |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `validate: warning: PyYAML not installed; using minimal fallback parser` | `validate.sh` auto-provisions PyYAML via `uv run --with pyyaml`, so this warning should not appear on the normal path. It only fires if you run `validate.py` directly with a Python interpreter that lacks PyYAML — in that case install it (`pip install pyyaml`) or invoke through `validate.sh`. The stdlib fallback handles most rule files correctly regardless. |
| `validate: cannot read commit message for '<ref>'` | The ref doesn't exist or `git log` failed. Confirm the SHA is reachable: `git log --oneline -5`. |
| `gh pr create` fails with "no such remote" or auth error | The `gh` CLI needs to be authenticated against the correct host: `gh auth login`. This plugin does not handle auth. |
| `az repos pr create` returns "no default organization" | Run `az devops configure --defaults organization=https://dev.azure.com/<org> project=<project>` once per machine. |
| Rule file scaffolded but validator still uses defaults | The rule file path must be `<git-root>/.claude/commit-message-rules.yaml` exactly. Check `git rev-parse --show-toplevel` and verify the file lives under `.claude/`. |

## Cross-platform

| Concern | Detail |
|---------|--------|
| Init script | `init.sh` requires Bash; `init.ps1` requires PowerShell 7+. Both produce identical output and the same scaffolded file. |
| Validator | `validate.sh` delegates to `validate.py` via `uv run` (no project virtualenv required); `uv` must be on `PATH`. On Windows, `validate.sh` runs under Git Bash or WSL. A native PowerShell wrapper is not included — invoke via `bash` or run `validate.py` with any Python 3 directly. |
| PyYAML | Auto-provisioned by `validate.sh` (`uv run --with pyyaml`), so the real YAML parser is always used on the standard path. If you run `validate.py` directly without PyYAML installed, the stdlib fallback parser runs and emits a warning. |
| Path separator | Rule file resolution uses `git rev-parse --show-toplevel`, which returns a POSIX path on all platforms when called from Bash / Git Bash. |

## What this plugin does NOT include

- A commit-message lint hook. Use [commitlint](https://commitlint.js.org/) or a CI workflow for
  enforcement. This plugin writes messages that pass — not enforces them.
- Authentication helpers. `gh auth login`, `az login`, and `glab auth login` are per-machine
  setup steps outside this plugin's scope.

## Project-specific extensions

Both skills target the universal shape. If your project layers on additional conventions:

- **Required `Tested:` block** in commits (common for firmware or regulated systems)
- **Required work-item reference** in PR titles (`AB#<id>` for Azure Boards, `JIRA-<id>` for Jira, `#<n>` for GitHub Issues)
- **Required reviewer token** before PR creation (pairs with the `review` plugin)

Fork the relevant skill into your project's `.claude/skills/` and add the project rules. Keep a
cross-reference to the upstream skill so the universal guidance still applies.

## Pairing with the `review` plugin

If you have the `review` plugin enabled, `pr-create`'s pre-flight checklist will mention running
`/reviewer-personas` and writing the completion token before opening the PR. The completion-token
convention is what the `review` plugin's SessionStart nag listens for.
