# plugins/evidence/tests/test_secret_scan_extra.py
"""Extra coverage for secret_scan.py uncovered branch.

Line targeted:
  84-85  check_override: ImportError on 'from evidence_hmac import redeem_token'
         -> return False immediately (the import guard branch).
"""
import io
import json
import sys

import pytest

from secret_scan import check_override


class TestCheckOverrideImportError:
    def test_import_error_returns_false(self, monkeypatch):
        """Lines 84-85: when evidence_hmac cannot be imported, check_override returns False."""
        # Set a non-empty token so the function doesn't short-circuit at the
        # 'if not token' guard (line 80).
        monkeypatch.setenv("EVIDENCE_OVERRIDE_TOKEN", "some.token")

        # Remove evidence_hmac from sys.modules and block re-import by
        # temporarily replacing it with a broken entry.
        real_mod = sys.modules.pop("evidence_hmac", None)

        # Insert a None sentinel — Python raises ImportError on `from None import …`
        sys.modules["evidence_hmac"] = None  # type: ignore[assignment]

        try:
            result = check_override()
        finally:
            # Restore original module state regardless of test outcome.
            if real_mod is not None:
                sys.modules["evidence_hmac"] = real_mod
            else:
                sys.modules.pop("evidence_hmac", None)

        assert result is False
