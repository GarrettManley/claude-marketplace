"""Phase 3: cluster near-duplicate machine instincts and merge each cluster.

Clusters machine-owned instincts by string similarity on `trigger + title`;
clusters of >=2 merge into their highest-confidence member (evidence unioned),
and the merged-away instincts are archived (moved) into the reserved `evolved/`
directory. No higher-order artifact generation (cut by design review).
"""
from __future__ import annotations

import difflib
import sys
from dataclasses import replace
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from instinct_schema import (  # noqa: E402
    Instinct,
    format_instinct,
    is_machine_source,
    parse_instinct,
)
from snapshot import snapshot_instincts  # noqa: E402
from storage import (  # noqa: E402
    get_data_root,
    get_global_instincts_dir,
    get_project_dir,
    get_project_id,
    get_project_instincts_dir,
    list_instinct_files,
)

SIMILARITY_THRESHOLD = 0.8


def _key(inst: Instinct) -> str:
    return f"{inst.trigger} {inst.title}"


def cluster_instincts(
    instincts: list[Instinct], *, threshold: float = SIMILARITY_THRESHOLD
) -> list[list[Instinct]]:
    """Greedy clustering: an instinct joins the first cluster whose representative
    key is >= `threshold` similar (difflib ratio); otherwise it starts a cluster.
    """
    clusters: list[list[Instinct]] = []
    for inst in instincts:
        key = _key(inst)
        for cluster in clusters:
            if difflib.SequenceMatcher(None, _key(cluster[0]), key).ratio() >= threshold:
                cluster.append(inst)
                break
        else:
            clusters.append([inst])
    return clusters


def merge_cluster(cluster: list[Instinct]) -> Instinct:
    """Merge a cluster into its highest-confidence member, unioning evidence."""
    base = max(cluster, key=lambda i: i.confidence)
    seen: list[str] = []
    for inst in cluster:
        line = inst.evidence.strip()
        if line and line not in seen:
            seen.append(line)
    return replace(base, evidence="\n".join(seen))


def _personal_dir(scope: str) -> Path:
    base = (
        get_global_instincts_dir()
        if scope == "global"
        else get_project_instincts_dir(get_project_id())
    )
    return base / "personal"


def _evolved_dir(scope: str) -> Path:
    if scope == "global":
        return get_data_root() / "evolved"
    return get_project_dir(get_project_id()) / "evolved"


def _load(directory: Path) -> list[tuple[Path, Instinct]]:
    out: list[tuple[Path, Instinct]] = []
    for p in list_instinct_files(directory):
        try:
            out.append((p, parse_instinct(p.read_text(encoding="utf-8"))))
        except (ValueError, OSError):
            continue
    return out


def cmd_evolve(*, scope: str = "project", apply: bool = False) -> int:
    personal = _personal_dir(scope)
    loaded = [(p, i) for p, i in _load(personal) if is_machine_source(i.source)]
    by_id = {i.id: p for p, i in loaded}
    clusters = [c for c in cluster_instincts([i for _p, i in loaded]) if len(c) >= 2]
    if not clusters:
        print(f"evolve: no mergeable clusters in {scope} scope ({len(loaded)} machine instincts).")
        return 0
    print(f"evolve: {len(clusters)} cluster(s) to merge in {scope} scope:")
    for cluster in clusters:
        base = max(cluster, key=lambda i: i.confidence)
        others = [i.id for i in cluster if i.id != base.id]
        print(f"  - {base.id} <= merge {', '.join(others)}")
    if not apply:
        print("dry-run: pass --apply to merge (a snapshot is taken first).")
        return 0
    snapshot_instincts()
    evolved = _evolved_dir(scope)
    evolved.mkdir(parents=True, exist_ok=True)
    for cluster in clusters:
        merged = merge_cluster(cluster)
        by_id[merged.id].write_text(format_instinct(merged), encoding="utf-8")
        for inst in cluster:
            if inst.id == merged.id:
                continue
            src = by_id[inst.id]
            src.replace(evolved / src.name)  # archive merged-away source
    print(f"merged {len(clusters)} cluster(s); archived sources to {evolved}.")
    return 0
