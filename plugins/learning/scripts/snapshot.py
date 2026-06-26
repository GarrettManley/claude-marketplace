"""Backup helper for the destructive Phase 3 commands (prune/promote/evolve).

Before any `--apply`, callers snapshot the instinct stores so a wrong decay,
merge, or promotion can be restored by copying the snapshot tree back over the
data root. Only instinct-bearing subtrees are copied (not `observations.jsonl`,
which can be large and is never mutated by these commands).
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from storage import get_data_root  # noqa: E402

# Subtrees that hold instinct YAML; `.snapshots` is deliberately excluded so a
# snapshot never recurses into prior snapshots.
_SNAPSHOT_SUBTREES = ("instincts", "projects", "evolved")
_SNAPSHOTS_DIRNAME = ".snapshots"


def snapshot_instincts(data_root: Path | None = None) -> Path:
    """Copy the instinct stores under `data_root` to a fresh timestamped backup.

    Returns the snapshot directory (under `<data_root>/.snapshots/`). Restoring
    is a manual `cp -r <snapshot>/* <data_root>/`.
    """
    root = Path(data_root) if data_root is not None else get_data_root()
    snapshots = root / _SNAPSHOTS_DIRNAME
    snapshots.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    # mkdtemp guarantees a unique dir even for two snapshots in the same second.
    dest = Path(tempfile.mkdtemp(prefix=f"{ts}-", dir=str(snapshots)))
    for sub in _SNAPSHOT_SUBTREES:
        src = root / sub
        if src.exists():
            shutil.copytree(src, dest / sub, dirs_exist_ok=True)
    return dest
