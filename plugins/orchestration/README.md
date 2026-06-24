# orchestration@garrettmanley

Routes work across cloud agents and local llama-server models, keeping cloud token spend in proportion to task value. The plugin ships three tiers of 7B–8B GGUF models (Reasoning / Tooling / General), decision heuristics for when to hand off to each tier, a monthly horizon-scan workflow to keep tier assignments current against published benchmarks, a loop-operator agent for safe autonomous loops, and a SessionStart hook that injects the agent/Workflow orchestration policy into every session.

Intended for developers running [llama-server (llama.cpp)](https://github.com/ggerganov/llama.cpp) locally with a consumer GPU and a VRAM ceiling where only one 7B–8B model fits at a time.

## Install

```
/plugin marketplace add garrettmanley/claude-marketplace
/plugin install orchestration@garrettmanley
```

**Prerequisite:** [`uv`](https://docs.astral.sh/uv/) must be installed and on PATH. The SessionStart hook runs via `uv run --no-project` (see `hooks/hooks.json`), which bootstraps the Python runtime itself — you do not need a separate `python3` on PATH.

## Components

| Component | Type | Description |
|-----------|------|-------------|
| `local-orchestrator` | Skill | Decision logic for handing off to local llama-server: >10-file searches, multi-round reasoning loops, log/history compaction, cost-sensitive iteration; includes producer-critic loop pattern |
| `horizon-scanning` | Skill | Monthly sweep of SOTA 7B–14B models and new MCP servers; re-evaluates tier assignments in `configs/tiers.json` against current benchmarks |
| `loop-operator` | Agent | Operates autonomous agent loops safely — required-checks gate, per-iteration checkpoints, stall detection, scope reduction on repeated failure, escalation protocol |
| `inject_orchestration_context.py` | SessionStart hook | Injects `context/agent-orchestration.md` (the agent/Workflow orchestration policy) into every session via `additionalContext` |
| `configs/tiers.json` | Config | Runtime block (binary path, endpoint, launch args) + Reasoning / Tooling / General tier definitions with GGUF names, VRAM footprints, capabilities, and `use_when` heuristics |
| `context/agent-orchestration.md` | Policy | Standing Workflow authorization (code review, deep research, codebase maps, migrations, design panels), subagent model-routing table, and guardrails |

## Init / Setup

The init scripts scaffold two files into `~/.claude/context/` — the tier definitions and a hardware-profile template — when those files are absent. Both scripts are idempotent: re-running is a no-op unless `--force` / `-Force` is passed.

**macOS / Linux (Bash):**

```bash
# From the plugin root
bash plugins/orchestration/scripts/init.sh
bash plugins/orchestration/scripts/init.sh --force   # overwrite existing files
bash plugins/orchestration/scripts/init.sh --quiet   # suppress status output
```

**Windows (PowerShell 7+):**

```powershell
# From the plugin root
pwsh plugins\orchestration\scripts\init.ps1
pwsh plugins\orchestration\scripts\init.ps1 -Force
pwsh plugins\orchestration\scripts\init.ps1 -Quiet
```

After running init, two placeholder files are created:

- `~/.claude/context/tiers.local.json` — copy of `configs/tiers.json` with `<placeholder>` values. Edit the `runtime` block to fill in your real `llama-server` binary path, model directory, and VRAM ceiling.
- `~/.claude/context/hardware-profile.md` — template with `<CPU model>`, `<N> GB VRAM`, `<GPU model>`, and binary/model-dir placeholders. Fill in your hardware details; the `always: true` frontmatter causes `inject_context` hooks to auto-load it every session.

The init scripts print `REMINDER:` lines for each file that needs editing.

## Usage

### `local-orchestrator` — deciding when to use a local model

```
/orchestration:local-orchestrator
```

Invoke the skill when you need the model to decide whether to hand off a task to llama-server. The skill surfaces the heuristics from `configs/tiers.json` and walks the tier-selection table.

**Hand off when the task matches any of:**
- Searching >10 files for a pattern
- Requires a multi-round reasoning loop to resolve an ambiguity
- Summarizing or compacting high-volume session history into permanent context
- Experimental work you'd run the same operation 5+ times

**Do not hand off when:**
- The task requires the latest external knowledge (cloud models have larger training cutoffs)
- The task requires strict adherence to a complex spec (small-model drift is real)
- The user is on a deadline and the local stack might be cold (cold load is ~40 s)
- Single-shot trivial task (round-trip cost exceeds the cloud-token cost)

#### Producer-Critic loop (multi-step code edits)

The standard pattern for non-trivial code work with two model tiers:

1. **Plan** (Reasoning tier): ask for a `task-plan.json` decomposition.
2. **Implement** (Tooling tier): pass the plan, get implementation back.
3. **Critique** (Reasoning tier): adversarial review against project conventions.
4. **Synthesize**: combine implementation + critique + verification for the cloud agent.

Because each tier is a separate llama-server process, batch all calls within one tier before swapping — stopping and restarting costs ~40 s per swap.

#### PowerShell single-shot example

```powershell
# Launch the tooling tier
Start-Process -FilePath "<path-to>\llama-server.exe" -ArgumentList `
  "-m <path-to-models>\qwen2.5-coder-7b-Q4_K_M.gguf --port 8080 --ctx-size 8192 --n-gpu-layers 99 --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0 --seed 42"
# Wait until http://localhost:8080/health returns {"status":"ok"}, then:

$body = @{
    model    = "qwen2.5-coder-7b"
    messages = @(@{ role = "user"; content = "Implement: $taskDescription" })
    stream   = $false
} | ConvertTo-Json -Depth 5

$resp = Invoke-RestMethod -Uri "http://localhost:8080/v1/chat/completions" `
  -Method POST -Body $body -ContentType "application/json"
$resp.choices[0].message.content
```

### `horizon-scanning` — keeping tier assignments current

```
/orchestration:horizon-scanning
```

Run on a monthly cadence (or after a major leaderboard update). The skill searches for SOTA 7B–14B models on the HF Open LLM Leaderboard and the MCP Server Gallery, compares against current `configs/tiers.json` assignments, and — if a candidate beats the current tier on at least two Tier-1 benchmarks and fits the VRAM ceiling — proposes a load-test plan before any swap.

## Configuration

### `configs/tiers.json` / `~/.claude/context/tiers.local.json`

Reference data the `local-orchestrator` skill reads when selecting a tier. The committed `configs/tiers.json` ships with generic `<placeholder>` values. On a configured machine, keep your real values in `~/.claude/context/tiers.local.json` (same schema); that file takes precedence.

Key fields in the `runtime` block:

| Field | Purpose |
|-------|---------|
| `binary` | Absolute path to your `llama-server` executable |
| `model_dir` | Directory containing your GGUF files |
| `endpoint` | Default `http://localhost:8080/v1/chat/completions` |
| `health` | Default `http://localhost:8080/health` |
| `launch_args` | Blessed args: `--ctx-size 8192 --n-gpu-layers 99 --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0 --seed 42` |

### Tier summary

| Tier | Default GGUF | VRAM (Q4_K_M) | Use when |
|------|-------------|---------------|---------|
| `reasoning` | `deepseek-r1-7b-Q4_K_M.gguf` | ~4.4 GB | Multi-step CoT, planning, adversarial review |
| `tooling` | `qwen2.5-coder-7b-Q4_K_M.gguf` | ~4.4 GB | Structured JSON, tool calls, code generation |
| `general` | `llama3.1-8b-Q4_K_M.gguf`, `gemma-4-E4B-it-Q4_K_M.gguf` | ~4.6 GB | Summarization, classification, general chat |

Avoid models ≥14B on VRAM-constrained hardware — partial offload drops throughput below 5 t/s and risks OOM under VRAM contention.

### `~/.claude/context/hardware-profile.md`

Created by init. The `always: true` frontmatter causes supporting `inject_context` hooks to auto-load it at session start, surfacing your hardware spec to the model without manual re-injection.

### SessionStart hook

`inject_orchestration_context.py` fires on every SessionStart. It reads `context/agent-orchestration.md` (bundled with the plugin) and emits it as `additionalContext`, injecting the Workflow authorization list, subagent model-routing table, and guardrails. The hook fails open — a missing or garbled policy file never blocks session start.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `local-orchestrator` skill references `<placeholder>` values in tier output | Run init (`scripts/init.ps1` or `init.sh`), then edit `~/.claude/context/tiers.local.json` with your real binary path, model directory, and VRAM ceiling |
| llama-server does not start or `health` returns unhealthy | Confirm the binary path in `tiers.local.json` is correct; check that no other process is on port 8080 (`--port` to change it); verify the GGUF path exists |
| Tier swap is slow (40+ s) | Expected — cold model load on llama-server takes ~40 s. Batch all calls within one tier before stopping the server and starting the next |
| `gemma3-4b-Q4_K_M.gguf` fails to load | Known issue on some llama-server builds (missing hyperparameter key). Use `gemma-4-E4B-it-Q4_K_M.gguf` instead; update `configs/tiers.json` or `tiers.local.json` accordingly |

## Cross-platform

| Area | Windows | macOS / Linux |
|------|---------|---------------|
| Init script | `scripts\init.ps1` (PowerShell 7+) — uses `$env:USERPROFILE\.claude\context\` | `scripts/init.sh` (Bash) — uses `~/.claude/context/` |
| Binary name | `llama-server.exe` | `llama-server` (no extension) |
| Model paths | Backslash separators in `tiers.local.json`; forward slashes also accepted by llama-server on Windows | Forward slashes standard |
| Hook script | `inject_orchestration_context.py` runs via `uv run --no-project` (configured in `hooks.json`) — ensure `uv` is installed and on PATH; `uv run --no-project` bootstraps Python | Same |

The shipped `configs/tiers.json` uses generic `<path-to>/llama-server.exe` as the binary key. On macOS/Linux, update the key to `<path-to>/llama-server` in `tiers.local.json`.
