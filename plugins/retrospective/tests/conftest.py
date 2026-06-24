# plugins/retrospective/tests/conftest.py
"""Pytest fixtures for retrospective hook tests."""
import sys
from pathlib import Path

# Make the plugin's hooks/ importable in tests.
_PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))
