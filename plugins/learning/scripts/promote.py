"""Phase 3: promote a project-scoped instinct to the global store.

Explicit mode promotes one instinct by id from the current project. `--auto`
promotes instincts that have proven general: present in >=2 project stores with
a (decayed) confidence at or above the detected-band cap. Promotion is
copy-verify-delete (the global copy is parsed back before the project copy is
removed) and snapshots the data root first.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from instinct_schema import (  # noqa: E402
    MAX_CONF_DETECTED,
    Instinct,
    format_instinct,
    parse_instinct,
)
from prune import HALF_LIFE_DAYS, decayed_confidence  # noqa: E402
from snapshot import snapshot_instincts  # noqa: E402
from storage import (  # noqa: E402
    get_data_root,
    get_global_instincts_dir,
    get_project_id,
    get_project_instincts_dir,
    list_instinct_files,
)


def _global_personal_dir() -> Path:
    return get_global_instincts_dir() / "personal"


def _project_personal_dir(project_id: str) -> Path:
    return get_project_instincts_dir(project_id) / "personal"


def _load_project_personal(directory: Path) -> list[Instinct]:
    out: list[Instinct] = []
    for p in list_instinct_files(directory):
        try:
            out.append(parse_instinct(p.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
    return out


def _all_project_personal() -> dict[str, list[Instinct]]:
    """Map project-id -> its personal instincts, across every project store."""
    projects_root = get_data_root() / "projects"
    by_project: dict[str, list[Instinct]] = {}
    if not projects_root.is_dir():
        return by_project
    for pdir in sorted(projects_root.iterdir()):
        personal = pdir / "instincts" / "personal"
        if personal.is_dir():
            by_project[pdir.name] = _load_project_personal(personal)
    return by_project


def select_auto_promotions(
    by_project: dict[str, list[Instinct]],
    now: float,
    *,
    cap: float = MAX_CONF_DETECTED,
    half_life_days: float = HALF_LIFE_DAYS,
) -> list[tuple[str, Instinct]]:
    """Pick ids present in >=2 project stores whose best decayed confidence >= cap.

    Returns [(id, best_instinct)] where best_instinct is the highest decayed-
    confidence instance to copy to the global store.
    """
    occurrences: dict[str, list[tuple[float, Instinct]]] = {}
    for instincts in by_project.values():
        for inst in instincts:
            decayed = decayed_confidence(
                inst.confidence, inst.last_reinforced, now, half_life_days=half_life_days
            )
            occurrences.setdefault(inst.id, []).append((decayed, inst))
    chosen: list[tuple[str, Instinct]] = []
    for iid, occ in sorted(occurrences.items()):
        if len(occ) < 2:
            continue
        best_decayed, best_inst = max(occ, key=lambda t: t[0])
        if best_decayed >= cap:
            chosen.append((iid, best_inst))
    return chosen


def _promote_one(inst: Instinct, *, apply: bool) -> bool:
    """Copy `inst` into the global personal store (verify it parses). Returns
    True if the global copy now exists (or would, in dry-run).
    """
    if not apply:
        return True
    target_dir = _global_personal_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    out = target_dir / f"{inst.id}.yaml"
    out.write_text(format_instinct(inst), encoding="utf-8")
    parse_instinct(out.read_text(encoding="utf-8"))  # verify before any delete
    return out.is_file()


def cmd_promote(
    instinct_id: str | None = None,
    *,
    scope: str = "project",
    auto: bool = False,
    apply: bool = False,
    now: float | None = None,
) -> int:
    now = time.time() if now is None else now

    if auto:
        by_project = _all_project_personal()
        chosen = select_auto_promotions(by_project, now)
        if not chosen:
            print("promote --auto: no instinct qualifies (need >=2 stores and high confidence).")
            return 0
        print(f"promote --auto: {len(chosen)} instinct(s) qualify: {', '.join(i for i, _ in chosen)}")
        if not apply:
            print("dry-run: pass --apply to promote (a snapshot is taken first).")
            return 0
        snapshot_instincts()
        projects_root = get_data_root() / "projects"
        for iid, best in chosen:
            _promote_one(best, apply=True)
            for pdir in projects_root.iterdir():
                stale = pdir / "instincts" / "personal" / f"{iid}.yaml"
                if stale.is_file():
                    stale.unlink()
        print(f"promoted {len(chosen)} instinct(s) to the global store.")
        return 0

    if not instinct_id:
        print("promote: provide an instinct id, or use --auto.")
        return 1
    src = _project_personal_dir(get_project_id()) / f"{instinct_id}.yaml"
    if not src.is_file():
        print(f"promote: instinct {instinct_id!r} not found in {scope} personal store.")
        return 1
    inst = parse_instinct(src.read_text(encoding="utf-8"))
    print(f"promote: {instinct_id} -> global personal store (source {inst.source!r} preserved).")
    if not apply:
        print("dry-run: pass --apply to promote (a snapshot is taken first).")
        return 0
    snapshot_instincts()
    _promote_one(inst, apply=True)
    src.unlink()  # only after the verified global copy exists
    print(f"promoted {instinct_id}.")
    return 0
