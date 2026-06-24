# plugins/evidence/tests/test_evidence_hmac.py
"""Unit tests for the HMAC override-token framework."""
import json
import time

import pytest

from evidence_hmac import (
    MAX_TTL_SECONDS,
    MAX_USES,
    _redemptions_path,
    issue_token,
    redeem_token,
    verify_token,
)

ACTION = "secret_scan"


class TestIssue:
    def test_issue_verify_redeem_happy_path(self, key_file):
        token = issue_token(ACTION, ttl_seconds=60, max_uses=2, key_path=key_file)
        ok, reason, payload = verify_token(token, ACTION, key_path=key_file)
        assert ok and reason == "valid"
        assert payload.action == ACTION and payload.max_uses == 2
        ok, reason = redeem_token(token, ACTION, key_path=key_file)
        assert ok and "uses_remaining=1" in reason

    def test_ttl_cap_enforced_at_issuance(self, key_file):
        with pytest.raises(ValueError):
            issue_token(ACTION, ttl_seconds=MAX_TTL_SECONDS + 1, key_path=key_file)
        with pytest.raises(ValueError):
            issue_token(ACTION, ttl_seconds=0, key_path=key_file)

    def test_uses_cap_enforced_at_issuance(self, key_file):
        with pytest.raises(ValueError):
            issue_token(ACTION, max_uses=MAX_USES + 1, key_path=key_file)
        with pytest.raises(ValueError):
            issue_token(ACTION, max_uses=0, key_path=key_file)

    def test_action_must_be_identifier(self, key_file):
        with pytest.raises(ValueError):
            issue_token("not an identifier!", key_path=key_file)
        with pytest.raises(ValueError):
            issue_token("", key_path=key_file)

    def test_missing_key_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            issue_token(ACTION, key_path=tmp_path / "nope")

    def test_short_key_rejected(self, tmp_path):
        kf = tmp_path / "short-key"
        kf.write_text("tooshort", encoding="utf-8")
        with pytest.raises(ValueError):
            issue_token(ACTION, key_path=kf)


class TestVerify:
    def test_expired(self, key_file):
        token = issue_token(ACTION, ttl_seconds=60, key_path=key_file)
        ok, reason, _ = verify_token(
            token, ACTION, key_path=key_file, now=int(time.time()) + 3600
        )
        assert not ok and "expired" in reason

    def test_not_yet_valid(self, key_file):
        token = issue_token(ACTION, ttl_seconds=60, key_path=key_file)
        ok, reason, _ = verify_token(
            token, ACTION, key_path=key_file, now=int(time.time()) - 100
        )
        assert not ok and "not yet valid" in reason

    def test_action_mismatch(self, key_file):
        token = issue_token(ACTION, ttl_seconds=60, key_path=key_file)
        ok, reason, _ = verify_token(token, "other_action", key_path=key_file)
        assert not ok and "action mismatch" in reason

    def test_tampered_signature(self, key_file):
        token = issue_token(ACTION, ttl_seconds=60, key_path=key_file)
        payload_b64, sig_b64 = token.split(".", 1)
        flipped = ("A" if sig_b64[0] != "A" else "B") + sig_b64[1:]
        ok, reason, _ = verify_token(f"{payload_b64}.{flipped}", ACTION, key_path=key_file)
        assert not ok and "signature mismatch" in reason

    def test_tampered_payload(self, key_file):
        token = issue_token(ACTION, ttl_seconds=60, key_path=key_file)
        payload_b64, sig_b64 = token.split(".", 1)
        flipped = ("A" if payload_b64[0] != "A" else "B") + payload_b64[1:]
        ok, reason, _ = verify_token(f"{flipped}.{sig_b64}", ACTION, key_path=key_file)
        assert not ok and "signature mismatch" in reason

    def test_malformed_token(self, key_file):
        ok, reason, _ = verify_token("no-dot-here", ACTION, key_path=key_file)
        assert not ok and "malformed token" in reason

    def test_wrong_key(self, key_file, tmp_path):
        token = issue_token(ACTION, ttl_seconds=60, key_path=key_file)
        other = tmp_path / "other-key"
        other.write_text("b" * 64, encoding="utf-8")
        ok, reason, _ = verify_token(token, ACTION, key_path=other)
        assert not ok and "signature mismatch" in reason


class TestRedeem:
    def test_exhaustion_persists_across_calls(self, key_file):
        token = issue_token(ACTION, ttl_seconds=60, max_uses=2, key_path=key_file)
        assert redeem_token(token, ACTION, key_path=key_file)[0] is True
        assert redeem_token(token, ACTION, key_path=key_file)[0] is True
        ok, reason = redeem_token(token, ACTION, key_path=key_file)
        assert not ok and "already exhausted" in reason
        # The exhausted nonce stays on disk at 0 — popping it would let the
        # token redeem again on the next fresh process (the guarded bug class).
        redemptions = json.loads(_redemptions_path(key_file).read_text(encoding="utf-8"))
        assert list(redemptions.values()) == [0]

    def test_invalid_token_does_not_touch_redemptions(self, key_file):
        ok, _ = redeem_token("garbage.token", ACTION, key_path=key_file)
        assert not ok
        assert not _redemptions_path(key_file).is_file()

    def test_independent_tokens_tracked_separately(self, key_file):
        t1 = issue_token(ACTION, ttl_seconds=60, max_uses=1, key_path=key_file)
        t2 = issue_token(ACTION, ttl_seconds=60, max_uses=1, key_path=key_file)
        assert redeem_token(t1, ACTION, key_path=key_file)[0] is True
        assert redeem_token(t1, ACTION, key_path=key_file)[0] is False
        assert redeem_token(t2, ACTION, key_path=key_file)[0] is True
