# plugins/orchestration/tests/conftest.py
"""Pytest configuration for orchestration plugin tests."""
import sys
from pathlib import Path

# Make hooks/ importable by bare name
_PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))
