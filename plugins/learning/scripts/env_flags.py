"""Shared env-var truthiness helper for learning hooks.

Both `observe.py` (LEARNING_OBSERVE) and `surface.py` (LEARNING_SURFACE) gate on
the same set of "on" spellings; factored here so the accepted values stay in one
place. Also hosts `force_utf8()` — every stdout-printing entry point in this
plugin must call it, because instinct/status output contains non-ASCII (arrows,
block bars) that crashes a cp1252 Windows stdout.
"""
from __future__ import annotations

import os
import sys

_ON_VALUES = frozenset({"1", "true", "on", "yes", "enabled"})


def is_on(name: str, default: str = "") -> bool:
    """True if env var `name` is set to a recognized on-value (case-insensitive)."""
    return (os.environ.get(name, default) or "").strip().lower() in _ON_VALUES


def force_utf8() -> None:
    """Make stdout/stderr UTF-8 so instinct content (→, █░, …) can't crash on a
    cp1252 Windows console or redirected pipe. No-op where reconfigure is
    unavailable (StringIO in tests, exotic streams)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
