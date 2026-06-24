# Local Hand-Off Guide

Hardware-tuned settings and command patterns for the orchestration plugin. The local runtime is
**llama-server (llama.cpp)** is used as the local runtime (instead of Ollama).

## Hardware constraints

See `~/.claude/context/hardware-profile.md` for the canonical machine spec.

Quick summary for the example target (<GPU model> / <N> GB VRAM) — edit to match your hardware:

| Tier | Model (GGUF) | VRAM | Speed |
|------|-------|------|-------|
| Reasoning | `deepseek-r1-7b-Q4_K_M.gguf` | ~4.4 GB | full GPU offload, >30 t/s |
| Tooling | `qwen2.5-coder-7b-Q4_K_M.gguf` | ~4.4 GB | full GPU offload, >30 t/s |
| General | `llama3.1-8b-Q4_K_M.gguf`, `gemma-4-E4B-it-Q4_K_M.gguf` | ~4.6 GB | full GPU offload |
| Stretch (avoid) | `*14b*` | ~10+ GB | partial offload, <5 t/s, OOM-prone |

## Runtime & launch args

The blessed launch arguments are load-bearing for stable behavior on this VRAM ceiling:

```
--ctx-size 8192 --n-gpu-layers 99 --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0 --seed 42
```

- `--n-gpu-layers 99` — full offload of a 7-8B Q4_K_M model under 8 GB.
- `--flash-attn on` — **requires a value** on the current build (the bare flag eats the next arg).
- `--cache-type-k/v q8_0` — quantized KV cache to fit the 8192 context.
- One model per process — no auto-swap. Serialize loads; an external launcher owns lifecycle.

```powershell
& "<path-to>\llama-server.exe" -m "<path-to-models>\deepseek-r1-7b-Q4_K_M.gguf" --port 8080 `
  --ctx-size 8192 --n-gpu-layers 99 --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0 --seed 42
```

## Models

GGUFs live at your configured `model_dir` from `configs/tiers.json` (Q4_K_M unless suffixed otherwise) — there is no `pull`; download the
GGUF once and point `-m` at it. Current slate: `deepseek-r1-7b`, `qwen2.5-coder-7b`, `llama3.1-8b`,
`gemma-4-E4B-it`, `phi4-mini`, `mistral-7b-instruct` (plus any project-specific GGUFs you have downloaded). Note: the
older `gemma3-4b-Q4_K_M.gguf` may fail to load on some llama-server builds — prefer `gemma-4-E4B-it`.

## Health check

```powershell
# Is llama-server up and a model loaded?
Invoke-RestMethod -Uri "http://localhost:8080/health" -Method GET
Invoke-RestMethod -Uri "http://localhost:8080/v1/models" -Method GET | Select-Object -ExpandProperty data
```

## Local-search tools

For multi-file searches that would burn cloud tokens, prefer:

- `everything-search-mcp` (Windows; very fast for local file search).
- `ripgrep` directly (`rg "pattern" --type ts`).
- `fd` for filename patterns.

These can be paired with the tooling-tier model for "search + reason about results" workflows.

## Cold-start mitigation

Cold load is ~40 s. Because there is no keep-alive auto-unload, **stop the server when done** —
leaving a model resident is the main way gaming/browser-GPU contention OOMs the next workload.
If a workflow will reuse a model several times, keep the one process up for the batch, then stop
it; don't relaunch per call.
