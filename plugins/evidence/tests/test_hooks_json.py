"""Guards that plugins/evidence/hooks/hooks.json's PreToolUse matchers stay in
sync with the tool names each hook's extractor actually handles — a hook whose
extractor covers a tool but whose matcher doesn't is silently inert in
production even though its unit tests (which call the extractor directly) pass.
"""
import json
from pathlib import Path

HOOKS_JSON = Path(__file__).parent.parent / "hooks" / "hooks.json"


def _matchers():
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    return {
        entry["hooks"][0]["command"]: set(entry["matcher"].split("|"))
        for entry in data["hooks"]["PreToolUse"]
    }


def test_secret_scan_matcher_includes_notebook_edit():
    matchers = _matchers()
    secret_scan = next(cmd for cmd in matchers if "secret_scan.py" in cmd)
    assert "NotebookEdit" in matchers[secret_scan]


def test_scope_bind_matcher_includes_notebook_edit():
    matchers = _matchers()
    scope_bind = next(cmd for cmd in matchers if "scope_bind.py" in cmd)
    assert "NotebookEdit" in matchers[scope_bind]
