"""Regression guard for hb-lv9 -- the CI gate scripts must not inherit stdin.

Root cause: pytest's fd-level capture can leave the Windows STD_INPUT_HANDLE holding
a stale (non-null but closed) handle. `subprocess.run(capture_output=True)` with stdin
left inheriting then resolves that handle and fails DuplicateHandle with
`OSError: [WinError 6] The handle is invalid`. The two gate scripts pin
`stdin=subprocess.DEVNULL`, so the inherited handle is never touched.

This reproduces that exact handle state deterministically (independent of the finicky
pytest-collection ordering that first surfaced it -- the combined-invocation flake only
fires for specific module sets, so a meta-test that shells out to pytest would be an
unreliable guard). Windows-only; the STD_INPUT_HANDLE mechanism does not exist elsewhere.
"""
from __future__ import annotations

import ctypes
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

CI = Path(__file__).resolve().parent.parent
ROOT = CI.parent

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="STD_INPUT_HANDLE inheritance bug is Windows-only",
)

STD_INPUT_HANDLE = -10


def _load(modname: str, filename: str):
    spec = importlib.util.spec_from_file_location(modname, CI / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


class _StaleStdin:
    """Point STD_INPUT_HANDLE at a stale (closed, non-null) handle -- exactly the state
    pytest's fd capture can leave behind -- and restore it on exit."""

    def __enter__(self):
        import msvcrt

        self._k = ctypes.WinDLL("kernel32", use_last_error=True)
        self._k.GetStdHandle.restype = ctypes.c_void_p
        self._k.SetStdHandle.argtypes = [ctypes.c_ulong, ctypes.c_void_p]
        self._saved = self._k.GetStdHandle(STD_INPUT_HANDLE)
        fd = os.open(os.devnull, os.O_RDONLY)
        stale = msvcrt.get_osfhandle(fd)
        os.close(fd)  # 'stale' is now non-null but refers to a closed handle
        self._set(stale)
        return self

    def __exit__(self, *exc):
        self._set(self._saved)  # always restore, even when the body raised
        return False

    def _set(self, handle):
        # Check the BOOL return: a failed restore would silently leave every later
        # test in this process with a broken stdin handle -- fail loud instead.
        if not self._k.SetStdHandle(STD_INPUT_HANDLE, ctypes.c_void_p(handle)):
            raise ctypes.WinError(ctypes.get_last_error())


def _stale_stdin_reproduces() -> "int | None":
    """Return the OSError.winerror an inherited-stdin capture_output call raises under
    a stale STD_INPUT_HANDLE, or None if this interpreter tolerates it. CPython >= 3.13
    fails DuplicateHandle (WinError 6); 3.12 does not exhibit the failure at all, so the
    mechanism this file guards is not reproducible there (the stdin=DEVNULL fix still
    applies to every version regardless)."""
    with _StaleStdin():
        try:
            subprocess.run(["git", "--version"], capture_output=True, text=True)
        except OSError as e:
            return e.winerror
    return None


def test_stale_stdin_handle_is_actually_broken():
    """Control: with a stale STD_INPUT_HANDLE, an inherited-stdin capture_output call
    really raises WinError 6 -- so the survives-tests can't pass vacuously. Skips on
    interpreters that tolerate the stale handle (CPython 3.12), where there is no
    failure to guard against."""
    winerror = _stale_stdin_reproduces()
    if winerror is None:
        pytest.skip("this CPython build tolerates a stale inherited stdin handle; "
                    "the WinError-6 mechanism is not reproducible here (e.g. CPython 3.12)")
    # Assert the specific WinError: a bare OSError could be FileNotFoundError (git
    # absent), which would let this control pass without the stale-handle firing.
    assert winerror == 6


def test_check_notice_survives_stale_stdin_handle():
    cn = _load("check_notice", "check-notice.py")
    with _StaleStdin():
        cn.triggering_files()  # git grep; must not raise OSError WinError 6


def test_check_doc_links_survives_stale_stdin_handle():
    cd = _load("check_doc_links", "check-doc-links.py")
    with _StaleStdin():
        cd.tracked_markdown()  # git ls-files; must not raise OSError WinError 6
