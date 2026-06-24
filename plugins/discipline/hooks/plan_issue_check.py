#!/usr/bin/env python3
"""PostToolUse hook: enforce issue + value + retrospective discipline on plan files.

Runs after Write/Edit/MultiEdit. When the touched file matches the configured
plan_pattern, validates:

  Rule 1 (always): plan must reference at least one issue — a GitHub issue
                   (`#N`) or a beads id (e.g. `hb-9yw.4`).
  Rule 2 (always): if a `## Retrospective` section exists, it must include
                   `Closes` / `Updates` / `Follows up` against a `#N` or a
                   beads id (e.g. `Closes hb-9yw.4`).
  Rule 3 (opt-in): in-flight plans (no Retrospective body) must include
                   a parseable `## Value Justification` section using the
                   formula `score = impact * confidence / effort`.
                   Enabled via require-value-justification config.

Auto-closes `Closes #N` references via `gh` (requires `gh` on PATH and a
configured `repo`) and `Closes <bd-id>` references via `bd` (requires `bd`
on PATH and a configured `bd_ledger`). Both are idempotent: already-closed
issues are skipped.

Configuration (env > .claude/discipline.local.md > git auto-detect):
  - DISCIPLINE_REPO=owner/repo
  - DISCIPLINE_PLAN_PATTERN=...regex...
  - DISCIPLINE_BD_ID_PATTERN=...regex...
  - DISCIPLINE_BD_LEDGER=/path/to/beads/ledger
  - DISCIPLINE_REQUIRE_VALUE_JUSTIFICATION=true|false
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from discipline_config import get_config, normalize_path_to_repo  # noqa: E402

LOG_FILE = Path(__file__).parent / "plan_issue_check.log"

# Override-able via PLAN_ISSUE_CHECK_GH so tests can swap in a fake binary.
GH_BIN = os.environ.get("PLAN_ISSUE_CHECK_GH", "gh")

# Override-able via PLAN_ISSUE_CHECK_BD so tests can swap in a fake binary.
BD_BIN = os.environ.get("PLAN_ISSUE_CHECK_BD", "bd")


def log_failure(msg: str) -> None:
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat()} {msg}\n")
    except OSError:
        pass


def strip_code_spans_and_fences(text: str) -> str:
    """Strip fenced blocks and inline code spans before structural checks."""
    # 1. Paired triple-backtick / tilde fences with matching close
    text = re.sub(
        r"(?ms)^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[ \t]*$",
        "",
        text,
    )
    # 2. Double-backtick spans
    text = re.sub(r"``[^`\n]*?``", "", text)
    # 3. Single-backtick spans (bound by newlines)
    text = re.sub(r"`[^`\n]+?`", "", text)
    return text


def emit_block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def emit_system(msg: str) -> None:
    print(json.dumps({"systemMessage": msg}))


def extract_retro_body(text_unfenced: str) -> str | None:
    """Return the Retrospective section body (or None if absent)."""
    m = re.search(r"(?m)^##\s+Retrospective\s*$", text_unfenced)
    if not m:
        return None
    start = m.end()
    nxt = re.search(r"(?m)^##\s+", text_unfenced[start:])
    return text_unfenced[start: start + nxt.start()] if nxt else text_unfenced[start:]


def main() -> None:
    cfg = get_config()
    plan_re = re.compile(cfg.plan_pattern)

    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    raw = (
        data.get("tool_input", {}).get("file_path")
        or data.get("tool_response", {}).get("filePath")
        or ""
    )
    if not raw:
        sys.exit(0)

    rel = normalize_path_to_repo(raw, cfg.repo_root)
    if not plan_re.search(rel):
        sys.exit(0)

    try:
        text = Path(raw).read_text(encoding="utf-8")
    except OSError:
        sys.exit(0)

    # Rule 1: at least one issue citation — GitHub #N or a beads id (e.g. hb-9yw.4)
    if not (re.search(r"#\d+", text) or re.search(cfg.bd_id_pattern, text)):
        gh_hint = (
            f" Run 'gh issue list --repo {cfg.repo} --state open' to find one, "
            "or 'gh issue create' if none fits."
            if cfg.repo else ""
        )
        emit_block(
            f"Plan at {rel} must reference at least one issue: a GitHub issue "
            "(#N) or a beads id (e.g. hb-9yw.4)." + gh_hint
        )

    text_unfenced = strip_code_spans_and_fences(text)
    retro_body = extract_retro_body(text_unfenced)

    # Rule 2: Retrospective must record issue-state changes (GitHub #N or beads id)
    if retro_body is not None and not re.search(
        r"\b(Closes|Updates|Follows up)\s+(?:#\d+|" + cfg.bd_id_pattern + r")",
        retro_body,
    ):
        emit_block(
            f"Plan at {rel} has a Retrospective section but doesn't record "
            "issue-state changes. Add 'Closes #N' / 'Updates #N' / 'Follows up #N' "
            "(or the beads equivalent, e.g. 'Closes hb-9yw.4') to reflect which "
            "issues this work closes or spawns."
        )

    # Rule 3 (opt-in): Value Justification on in-flight plans
    if cfg.require_value_justification and retro_body is None:
        vj = re.search(r"(?ms)^##\s+Value Justification\s*$(.+?)(?=^##\s+|\Z)", text_unfenced)
        if not vj:
            emit_block(
                f"Plan at {rel} must include a '## Value Justification' "
                "section with impact, confidence, effort, and score "
                "(impact * confidence / effort). Template:\n\n"
                "  ## Value Justification\n\n"
                "  - **Impact** (1-5): N - rationale\n"
                "  - **Confidence** (1-5): N - rationale\n"
                "  - **Effort** (hours): N - honest estimate, >=1\n"
                "  - **Score**: N.NN  (impact * confidence / effort)"
            )
        else:
            body = vj.group(1)
            impact_m = re.search(r"\*\*Impact\*\*[^:]*:\s*([0-9.]+)", body)
            conf_m = re.search(r"\*\*Confidence\*\*[^:]*:\s*([0-9.]+)", body)
            eff_m = re.search(r"\*\*Effort\*\*[^:]*:\s*([0-9.]+)", body)
            score_m = re.search(r"\*\*Score\*\*\s*:\s*([0-9.]+)", body)
            if not (impact_m and conf_m and eff_m and score_m):
                emit_block(
                    f"Plan at {rel} '## Value Justification' section is "
                    "missing one of: Impact, Confidence, Effort, Score. "
                    "All four must be present and numeric."
                )
            try:
                impact = float(impact_m.group(1))
                conf = float(conf_m.group(1))
                eff = float(eff_m.group(1))
                score = float(score_m.group(1))
            except ValueError:
                emit_block(
                    f"Plan at {rel} '## Value Justification' has a "
                    "non-numeric value. All four scores must parse as floats."
                )
            if eff <= 0:
                emit_block(
                    f"Plan at {rel} effort must be > 0 (avoids division "
                    "by zero). 1 hour is the minimum."
                )
            expected = impact * conf / eff
            # +-5% tolerance for human rounding
            if abs(expected - score) / max(score, 0.01) > 0.05:
                emit_block(
                    f"Plan at {rel} score {score} does not match "
                    f"impact * confidence / effort = {impact}*{conf}/{eff} "
                    f"= {expected:.2f}. Recompute, or fix one of the inputs."
                )

    # Auto-close `Closes #N` from the Retrospective body (gh-gated)
    if retro_body is not None and cfg.has_gh:
        closed = []
        skipped = []
        for num in {int(n) for n in re.findall(r"\bCloses\s+#(\d+)", retro_body)}:
            try:
                state = subprocess.check_output(
                    [GH_BIN, "issue", "view", str(num), "--repo", cfg.repo,
                     "--json", "state", "--jq", ".state"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
            except Exception:
                skipped.append(num)
                continue
            if state == "OPEN":
                result = subprocess.run(
                    [GH_BIN, "issue", "close", str(num), "--repo", cfg.repo,
                     "--comment", f"Closed via plan: {rel}"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    closed.append(num)
                else:
                    skipped.append(num)
                    log_failure(
                        f"gh issue close {num} failed (exit {result.returncode}): "
                        f"{result.stderr.strip()}"
                    )

        parts = []
        if closed:
            parts.append("closed " + ", ".join(f"#{n}" for n in sorted(closed)))
        if skipped:
            parts.append("could not close " + ", ".join(f"#{n}" for n in sorted(skipped)))
        if parts:
            emit_system(f"plan_issue_check: {'; '.join(parts)}")

    # Auto-close `Closes <bd-id>` from the Retrospective body (bd-gated)
    if retro_body is not None and cfg.has_bd:
        bd_closed = []
        bd_skipped = []
        # dict.fromkeys dedupes while preserving first-seen order
        for bid in dict.fromkeys(
            re.findall(r"\bCloses\s+((?:bd|hb)-[0-9a-z]+(?:\.\d+)?)", retro_body)
        ):
            try:
                rows = json.loads(subprocess.check_output(
                    [BD_BIN, "-C", cfg.bd_ledger, "show", bid, "--json"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ))
                status = (rows[0].get("status") if rows else "") or ""
            except Exception:
                bd_skipped.append(bid)
                continue
            if status == "closed":
                continue
            result = subprocess.run(
                [BD_BIN, "-C", cfg.bd_ledger, "close", bid,
                 "-r", f"Closed via plan: {rel}"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                bd_closed.append(bid)
            else:
                bd_skipped.append(bid)
                log_failure(
                    f"bd close {bid} failed (exit {result.returncode}): "
                    f"{result.stderr.strip()}"
                )

        parts = []
        if bd_closed:
            parts.append("closed " + ", ".join(sorted(bd_closed)))
        if bd_skipped:
            parts.append("could not close " + ", ".join(sorted(bd_skipped)))
        if parts:
            emit_system(f"plan_issue_check (beads): {'; '.join(parts)}")

    sys.exit(0)


if __name__ == "__main__":
    main()
