# 0005. Machine-specific context routes to ~/.claude/context/, never to the repo

**Status:** Accepted

## Context

The `orchestration@garrettmanley` plugin needs three classes of machine-specific
information at runtime:

1. **Hardware profile** — CPU, RAM, VRAM ceiling, local runtime binary paths.
2. **Local tier definitions** — GGUF paths, VRAM figures, per-tier launch args.
3. **Operator identity** — email, timezone, persona notes.

Committing live values for any of these to a public marketplace repository creates
two problems. First, **publish safety**: real paths, hardware fingerprints, and
identity tokens would be visible in git history to anyone who installs or forks the
plugin. Second, **portability**: values that are correct for one machine silently
break setup on any other machine, so a second contributor's install would start with
wrong paths and incorrect tier VRAM limits.

ADR 0003 resolved this for tier definitions specifically. This ADR generalizes the
principle to cover all machine-specific context.

## Decision

The marketplace repo ships **generic templates only**. Machine-specific context lives
exclusively in `~/.claude/context/` and is never tracked by this repository:

| Artifact | Repo ships | Machine holds |
|----------|-----------|---------------|
| Tier definitions | `configs/tiers.json` (placeholder values) | `~/.claude/context/tiers.local.json` |
| Hardware profile | `context/hardware-profile.template.md` (placeholder values) | `~/.claude/context/hardware-profile.md` |
| Operator identity / persona | nothing | `~/.claude/context/user-persona.md` (user-authored) |

The init scripts (`scripts/init.sh` / `scripts/init.ps1`) seed the two template-backed
files on first run. Both scripts are idempotent and print `REMINDER:` lines for every
`<placeholder>` that requires a real value:

```bash
bash plugins/orchestration/scripts/init.sh
# then edit ~/.claude/context/tiers.local.json and ~/.claude/context/hardware-profile.md
```

The `inject_context.py` user-level SessionStart hook reads `~/.claude/context/*.md`
files whose frontmatter contains `always: true` and injects them into session context.
The orchestration plugin's own SessionStart hook (`inject_orchestration_context.py`)
injects `context/agent-orchestration.md` (generic policy) by the same channel. Neither
hook reads from the repo working tree at runtime.

## Consequences

- **Publish safety**: no machine paths, VRAM figures, GPU labels, binary locations, or
  identity tokens appear in git history or any published release artifact.
- **Portability**: a fresh install has schema-correct templates; every contributor fills
  in real values for their own machine without touching shared files.
- **Drift risk**: if a template gains new fields, existing `~/.claude/context/` files
  will miss them until the user re-runs init with `--force` or merges manually. The
  `horizon-scanning` skill's periodic review is the intended reconciliation trigger.
- **No CI coverage for machine context**: `~/.claude/context/` files are outside the
  repo and therefore outside CI. Correctness of the seeded files is the installer's
  responsibility after reviewing the `REMINDER:` output.
