---
name: local-orchestrator
description: Use when a task requires multi-file searches (>10 files), high-volume log/history compaction, or multi-round reasoning loops that would burn cloud tokens unnecessarily. Hands off to local llama-server models per the tier definitions in `configs/tiers.json`.
version: 0.1.0
dependencies: []
---

# Local Orchestrator

Optimize cloud-token usage by offloading specific task types to local llama-server models.

## When to Hand Off

Hand off to local models if the task matches ANY of:

- **Search Intensity**: requires searching > 10 files for a pattern.
- **Reasoning Depth**: requires a multi-round "thought loop" to resolve an ambiguity.
- **Data Volume**: summarizing or compacting session history into permanent context.
- **Cost-sensitive iteration**: experimental work where you'd run the same operation 5+ times.

Do NOT hand off when:

- The task requires the latest external knowledge (cloud models have larger training cutoffs).
- The task requires strict adherence to a complex spec (small-model drift is real).
- The user is on a deadline and the local stack might be cold (load takes ~30s).

## Tier Selection

See `${CLAUDE_PLUGIN_ROOT}/configs/tiers.json` for the tier schema and model assignments. The
committed `tiers.json` ships with **placeholder** runtime values (`<path-to>/llama-server.exe`,
`<path-to-models>/`, `<N> GB VRAM`, `<GPU model>`) — fill them in for your hardware, or keep a private
machine-specific override at `~/.claude/context/tiers.local.json` (same schema) and treat that as the
source of truth on a configured machine.

| Need | Tier | Default model (GGUF) |
|------|------|---------------|
| Strategic planning, code review, multi-step CoT | `reasoning` | `deepseek-r1-7b-Q4_K_M` |
| JSON output, tool calls, code generation, file search | `tooling` | `qwen2.5-coder-7b-Q4_K_M` |
| General chat, summarization, classification | `general` | `llama3.1-8b-Q4_K_M` |

## Orchestration Protocol

llama-server serves **one model per process** — there is no per-request model swap. Launch it
once with the GGUF for the tier you need (see `configs/tiers.json` for the binary path, blessed
launch args, and per-tier GGUF), hit the OpenAI-compatible `/v1/chat/completions` endpoint, and
stop it before loading a different tier. Your VRAM ceiling (e.g. 8 GB) holds roughly one 7B Q4_K_M model at a time; adjust for your hardware.

### Single-shot
Launch llama-server with the right tier's GGUF, wait for `/health`, fire one
`/v1/chat/completions` call, get the result.

```powershell
# Launch the tooling tier (one model per process)
Start-Process -FilePath "<path-to>\llama-server.exe" -ArgumentList `
  "-m <path-to-models>\qwen2.5-coder-7b-Q4_K_M.gguf --port 8080 --ctx-size 8192 --n-gpu-layers 99 --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0 --seed 42"
# wait until http://localhost:8080/health returns ok, then:

$body = @{
    model    = "qwen2.5-coder-7b"   # llama-server serves whatever GGUF is loaded; field is a label
    messages = @(@{ role = "user"; content = "Implement: $taskDescription" })
    stream   = $false
} | ConvertTo-Json -Depth 5
$resp = Invoke-RestMethod -Uri "http://localhost:8080/v1/chat/completions" -Method POST -Body $body -ContentType "application/json"
$code = $resp.choices[0].message.content
```

### Producer-Critic (multi-step edits)
1. **Plan** (reasoning): ask for a `task-plan.json` decomposition.
2. **Implement** (tooling): pass the plan, get code back.
3. **Critique** (reasoning): adversarial review of the implementation against project conventions.
4. **Final synthesis**: combine implementation + critique + verification.

Because reasoning and tooling are different models, any step that changes tier requires
**stopping the current llama-server and starting the other GGUF**. Batch all of one tier's calls
together, then swap once to the other tier — don't ping-pong per step, or you pay the ~40 s cold
load every swap.

## Return Synthesis

After receiving a response from a local model:

- **Thought capture**: extract the `<think>` block (deepseek-r1) to expose the reasoning chain.
- **Evidence verification**: results that claim something must contain a shell command output or web excerpt; treat unverified claims as hypotheses.
- **State sync**: if the local agent discovered a new fact about the project, update the relevant context file (CLAUDE.md, project docs, or memory).

See `references/HANDOFF_GUIDE.md` for hardware-tuning specifics and command patterns.
