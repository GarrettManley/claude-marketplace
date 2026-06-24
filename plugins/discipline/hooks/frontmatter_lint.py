#!/usr/bin/env python3
"""PostToolUse hook: validate YAML frontmatter on docs/**/*.md writes.

Disabled by default — opt in by setting `require-frontmatter-fields` in
.claude/discipline.local.md (or DISCIPLINE_REQUIRE_FRONTMATTER_FIELDS env var).

When enabled, every doc under `docs/` must open with the configured fields.
Skips files whose path begins with any prefix in `frontmatter-skip-prefixes`
(defaults: node_modules/, dist/, build/, vendor/) and files whose names start
with `_` (draft convention).

Built-in validators for common fields (status, author, created, diataxis,
updated, last-verified, follows-conventions); other fields just need to be
present and non-empty.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from discipline_config import get_config, normalize_path_to_repo  # noqa: E402

VALID_STATUS = {"draft", "active", "superseded"}
VALID_DIATAXIS = {"tutorial", "how-to", "reference", "explanation"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_status(value: str) -> Optional[str]:
    if value.strip().lower() not in VALID_STATUS:
        return f"value '{value.strip()}' is not one of {sorted(VALID_STATUS)} (case-insensitive)"
    return None


def _validate_author(value: str) -> Optional[str]:
    if not value.strip():
        return "must be non-empty"
    return None


def _validate_date(value: str) -> Optional[str]:
    if not DATE_RE.match(value.strip()):
        return f"value '{value.strip()}' must match YYYY-MM-DD"
    return None


def _validate_diataxis(value: str) -> Optional[str]:
    if value.strip().lower() not in VALID_DIATAXIS:
        return f"value '{value.strip()}' is not one of {sorted(VALID_DIATAXIS)} (case-insensitive)"
    return None


def _validate_nonempty(value: str) -> Optional[str]:
    if not value.strip():
        return "must be non-empty"
    return None


def _validate_true(value: str) -> Optional[str]:
    if value.strip().lower() != "true":
        return f"value '{value.strip()}' must be 'true'"
    return None


# Built-in validators. Fields not in here just require presence + non-empty.
VALIDATORS: dict[str, "callable[[str], Optional[str]]"] = {
    "status": _validate_status,
    "author": _validate_author,
    "created": _validate_date,
    "updated": _validate_date,
    "diataxis": _validate_diataxis,
    "last-verified": _validate_nonempty,
    "follows-conventions": _validate_true,
}


def should_skip(rel_path: str, skip_prefixes: tuple[str, ...]) -> bool:
    """Return True when this path is outside the lint scope."""
    if not rel_path.startswith("docs/"):
        return True
    if not rel_path.endswith(".md"):
        return True
    for prefix in skip_prefixes:
        if rel_path.startswith(prefix):
            return True
    name = rel_path.rsplit("/", 1)[-1]
    if name.startswith("_"):
        return True
    return False


def parse_frontmatter(text: str) -> tuple[Optional[dict[str, str]], Optional[str]]:
    """Return ({field: value}, None) on success or (None, error) on failure."""
    lines = text.splitlines()
    if not lines:
        return None, "file is empty"
    if lines[0].strip() != "---":
        return None, "file must start with `---` on line 1"
    end_idx: Optional[int] = None
    for i in range(1, min(len(lines), 30)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return None, "frontmatter block must close with `---` within the first 30 lines"

    fields: dict[str, str] = {}
    for line in lines[1:end_idx]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        fields[key] = value
    return fields, None


def emit_block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def emit_warn(message: str) -> None:
    print(json.dumps({"systemMessage": message}))
    sys.exit(0)


def lint(rel_path: str, text: str, required_fields: tuple[str, ...]) -> list[str]:
    """Validate frontmatter. Returns a list of error strings."""
    errors: list[str] = []

    fields, parse_err = parse_frontmatter(text)
    if parse_err is not None:
        return [parse_err]

    assert fields is not None
    for key in required_fields:
        if key not in fields:
            errors.append(f"missing required field `{key}`")
            continue
        validator = VALIDATORS.get(key, _validate_nonempty)
        err = validator(fields[key])
        if err is not None:
            errors.append(f"`{key}`: {err}")

    return errors


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    cfg = get_config()
    if not cfg.require_frontmatter_fields:
        # Lint disabled; exit silently.
        return 0

    raw = (
        data.get("tool_input", {}).get("file_path")
        or data.get("tool_response", {}).get("filePath")
        or ""
    )
    if not raw:
        return 0

    rel_path = normalize_path_to_repo(raw, cfg.repo_root)
    if should_skip(rel_path, cfg.frontmatter_skip_prefixes):
        return 0

    try:
        text = Path(raw).read_text(encoding="utf-8")
    except OSError:
        return 0

    errors = lint(rel_path, text, cfg.require_frontmatter_fields)
    if errors:
        bullet = "\n  - "
        msg = (
            f"frontmatter_lint: {rel_path} has invalid frontmatter."
            f"{bullet}" + bullet.join(errors) +
            f"\n\nRequired fields configured: {list(cfg.require_frontmatter_fields)}."
        )
        sys.stderr.write(msg + "\n")
        emit_block(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
