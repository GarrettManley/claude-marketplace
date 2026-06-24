#!/usr/bin/env python3
"""Validates a commit message against a YAML rule set.

Args:
    ref        — the git ref that was inspected (for display only)
    msg_file   — path to a file containing the commit message
    rules_file — (optional) path to the YAML rule file; omit or pass empty string for defaults only

Exit codes:
    0 — valid
    1 — validation failed
    2 — usage or infrastructure error
"""

import pathlib
import re
import sys
from typing import Any, Optional


def _coerce(v: str) -> Any:
    """Coerce a YAML scalar string to Python bool / int / str."""
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    try:
        return int(v)
    except ValueError:
        return v


def load_rules(rules_path: str) -> dict[str, Any]:
    if not rules_path:
        return {}
    p = pathlib.Path(rules_path)
    if not p.exists():
        return {}
    try:
        import yaml  # type: ignore
        with open(p) as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        pass
    # Minimal fallback parser — supports key: value pairs and single-level lists.
    # Inline comments (# ...) are stripped from values.
    print(
        "validate: warning: PyYAML not installed; using minimal fallback parser. "
        "Install: pip install pyyaml",
        file=sys.stderr,
    )
    try:
        return _minimal_yaml_load(p)
    except Exception as e:
        print(f"validate: error: could not parse rules file '{rules_path}': {e}", file=sys.stderr)
        sys.exit(2)


def _minimal_yaml_load(p: pathlib.Path) -> dict[str, Any]:
    result: dict = {}
    current: list[str] = []
    with open(p) as f:
        for raw in f:
            line = raw.rstrip()
            if not line or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            depth = indent // 2
            while len(current) > depth:
                current.pop()
            stripped = line.strip()
            if stripped.startswith("- "):
                # List item — append to the list under the current parent key.
                val = stripped[2:].strip().strip('"\'')
                if current:
                    node = result
                    for part in current[:-1]:
                        node = node.setdefault(part, {})
                    parent_key = current[-1]
                    if not isinstance(node.get(parent_key), list):
                        node[parent_key] = []
                    node[parent_key].append(val)
            elif ": " in stripped:
                k, _, v = stripped.partition(": ")
                # Strip trailing inline comment (e.g., "72  # chars…")
                v = re.sub(r'\s+#[^"]*$', '', v).strip()
                # Decode YAML double-quoted string escapes (e.g., \\ → \, \" → ")
                if v.startswith('"') and v.endswith('"'):
                    inner = v[1:-1]
                    inner = inner.replace('\\\\', '\x00')  # protect \\
                    inner = inner.replace('\\"', '"')
                    inner = inner.replace('\\n', '\n')
                    inner = inner.replace('\x00', '\\')    # restore as single \
                    v = inner
                else:
                    v = v.strip("'")
                node = result
                for part in current:
                    node = node.setdefault(part, {})
                node[k] = _coerce(v)
            elif stripped.endswith(":"):
                key = stripped.rstrip(":")
                node = result
                for part in current:
                    node = node.setdefault(part, {})
                if key not in node:
                    node[key] = {}
                current.append(key)
    return result


def _find_trailer_start(rest: list[str]) -> Optional[int]:
    """Return the index in rest where the trailer block begins, or None.

    Searches backward from the end for the last blank-line-before-Key pattern,
    so mid-body lines like "Note: see docs" are never mistaken for trailers.
    """
    for i in range(len(rest) - 1, -1, -1):
        if rest[i].strip() == "" and i + 1 < len(rest):
            if re.match(r"^[A-Za-z][A-Za-z0-9-]*:", rest[i + 1]):
                return i + 1
    return None


def _extract_trailer_block(rest: list[str], trailer_name: str) -> str:
    """Return lines belonging to the named trailer block."""
    start = None
    for i, line in enumerate(rest):
        if line.strip().startswith(f"{trailer_name}:"):
            start = i
            break
    if start is None:
        return ""
    block = [rest[start]]
    for line in rest[start + 1:]:
        if not line.strip():
            break
        if re.match(r"^[A-Za-z][A-Za-z0-9-]*:", line):
            break
        block.append(line)
    return "\n".join(block)


def validate(ref: str, commit_msg: str, rules: dict) -> list[str]:
    lines = [ln for ln in commit_msg.splitlines() if not ln.startswith("#")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    if not lines:
        return ["empty commit message"]

    header = lines[0]
    rest = lines[1:]
    failures: list[str] = []

    header_rules = rules.get("header", {})
    pattern = header_rules.get("pattern")
    max_length = int(header_rules.get("max_length", 0))

    if pattern and not re.match(pattern, header):
        failures.append(
            f"header-format: header does not match pattern\n"
            f"    pattern: {pattern}\n"
            f"    got:     {header}"
        )

    if max_length and len(header) > max_length:
        failures.append(
            f"header-length: {len(header)} chars > {max_length}\n"
            f"    got: {header}"
        )

    body_rules = rules.get("body", {})
    if body_rules.get("required"):
        min_lines = int(body_rules.get("min_lines_before_trailer", 1))
        trailers_start = _find_trailer_start(rest)
        body_end = trailers_start if trailers_start is not None else len(rest)
        non_empty_body = [ln for ln in rest[:body_end] if ln.strip()]
        if len(non_empty_body) < min_lines:
            failures.append(
                f"missing-body: need at least {min_lines} non-empty body line(s) before trailers"
            )

    trailer_rules = rules.get("trailers", {})
    full_rest = "\n".join(rest)
    for trailer_name, trailer_cfg in (trailer_rules or {}).items():
        if not isinstance(trailer_cfg, dict):
            continue
        trailer_present = f"{trailer_name}:" in full_rest
        if not trailer_present:
            if trailer_cfg.get("required"):
                failures.append(f"missing-trailer: '{trailer_name}:' is required")
            continue
        must_contain = trailer_cfg.get("must_contain", [])
        if must_contain:
            trailer_block = _extract_trailer_block(rest, trailer_name)
            for required in must_contain:
                if required not in trailer_block:
                    failures.append(
                        f"trailer-missing-field: '{required}' required in '{trailer_name}:' block"
                    )

    return failures


def main() -> int:
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <ref> <msg_file> [rules_file]", file=sys.stderr)
        return 2

    ref = sys.argv[1]
    msg_file = sys.argv[2]
    rules_file = sys.argv[3] if len(sys.argv) > 3 else ""

    try:
        commit_msg = pathlib.Path(msg_file).read_text()
    except OSError as e:
        print(f"validate: cannot read message file '{msg_file}': {e}", file=sys.stderr)
        return 2

    rules = load_rules(rules_file)
    failures = validate(ref, commit_msg, rules)

    if failures:
        print(f"validate: {ref} FAILED", file=sys.stderr)
        for f in failures:
            print(f"  FAIL {f}", file=sys.stderr)
        return 1

    print(f"validate: {ref} OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
