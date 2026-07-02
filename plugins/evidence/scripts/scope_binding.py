"""Generic scope-binding scaffold for the evidence plugin.

Provides a reusable check: "is this URL/host/path within the loaded scope?"
Hooks in any project can import this and apply it to network calls, file
reads, or any operation that should be confined to a known scope.

Scope manifest format (project-supplied, default location
`.claude/evidence-scope.yaml`):

    name: my-engagement
    hosts:
      - example.com
      - api.example.com
      - "*.example.com"   # wildcard prefix supported
    path_prefixes:
      - /opt/data/engagement-2026/
      - C:\\Engagements\\2026\\
    deny_hosts:               # optional explicit denylist (wins over allow)
      - internal.example.com

If no manifest is loaded, every check returns `(True, "no scope manifest;
permissive mode")`. This means the scaffold is opt-in: project must drop
in a manifest to enable enforcement.

Hosts are matched case-insensitively. `*.foo.com` matches any subdomain
but NOT `foo.com` itself.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_SCOPE_PATH = ".claude/evidence-scope.yaml"


@dataclass
class Scope:
    name: str = ""
    hosts: list[str] = field(default_factory=list)
    deny_hosts: list[str] = field(default_factory=list)
    path_prefixes: list[str] = field(default_factory=list)
    loaded_from: str | None = None

    @property
    def is_loaded(self) -> bool:
        return self.loaded_from is not None


def _parse_simple_yaml(text: str) -> dict:
    """Tiny YAML subset parser sufficient for the scope manifest.

    Supports: top-level scalar `key: value`, list-of-scalars under a key,
    and `# comments`. Does NOT support nested mappings, multi-line
    strings, or any of YAML's other tar pits.
    """
    result: dict = {}
    current_list_key: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith(("  -", "\t-")) and current_list_key is not None:
            value = line.lstrip().lstrip("-").strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            result[current_list_key].append(value)
            continue
        if line.startswith((" ", "\t")):
            continue  # unhandled indentation — skip
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if not value:
                result[key] = []
                current_list_key = key
            else:
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                    value = value[1:-1]
                result[key] = value
                current_list_key = None
    return result


def _detect_repo_root() -> Path | None:
    import subprocess
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True, stderr=subprocess.DEVNULL, timeout=2,
        ).strip()
        return Path(out) if out else None
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


@lru_cache(maxsize=1)
def load_scope(scope_path: str | None = None) -> Scope:
    """Load the scope manifest. Search order:

    1. Explicit `scope_path` argument.
    2. `EVIDENCE_SCOPE_PATH` env var.
    3. `<repo_root>/.claude/evidence-scope.yaml`.

    Returns an empty (permissive) Scope if no manifest is found.
    """
    candidate = scope_path or os.environ.get("EVIDENCE_SCOPE_PATH")
    if candidate is None:
        root = _detect_repo_root()
        if root is not None:
            default = root / DEFAULT_SCOPE_PATH
            if default.is_file():
                candidate = str(default)

    if candidate is None or not Path(candidate).is_file():
        return Scope()

    try:
        text = Path(candidate).read_text(encoding="utf-8")
    except OSError:
        return Scope()

    parsed = _parse_simple_yaml(text)
    return Scope(
        name=str(parsed.get("name", "")),
        hosts=[h for h in parsed.get("hosts", []) if isinstance(h, str)],
        deny_hosts=[h for h in parsed.get("deny_hosts", []) if isinstance(h, str)],
        path_prefixes=[p for p in parsed.get("path_prefixes", []) if isinstance(p, str)],
        loaded_from=candidate,
    )


def _host_matches(host: str, pattern: str) -> bool:
    host = host.lower().strip()
    pattern = pattern.lower().strip()
    if pattern.startswith("*."):
        return host.endswith(pattern[1:]) and host != pattern[2:]
    return host == pattern


def check_url(url: str, scope: Scope | None = None) -> tuple[bool, str]:
    """Return (in_scope, reason) for a URL.

    Permissive when no scope is loaded (returns True with explanation).
    Denylist wins over allowlist.
    """
    sc = scope or load_scope()
    if not sc.is_loaded:
        return True, "no scope manifest loaded; permissive mode"

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return False, f"could not parse host from URL: {url!r}"

    for pattern in sc.deny_hosts:
        if _host_matches(host, pattern):
            return False, f"host {host} is explicitly denied by scope {sc.name!r} (pattern: {pattern})"

    if not sc.hosts:
        return False, f"scope {sc.name!r} has no allowed hosts; reject all"

    for pattern in sc.hosts:
        if _host_matches(host, pattern):
            return True, f"host {host} matches allow-pattern {pattern!r} in scope {sc.name!r}"

    return False, f"host {host} not in allow-list of scope {sc.name!r} ({len(sc.hosts)} patterns)"


def check_path(path: str, scope: Scope | None = None) -> tuple[bool, str]:
    """Return (in_scope, reason) for a filesystem path."""
    sc = scope or load_scope()
    if not sc.is_loaded:
        return True, "no scope manifest loaded; permissive mode"
    if not sc.path_prefixes:
        return True, f"scope {sc.name!r} has no path restrictions"

    # Reject parent-traversal outright: a `..` segment can escape the prefix,
    # and for a not-yet-created file the raw-string prefix check below never
    # collapses it. Wholesale `..` rejection is standard confinement behavior
    # (an in-scope `..` write path is pathological and correctly refused).
    if ".." in path.replace("\\", "/").split("/"):
        return False, f"path {path!r} contains a parent-traversal ('..') segment; rejected by scope {sc.name!r}"

    norm = str(Path(path).resolve()) if Path(path).exists() else path
    for prefix in sc.path_prefixes:
        if norm.startswith(prefix):
            return True, f"path matches prefix {prefix!r} in scope {sc.name!r}"

    return False, f"path {norm!r} outside path_prefixes of scope {sc.name!r}"
