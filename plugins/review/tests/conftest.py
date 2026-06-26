# plugins/review/tests/conftest.py
"""Pytest fixtures for review plugin tests."""
import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PLUGIN_ROOT / "scripts"))
