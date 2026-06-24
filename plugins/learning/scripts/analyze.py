"""Analyze observations.jsonl for tool-use frequency + common sequences.

Phase 2a manual-review analyzer. Pure-function library; the slash command
+ CLI subcommand are the user-facing entry points.

Detection scope:
  - Tool-use frequency (pre-phase only, to avoid double-counting pre+post pairs)
  - Pre→Post tool-pair sequences within a configurable time window (default
    30s) and within the same session
  - Bash command prefixes (first 2 tokens), top-N
  - File hotspots (edited files), top-N

NOT covered (would require richer data or LLM):
  - User-correction patterns (would need transcript access)
  - Tool-outcome analysis (would need consistent tool_response capture; only
    Phase 2a+ records have it)
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from storage import get_observations_file, get_project_id  # noqa: E402


def load_observations(project_id: str | None = None) -> list[dict[str, Any]]:
    pid = project_id or get_project_id()
    obs_file = get_observations_file(pid)
    if not obs_file.is_file():
        return []
    records: list[dict[str, Any]] = []
    try:
        with open(obs_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict):
                    records.append(rec)
    except OSError:
        return []
    return records


def tool_frequency(records: list[dict[str, Any]]) -> dict[str, int]:
    """Count tool invocations. Counts pre-phase only to avoid double-counting
    pre+post pairs.
    """
    counts: Counter[str] = Counter()
    for r in records:
        if r.get("phase") != "pre":
            continue
        name = r.get("tool_name")
        if isinstance(name, str) and name:
            counts[name] += 1
    return dict(counts)


def pre_post_sequences(
    records: list[dict[str, Any]],
    *,
    max_gap_seconds: float = 30.0,
) -> dict[tuple[str, str], int]:
    """Count (tool_A, tool_B) pairs where a `post` event for tool_A is
    followed by a `pre` event for tool_B within max_gap_seconds, in the
    same session.

    Only pairs immediately adjacent in the sequence (per session) are
    counted; this measures "did B happen right after A?" which is the
    interesting signal for workflows like "Grep, then Edit".
    """
    # Sort by timestamp within session
    by_session: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        sid = r.get("session_id") or ""
        by_session.setdefault(str(sid), []).append(r)

    pairs: Counter[tuple[str, str]] = Counter()
    for sid, sess in by_session.items():
        sess_sorted = sorted(sess, key=lambda r: r.get("timestamp", 0))
        # Walk; track most-recent post event and pair with next pre within window
        last_post: dict[str, Any] | None = None
        for r in sess_sorted:
            phase = r.get("phase")
            if phase == "post":
                last_post = r
                continue
            if phase == "pre" and last_post is not None:
                gap = (r.get("timestamp", 0) or 0) - (last_post.get("timestamp", 0) or 0)
                if 0 <= gap <= max_gap_seconds:
                    a = last_post.get("tool_name") or ""
                    b = r.get("tool_name") or ""
                    if a and b:
                        pairs[(a, b)] += 1
                # consume the last_post regardless — we only count immediate pairs
                last_post = None
    return dict(pairs)


def bash_command_prefixes(
    records: list[dict[str, Any]],
    *,
    top_n: int = 10,
) -> list[tuple[str, int]]:
    """Most common Bash command prefixes (first two whitespace-separated tokens).
    Counts pre-phase Bash records only.
    """
    counts: Counter[str] = Counter()
    for r in records:
        if r.get("phase") != "pre" or r.get("tool_name") != "Bash":
            continue
        cmd = (r.get("tool_input") or {}).get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            continue
        tokens = cmd.strip().split()
        prefix = " ".join(tokens[:2]) if len(tokens) >= 2 else tokens[0]
        counts[prefix] += 1
    return counts.most_common(top_n)


def file_hotspots(
    records: list[dict[str, Any]],
    *,
    top_n: int = 10,
) -> list[tuple[str, int]]:
    """Most-edited file paths. Counts Edit/Write/MultiEdit pre-records.

    MultiEdit emits one record but may carry multiple file paths in
    `tool_input.edits[]`; each is counted once.
    """
    edit_tools = {"Edit", "Write", "MultiEdit"}
    counts: Counter[str] = Counter()
    for r in records:
        if r.get("phase") != "pre":
            continue
        name = r.get("tool_name") or ""
        if name not in edit_tools:
            continue
        tinput = r.get("tool_input") or {}
        if name == "MultiEdit":
            for edit in tinput.get("edits") or []:
                if isinstance(edit, dict):
                    fp = edit.get("file_path")
                    if isinstance(fp, str) and fp:
                        counts[fp] += 1
        else:
            fp = tinput.get("file_path")
            if isinstance(fp, str) and fp:
                counts[fp] += 1
    return counts.most_common(top_n)
