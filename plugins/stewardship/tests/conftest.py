# plugins/stewardship/tests/conftest.py
"""Pytest fixtures for stewardship hook tests."""
import os
import sys
from pathlib import Path

import pytest

# Make plugin's scripts/ and hooks/ importable in tests
_PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PLUGIN_ROOT / "scripts"))
sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))


@pytest.fixture
def clean_env(monkeypatch):
    """Strip all STEWARDSHIP_* env vars so tests start from defaults."""
    for key in list(os.environ):
        if key.startswith("STEWARDSHIP_"):
            monkeypatch.delenv(key, raising=False)
    yield monkeypatch


@pytest.fixture(autouse=True)
def _isolate_learning_data_root(monkeypatch, tmp_path):
    """Point LEARNING_DATA_ROOT (the hook-error sink + instinct report the briefing
    reads via render_briefing) at a throwaway dir, so no test reads the developer's
    real ~/.../claude-marketplace/learning files. Without this, a real sink polluted
    with surrogate content makes the briefing subprocess tests crash and flake
    (the hb-rap retro's test-pollution scar). Tests that need a specific path still
    override with their own monkeypatch/--flag, which runs after this fixture."""
    monkeypatch.setenv("LEARNING_DATA_ROOT", str(tmp_path / "learning-data-iso"))
