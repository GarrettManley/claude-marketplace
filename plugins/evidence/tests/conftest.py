# plugins/evidence/tests/conftest.py
"""Pytest fixtures for evidence plugin tests."""
import os
import sys
from pathlib import Path

import pytest

# Make plugin's scripts/ and hooks/ importable in tests
_PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PLUGIN_ROOT / "scripts"))
sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))


@pytest.fixture
def key_file(tmp_path):
    """A valid override key (64 hex chars) at a temp path."""
    kf = tmp_path / "override-key"
    kf.write_text("a" * 64, encoding="utf-8")
    return kf


@pytest.fixture
def clean_env(monkeypatch):
    """Strip evidence-related env vars so tests start from defaults."""
    for key in list(os.environ):
        if key.startswith("EVIDENCE_"):
            monkeypatch.delenv(key, raising=False)
    yield monkeypatch
