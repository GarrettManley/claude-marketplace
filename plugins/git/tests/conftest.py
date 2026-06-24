# plugins/git/tests/conftest.py
"""Pytest fixtures for git plugin tests."""
import sys
from pathlib import Path

# Make the commit-message scripts importable by bare name (e.g. `import validate`)
_SCRIPTS_DIR = Path(__file__).parent.parent / "skills" / "commit-message" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))
