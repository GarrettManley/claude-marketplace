# plugins/evidence/tests/test_secret_scan.py
"""Unit tests for the secret_scan PreToolUse hook.

All credential fixtures are constructed by concatenation at runtime so this
file never contains a contiguous secret-shaped string — that keeps the repo
clean for scanners (including the secret_scan hook itself when this file is
written by an agent).
"""
import io
import json
import sys

import pytest

from secret_scan import PATTERNS, check_text, extract_text, main
from evidence_hmac import issue_token

# label -> sample that must MATCH that pattern (built non-contiguously)
POSITIVE_SAMPLES = {
    "AWS Access Key ID": "AKIA" + "ABCDEFGHIJKLMNOP",
    "AWS Secret (regex)": "aws_secret_access_key = " + "A" * 40,
    "GitHub PAT (classic)": "ghp_" + "a" * 36,
    "GitHub OAuth": "gho_" + "b" * 36,
    "GitHub User Token": "ghu_" + "c" * 36,
    "GitHub Server Token": "ghs_" + "d" * 36,
    "GitHub Refresh Token": "ghr_" + "e" * 36,
    "OpenAI API Key": "sk-" + "proj-" + "f" * 24,
    "Anthropic API Key": "sk-" + "ant-" + "g" * 24,
    "Stripe Live Key": "sk_live_" + "h" * 24,
    "Slack Bot Token": "xoxb-" + "1234567890-" + "i" * 12,
    "Slack User Token": "xoxp-" + "0987654321-" + "j" * 12,
    "Generic Bearer (regex)": "Bearer " + "k" * 48,
    "Private Key Block": "-----BEGIN " + "RSA PRIVATE" + " KEY-----",
}

NEGATIVE_TEXTS = [
    "AKIA1234",  # too short
    "ghp_short",
    "plain prose about aws secret keys without a literal value",
    "sk_live_",  # prefix only
    "Bearer short",
    "echo hello world",
    "",
]


class TestPatterns:
    @pytest.mark.parametrize("label", [label for label, _, _ in PATTERNS])
    def test_each_pattern_has_a_matching_positive(self, label):
        sample = POSITIVE_SAMPLES[label]
        hits = check_text(sample)
        assert any(hit_label == label for hit_label, _ in hits), (
            f"{label!r} did not match its positive sample"
        )

    @pytest.mark.parametrize("text", NEGATIVE_TEXTS)
    def test_negatives_are_clean(self, text):
        assert check_text(text) == []

    def test_anthropic_key_also_matches_openai_pattern(self):
        # Known, pinned behavior: the OpenAI pattern sk-[A-Za-z0-9_-]{20,}
        # is a superset that also matches Anthropic sk-ant-* keys, so an
        # Anthropic key yields BOTH labels. The block decision is identical
        # either way; this test documents the overlap rather than "fixing" it.
        hits = check_text(POSITIVE_SAMPLES["Anthropic API Key"])
        labels = {label for label, _ in hits}
        assert labels == {"OpenAI API Key", "Anthropic API Key"}


class TestExtractText:
    def test_bash(self):
        assert extract_text("Bash", {"command": "echo hi"}) == "echo hi"

    def test_write(self):
        out = extract_text("Write", {"content": "body", "file_path": "f.txt"})
        assert "body" in out and "f.txt" in out

    def test_edit(self):
        out = extract_text("Edit", {"new_string": "new", "file_path": "f.txt"})
        assert "new" in out and "f.txt" in out

    def test_multiedit(self):
        out = extract_text(
            "MultiEdit",
            {"file_path": "f.txt", "edits": [{"new_string": "one"}, {"new_string": "two"}]},
        )
        assert "one" in out and "two" in out and "f.txt" in out

    def test_webfetch(self):
        assert "example.com" in extract_text("WebFetch", {"url": "https://example.com"})

    def test_unknown_tool_yields_empty(self):
        assert extract_text("Glob", {"pattern": "**/*.py"}) == ""


def test_extract_text_covers_notebook_edit():
    secret = "AKIA" + "ABCDEFGHIJKLMNOP"
    text = extract_text("NotebookEdit", {"new_source": secret, "notebook_path": "n.ipynb"})
    assert secret in text
    assert check_text(text)  # the secret is now detected


def _run_main(monkeypatch, payload) -> int:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    return main()


class TestMain:
    def test_clean_command_passes(self, clean_env, capsys):
        rc = _run_main(clean_env, {"tool_name": "Bash", "tool_input": {"command": "ls"}})
        assert rc == 0
        assert capsys.readouterr().err == ""

    def test_detection_blocks_with_exit_2(self, clean_env, capsys):
        cmd = f"export TOKEN={POSITIVE_SAMPLES['GitHub PAT (classic)']}"
        rc = _run_main(clean_env, {"tool_name": "Bash", "tool_input": {"command": cmd}})
        assert rc == 2
        assert "Blocked: secret_scan detected" in capsys.readouterr().err

    def test_block_message_redacts_secret(self, clean_env, capsys):
        secret = POSITIVE_SAMPLES["GitHub PAT (classic)"]
        rc = _run_main(
            clean_env, {"tool_name": "Write", "tool_input": {"content": secret, "file_path": "x"}}
        )
        err = capsys.readouterr().err
        assert rc == 2
        assert secret not in err  # never echo the full match
        assert secret[:8] in err  # 8-char preview only

    def test_malformed_stdin_passes(self, clean_env, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
        assert main() == 0

    def test_empty_input_passes(self, clean_env, monkeypatch):
        rc = _run_main(clean_env, {"tool_name": "Bash", "tool_input": {}})
        assert rc == 0

    def test_override_token_allows(self, clean_env, key_file, capsys):
        clean_env.setenv("EVIDENCE_OVERRIDE_KEY", str(key_file))
        token = issue_token("secret_scan", ttl_seconds=60, max_uses=1, key_path=key_file)
        clean_env.setenv("EVIDENCE_OVERRIDE_TOKEN", token)
        cmd = f"export TOKEN={POSITIVE_SAMPLES['GitHub PAT (classic)']}"
        rc = _run_main(clean_env, {"tool_name": "Bash", "tool_input": {"command": cmd}})
        assert rc == 0
        assert "override token redeemed" in capsys.readouterr().err

    def test_exhausted_override_still_blocks(self, clean_env, key_file, capsys):
        clean_env.setenv("EVIDENCE_OVERRIDE_KEY", str(key_file))
        token = issue_token("secret_scan", ttl_seconds=60, max_uses=1, key_path=key_file)
        clean_env.setenv("EVIDENCE_OVERRIDE_TOKEN", token)
        cmd = f"export TOKEN={POSITIVE_SAMPLES['GitHub PAT (classic)']}"
        assert _run_main(clean_env, {"tool_name": "Bash", "tool_input": {"command": cmd}}) == 0
        capsys.readouterr()
        # Single-use token burned by the first redemption -> second call blocks.
        assert _run_main(clean_env, {"tool_name": "Bash", "tool_input": {"command": cmd}}) == 2
