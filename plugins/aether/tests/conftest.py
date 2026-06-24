# plugins/aether/tests/conftest.py
"""Pytest fixtures for aether plugin tests."""
import os
import sys
from pathlib import Path

import pytest

# Make plugin's scripts/ and hooks/ importable by bare module name
_PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PLUGIN_ROOT / "scripts"))
sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))


@pytest.fixture
def aether_checkout(tmp_path: Path) -> Path:
    """A synthetic Aether checkout with core/Cargo.toml marker and representative files.

    The directory is deliberately named something unrelated to the original repo
    to confirm that name-independent marker-based root detection works.
    """
    root = tmp_path / "acme-engine"
    (root / "core" / "src").mkdir(parents=True)
    (root / "core" / "target" / "release").mkdir(parents=True)
    (root / "src" / "llm").mkdir(parents=True)
    (root / "core" / "Cargo.toml").write_text("[package]\nname='core'\n", encoding="utf-8")
    (root / "core" / "src" / "main.rs").write_text("fn main() {}\n", encoding="utf-8")
    (root / "core" / "target" / "release" / "core.exe").write_text("", encoding="utf-8")
    (root / "src" / "dm.ts").write_text("// dm\n", encoding="utf-8")
    (root / "src" / "bus.ts").write_text("// bus\n", encoding="utf-8")
    (root / "src" / "server.ts").write_text("// server\n", encoding="utf-8")
    (root / "src" / "actor.ts").write_text("// actor\n", encoding="utf-8")
    (root / "src" / "roll-proposal.ts").write_text("// roll\n", encoding="utf-8")
    (root / "src" / "state-sync.ts").write_text("// sync\n", encoding="utf-8")
    (root / "src" / "llm" / "classifier_prompt.ts").write_text("// clf\n", encoding="utf-8")
    (root / "src" / "llm" / "ollama.ts").write_text("// ollama\n", encoding="utf-8")
    (root / "src" / "llm" / "gemini.ts").write_text("// gemini\n", encoding="utf-8")
    (root / "src" / "llm" / "schemas.ts").write_text("// schemas\n", encoding="utf-8")
    (root / "src" / "llm" / "provider.ts").write_text("// provider\n", encoding="utf-8")
    (root / "README.md").write_text("# acme\n", encoding="utf-8")
    return root
