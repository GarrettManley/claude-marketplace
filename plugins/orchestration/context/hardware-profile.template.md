# Hardware Profile

> Template created by `orchestration` plugin init. Replace every `<placeholder>` with
> real values for your machine, then save this file to `~/.claude/context/hardware-profile.md`.
> The `always: true` front-matter below tells the inject_context hook to auto-load it every session.

---
always: true
---

## System Specs

- **CPU**: <CPU model> (<N>c/<M>t)
- **RAM**: <RAM> GB
- **GPU**: <GPU model> — **<N> GB VRAM ceiling**

## Local Runtime

- **Stack**: llama-server (llama.cpp) — no Ollama.
- **Binary**: `<path-to>/llama-server.exe`
- **Model directory**: `<path-to-models>/` (GGUFs, Q4_K_M recommended)
- **Blessed launch args**: `--ctx-size 8192 --n-gpu-layers 99 --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0 --seed 42`
- **Constraint**: One model per process. Serialize loads under the VRAM ceiling; switching tiers means stopping the current llama-server and starting another.

## Model Tier Strategy

Local tier definitions live in `~/.claude/context/tiers.local.json` (same schema as the
plugin's `configs/tiers.json`). Edit that file to point at your actual binary/model paths
and VRAM ceiling. Summary of the three tiers:

| Tier | Default GGUF | VRAM (Q4_K_M) | When to use |
|------|-------------|---------------|-------------|
| `reasoning` | `deepseek-r1-7b-Q4_K_M.gguf` | ~4.4 GB | Multi-step CoT, planning, adversarial review |
| `tooling` | `qwen2.5-coder-7b-Q4_K_M.gguf` | ~4.4 GB | Structured JSON, tool calls, code generation |
| `general` | `llama3.1-8b-Q4_K_M.gguf` | ~4.6 GB | Summarization, classification, general chat |

**Avoid 14B+ models** on a <N> GB VRAM ceiling — partial offload drops throughput below
5 t/s and risks OOM under VRAM contention (gaming, browser GPU compositing).

## Inference Targets

- Target throughput: >40 tok/s on primary 7B–8B Q4_K_M models with full GPU offload.
- Health check: `http://localhost:8080/health` (default port; adjust if you use `--port`).
- OpenAI-compatible endpoint: `http://localhost:8080/v1/chat/completions`.
