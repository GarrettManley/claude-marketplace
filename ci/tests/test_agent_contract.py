"""Structural contract suite for every marketplace sub-agent.

Agents (``plugins/*/agents/*.agent.md``) are markdown role-prompts with no
executable code, so there is no deterministic, CI-safe way to exercise their
*runtime* behavior (that would need a live model). What we CAN enforce — and what
silently rots otherwise — is the structural contract: valid frontmatter, an id
that matches the filename, a non-stub body, and discoverability via the generated
skill index. This is a repo-wide invariant (it spans all agent-bearing plugins),
so it lives in ``ci/tests`` alongside the other cross-cutting checks rather than
under any single plugin. Parametrizing over a glob means new agents are covered
automatically.

``agent_contract.py`` is loaded by path (mirroring ``test_release.py``) because
``ci`` is not an importable package under ``--import-mode=importlib``.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

CI = Path(__file__).resolve().parent.parent
ROOT = CI.parent


def _load(modname: str, filename: str):
    spec = importlib.util.spec_from_file_location(modname, CI / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


ac = _load("agent_contract", "agent_contract.py")

AGENTS = ac.iter_agent_paths()
AGENT_IDS = [ac.agent_stem(p) for p in AGENTS]


def test_agents_discovered():
    # 16 review archetypes + 4 plugin agents (aether/discipline/orchestration/
    # stewardship). The floor guards against a glob that silently finds nothing.
    assert len(AGENTS) >= 20


@pytest.mark.parametrize("path", AGENTS, ids=AGENT_IDS)
class TestAgentContract:
    def test_required_frontmatter_fields(self, path):
        fm = ac.parse_frontmatter(path.read_text(encoding="utf-8"))
        for field in ac.REQUIRED_FIELDS:
            assert fm.get(field), f"{path.name}: missing/empty frontmatter `{field}:`"

    def test_name_matches_filename(self, path):
        fm = ac.parse_frontmatter(path.read_text(encoding="utf-8"))
        assert fm.get("name") == ac.agent_stem(path)

    def test_body_is_not_a_stub(self, path):
        body = ac.body_after_frontmatter(path.read_text(encoding="utf-8"))
        assert ac.has_heading(body), f"{path.name}: body has no markdown heading"

    def test_registered_in_skill_index(self, path):
        index = (ROOT / "docs" / "skill-index.md").read_text(encoding="utf-8")
        assert ac.agent_stem(path) in index, (
            f"{path.name}: not listed in docs/skill-index.md "
            "(run: python3 ci/gen-skill-index.py --write)"
        )


def test_skill_index_agent_count_matches_files():
    index = (ROOT / "docs" / "skill-index.md").read_text(encoding="utf-8")
    assert ac.parse_skill_index_agent_count(index) == len(AGENTS)


# --- helper branch coverage (synthetic inputs) --------------------------------


class TestHelpers:
    def test_parse_frontmatter_no_block(self):
        assert ac.parse_frontmatter("") == {}
        assert ac.parse_frontmatter("no frontmatter here") == {}

    def test_parse_frontmatter_skips_and_unquotes(self):
        text = (
            "---\n"
            "# a comment\n"
            "\n"
            "name: 'x'\n"
            "  indented: y\n"
            "nocolon\n"
            'desc: "q"\n'
            "---\n"
            "body"
        )
        assert ac.parse_frontmatter(text) == {"name": "x", "desc": "q"}

    def test_body_after_frontmatter_no_block_returns_text(self):
        assert ac.body_after_frontmatter("plain") == "plain"

    def test_body_after_frontmatter_unterminated_returns_empty(self):
        assert ac.body_after_frontmatter("---\nname: x\nstill open") == ""

    def test_has_heading_true_and_false(self):
        assert ac.has_heading("## A heading\ntext") is True
        assert ac.has_heading("just prose, no heading") is False

    def test_skill_index_count_present_and_absent(self):
        assert ac.parse_skill_index_agent_count("## Agents (7)\n| ... |") == 7
        assert ac.parse_skill_index_agent_count("no header here") is None
