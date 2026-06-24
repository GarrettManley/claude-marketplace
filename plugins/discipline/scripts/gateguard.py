"""GateGuard fact-forcing PreToolUse hook for discipline@garrettmanley.

Adapted from affaan-m/everything-claude-code @ 4774946d, scripts/hooks/
gateguard-fact-force.js (MIT licensed). Python port reuses
discipline's run_with_flags.py wrapper (PR #9) for profile/disable
gating; the script itself is invoked in-process via importlib.

Behavior (hb-of7 retarget):
  - Edit/Write/MultiEdit: deny the first touch per CODE file per session
    until the agent presents importers + schemas + the user instruction.
    Prose files (.md/.markdown/.txt/.rst) are exempt — the gate's questions
    don't map to docs, so gating them only trains rote fact-recital. The
    config trio CLAUDE.md/AGENTS.md/GEMINI.md stays gated (binding instructions).
  - Bash (destructive): deny rm -rf, git push --force, drop table, dd if=
    until the agent presents targets + rollback + the user instruction.
  - Bash (routine): passes through. The former once-per-session routine gate
    forced no investigation and was dropped as pure friction.

Disable:
  - DISCIPLINE_GATEGUARD=off (project convention)
  - GATEGUARD_DISABLED=1     (ecc-compat)
  - DISCIPLINE_DISABLED_HOOKS=discipline:pre-edit:gateguard-fact-force
    (PR #9 mechanism)
  - DISCIPLINE_HOOK_PROFILE=minimal or standard (edit gate is strict-only as of v0.7.1)

Fire log:
  - GATEGUARD_FIRE_LOG overrides log path (default: ~/.claude/discipline/gateguard/fire.jsonl)
  - Each deny appends: {"ts":<ms>,"session":"<key>","tool":"<name>","path":"<file>","ext":"<.ext>"}

NOTE: This file currently contains only state management. Destructive bash
detection, gate messages, and the main dispatcher land in Tasks 3, 4, 5.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# State
STATE_DIR = Path(os.environ.get(
    "GATEGUARD_STATE_DIR",
    os.path.expanduser("~/.claude/discipline/gateguard"),
))
FIRE_LOG_PATH = Path(os.environ.get(
    "GATEGUARD_FIRE_LOG",
    os.path.expanduser("~/.claude/discipline/gateguard/fire.jsonl"),
))
SESSION_TIMEOUT_MS = 30 * 60 * 1000
READ_HEARTBEAT_MS = 60 * 1000
MAX_CHECKED_ENTRIES = 500
MAX_SESSION_KEYS = 50
ROUTINE_BASH_SESSION_KEY = "__bash_session__"

# Hook IDs (must match hooks.json)
EDIT_WRITE_HOOK_ID = "discipline:pre-edit:gateguard-fact-force"

# Disable env values (ecc-compat)
_DISABLE_VALUES = frozenset({"0", "false", "off", "disabled", "disable"})

_active_state_file: Path | None = None


def _now_ms() -> int:
    return int(time.time() * 1000)


def _normalize_env(value: str | None) -> str:
    return (value or "").strip().lower()


def is_gateguard_disabled() -> bool:
    if _normalize_env(os.environ.get("GATEGUARD_DISABLED")) == "1":
        return True
    return _normalize_env(os.environ.get("DISCIPLINE_GATEGUARD")) in _DISABLE_VALUES


def _hash_session_key(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


def _sanitize_session_key(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", raw)
    if sanitized and len(sanitized) <= 64:
        return sanitized
    return _hash_session_key("sid", raw)


def resolve_session_key(data: dict[str, Any]) -> str:
    session_obj = data.get("session")
    session_id_nested = session_obj.get("id") if isinstance(session_obj, dict) else None
    for candidate in (
        data.get("session_id"),
        data.get("sessionId"),
        session_id_nested,
        os.environ.get("CLAUDE_SESSION_ID"),
    ):
        sanitized = _sanitize_session_key(candidate)
        if sanitized:
            return sanitized
    transcript = (
        data.get("transcript_path")
        or data.get("transcriptPath")
        or os.environ.get("CLAUDE_TRANSCRIPT_PATH")
    )
    if transcript and str(transcript).strip():
        return _hash_session_key("tx", str(Path(transcript).resolve()))
    cwd = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return _hash_session_key("proj", str(Path(cwd).resolve()))


def _get_state_file(data: dict[str, Any] | None = None) -> Path:
    global _active_state_file
    if _active_state_file is None:
        key = resolve_session_key(data or {})
        _active_state_file = STATE_DIR / f"state-{key}.json"
    return _active_state_file


def load_state() -> dict[str, Any]:
    state_file = _get_state_file()
    if not state_file.exists():
        return {"checked": [], "last_active": _now_ms()}
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"checked": [], "last_active": _now_ms()}
    last_active = data.get("last_active", 0)
    if _now_ms() - last_active > SESSION_TIMEOUT_MS:
        try:
            state_file.unlink()
        except OSError:
            pass
        return {"checked": [], "last_active": _now_ms()}
    return data


def prune_checked_entries(checked: list[str]) -> list[str]:
    if len(checked) <= MAX_CHECKED_ENTRIES:
        return list(checked)
    preserved = [ROUTINE_BASH_SESSION_KEY] if ROUTINE_BASH_SESSION_KEY in checked else []
    session_keys = [
        k for k in checked
        if k.startswith("__") and k != ROUTINE_BASH_SESSION_KEY
    ]
    file_keys = [k for k in checked if not k.startswith("__")]
    remaining_session = max(MAX_SESSION_KEYS - len(preserved), 0)
    capped_session = session_keys[-remaining_session:]
    remaining_files = max(MAX_CHECKED_ENTRIES - len(preserved) - len(capped_session), 0)
    capped_files = file_keys[-remaining_files:]
    return [*preserved, *capped_session, *capped_files]


def save_state(state: dict[str, Any]) -> bool:
    state_file = _get_state_file()
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        merged_checked = list(state.get("checked", []) or [])
        merged_last = int(state.get("last_active", 0) or 0)
        # Merge with on-disk to handle racing hook invocations
        if state_file.exists():
            try:
                disk = json.loads(state_file.read_text(encoding="utf-8"))
                if isinstance(disk.get("checked"), list):
                    merged_checked = list({*disk["checked"], *merged_checked})
                if isinstance(disk.get("last_active"), int):
                    merged_last = max(merged_last, disk["last_active"])
            except (json.JSONDecodeError, OSError):
                pass
        final_state = {
            "checked": prune_checked_entries(merged_checked),
            "last_active": max(merged_last, _now_ms()),
        }
        # Atomic write: temp + rename
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=STATE_DIR,
            delete=False,
            suffix=".tmp",
        ) as tmp:
            json.dump(final_state, tmp, indent=2)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, state_file)
        return True
    except OSError:
        return False


def mark_checked(key: str) -> bool:
    state = load_state()
    if key not in state["checked"]:
        state["checked"].append(key)
        return save_state(state)
    return True


def is_checked(key: str) -> bool:
    state = load_state()
    found = key in state["checked"]
    if found and _now_ms() - state.get("last_active", 0) > READ_HEARTBEAT_MS:
        save_state(state)
    return found


# ---------------------------------------------------------------------------
# Destructive-bash detection
# ---------------------------------------------------------------------------

# Make scripts/ importable when this module is loaded directly via importlib
_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from shell_substitution import (  # noqa: E402
    extract_command_substitutions,
    extract_subshell_groups,
    extract_brace_groups,
)


_DESTRUCTIVE_SQL = re.compile(
    r"\b(drop\s+table|delete\s+from|truncate)\b", re.IGNORECASE,
)
_DESTRUCTIVE_DD = re.compile(r"\bdd\s+if=", re.IGNORECASE)


def _DESTRUCTIVE_SQL_DD(text: str) -> bool:  # type: ignore[misc]
    return bool(_DESTRUCTIVE_SQL.search(text) or _DESTRUCTIVE_DD.search(text))


def _strip_quoted_strings(text: str) -> str:
    return re.sub(
        r"'(?:[^'\\]|\\.)*'", "''",
        re.sub(r'"(?:[^"\\]|\\.)*"', '""', text),
    )


def _explode_subshells(text: str) -> str:
    out = text
    for _ in range(4):
        before = out
        out = re.sub(r"\$\(([^()`]*)\)", r";\1;", out)
        out = re.sub(r"`([^`]*)`", r";\1;", out)
        if out == before:
            break
    return out


def _split_command_segments(text: str) -> list[str]:
    stripped = _explode_subshells(_strip_quoted_strings(text))
    parts = re.split(r"[;|&]+", stripped)
    return [
        re.sub(r"(^|\s)#.*", r"\1", p).strip()
        for p in parts
        if p.strip()
    ]


def _tokenize(segment: str) -> list[str]:
    return [t for t in re.split(r"\s+", segment) if t]


def _command_basename(token: str) -> str:
    if not token:
        return ""
    base = re.sub(r"^.*[\\/]", "", token)
    base = re.sub(r"\.exe$", "", base, flags=re.IGNORECASE)
    return base.lower()


def _is_destructive_rm(tokens: list[str]) -> bool:
    if not tokens or _command_basename(tokens[0]) != "rm":
        return False
    has_r = has_f = False
    for t in tokens[1:]:
        if t == "--recursive":
            has_r = True
            continue
        if t == "--force":
            has_f = True
            continue
        if not t.startswith("-") or t.startswith("--"):
            continue
        body = t[1:]
        if re.search(r"[rR]", body):
            has_r = True
        if "f" in body:
            has_f = True
    return has_r and has_f


def _find_git_subcommand(tokens: list[str]) -> tuple[str, list[str]] | None:
    if not tokens or _command_basename(tokens[0]) != "git":
        return None
    value_consuming_short = {"-c", "-C"}
    value_consuming_long_prefix = ("--git-dir", "--work-tree", "--namespace", "--super-prefix")
    i = 1
    while i < len(tokens):
        t = tokens[i]
        if t in value_consuming_short:
            i += 2
            continue
        if any(t == p for p in value_consuming_long_prefix):
            i += 2
            continue
        if any(t.startswith(p + "=") for p in value_consuming_long_prefix):
            i += 1
            continue
        if t.startswith("-"):
            i += 1
            continue
        return (t.lower(), tokens[i + 1:])
    return None


def _is_destructive_git(tokens: list[str]) -> bool:
    sub = _find_git_subcommand(tokens)
    if not sub:
        return False
    cmd, rest = sub
    if cmd == "reset":
        return "--hard" in rest
    if cmd == "checkout":
        return "--" in rest
    if cmd == "clean":
        return any(
            t == "--force"
            or (t.startswith("-") and not t.startswith("--") and "f" in t[1:])
            for t in rest
        )
    if cmd == "push":
        with_lease = False
        bare_force = False
        plus_force = False
        for t in rest:
            if t == "--force-with-lease" or t.startswith("--force-with-lease="):
                with_lease = True
            elif t == "--force" or t.startswith("--force="):
                bare_force = True
            elif t.startswith("-") and not t.startswith("--") and "f" in t[1:]:
                bare_force = True
            elif t.startswith("+") and len(t) > 1 and re.match(r"^\+(?:[a-zA-Z_/.:]|HEAD)", t):
                plus_force = True
        return bare_force or (plus_force and not with_lease)
    if cmd == "commit":
        return "--amend" in rest
    if cmd == "rm":
        return any(
            t.startswith("-") and not t.startswith("--") and re.search(r"[rR]", t[1:])
            for t in rest
        )
    if cmd == "switch":
        for t in rest:
            if t in ("--discard-changes", "--force"):
                return True
            if t.startswith("-") and not t.startswith("--") and re.search(r"[fC]", t[1:]):
                return True
        return False
    return False


def _collect_executable_bodies(raw: str) -> list[str]:
    bodies = [raw]
    queue = [raw]
    seen: set[str] = set()
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        for extractor in (
            extract_command_substitutions,
            extract_subshell_groups,
            extract_brace_groups,
        ):
            for body in extractor(current):
                if body not in seen:
                    bodies.append(body)
                    queue.append(body)
    return bodies


def is_destructive_bash(command: str) -> bool:
    raw = command or ""
    flattened = _explode_subshells(_strip_quoted_strings(raw))
    if _DESTRUCTIVE_SQL_DD(flattened):
        return True
    for body in _collect_executable_bodies(raw):
        for segment in _split_command_segments(body):
            if _DESTRUCTIVE_SQL_DD(_strip_quoted_strings(segment)):
                return True
            tokens = _tokenize(segment)
            if _is_destructive_rm(tokens):
                return True
            if _is_destructive_git(tokens):
                return True
    return False


# ---------------------------------------------------------------------------
# Path sanitization + allowlists + gate messages
# ---------------------------------------------------------------------------


def sanitize_path(file_path: str) -> str:
    out_chars: list[str] = []
    for ch in str(file_path or ""):
        code = ord(ch)
        is_ascii_control = code <= 0x1F or code == 0x7F
        is_bidi = (
            0x200E <= code <= 0x200F
            or 0x202A <= code <= 0x202E
            or 0x2066 <= code <= 0x2069
        )
        out_chars.append(" " if (is_ascii_control or is_bidi) else ch)
    return "".join(out_chars).strip()[:500]


def _normalize_for_match(value: str) -> str:
    return str(value or "").replace("\\", "/").lower()


_CLAUDE_SETTINGS_RE = re.compile(r"(^|/)\.claude/settings(?:\.[^/]+)?\.json$")


def is_claude_settings_path(file_path: str) -> bool:
    return bool(_CLAUDE_SETTINGS_RE.search(_normalize_for_match(file_path)))


# Prose file extensions exempt from the first-touch fact gate (hb-of7 retarget).
# The gate's questions — importers, public API, schemas — are meaningful only for
# code. For prose the honest answer is always "none/N/A", so gating docs trains
# rote fact-recital (alarm fatigue) without forcing real investigation.
_DOC_EXTENSIONS = frozenset({".md", ".markdown", ".txt", ".rst"})

# Agent-config files are .md by convention but carry BINDING agent instructions —
# editing them is behavior-bearing, not prose. They stay gated despite the doc
# extension so a first-touch edit still forces investigation (basename match,
# case-insensitive).
_AGENT_CONFIG_BASENAMES = frozenset({"claude.md", "agents.md", "gemini.md"})


def is_doc_path(file_path: str) -> bool:
    normalized = _normalize_for_match(file_path)
    basename = normalized.rsplit("/", 1)[-1]
    if basename in _AGENT_CONFIG_BASENAMES:
        return False
    dot = basename.rfind(".")
    if dot <= 0:  # no extension, or dotfile with no suffix
        return False
    return basename[dot:] in _DOC_EXTENSIONS


def is_subagent_invocation(data: dict[str, Any]) -> bool:
    for key in ("agent_id", "agentId", "parent_tool_use_id", "parentToolUseId"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return True
    return False


def edit_gate_msg(file_path: str) -> str:
    safe = sanitize_path(file_path)
    return "\n".join([
        "[Fact-Forcing Gate]",
        "",
        f"Before editing {safe}, present these facts:",
        "",
        "1. List ALL files that import/require this file (use Grep)",
        "2. List the public functions/classes affected by this change",
        "3. If this file reads/writes data files, show field names, structure, and date "
        "format (use redacted or synthetic values, not raw production data)",
        "4. Quote the user's current instruction verbatim",
        "",
        "Present the facts, then retry the same operation.",
    ])


def write_gate_msg(file_path: str) -> str:
    safe = sanitize_path(file_path)
    return "\n".join([
        "[Fact-Forcing Gate]",
        "",
        f"Before creating {safe}, present these facts:",
        "",
        "1. Name the file(s) and line(s) that will call this new file",
        "2. Confirm no existing file serves the same purpose (use Glob)",
        "3. If this file reads/writes data files, show field names, structure, and date "
        "format (use redacted or synthetic values, not raw production data)",
        "4. Quote the user's current instruction verbatim",
        "",
        "Present the facts, then retry the same operation.",
    ])


def destructive_bash_msg() -> str:
    return "\n".join([
        "[Fact-Forcing Gate]",
        "",
        "Destructive command detected. Before running, present:",
        "",
        "1. List all files/data this command will modify or delete",
        "2. Write a one-line rollback procedure",
        "3. Quote the user's current instruction verbatim",
        "",
        "Present the facts, then retry the same operation.",
    ])


def _with_recovery_hint(message: str, hook_ids: list[str]) -> str:
    targets = " or ".join(f"`{h}`" for h in hook_ids)
    return "\n".join([
        message,
        "",
        f"Recovery: if GateGuard is blocking setup or repair work, run with "
        f"`DISCIPLINE_GATEGUARD=off` or add {targets} to `DISCIPLINE_DISABLED_HOOKS`.",
    ])


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

_TOOL_MAP = {"edit": "Edit", "write": "Write", "multiedit": "MultiEdit", "bash": "Bash"}


def _log_fire(tool_name: str, path: str | None) -> None:
    """Append one line to FIRE_LOG_PATH on each deny. Best-effort; never blocks a deny."""
    try:
        state_file = _active_state_file
        session_id = state_file.stem.replace("state-", "", 1) if state_file else "unknown"
        ext = Path(path).suffix.lower() if path else None
        record = json.dumps({
            "ts": _now_ms(),
            "session": session_id,
            "tool": tool_name,
            "path": path,
            "ext": ext,
        })
        FIRE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(FIRE_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(record + "\n")
    except Exception:
        pass  # best-effort; never fail a deny due to a log write error


def _deny_result_json(
    reason: str,
    *,
    include_recovery_hint: bool = True,
    hook_ids: list[str] | None = None,
) -> str:
    hook_ids = hook_ids or [EDIT_WRITE_HOOK_ID]
    final_reason = _with_recovery_hint(reason, hook_ids) if include_recovery_hint else reason
    return json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": final_reason,
        }
    })


def _process_event(data: dict[str, Any]) -> str:
    """Return the JSON string to write to stdout. Empty string = passthrough/allow."""
    if is_gateguard_disabled():
        return ""

    global _active_state_file
    _active_state_file = None
    _get_state_file(data)

    raw_tool = str(data.get("tool_name") or "")
    tool_name = _TOOL_MAP.get(raw_tool.lower(), raw_tool)
    tool_input = data.get("tool_input") or {}
    in_subagent = is_subagent_invocation(data)

    if tool_name in ("Edit", "Write"):
        file_path = tool_input.get("file_path") or ""
        if not file_path or is_claude_settings_path(file_path) or is_doc_path(file_path):
            return ""
        if in_subagent:
            return ""
        if not is_checked(file_path):
            if not mark_checked(file_path):
                return ""  # passthrough on state-write failure
            msg = edit_gate_msg(file_path) if tool_name == "Edit" else write_gate_msg(file_path)
            _log_fire(tool_name, file_path)
            return _deny_result_json(msg)
        return ""

    if tool_name == "MultiEdit":
        if in_subagent:
            return ""
        for edit in tool_input.get("edits") or []:
            fp = edit.get("file_path") or ""
            if fp and not is_claude_settings_path(fp) and not is_doc_path(fp) and not is_checked(fp):
                if not mark_checked(fp):
                    return ""
                _log_fire("MultiEdit", fp)
                return _deny_result_json(edit_gate_msg(fp))
        return ""

    if tool_name == "Bash":
        # Retarget (hb-of7): only destructive commands are gated. The former
        # once-per-session routine-bash gate forced no investigation (the user
        # instruction is already in context) and was dropped as pure friction.
        command = tool_input.get("command") or ""
        if is_destructive_bash(command):
            digest = hashlib.sha256(command.encode("utf-8")).hexdigest()[:16]
            key = f"__destructive__{digest}"
            if not is_checked(key):
                if not mark_checked(key):
                    return ""
                _log_fire("Bash", command[:120])
                return _deny_result_json(destructive_bash_msg(), include_recovery_hint=False)
        return ""

    return ""


def main(argv: list[str] | None = None) -> int:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return 0
    if not isinstance(data, dict):
        return 0
    output = _process_event(data)
    if output:
        sys.stdout.write(output)
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
