import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from snapshot import snapshot_instincts  # noqa: E402


@pytest.fixture
def data_root(monkeypatch, tmp_path):
    monkeypatch.setenv("LEARNING_DATA_ROOT", str(tmp_path))
    return tmp_path


def _seed(root: Path, rel: str, text: str = "x") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_snapshot_copies_instinct_files(data_root):
    _seed(data_root, "instincts/personal/foo.yaml", "FOO")
    _seed(data_root, "projects/abc/instincts/personal/bar.yaml", "BAR")
    dest = snapshot_instincts(data_root)
    assert (dest / "instincts/personal/foo.yaml").read_text(encoding="utf-8") == "FOO"
    assert (dest / "projects/abc/instincts/personal/bar.yaml").read_text(encoding="utf-8") == "BAR"


def test_snapshot_returns_path_under_snapshots_dir(data_root):
    _seed(data_root, "instincts/personal/foo.yaml")
    dest = snapshot_instincts(data_root)
    assert dest.exists()
    assert dest.parent == data_root / ".snapshots"


def test_snapshot_does_not_recurse_into_prior_snapshots(data_root):
    _seed(data_root, "instincts/personal/foo.yaml")
    snapshot_instincts(data_root)  # creates .snapshots/<ts1>/
    dest2 = snapshot_instincts(data_root)  # must NOT copy .snapshots into itself
    assert not (dest2 / ".snapshots").exists()


def test_snapshot_empty_root_ok(data_root):
    dest = snapshot_instincts(data_root)
    assert dest.exists()
    assert list(dest.rglob("*.yaml")) == []
