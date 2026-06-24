# plugins/discipline/tests/conftest.py
"""Pytest fixtures for discipline hook tests."""
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
    """Strip all DISCIPLINE_* env vars so tests start from defaults."""
    for key in list(os.environ):
        if key.startswith("DISCIPLINE_"):
            monkeypatch.delenv(key, raising=False)
    yield monkeypatch
