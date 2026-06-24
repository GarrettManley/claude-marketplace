"""Structural contract for marketplace sub-agents.

Agents (``plugins/*/agents/*.agent.md``) are markdown role-prompts with YAML
frontmatter and no executable code, so the enforceable "behavioral" contract is
structural: every agent must declare valid, discoverable frontmatter and a
non-stub body. These helpers back ``ci/tests/test_agent_contract.py`` and are
stdlib-only (no PyYAML dependency, matching the runtime hooks).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT_GLOB = "plugins/*/agents/*.agent.md"
AGENT_SUFFIX = ".agent.md"
REQUIRED_FIELDS = ("name", "description", "tools")


def iter_agent_paths(root: Path = ROOT) -> list[Path]:
    """Every agent file across all plugins, sorted by path."""
    return sorted(root.glob(AGENT_GLOB))


def agent_stem(path: Path) -> str:
    """The canonical agent id: filename minus the ``.agent.md`` suffix."""
    return path.name[: -len(AGENT_SUFFIX)]


def parse_frontmatter(text: str) -> dict[str, str]:
    """Flat parse of the leading ``---`` frontmatter block (lenient, stdlib-only)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line or line.startswith((" ", "\t")):
            continue
        key, _, value = line.partition(":")
        v = value.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in {"'", '"'}:
            v = v[1:-1]
        fields[key.strip()] = v
    return fields


def body_after_frontmatter(text: str) -> str:
    """Document text after the closing ``---``; '' if the block never closes."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1:])
    return ""


_HEADING_RE = re.compile(r"(?m)^#{1,6}\s+\S")


def has_heading(body: str) -> bool:
    """True if the body has at least one markdown heading (i.e. not an empty stub)."""
    return _HEADING_RE.search(body) is not None


_INDEX_COUNT_RE = re.compile(r"^##\s+Agents\s+\((\d+)\)", re.MULTILINE)


def parse_skill_index_agent_count(index_text: str) -> int | None:
    """The N from docs/skill-index.md's ``## Agents (N)`` header, or None if absent."""
    m = _INDEX_COUNT_RE.search(index_text)
    return int(m.group(1)) if m else None
