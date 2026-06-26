"""Phase 2b: synthesize instincts from frequency patterns in observations.

Turns the pattern detectors in `analyze.py` into `Instinct` objects written to
the `personal/` directory. Pure-function core (testable without I/O) plus a
small idempotent writer.

Confidence model (saturating, capped):

    confidence = min(max_conf, consistency * n / (n + K))

  - `n` is the support (how many times the pattern was observed)
  - `consistency` is P(outcome | trigger) for sequence patterns, 1.0 for bash
    prefixes (a prefix has no competing alternative to normalise against)
  - `K` (default 5) is the saturation constant: more support pushes confidence
    toward `consistency`, but never past it
  - `max_conf` caps auto-derived confidence below the band reserved for
    human-authored / validated instincts (0.85 for workflow, 0.70 for bash)

The cap and the `auto-` source tag keep auto-learned instincts distinguishable
from manual ones, which a future prune/promote pass can act on.

Only two of the four `analyze.py` detectors feed synthesis: `pre_post_sequences`
(workflow habits) and `bash_command_prefixes` (tooling habits). `tool_frequency`
is too generic and `file_hotspots` is project-file-specific, not a generalizable
behavior.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Mapping

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from analyze import bash_command_prefixes, pre_post_sequences  # noqa: E402
from instinct_schema import (  # noqa: E402
    Instinct,
    format_instinct,
    is_machine_source,
    parse_instinct,
)
from storage import (  # noqa: E402
    get_global_instincts_dir,
    get_project_id,
    get_project_instincts_dir,
)

MIN_SUPPORT = 5
MIN_CONSISTENCY = 0.5
SATURATION_K = 5
MAX_CONF_WORKFLOW = 0.85
MAX_CONF_BASH = 0.70


def slugify(value: str) -> str:
    """Lowercase, collapse non-alphanumeric runs to single hyphens, trim."""
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def confidence(
    n: int,
    consistency: float,
    *,
    k: int = SATURATION_K,
    max_conf: float = MAX_CONF_WORKFLOW,
) -> float:
    """Saturating, capped confidence in [0, max_conf]. See module docstring."""
    raw = consistency * (n / (n + k))
    return round(min(max_conf, raw), 2)


def workflow_instincts_from_sequences(
    sequences: Mapping[tuple[str, str], int],
    *,
    min_support: int = MIN_SUPPORT,
    min_consistency: float = MIN_CONSISTENCY,
) -> list[Instinct]:
    """Build workflow instincts from (tool_A, tool_B) transition counts.

    For each pair, support = count(A→B) and consistency = count(A→B)/count(A→*).
    """
    totals_by_a: dict[str, int] = {}
    for (a, _b), count in sequences.items():
        totals_by_a[a] = totals_by_a.get(a, 0) + count

    out: list[Instinct] = []
    for (a, b), n in sequences.items():
        total_a = totals_by_a.get(a, 0)
        p = n / total_a if total_a else 0.0
        if n < min_support or p < min_consistency:
            continue
        out.append(
            Instinct(
                id=f"auto-seq-{slugify(a)}-{slugify(b)}",
                trigger=f"after using {a}",
                confidence=confidence(n, p, max_conf=MAX_CONF_WORKFLOW),
                domain="workflow",
                source="auto-frequency",
                source_repo=None,
                title=f"{b} often follows {a}",
                action=(
                    f"Consider reaching for {b} after {a}; it followed {a} "
                    f"{n} times ({p:.0%} of observed transitions)."
                ),
                evidence=f"Auto-derived from {n} observed {a}->{b} transitions (consistency {p:.0%}).",
            )
        )
    return sorted(out, key=lambda i: (-i.confidence, i.id))


def bash_instincts_from_prefixes(
    prefixes: Mapping[str, int] | Iterable[tuple[str, int]],
    *,
    min_support: int = MIN_SUPPORT,
) -> list[Instinct]:
    """Build tooling instincts from Bash command-prefix counts."""
    counts = dict(prefixes)
    out: list[Instinct] = []
    for prefix, n in counts.items():
        if n < min_support:
            continue
        out.append(
            Instinct(
                id=f"auto-bash-{slugify(prefix)}",
                trigger="reaching for the shell",
                confidence=confidence(n, 1.0, max_conf=MAX_CONF_BASH),
                domain="tooling",
                source="auto-frequency",
                source_repo=None,
                title=f"Frequent command: {prefix}",
                action=f"`{prefix}` is a frequently used command ({n} invocations observed in this project).",
                evidence=f"Auto-derived from {n} observed Bash invocations starting with `{prefix}`.",
            )
        )
    return sorted(out, key=lambda i: (-i.confidence, i.id))


def synthesize(
    records: list[dict],
    *,
    min_support: int = MIN_SUPPORT,
    min_consistency: float = MIN_CONSISTENCY,
) -> list[Instinct]:
    """Build the full candidate set from raw observation records."""
    seqs = pre_post_sequences(records)
    prefixes = dict(bash_command_prefixes(records, top_n=10_000))
    out = workflow_instincts_from_sequences(
        seqs, min_support=min_support, min_consistency=min_consistency
    )
    out += bash_instincts_from_prefixes(prefixes, min_support=min_support)
    return sorted(out, key=lambda i: (-i.confidence, i.id))


def get_target_dir(scope: str) -> Path:
    """Resolve the `personal/` dir for auto-learned instincts in a scope."""
    if scope == "global":
        return get_global_instincts_dir() / "personal"
    return get_project_instincts_dir(get_project_id()) / "personal"


def write_instincts(
    instincts: list[Instinct],
    target_dir: Path,
    *,
    dry_run: bool = True,
) -> dict[str, int]:
    """Write instincts to `target_dir`, idempotently.

    Existing files are overwritten ONLY when their `source` starts with `auto-`
    (so a human-promoted instinct under the same id is preserved). Unparseable
    files are left untouched. Returns counts of written / updated / skipped.
    """
    counts = {"written": 0, "updated": 0, "skipped": 0}
    for inst in instincts:
        out_file = target_dir / f"{inst.id}.yaml"
        if out_file.exists():
            try:
                existing = parse_instinct(out_file.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                counts["skipped"] += 1
                continue
            # Only machine-owned instincts (auto-* / *-detected) are reinforced in
            # place; a human-promoted instinct under the same id is preserved.
            if not is_machine_source(existing.source):
                counts["skipped"] += 1
                continue
            counts["updated"] += 1
        else:
            counts["written"] += 1
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            # Stamp reinforcement time so a later prune pass can decay by age.
            stamped = replace(inst, last_reinforced=time.time())
            _atomic_write(out_file, format_instinct(stamped))
    return counts


def _atomic_write(path: Path, text: str) -> None:
    """Write text to `path` atomically (temp file in the same dir + os.replace),
    so a crash mid-write cannot corrupt an existing instinct file.
    """
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
