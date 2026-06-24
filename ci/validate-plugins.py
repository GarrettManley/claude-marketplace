#!/usr/bin/env python3
"""Validate plugin + marketplace manifests against Claude Code's enforced schema.

Codifies the rules in docs/plugin-schema-gotchas.md so a malformed manifest fails
pre-merge here rather than at consumer install time (where the validator emits a
vague "Invalid input"). This is intentionally a standalone Python check — it does
not shell out to the `claude` CLI, which is not guaranteed to be present on CI
runners; maintainers can still run `claude plugin validate` locally as the
authoritative check.

Enforced:
  - plugin.json has mandatory `name` and `version`
  - plugin.json does NOT declare `agents` (auto-discovered) or `hooks` (auto-loaded)
  - `commands` / `skills` / `keywords` are arrays when present
  - every marketplace.json entry resolves to ./plugins/<dir>/.claude-plugin/plugin.json
  - the plugin.json `name` matches its marketplace entry
  - every plugins/*/ with a manifest is listed in marketplace.json (no orphans)

Run: python3 ci/validate-plugins.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
PLUGINS_DIR = ROOT / "plugins"

FORBIDDEN_FIELDS = ("agents", "hooks")
ARRAY_FIELDS = ("commands", "skills", "keywords")


def validate_plugin_manifest(path: Path, errors: list[str]) -> str | None:
    rel = path.relative_to(ROOT).as_posix()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{rel}: invalid JSON ({exc})")
        return None
    if not data.get("name"):
        errors.append(f"{rel}: missing required `name`")
    if not data.get("version"):
        errors.append(f"{rel}: missing required `version` (mandatory even if examples omit it)")
    for field in FORBIDDEN_FIELDS:
        if field in data:
            errors.append(f"{rel}: must NOT declare `{field}` (auto-discovered/auto-loaded; errors at install)")
    for field in ARRAY_FIELDS:
        if field in data and not isinstance(data[field], list):
            errors.append(f"{rel}: `{field}` must be an array, not {type(data[field]).__name__}")
    return data.get("name")


def main() -> int:
    errors: list[str] = []
    market = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    entries = market.get("plugins", [])
    seen_dirs: set[str] = set()

    for entry in entries:
        name = entry.get("name", "<unnamed>")
        source = entry.get("source", "")
        if not source.startswith("./plugins/"):
            errors.append(f"marketplace.json[{name}]: source must be ./plugins/<dir>, got {source!r}")
            continue
        plugin_dir = ROOT / source[2:]
        seen_dirs.add(plugin_dir.name)
        manifest = plugin_dir / ".claude-plugin" / "plugin.json"
        if not manifest.is_file():
            errors.append(f"marketplace.json[{name}]: no plugin.json at {source}/.claude-plugin/")
            continue
        pname = validate_plugin_manifest(manifest, errors)
        if pname and pname != name:
            errors.append(f"marketplace.json[{name}]: plugin.json name is {pname!r} (mismatch)")

    for manifest in sorted(PLUGINS_DIR.glob("*/.claude-plugin/plugin.json")):
        dirname = manifest.parent.parent.name
        if dirname not in seen_dirs:
            errors.append(f"plugins/{dirname}: has a plugin.json but is not listed in marketplace.json")

    if errors:
        print(f"validate-plugins: {len(errors)} problem(s):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"validate-plugins: clean ({len(entries)} plugins).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
