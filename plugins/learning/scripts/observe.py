"""PreToolUse + PostToolUse observation hook.

When LEARNING_OBSERVE=on, appends a JSONL record per tool invocation to
the per-project observations file. Default is OFF (no env var → silent skip).

The observation schema is minimal: timestamp + tool_name + tool_input.
Phase 2 (future PR) adds the analysis layer that converts observations to instincts.

Adapted from affaan-m/everything-claude-code @ 4774946d,
skills/continuous-learning-v2/hooks/observe.sh (bash → Python).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from env_flags import is_on  # noqa: E402
from storage import get_observations_file, get_project_id  # noqa: E402

# Cap for stored tool_response payloads. Uncapped, verbatim responses (full
# Read outputs, command dumps) dominate observations.jsonl — measured ~90% of
# a 106 MB file. The only consumer that looks inside tool_response is
# detect._looks_like_error's substring scan, which works fine on a head slice.
RESPONSE_MAX_CHARS = 2000


def _is_enabled() -> bool:
    return is_on("LEARNING_OBSERVE")


def cap_tool_response(tool_response: Any, max_chars: int = RESPONSE_MAX_CHARS) -> Any:
    """Return tool_response unchanged if small, else a truncated marker dict.

    The marker keeps the head of the serialized payload so error/traceback
    markers (which lead the payload) stay greppable.
    """
    serialized = json.dumps(tool_response, default=str)
    if len(serialized) <= max_chars:
        return tool_response
    return {"truncated": True, "text": serialized[:max_chars]}


def _build_observation(event: dict[str, Any], phase: str) -> dict[str, Any]:
    obs: dict[str, Any] = {
        "timestamp": time.time(),
        "phase": phase,
        "tool_name": event.get("tool_name") or "",
        "tool_input": event.get("tool_input") or {},
        "session_id": event.get("session_id") or "",
    }
    # Phase 2a additions: capture outcome data on PostToolUse + a per-call ID
    # for matching pre/post pairs. Both fields are optional.
    tool_use_id = event.get("tool_use_id") or event.get("toolUseId")
    if isinstance(tool_use_id, str) and tool_use_id:
        obs["tool_use_id"] = tool_use_id
    if phase == "post":
        tool_response = event.get("tool_response")
        if tool_response is not None:
            obs["tool_response"] = cap_tool_response(tool_response)
    return obs


def _detect_phase(event: dict[str, Any], argv: list[str]) -> str:
    # Canonical signal: Claude Code includes "hook_event_name" in the stdin JSON
    # for PreToolUse / PostToolUse events. This is the only reliable source in
    # production -- the wrapper (run_with_flags.py) imports observe and calls
    # main() without setting sys.argv, and CLAUDE_HOOK_EVENT_NAME is not a CC
    # env var, so the argv/env paths below only fire in direct-invocation tests.
    name = str(event.get("hook_event_name") or "").lower()
    if name.startswith("pretool"):
        return "pre"
    if name.startswith("posttool"):
        return "post"
    # Fallbacks for direct invocation (tests / manual runs).
    if len(argv) > 1 and argv[1] in ("pre", "post"):
        return argv[1]
    env_name = (os.environ.get("CLAUDE_HOOK_EVENT_NAME") or "").lower()
    if "pretooluse" in env_name or env_name == "pre":
        return "pre"
    return "post"


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv
    if not _is_enabled():
        return 0
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return 0
    if not isinstance(event, dict):
        return 0
    phase = _detect_phase(event, argv)
    obs = _build_observation(event, phase)
    obs_file = get_observations_file(get_project_id())
    try:
        obs_file.parent.mkdir(parents=True, exist_ok=True)
        with open(obs_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(obs) + "\n")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
