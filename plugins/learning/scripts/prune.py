"""Phase 3: confidence-decay pruning of machine-learned instincts.

An instinct's confidence decays with age-since-last-reinforcement on a
half-life curve; once the decayed value falls below `PRUNE_FLOOR` it is removed.
Only machine-owned sources (auto-* / *-detected) decay — human-curated
instincts are exempt. `--apply` snapshots the data root first.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from instinct_schema import Instinct, is_machine_source, parse_instinct  # noqa: E402
from snapshot import snapshot_instincts  # noqa: E402
from storage import (  # noqa: E402
    get_global_instincts_dir,
    get_project_id,
    get_project_instincts_dir,
    list_instinct_files,
)

HALF_LIFE_DAYS = 30.0
PRUNE_FLOOR = 0.2
_DAY = 86400.0
_SUBDIRS = ("personal", "inherited")


def decayed_confidence(
    confidence: float,
    last_reinforced: float | None,
    now: float,
    *,
    half_life_days: float = HALF_LIFE_DAYS,
) -> float:
    """Confidence after half-life decay by age since `last_reinforced`.

    `last_reinforced=None` (legacy instincts) can't be aged, so confidence is
    returned unchanged — such instincts are only pruned once re-derivation
    stamps a timestamp on them.
    """
    if last_reinforced is None:
        return confidence
    age_days = max(0.0, (now - last_reinforced) / _DAY)
    return confidence * (0.5 ** (age_days / half_life_days))


def _scope_dirs(scope: str) -> list[Path]:
    base = (
        get_global_instincts_dir()
        if scope == "global"
        else get_project_instincts_dir(get_project_id())
    )
    return [base / sub for sub in _SUBDIRS]


def _load_scope(scope: str) -> list[tuple[Path, Instinct]]:
    loaded: list[tuple[Path, Instinct]] = []
    for d in _scope_dirs(scope):
        for p in list_instinct_files(d):
            try:
                loaded.append((p, parse_instinct(p.read_text(encoding="utf-8"))))
            except (ValueError, OSError):
                continue
    return loaded


def plan_prune(
    loaded: list[tuple[Path, Instinct]],
    now: float,
    *,
    floor: float = PRUNE_FLOOR,
    half_life_days: float = HALF_LIFE_DAYS,
) -> list[tuple[Path, Instinct, float]]:
    """Return [(path, instinct, decayed_confidence)] for machine instincts that
    have decayed below `floor`. Human-curated instincts are never included.
    """
    out: list[tuple[Path, Instinct, float]] = []
    for path, inst in loaded:
        if not is_machine_source(inst.source):
            continue
        decayed = decayed_confidence(
            inst.confidence, inst.last_reinforced, now, half_life_days=half_life_days
        )
        if decayed < floor:
            out.append((path, inst, decayed))
    return out


def cmd_prune(*, scope: str = "project", apply: bool = False, now: float | None = None) -> int:
    now = time.time() if now is None else now
    loaded = _load_scope(scope)
    prunable = plan_prune(loaded, now)
    if not prunable:
        print(f"prune: nothing below floor {PRUNE_FLOOR} in {scope} scope ({len(loaded)} instincts).")
        return 0
    print(f"prune: {len(prunable)} instinct(s) below floor {PRUNE_FLOOR} in {scope} scope:")
    for path, inst, decayed in prunable:
        print(f"  - {inst.id}  (conf {inst.confidence:.2f} -> decayed {decayed:.2f})")
    if not apply:
        print("dry-run: pass --apply to delete (a snapshot is taken first).")
        return 0
    backup = snapshot_instincts()
    print(f"snapshot: {backup}")
    for path, _inst, _d in prunable:
        try:
            path.unlink()
        except OSError:
            pass
    print(f"pruned {len(prunable)} instinct(s).")
    return 0
