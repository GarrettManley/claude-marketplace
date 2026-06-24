# plugins/evidence/tests/test_evidence_hmac_extra.py
"""Extra coverage for evidence_hmac.py uncovered branches.

Lines targeted:
  132-133  verify_token: key file missing / bad key -> (False, str(e), None)
  150-151  verify_token: malformed payload JSON -> (False, f"malformed payload: …", None)
  191-192  redeem_token: corrupted redemptions.json -> silently resets to {}
  205-206  redeem_token: OSError writing redemptions.json -> (False, reason)
"""
import base64
import json

import pytest

from evidence_hmac import (
    _b64url,
    _redemptions_path,
    issue_token,
    redeem_token,
    verify_token,
)

ACTION = "secret_scan"


# ---------------------------------------------------------------------------
# verify_token: lines 132-133 — key file missing or bad
# ---------------------------------------------------------------------------

class TestVerifyTokenKeyErrors:
    def test_missing_key_returns_false_not_raises(self, tmp_path):
        """Lines 132-133: FileNotFoundError from _read_key is caught."""
        # Issue a real token first so we have something syntactically valid.
        real_key = tmp_path / "real-key"
        real_key.write_text("a" * 64, encoding="utf-8")
        token = issue_token(ACTION, ttl_seconds=60, key_path=real_key)

        # Now verify with a nonexistent key path — should return False, not raise.
        missing = tmp_path / "nonexistent-key"
        ok, reason, payload = verify_token(token, ACTION, key_path=missing)
        assert not ok
        assert "not found" in reason.lower() or "override key" in reason.lower()
        assert payload is None

    def test_short_key_returns_false_not_raises(self, tmp_path):
        """Lines 132-133: ValueError from _read_key (key too short) is caught."""
        real_key = tmp_path / "real-key"
        real_key.write_text("a" * 64, encoding="utf-8")
        token = issue_token(ACTION, ttl_seconds=60, key_path=real_key)

        short_key = tmp_path / "short-key"
        short_key.write_text("x" * 8, encoding="utf-8")
        ok, reason, payload = verify_token(token, ACTION, key_path=short_key)
        assert not ok
        assert payload is None


# ---------------------------------------------------------------------------
# verify_token: lines 150-151 — malformed payload after valid signature
# ---------------------------------------------------------------------------

class TestVerifyTokenMalformedPayload:
    def _forge_token_with_bad_payload(self, key_file) -> str:
        """Craft a token whose payload is valid base64url but not a JSON object
        with the expected keys, yet whose signature is correct for that payload."""
        import hashlib
        import hmac as hmac_mod

        key = key_file.read_bytes().strip()

        # Payload that is valid JSON but missing required keys
        bad_payload = json.dumps({"action": ACTION}).encode("utf-8")
        payload_b64 = _b64url(bad_payload)
        sig = hmac_mod.new(key, payload_b64.encode("ascii"), hashlib.sha256).digest()
        sig_b64 = _b64url(sig)
        return f"{payload_b64}.{sig_b64}"

    def test_missing_payload_keys_returns_false(self, key_file):
        """Lines 150-151: KeyError in payload parsing -> (False, 'malformed payload…', None)."""
        token = self._forge_token_with_bad_payload(key_file)
        ok, reason, payload = verify_token(token, ACTION, key_path=key_file)
        assert not ok
        assert "malformed payload" in reason
        assert payload is None

    def test_non_json_payload_returns_false(self, key_file):
        """Lines 150-151: JSONDecodeError -> (False, 'malformed payload…', None)."""
        import hashlib
        import hmac as hmac_mod

        key = key_file.read_bytes().strip()
        raw = b"this-is-not-json"
        payload_b64 = _b64url(raw)
        sig = hmac_mod.new(key, payload_b64.encode("ascii"), hashlib.sha256).digest()
        token = f"{payload_b64}.{_b64url(sig)}"

        ok, reason, payload = verify_token(token, ACTION, key_path=key_file)
        assert not ok
        assert "malformed payload" in reason
        assert payload is None


# ---------------------------------------------------------------------------
# redeem_token: lines 191-192 — corrupted redemptions.json silently resets
# ---------------------------------------------------------------------------

class TestRedeemCorruptedRedemptionsFile:
    def test_corrupted_redemptions_json_is_silently_reset(self, key_file):
        """Lines 191-192: (json.JSONDecodeError, OSError) -> existing = {} fallback."""
        token = issue_token(ACTION, ttl_seconds=60, max_uses=2, key_path=key_file)

        # Write garbage into the redemptions file so json.loads fails.
        redemptions_file = _redemptions_path(key_file)
        redemptions_file.write_text("NOT VALID JSON ][", encoding="utf-8")

        # redeem_token should silently treat existing = {} and succeed.
        ok, reason = redeem_token(token, ACTION, key_path=key_file)
        assert ok
        assert "uses_remaining" in reason


# ---------------------------------------------------------------------------
# redeem_token: lines 205-206 — OSError writing redemptions.json
# ---------------------------------------------------------------------------

class TestRedeemPersistError:
    def test_write_failure_returns_false(self, key_file, tmp_path, monkeypatch):
        """Lines 205-206: OSError on write -> (False, 'could not persist…')."""
        token = issue_token(ACTION, ttl_seconds=60, max_uses=2, key_path=key_file)

        # Monkey-patch Path.write_text to raise OSError only for the
        # redemptions file, so the verify step still works fine but the
        # persist step fails.
        redemptions_path = _redemptions_path(key_file)
        original_write_text = redemptions_path.__class__.write_text

        def _failing_write_text(self, *args, **kwargs):
            if self == redemptions_path:
                raise OSError("disk full (simulated)")
            return original_write_text(self, *args, **kwargs)

        monkeypatch.setattr(redemptions_path.__class__, "write_text", _failing_write_text)

        ok, reason = redeem_token(token, ACTION, key_path=key_file)
        assert not ok
        assert "could not persist redemption" in reason
