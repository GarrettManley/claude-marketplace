"""PostToolUse hook: remind about classifier eval after edits to classifier code.

Spec 029 §5.2 mandates running `tests/eval/classifier.eval.ts` after any
classifier prompt change, because the eval is the only coverage for
live-Ollama (gemma3:4b) regressions — unit tests can't catch model-specific
output drift.

Triggered after Edit/Write/MultiEdit to:
  - src/llm/classifier_prompt.ts
  - src/llm/ollama.ts
  - src/llm/gemini.ts
  - src/llm/schemas.ts

The edited file's repo-relative path is resolved via aether_repo (nearest
core/Cargo.toml ancestor), so the hook is checkout-location- and
directory-name-independent and no-ops outside an Aether repo. Output goes to
stdout as a short reminder; the hook never blocks the edit. Exit 0 always.

See issue #14 and the `classifier-regression-checker` agent.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from aether_repo import edited_file_path, load_payload, repo_relative  # noqa: E402


TRIGGER_FILES = {
    "src/llm/classifier_prompt.ts",
    "src/llm/ollama.ts",
    "src/llm/gemini.ts",
    "src/llm/schemas.ts",
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
        f"[classifier-eval-reminder] {rel} changed — run `npm run eval:classifier` "
        "against live Ollama before declaring the edit complete. "
        "(Spec 029 §5.2; issue #14.)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
