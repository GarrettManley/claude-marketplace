"""Tests for env_flags: is_on truthiness (all accepted spellings) + force_utf8.

Closes the #40 coverage gap: previously only one of the five accepted on-values
was exercised anywhere in the suite.
"""
import io
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import env_flags  # noqa: E402
from env_flags import force_utf8, is_on  # noqa: E402


# --- is_on ---


@pytest.mark.parametrize("value", ["1", "true", "on", "yes", "enabled"])
def test_is_on_accepts_every_documented_spelling(monkeypatch, value):
    monkeypatch.setenv("LEARNING_TEST_FLAG", value)
    assert is_on("LEARNING_TEST_FLAG") is True


@pytest.mark.parametrize("value", ["TRUE", "On", " yes ", "ENABLED"])
def test_is_on_is_case_and_whitespace_insensitive(monkeypatch, value):
    monkeypatch.setenv("LEARNING_TEST_FLAG", value)
    assert is_on("LEARNING_TEST_FLAG") is True


@pytest.mark.parametrize("value", ["", "0", "false", "off", "no", "disabled", "yep"])
def test_is_on_rejects_off_and_unrecognized_values(monkeypatch, value):
    monkeypatch.setenv("LEARNING_TEST_FLAG", value)
    assert is_on("LEARNING_TEST_FLAG") is False


def test_is_on_unset_uses_default(monkeypatch):
    monkeypatch.delenv("LEARNING_TEST_FLAG", raising=False)
    assert is_on("LEARNING_TEST_FLAG") is False
    assert is_on("LEARNING_TEST_FLAG", default="on") is True


# --- force_utf8 ---


def test_force_utf8_is_safe():
    force_utf8()  # must never raise, even where streams can't be reconfigured


def test_force_utf8_swallows_missing_reconfigure(monkeypatch):
    monkeypatch.setattr(env_flags.sys, "stdout", io.StringIO())  # no .reconfigure
    monkeypatch.setattr(env_flags.sys, "stderr", io.StringIO())
    force_utf8()  # AttributeError swallowed, no raise


def test_force_utf8_reconfigures_cp1252_stream(monkeypatch):
    buf = io.BytesIO()
    wrapper = io.TextIOWrapper(buf, encoding="cp1252")
    monkeypatch.setattr(env_flags.sys, "stdout", wrapper)
    force_utf8()
    wrapper.write("→█░")  # would raise UnicodeEncodeError under cp1252
    wrapper.flush()
    assert buf.getvalue().decode("utf-8") == "→█░"
