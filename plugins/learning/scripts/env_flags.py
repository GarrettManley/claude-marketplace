"""Shared env-var truthiness helper for learning hooks.

Both `observe.py` (LEARNING_OBSERVE) and `surface.py` (LEARNING_SURFACE) gate on
the same set of "on" spellings; factored here so the accepted values stay in one
place.
"""
from __future__ import annotations

import os

_ON_VALUES = frozenset({"1", "true", "on", "yes", "enabled"})


def is_on(name: str, default: str = "") -> bool:
    """True if env var `name` is set to a recognized on-value (case-insensitive)."""
    return (os.environ.get(name, default) or "").strip().lower() in _ON_VALUES
