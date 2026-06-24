#!/usr/bin/env python3
"""Drift-check: verify context-file claims by running their verification commands.

Scans `.md` files under a context directory for `verification_cmd:` frontmatter
keys, runs each command, and reports pass / fail. A generic, repo-agnostic
context-file drift check, decoupled from any specific repo.

Frontmatter format expected:

    ---
    topic: ...
    verification_cmd: "nvidia-smi"   # any shell command
    ---

The command runs in the context dir (so relative paths resolve there).
Pass = exit 0, Fail = anything else. Output is structured JSON suitable
for piping to other tools or templating into a briefing.

Usage:
    python drift_check.py [--dir PATH] [--json]

Markdown is the default output; pass --json for machine-readable output.
Default --dir is `~/.claude/context/`.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

VERIFICATION_RE = re.compile(r"^verification_cmd:\s*(.+?)\s*$", re.MULTILINE)
LAST_VERIFIED_RE = re.compile(r"^last_verified:\s*['\"]?(\d{4}-\d{2}-\d{2})", re.MULTILINE)


@dataclass
class CheckResult:
    file: str
    cmd: str
    passed: bool
    exit_code: int
    stdout: str
    stderr: str


def extract_verification_cmd(text: str) -> str | None:
    """Pull the verification_cmd value from YAML-ish frontmatter."""
    if not text.startswith("---"):
        return None
    # Bound the search to the frontmatter block (first --- to next ---)
    end = text.find("\n---", 3)
    block = text[:end] if end > 0 else text[:1000]
    m = VERIFICATION_RE.search(block)
    if not m:
        return None
    val = m.group(1).strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in {"'", '"'}:
        val = val[1:-1]
    return val or None


def extract_last_verified(text: str) -> date | None:
    """Pull the last_verified date from frontmatter (date or datetime forms)."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    block = text[:end] if end > 0 else text[:1000]
    m = LAST_VERIFIED_RE.search(block)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


@dataclass
class StaleResult:
    file: str
    last_verified: str
    age_days: int


def scan_staleness(
    context_dir: Path, max_age_days: int, today: date | None = None
) -> list[StaleResult]:
    """Files whose last_verified is older than max_age_days (<=0 disables).

    Catches the failure mode verification_cmd can't: a command that still
    exits 0 while nobody has actually re-read the claims in months.
    """
    if max_age_days <= 0:
        return []
    today = today or date.today()
    out: list[StaleResult] = []
    for path in sorted(context_dir.rglob("*.md")):
        if path.name == "README.md":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        verified = extract_last_verified(text)
        if verified is None:
            continue
        age = (today - verified).days
        if age > max_age_days:
            out.append(
                StaleResult(
                    file=str(path),
                    last_verified=verified.isoformat(),
                    age_days=age,
                )
            )
    return out


def run_check(path: Path, cmd: str, cwd: Path, timeout: int = 30) -> CheckResult:
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=cwd, timeout=timeout,
            capture_output=True, text=True,
        )
        return CheckResult(
            file=str(path), cmd=cmd, passed=proc.returncode == 0,
            exit_code=proc.returncode,
            stdout=proc.stdout[:500], stderr=proc.stderr[:500],
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            file=str(path), cmd=cmd, passed=False, exit_code=-1,
            stdout="", stderr=f"timed out after {timeout}s",
        )
    except OSError as e:
        return CheckResult(
            file=str(path), cmd=cmd, passed=False, exit_code=-1,
            stdout="", stderr=f"command failed to launch: {e}",
        )


def scan_context_dir(context_dir: Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    for path in sorted(context_dir.rglob("*.md")):
        if path.name == "README.md":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        cmd = extract_verification_cmd(text)
        if not cmd:
            continue
        results.append(run_check(path, cmd, context_dir))
    return results


def render_markdown(
    results: list[CheckResult], stale: list[StaleResult] | None = None
) -> str:
    stale = stale or []
    if not results and not stale:
        return "## Drift Check\n\n_No verifiable context files found._\n"
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    lines = [
        "## Drift Check",
        "",
        f"- Files verified: **{len(results)}**",
        f"- Passed: **{len(passed)}**",
        f"- Failed: **{len(failed)}**",
        f"- Stale (last_verified): **{len(stale)}**",
        "",
    ]
    if stale:
        lines.append("### Stale")
        for s in stale:
            lines.append(
                f"- `{Path(s.file).name}` last_verified {s.last_verified} ({s.age_days}d ago)"
            )
        lines.append("")
    if failed:
        lines.append("### Failures")
        for r in failed:
            lines.append(f"- `{Path(r.file).name}` (`{r.cmd}` exit {r.exit_code})")
            if r.stderr.strip():
                lines.append(f"  - stderr: `{r.stderr.strip().splitlines()[0][:200]}`")
        lines.append("")
    if passed:
        lines.append("### Passed")
        for r in passed:
            lines.append(f"- `{Path(r.file).name}`")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify context-file claims via their verification_cmd.")
    parser.add_argument(
        "--dir", type=Path,
        default=Path.home() / ".claude" / "context",
        help="Directory to scan recursively for *.md files (default: ~/.claude/context/)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    parser.add_argument(
        "--max-age-days", type=int, default=45,
        help="Flag files whose last_verified is older than this (0 disables; default 45)",
    )
    args = parser.parse_args()

    if not args.dir.is_dir():
        print(f"drift_check: directory not found: {args.dir}", file=sys.stderr)
        return 2

    results = scan_context_dir(args.dir)
    stale = scan_staleness(args.dir, args.max_age_days)

    if args.json:
        print(json.dumps(
            {"checks": [asdict(r) for r in results], "stale": [asdict(s) for s in stale]},
            indent=2,
        ))
    else:
        print(render_markdown(results, stale))

    failed = sum(1 for r in results if not r.passed)
    return 1 if failed or stale else 0


if __name__ == "__main__":
    sys.exit(main())
