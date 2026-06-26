"""Phase 2d: mine retrospectives into instincts (Claude-driven).

The intelligence lives in the `/instinct-from-retro` command, where Claude reads
the friction summary this module dumps, clusters recurring `*Rule:*` lines across
retros, and hands candidate instincts back to `--ingest`. Here we only:

  * `--dump-retros`: deterministically parse the structured retro files and emit a
    JSON friction summary (one entry per rule-bearing `## Friction / bugs` item),
  * `--ingest <file>`: validate Claude-authored candidates, force them into the
    `retro-mined` band (capped confidence), and write them idempotently.

This closes the previously write-only retrospective loop: friction Rules become
machine-owned instincts that `surface.py` injects at SessionStart, and that
`evolve`/`prune` maintain like any other machine instinct.

Mirrors `detect.py` (the `command = judgment / script = mechanical` split).
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from instinct_schema import (  # noqa: E402
    MAX_CONF_DETECTED,
    Instinct,
    parse_multi_instinct_file,
)
from synthesize import get_target_dir, write_instincts  # noqa: E402

_RETRO_SOURCE = "retro-mined"

# Sub-labels inside a friction entry; values are wrapped like `*Root cause:* text`
# (italic) or `**Root cause:** text` (bold), optionally with a parenthetical before
# the colon, e.g. `*Rule (generalizable):*`.
_SUBLABELS = {
    "what_happened": "What happened",
    "root_cause": "Root cause",
    "how_caught": "How caught",
    "rule": "Rule",
}


@dataclass
class FrictionEntry:
    header: str
    what_happened: str | None
    root_cause: str | None
    how_caught: str | None
    rule: str | None


@dataclass
class RetroDoc:
    slug: str
    date: str | None
    friction: list[FrictionEntry]


def _friction_section(text: str) -> str:
    """Text under the `## Friction / bugs` heading until the next `## ` or EOF."""
    m = re.search(
        r"^##\s+Friction\b.*?$(.+?)(?=^##\s+|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    return m.group(1) if m else ""


def _split_entries(section: str) -> list[str]:
    """Split a friction section into per-entry blocks on top-level `- **...` bullets."""
    starts = [m.start() for m in re.finditer(r"^- \*\*", section, re.MULTILINE)]
    if not starts:
        return []
    bounds = starts + [len(section)]
    return [section[bounds[i]:bounds[i + 1]] for i in range(len(starts))]


def _sublabel(entry: str, label: str) -> str | None:
    """Pull the value of an italic/bold `*Label[...]:* value` sub-bullet."""
    m = re.search(
        rf"\*+\s*{re.escape(label)}[^:*]*:\s*\*+\s*(.+)",
        entry,
        re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


def parse_retro(text: str, *, slug: str = "") -> RetroDoc:
    """Parse one retro's header date + structured friction entries.

    Degrades gracefully: a retro without a `## Friction / bugs` section (or whose
    entries don't match the template) yields an empty friction list, never raises.
    """
    date_match = re.search(r"^\*\*Date:\*\*\s*(.+)$", text, re.MULTILINE)
    date = date_match.group(1).strip() if date_match else None

    friction: list[FrictionEntry] = []
    for block in _split_entries(_friction_section(text)):
        header_match = re.search(r"\*\*(.+?)\*\*", block)
        header = header_match.group(1).strip() if header_match else ""
        friction.append(
            FrictionEntry(
                header=header,
                what_happened=_sublabel(block, _SUBLABELS["what_happened"]),
                root_cause=_sublabel(block, _SUBLABELS["root_cause"]),
                how_caught=_sublabel(block, _SUBLABELS["how_caught"]),
                rule=_sublabel(block, _SUBLABELS["rule"]),
            )
        )
    return RetroDoc(slug=slug, date=date, friction=friction)


def build_retro_summary(retros_dir: Path) -> dict:
    """A compact, JSON-serializable view of rule-bearing friction for Claude.

    Only entries that carry a `*Rule:*` surface (a rule-less entry isn't an
    actionable instinct). `parsed_empty` counts retros that yielded zero such
    entries — visibility into template drift, not a silent drop.
    """
    retros: list[dict] = []
    parsed_empty = 0
    total_rules = 0
    for path in sorted(Path(retros_dir).glob("*.md")):
        doc = parse_retro(path.read_text(encoding="utf-8"), slug=path.stem)
        rule_entries = [e for e in doc.friction if e.rule]
        if not rule_entries:
            parsed_empty += 1
            continue
        total_rules += len(rule_entries)
        retros.append({
            "slug": doc.slug,
            "date": doc.date,
            "friction": [
                {
                    "what_happened": e.what_happened,
                    "root_cause": e.root_cause,
                    "how_caught": e.how_caught,
                    "rule": e.rule,
                }
                for e in rule_entries
            ],
        })
    return {"retros": retros, "parsed_empty": parsed_empty, "total_rules": total_rules}


def normalize_candidate(inst: Instinct) -> Instinct:
    """Force a Claude-authored candidate into the retro band: source is set to
    `retro-mined` and confidence is capped at `MAX_CONF_DETECTED`.
    """
    return replace(
        inst,
        source=_RETRO_SOURCE,
        confidence=min(inst.confidence, MAX_CONF_DETECTED),
    )


def ingest_candidates(text: str, target_dir: Path, *, apply: bool) -> dict:
    """Parse candidate instincts, normalize to the retro band, and write."""
    candidates = [normalize_candidate(i) for i in parse_multi_instinct_file(text)]
    return write_instincts(candidates, target_dir, dry_run=not apply)


def cmd_retro_mine(
    *,
    scope: str = "project",
    dump_retros: bool = False,
    retros_dir: str = "retrospectives/done",
    ingest_path: str | None = None,
    apply: bool = False,
) -> int:
    if dump_retros:
        print(json.dumps(build_retro_summary(Path(retros_dir)), indent=2))
        return 0
    if ingest_path:
        text = Path(ingest_path).read_text(encoding="utf-8")
        counts = ingest_candidates(text, get_target_dir(scope), apply=apply)
        verb = "wrote" if apply else "would write"
        print(
            f"retro-mine: {verb} {counts['written']} new + {counts['updated']} updated, "
            f"{counts['skipped']} skipped (retro-mined, capped at {MAX_CONF_DETECTED})."
        )
        if not apply:
            print("dry-run: pass --apply to persist.")
        return 0
    print("retro-mine: pass --dump-retros or --ingest <file>.")
    return 1
