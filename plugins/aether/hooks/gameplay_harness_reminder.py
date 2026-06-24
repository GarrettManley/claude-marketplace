"""PostToolUse hook: remind to run the gameplay harness after edits to gameplay code.

The gameplay harness (`scripts/run-gameplay-tests.mjs`, backed by
`scripts/gameplay-harness.ts`) is the only coverage for live-Ollama behavior
that unit tests cannot catch: stochastic stage-directions combat initiation,
classifier skill-proficiency bias under real models, cross-pass prompt
regressions. See `docs/engineering/plans/2026-04-23-gameplay-harness-findings.md`
for the F1-F7 findings that motivate this gate.

Triggered after Edit/Write/MultiEdit to any file that influences the DM cycle
or the LLM pipeline (see TRIGGER_FILES). The edited file's repo-relative path is
resolved via aether_repo (nearest core/Cargo.toml ancestor), so the hook is
checkout-location- and directory-name-independent and no-ops outside an Aether
repo. The trigger list intentionally overlaps with `classifier_eval_reminder.py`:
that reminder is about `eval:classifier` (unit-scope golden prompts), this one is
about the end-to-end scenario suite (multi-turn + real prose + real accept-parser).

Output goes to stdout as a short reminder; the hook never blocks the edit. Exit 0 always.

See issue #10 Phase 1 plan (P1.0) and CLAUDE.md per-edit checklist.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from aether_repo import edited_file_path, load_payload, repo_relative  # noqa: E402


TRIGGER_FILES = {
    "src/dm.ts",
    "src/bus.ts",
    "src/server.ts",
    "src/actor.ts",
    "src/roll-proposal.ts",
    "src/state-sync.ts",
    "src/llm/classifier_prompt.ts",
    "src/llm/ollama.ts",
    "src/llm/gemini.ts",
    "src/llm/schemas.ts",
    "src/llm/provider.ts",
}


def main() -> int:
    payload = load_payload()
    raw = edited_file_path(payload) if payload is not None else None
    if not raw:
        return 0

    _root, rel = repo_relative(raw)
    if rel not in TRIGGER_FILES:
        return 0

    print(
        f"[gameplay-harness-reminder] {rel} changed — run "
        "`node scripts/run-gameplay-tests.mjs` against live Ollama "
        "(scenarios 01-03 baseline, plus any scenario covering the touched "
        "area) before declaring the edit complete. "
        "See docs/engineering/plans/2026-04-23-gameplay-harness-findings.md."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
