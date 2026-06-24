"""Shared configuration loader for the `discipline` plugin hooks.

Resolution order for any setting (first wins):

1. **Environment variable** (e.g. `DISCIPLINE_REPO`) — explicit override.
2. **`.claude/discipline.local.md` frontmatter** in the repo root —
   per-project config. Format mirrors the `plugin-settings` skill.
3. **Auto-detection** from git: `origin` remote URL → `<owner>/<repo>`,
   `refs/remotes/origin/HEAD` → main branch.
4. **Sane default** (e.g. `main` for branch).

Hooks should call `get_config()` once near the top of `main()` and read
attributes off the returned object.

Importing this module from a plugin hook:

```python
import os, sys
sys.path.insert(0, os.path.join(
    os.environ.get("CLAUDE_PLUGIN_ROOT", "."), "scripts",
))
from discipline_config import get_config
```
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


@dataclass
class DisciplineConfig:
    """Resolved per-project discipline plugin settings."""

    repo: str | None = None
    """GitHub `<owner>/<repo>` for `gh` calls. None disables gh integration."""

    main_branch: str = "main"
    """Default branch name for branch-state checks."""

    repo_root: Path | None = None
    """Absolute path to the repo root. None when not in a git repo."""

    source_extensions: tuple[str, ...] = (
        ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
        ".rs", ".py", ".go", ".java", ".kt", ".cs",
    )
    """File extensions that trigger TODO-issue checks."""

    spec_pattern: str = r"^docs/.*\d{3,4}-[\w-]+\.md$"
    """Regex matching spec doc paths (for spec_companion_check)."""

    plan_pattern: str = r"(?:^docs/.*plans?/\d{4}-\d{2}-\d{2}-.+\.md$)|(?:(?:^|/)\.claude/plans/[^/]+\.md$)"
    """Regex matching plan doc paths (for plan_issue_check).

    Covers two locations: dated `docs/**/plans/YYYY-MM-DD-*.md` files and Claude
    Code plan-mode files under `.claude/plans/`. Narrow it via `plan-pattern` /
    `DISCIPLINE_PLAN_PATTERN` if a project only wants the dated-docs form.
    """

    bd_id_pattern: str = r"\b(?:bd|hb)-[0-9a-z]+(?:\.\d+)?\b"
    """Regex matching a beads issue id (e.g. `hb-9yw`, `hb-9yw.4`, `bd-abc1`).

    Prefix-anchored on `bd-`/`hb-` so it doesn't match ordinary hyphenated words
    (`claude-code`, `pre-commit`) — which would make the citation check pass on
    any plan. Override via `bd-id-pattern` / `DISCIPLINE_BD_ID_PATTERN`.
    """

    bd_ledger: str | None = None
    """Beads ledger dir for `bd -C <dir>` auto-close. None disables bd auto-close."""

    require_value_justification: bool = False
    """Block in-flight plans missing `## Value Justification`."""

    require_frontmatter_fields: tuple[str, ...] = ()
    """Fields required in YAML frontmatter on docs/**/*.md (empty disables lint)."""

    frontmatter_skip_prefixes: tuple[str, ...] = (
        "node_modules/", "dist/", "build/", "vendor/",
    )
    """Path prefixes the frontmatter lint skips."""

    pitfalls_root: str | None = None
    """Repo-relative dir where pitfalls docs live (e.g. 'docs/pitfalls'). None disables pointer."""

    pitfalls_routes: dict = field(default_factory=dict)
    """Map of {file_or_prefix: area_slug} for pitfalls routing."""

    inject_issues: bool = True
    """Inject open GH issues into SessionStart additionalContext."""

    inject_branch_state: bool = True
    """Inject stale-branch warnings into SessionStart additionalContext."""

    @property
    def has_gh(self) -> bool:
        """True when both `repo` is set and `gh` is on PATH."""
        if not self.repo:
            return False
        try:
            subprocess.run(["gh", "--version"], capture_output=True, check=True, timeout=2)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    @property
    def has_bd(self) -> bool:
        """True when a beads ledger is configured and `bd` is on PATH."""
        if not self.bd_ledger:
            return False
        try:
            subprocess.run(["bd", "--version"], capture_output=True, check=True, timeout=2)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False


_FRONTMATTER_BOUND = re.compile(r"^---\s*$", re.MULTILINE)


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract scalar key:value pairs from a YAML frontmatter block.

    Returns {} if the doc has no opening `---` on line 1, or no closing
    `---` within 60 lines. Quoted values are unwrapped. Lists/objects
    get the raw RHS string and are left to the caller to interpret.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields_out: dict[str, str] = {}
    for line in lines[1:60]:
        if line.strip() == "---":
            break
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
        fields_out[key] = value
    return fields_out


def _detect_git_root() -> Path | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True, stderr=subprocess.DEVNULL, timeout=2,
        ).strip()
        return Path(out) if out else None
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def _detect_repo() -> str | None:
    """Return `owner/repo` parsed from `origin` remote URL, or None."""
    try:
        url = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"],
            text=True, stderr=subprocess.DEVNULL, timeout=2,
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    if not url:
        return None
    # Match either git@host:owner/repo[.git] or https://host/owner/repo[.git]
    m = re.search(r"[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url)
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2)}"


def _detect_main_branch(repo_root: Path | None) -> str:
    """Return the default branch (`main`/`master`/...) or 'main' as fallback."""
    if repo_root is None:
        return "main"
    try:
        out = subprocess.check_output(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            text=True, stderr=subprocess.DEVNULL, cwd=repo_root, timeout=2,
        ).strip()
        # Format: refs/remotes/origin/<branch>
        return out.rsplit("/", 1)[-1] or "main"
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return "main"


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _parse_bool(value: str, default: bool) -> bool:
    v = value.strip().lower()
    if v in {"true", "yes", "1", "on"}:
        return True
    if v in {"false", "no", "0", "off"}:
        return False
    return default


def _parse_routes(value: str) -> dict:
    """Parse a `pitfalls-routes` value of the form `key1=area1; key2=area2`."""
    out: dict = {}
    for pair in value.split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        k, _, v = pair.partition("=")
        out[k.strip()] = v.strip()
    return out


@lru_cache(maxsize=1)
def get_config() -> DisciplineConfig:
    """Return the resolved configuration for this process.

    Cached for the lifetime of the python process — hooks are short-lived
    so this just avoids repeated git subprocess calls within a single hook
    invocation.
    """
    repo_root = _detect_git_root()

    # Layer 3: auto-detection
    cfg = DisciplineConfig(
        repo=_detect_repo(),
        main_branch=_detect_main_branch(repo_root),
        repo_root=repo_root,
    )

    # Layer 2: per-project .claude/discipline.local.md
    if repo_root is not None:
        local = repo_root / ".claude" / "discipline.local.md"
        if local.is_file():
            try:
                fields_out = _parse_frontmatter(local.read_text(encoding="utf-8"))
            except OSError:
                fields_out = {}
            if "repo" in fields_out:
                cfg.repo = fields_out["repo"]
            if "main-branch" in fields_out:
                cfg.main_branch = fields_out["main-branch"]
            if "source-extensions" in fields_out:
                cfg.source_extensions = _split_csv(fields_out["source-extensions"])
            if "spec-pattern" in fields_out:
                cfg.spec_pattern = fields_out["spec-pattern"]
            if "plan-pattern" in fields_out:
                cfg.plan_pattern = fields_out["plan-pattern"]
            if "bd-id-pattern" in fields_out:
                cfg.bd_id_pattern = fields_out["bd-id-pattern"]
            if "bd-ledger" in fields_out:
                cfg.bd_ledger = fields_out["bd-ledger"]
            if "require-value-justification" in fields_out:
                cfg.require_value_justification = _parse_bool(
                    fields_out["require-value-justification"], cfg.require_value_justification,
                )
            if "require-frontmatter-fields" in fields_out:
                cfg.require_frontmatter_fields = _split_csv(
                    fields_out["require-frontmatter-fields"],
                )
            if "frontmatter-skip-prefixes" in fields_out:
                cfg.frontmatter_skip_prefixes = _split_csv(
                    fields_out["frontmatter-skip-prefixes"],
                )
            if "pitfalls-root" in fields_out:
                cfg.pitfalls_root = fields_out["pitfalls-root"]
            if "pitfalls-routes" in fields_out:
                cfg.pitfalls_routes = _parse_routes(fields_out["pitfalls-routes"])
            if "inject-issues" in fields_out:
                cfg.inject_issues = _parse_bool(fields_out["inject-issues"], cfg.inject_issues)
            if "inject-branch-state" in fields_out:
                cfg.inject_branch_state = _parse_bool(
                    fields_out["inject-branch-state"], cfg.inject_branch_state,
                )

    # Layer 1: env var overrides (highest priority)
    if env := os.environ.get("DISCIPLINE_REPO"):
        cfg.repo = env
    if env := os.environ.get("DISCIPLINE_MAIN_BRANCH"):
        cfg.main_branch = env
    if env := os.environ.get("DISCIPLINE_SOURCE_EXTENSIONS"):
        cfg.source_extensions = _split_csv(env)
    if env := os.environ.get("DISCIPLINE_SPEC_PATTERN"):
        cfg.spec_pattern = env
    if env := os.environ.get("DISCIPLINE_PLAN_PATTERN"):
        cfg.plan_pattern = env
    if env := os.environ.get("DISCIPLINE_BD_ID_PATTERN"):
        cfg.bd_id_pattern = env
    if env := os.environ.get("DISCIPLINE_BD_LEDGER"):
        cfg.bd_ledger = env
    if env := os.environ.get("DISCIPLINE_REQUIRE_VALUE_JUSTIFICATION"):
        cfg.require_value_justification = _parse_bool(env, cfg.require_value_justification)
    if env := os.environ.get("DISCIPLINE_REQUIRE_FRONTMATTER_FIELDS"):
        cfg.require_frontmatter_fields = _split_csv(env)
    if env := os.environ.get("DISCIPLINE_FRONTMATTER_SKIP_PREFIXES"):
        cfg.frontmatter_skip_prefixes = _split_csv(env)
    if env := os.environ.get("DISCIPLINE_PITFALLS_ROOT"):
        cfg.pitfalls_root = env
    if env := os.environ.get("DISCIPLINE_PITFALLS_ROUTES"):
        cfg.pitfalls_routes = _parse_routes(env)
    if env := os.environ.get("DISCIPLINE_INJECT_ISSUES"):
        cfg.inject_issues = _parse_bool(env, cfg.inject_issues)
    if env := os.environ.get("DISCIPLINE_INJECT_BRANCH_STATE"):
        cfg.inject_branch_state = _parse_bool(env, cfg.inject_branch_state)

    return cfg


def normalize_path_to_repo(raw: str, repo_root: Path | None) -> str:
    """Return a repo-relative POSIX path for a raw absolute file path.

    Handles Windows backslashes and worktree paths. Falls back to a
    `docs/...` substring extraction when repo_root is not available
    (e.g., in unit tests under tmp_path).
    """
    posix = raw.replace("\\", "/")

    # Strip .worktrees/<branch>/ if present
    wt_idx = posix.rfind(".worktrees/")
    if wt_idx != -1:
        tail = posix[wt_idx + len(".worktrees/"):]
        if "/" in tail:
            return tail.split("/", 1)[1]
        return tail

    # Strip the repo root prefix when known
    if repo_root is not None:
        try:
            rel = Path(posix).resolve().relative_to(repo_root.resolve())
            return rel.as_posix()
        except (ValueError, OSError):
            pass

    # Fallback: substring beginning at /docs/
    docs_idx = posix.find("/docs/")
    if docs_idx != -1:
        return posix[docs_idx + 1:]
    if posix.startswith("docs/"):
        return posix

    return posix
