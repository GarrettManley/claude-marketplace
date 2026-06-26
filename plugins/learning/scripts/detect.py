"""Phase 2c: Claude-driven correction/preference detection (Path A).

This module holds no detection *intelligence* — that lives in the
`/instinct-detect` command, where Claude reads the live transcript plus the
observation summary this module dumps, then hands candidate instincts back to
`--ingest`. Here we only:

  * `--dump-observations`: emit a JSON observation summary to stdout, and
  * `--ingest <file>`: validate Claude-authored candidates, force them into the
    `claude-detected` band (capped confidence), and write them idempotently.

The opt-in local-LLM backend (Path B) is deferred until a headless consumer
exists (see the program roadmap).
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from analyze import (  # noqa: E402
    bash_command_prefixes,
    load_observations,
    pre_post_sequences,
    tool_frequency,
)
from instinct_schema import (  # noqa: E402
    MAX_CONF_DETECTED,
    Instinct,
    parse_multi_instinct_file,
)
from storage import get_project_id  # noqa: E402
from synthesize import get_target_dir, write_instincts  # noqa: E402

_DETECTED_SOURCE = "claude-detected"


def normalize_candidate(inst: Instinct) -> Instinct:
    """Force a Claude-authored candidate into the detected band: source is set
    to `claude-detected` and confidence is capped at `MAX_CONF_DETECTED`.
    """
    return replace(
        inst,
        source=_DETECTED_SOURCE,
        confidence=min(inst.confidence, MAX_CONF_DETECTED),
    )


def _looks_like_error(tool_response: object) -> bool:
    """Best-effort: does a (opaque) tool_response read like a failure?

    `tool_response` is stored as an opaque blob; the command's intelligence
    (Claude) makes the real judgment, so this only surfaces likely-error
    records as hints in the dump.
    """
    text = json.dumps(tool_response, default=str).lower()
    return "error" in text or "traceback" in text or "exception" in text


def build_observation_summary(records: list[dict]) -> dict:
    """A compact, JSON-serializable view of observations for Claude to reason over."""
    sequences = pre_post_sequences(records)
    top_sequences = sorted(
        ([a, b, n] for (a, b), n in sequences.items()),
        key=lambda t: (-t[2], t[0], t[1]),
    )[:20]
    error_samples = [
        {"tool_name": r.get("tool_name", ""), "session_id": r.get("session_id", "")}
        for r in records
        if r.get("phase") == "post" and "tool_response" in r and _looks_like_error(r["tool_response"])
    ][:20]
    return {
        "record_count": len(records),
        "tool_frequency": tool_frequency(records),
        "top_sequences": top_sequences,
        "bash_prefixes": [list(t) for t in bash_command_prefixes(records, top_n=20)],
        "error_samples": error_samples,
    }


def ingest_candidates(text: str, target_dir: Path, *, apply: bool) -> dict:
    """Parse candidate instincts, normalize to the detected band, and write."""
    candidates = [normalize_candidate(i) for i in parse_multi_instinct_file(text)]
    return write_instincts(candidates, target_dir, dry_run=not apply)


def cmd_detect(
    *,
    scope: str = "project",
    dump_observations: bool = False,
    ingest_path: str | None = None,
    apply: bool = False,
) -> int:
    if dump_observations:
        records = load_observations(get_project_id())
        print(json.dumps(build_observation_summary(records), indent=2))
        return 0
    if ingest_path:
        text = Path(ingest_path).read_text(encoding="utf-8")
        counts = ingest_candidates(text, get_target_dir(scope), apply=apply)
        verb = "wrote" if apply else "would write"
        print(
            f"detect: {verb} {counts['written']} new + {counts['updated']} updated, "
            f"{counts['skipped']} skipped (claude-detected, capped at {MAX_CONF_DETECTED})."
        )
        if not apply:
            print("dry-run: pass --apply to persist.")
        return 0
    print("detect: pass --dump-observations or --ingest <file>.")
    return 1
