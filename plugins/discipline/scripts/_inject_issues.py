"""SessionStart hook: surface open GitHub issues as additionalContext.

Importable functions
--------------------
detect_repo() -> str | None
    Resolve the ``<owner>/<repo>`` string for this working directory.
    Priority: DISCIPLINE_REPO env var > .claude/discipline.local.md `repo:` key
    > git remote.origin.url.

build_context(repo, issues_text) -> str
    Render the markdown block that Claude Code injects at session start.

main() -> None
    Orchestrate the full hook run and print the hookSpecificOutput JSON
    to stdout.  Exits 0 silently on any non-fatal failure (fail-soft).

Called by inject_issues.sh via ``python3 .../scripts/_inject_issues.py``.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_repo() -> str | None:
    """Return ``<owner>/<repo>`` for the current working directory.

    Resolution order (first match wins):
    1. ``DISCIPLINE_REPO`` environment variable.
    2. ``repo:`` key in ``<repo-root>/.claude/discipline.local.md``.
    3. ``remote.origin.url`` parsed from git config.
    Returns ``None`` when no repo can be identified.
    """
    if env_repo := os.environ.get("DISCIPLINE_REPO"):
        return env_repo

    # Try .claude/discipline.local.md
    try:
        root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
        local = Path(root) / ".claude" / "discipline.local.md"
        if local.is_file():
            try:
                text = local.read_text(encoding="utf-8")
                m = re.search(r"^repo:\s*(.+)$", text, re.MULTILINE)
                if m:
                    return m.group(1).strip()
            except OSError:
                pass
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass

    # Fall back to parsing origin remote URL
    try:
        url = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
        m = re.search(r"[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass

    return None


def build_context(repo: str, issues_text: str) -> str:
    """Return the markdown block injected into the session as additionalContext."""
    return (
        f"## Open GitHub issues ({repo})\n"
        f"\n"
        f"{issues_text}\n"
        f"\n"
        f"**Planning rules:**\n"
        f"- When entering plan mode, identify which issue(s) the work relates to.\n"
        f"- Plan files referencing issues by `#N` get auto-validated by the discipline plugin.\n"
        f"- Retrospective sections that include `Closes #N` / `Updates #N` / "
        f"`Follows up #N` auto-close issues via PostToolUse.\n"
        f"- If the work isn't tracked yet, run `gh issue create` before writing the plan."
    )


def main() -> None:
    """Run the SessionStart issues-injection hook and print JSON to stdout."""
    repo = detect_repo()
    if not repo:
        sys.exit(0)

    try:
        raw = subprocess.check_output(
            [
                "gh", "issue", "list",
                "--repo", repo,
                "--state", "open",
                "--limit", "50",
                "--json", "number,title,labels",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        issues_data: list[dict] = json.loads(raw)
        lines = []
        for issue in issues_data:
            label_names = [lbl["name"] for lbl in issue.get("labels", [])]
            label_str = f" [{', '.join(label_names)}]" if label_names else ""
            lines.append(f"- #{issue['number']}: {issue['title']}{label_str}")
        issues_text = "\n".join(lines) if lines else "(no open issues)"
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        # gh not available or call failed — exit silently
        sys.exit(0)
    except Exception:
        issues_text = "(gh unavailable)"

    ctx = build_context(repo, issues_text)
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": ctx,
        }
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
