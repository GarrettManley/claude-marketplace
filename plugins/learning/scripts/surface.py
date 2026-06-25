"""SessionStart hook: surface high-confidence instincts into session context.

Without this, instincts written by `synthesize` (or imported manually) are inert
storage that nothing reads. When LEARNING_SURFACE is on, this prints a compact
block of the highest-confidence project + global instincts to stdout, which the
SessionStart hook injects as additional context. Default is OFF.

Gated like `observe.py`: the `run_with_flags.py` wrapper enforces the `strict`
profile; this script additionally requires LEARNING_SURFACE to be on. Either gate
closed keeps it silent.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from env_flags import is_on  # noqa: E402
from instinct_schema import Instinct  # noqa: E402

DEFAULT_MIN_CONFIDENCE = 0.6
SURFACE_CAP = 15


def _min_confidence() -> float:
    raw = os.environ.get("LEARNING_SURFACE_MIN_CONFIDENCE", "")
    try:
        return float(raw)
    except (ValueError, TypeError):
        return DEFAULT_MIN_CONFIDENCE


def collect_instincts() -> list[Instinct]:
    """All instincts across project + global, personal + inherited."""
    from instinct_cli import _load_all_instincts, _scope_dirs

    out: list[Instinct] = []
    for scope in ("project", "global"):
        for directory in _scope_dirs(scope):
            out.extend(_load_all_instincts(directory))
    return out


def select(
    instincts: list[Instinct],
    *,
    min_conf: float,
    cap: int,
) -> list[Instinct]:
    """Filter to confidence >= min_conf, sort by confidence desc (id tie-break), cap."""
    kept = [i for i in instincts if i.confidence >= min_conf]
    kept.sort(key=lambda i: (-i.confidence, i.id))
    return kept[:cap]


def render(instincts: list[Instinct]) -> str:
    """Compact, context-injectable block of instincts."""
    lines = ["## Learned instincts (this project + global)", ""]
    for i in instincts:
        lines.append(f"- [{int(i.confidence * 100)}%] {i.trigger} → {i.action}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    if not is_on("LEARNING_SURFACE"):
        return 0
    selected = select(collect_instincts(), min_conf=_min_confidence(), cap=SURFACE_CAP)
    if not selected:
        return 0
    sys.stdout.write(render(selected))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
