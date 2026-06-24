"""Instinct schema: YAML frontmatter (id/trigger/confidence/domain/source[/source_repo])
followed by Markdown body containing `## Action` and `## Evidence` sections.

We don't depend on PyYAML — the schema is small and controlled, so a minimal
line parser handles it. Supports multi-instinct files separated by `---` lines.

Adapted from affaan-m/everything-claude-code @ 4774946d,
skills/continuous-learning-v2/SKILL.md lines 142-268.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

INSTINCT_FRONTMATTER_FIELDS = ("id", "trigger", "confidence", "domain", "source")
_OPTIONAL_FIELDS = ("source_repo",)


@dataclass
class Instinct:
    id: str
    trigger: str
    confidence: float
    domain: str
    source: str
    source_repo: str | None
    title: str
    action: str
    evidence: str


def _parse_frontmatter(block: str) -> dict[str, str]:
    """Parse flat key: value lines into a dict."""
    fields: dict[str, str] = {}
    for line in block.strip().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if ":" not in s:
            continue
        k, _, v = s.partition(":")
        fields[k.strip()] = v.strip().strip('"').strip("'")
    return fields


def _extract_section(body: str, heading: str) -> str:
    """Extract text under a `## Heading` until the next `## ` or EOF."""
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$(.+?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(body)
    return m.group(1).strip() if m else ""


def parse_instinct(text: str) -> Instinct:
    """Parse a single instinct's text representation."""
    if not text.lstrip().startswith("---"):
        raise ValueError("Instinct must begin with --- frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Instinct frontmatter must be closed with ---")
    _, fm_text, body = parts
    fields = _parse_frontmatter(fm_text)
    for required in INSTINCT_FRONTMATTER_FIELDS:
        if required not in fields:
            raise ValueError(f"Missing required field: {required}")
    try:
        confidence = float(fields["confidence"])
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid confidence value: {fields['confidence']!r}") from e
    if not (0.0 <= confidence <= 1.0):
        raise ValueError(f"Confidence out of [0,1]: {confidence}")
    title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else fields["id"]
    return Instinct(
        id=fields["id"],
        trigger=fields["trigger"],
        confidence=confidence,
        domain=fields["domain"],
        source=fields["source"],
        source_repo=fields.get("source_repo"),
        title=title,
        action=_extract_section(body, "Action"),
        evidence=_extract_section(body, "Evidence"),
    )


def format_instinct(inst: Instinct) -> str:
    """Serialize an Instinct back to text representation."""
    fm_lines = [
        f"id: {inst.id}",
        f"trigger: {inst.trigger}",
        f"confidence: {inst.confidence}",
        f"domain: {inst.domain}",
        f"source: {inst.source}",
    ]
    if inst.source_repo:
        fm_lines.append(f"source_repo: {inst.source_repo}")
    return (
        "---\n"
        + "\n".join(fm_lines)
        + "\n---\n\n"
        + f"# {inst.title}\n\n"
        + "## Action\n\n"
        + inst.action.strip()
        + "\n\n## Evidence\n\n"
        + inst.evidence.strip()
        + "\n"
    )


def parse_multi_instinct_file(text: str) -> list[Instinct]:
    """Parse a file containing one or more instincts.

    Strategy: split on lines that are exactly `---`; the resulting alternating
    pattern is: pre-content (empty for first), fm, body, fm, body, ...
    Re-stitch as ("---\\n" + fm + "\\n---\\n" + body) per instinct.
    """
    # Split on lines that are EXACTLY "---" (with optional whitespace)
    blocks = re.split(r"(?m)^\s*---\s*$\n?", text)
    # blocks[0] is everything before the first ---; for a well-formed instinct
    # file, that's empty or whitespace. Drop it and any other empty leading
    # blocks. The remaining sequence alternates: frontmatter, body, frontmatter, body, ...
    if blocks and not blocks[0].strip():
        blocks = blocks[1:]
    instincts: list[Instinct] = []
    # Walk pairs of (frontmatter, body)
    i = 0
    while i + 1 < len(blocks):
        fm = blocks[i]
        body = blocks[i + 1]
        if not fm.strip():
            i += 1
            continue
        # Reconstruct the canonical single-instinct text and parse
        text_block = f"---\n{fm.strip()}\n---\n\n{body}"
        try:
            instincts.append(parse_instinct(text_block))
        except ValueError:
            # Skip malformed; could be trailing content. Continue.
            pass
        i += 2
    return instincts
