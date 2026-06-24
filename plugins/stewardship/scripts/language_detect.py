"""Per-language project-root + language detection for stewardship's
edit-accumulator + Stop format/typecheck hooks.

Detection strategy:
1. File extension determines candidate language.
2. Walk upward from the file's directory looking for the language's
   repo marker (tsconfig.json / pyproject.toml / Cargo.toml).
3. If no marker found, fall back to extension-only language assignment
   (still useful for one-off scripts; find_project_root returns None).

Returns canonical language names: "typescript", "python", "rust".
"""
from __future__ import annotations

from pathlib import Path

LANGUAGES: dict[str, dict] = {
    "typescript": {
        "extensions": {".ts", ".tsx", ".js", ".jsx", ".mts", ".cts"},
        "markers": ("tsconfig.json", "package.json"),
    },
    "python": {
        "extensions": {".py", ".pyi"},
        "markers": ("pyproject.toml", "setup.py", "setup.cfg"),
    },
    "rust": {
        "extensions": {".rs"},
        "markers": ("Cargo.toml",),
    },
}


def detect_language(file_path: Path | str) -> str | None:
    p = Path(file_path)
    ext = p.suffix.lower()
    for lang, spec in LANGUAGES.items():
        if ext in spec["extensions"]:
            return lang
    return None


def find_project_root(file_path: Path | str, language: str) -> Path | None:
    p = Path(file_path).resolve()
    markers = LANGUAGES.get(language, {}).get("markers", ())
    if not markers:
        return None
    dir_ = p.parent if p.is_file() or not p.exists() else p
    fs_root = Path(dir_.anchor)
    depth = 0
    while dir_ != fs_root and depth < 30:
        for marker in markers:
            if (dir_ / marker).exists():
                return dir_
        dir_ = dir_.parent
        depth += 1
    return None
