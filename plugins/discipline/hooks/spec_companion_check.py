#!/usr/bin/env python3
"""PostToolUse hook: enforce companion-doc presence on new spec writes.

Fires only on `Write` (new doc creation), not `Edit`. When the touched
file matches the configured spec_pattern, validates:

  - Spec body must reference at least one GitHub issue (`#N`).
  - Spec must have a `## Goal` (or `# Goal` / `## N. Goal`) heading.
  - Spec must have any heading containing 'Acceptance' (case-insensitive).
  - Warn if no `## References` heading.
  - Warn when phrases suggest a companion doc (auth/security -> threat
    model; runbook/operate/monitor -> runbook; user guide/operator ->
    user guide) but no companion file is found at the conventional path.
  - Warn if a referenced ADR-NNNN file doesn't exist.
  - Warn if no companion plan exists within 7 days of `created`.

Spec pattern is configurable via DISCIPLINE_SPEC_PATTERN. Default matches
`docs/.../NNN-slug.md` or `docs/.../NNNN-slug.md`. The hook is silent
when the pattern doesn't match.
"""
from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from discipline_config import get_config, normalize_path_to_repo  # noqa: E402


ISSUE_RE = re.compile(r"#\d+")
ADR_REF_RE = re.compile(r"\bADR-(\d{3,4})\b")


# Phrase triggers (case-insensitive). Each maps to a (label, candidate
# path templates) tuple. The first existing path satisfies the rule.
COMPANION_TRIGGERS: list[tuple[tuple[str, ...], str, list[str]]] = [
    (
        ("auth", "oidc", "tls", "secret", "credential", "permission"),
        "threat model",
        [
            "docs/security/{slug}-threat-model.md",
            "docs/security/{number}-{slug}-threat-model.md",
        ],
    ),
    (
        ("runbook", "operate", "monitor", "deploy"),
        "runbook",
        ["docs/runbooks/{slug}.md"],
    ),
    (
        ("user guide", "operator manual", "operator workflow"),
        "user guide",
        [
            "docs/user/{slug}.md",
            "docs/user/{slug}-manual.md",
        ],
    ),
]


def parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:30]:
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
        fields[key] = value
    return fields


def strip_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for i in range(1, min(len(lines), 30)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1:])
    return text


def find_plan(repo_root: Path, number: str, slug: str) -> Optional[Path]:
    """Find a plan file under docs/**/plans/ matching number or slug."""
    for plans_dir in repo_root.rglob("plans"):
        if not plans_dir.is_dir():
            continue
        # Skip nested plans dirs that aren't under docs/
        if "docs" not in plans_dir.parts:
            continue
        for child in plans_dir.iterdir():
            if not child.is_file() or not child.name.endswith(".md"):
                continue
            if number in child.name or slug in child.name:
                return child
    return None


def days_between(a_iso: str, b_iso: str) -> Optional[int]:
    try:
        da = datetime.date.fromisoformat(a_iso)
        db = datetime.date.fromisoformat(b_iso)
    except ValueError:
        return None
    return abs((da - db).days)


def slug_prefixes(slug: str) -> list[str]:
    parts = slug.split("-")
    return ["-".join(parts[:i]) for i in range(len(parts), 0, -1)]


def companion_path_exists(
    repo_root: Path, templates: list[str], slug: str, number: str
) -> bool:
    prefixes = slug_prefixes(slug)
    for tmpl in templates:
        for candidate_slug in prefixes:
            candidate = repo_root / tmpl.format(slug=candidate_slug, number=number)
            if candidate.exists():
                return True
    if templates:
        first_template_dir = (repo_root / templates[0]).parent
        if first_template_dir.is_dir():
            for child in first_template_dir.iterdir():
                if not child.is_file():
                    continue
                stem = child.stem
                for candidate_slug in prefixes:
                    if stem.startswith(candidate_slug):
                        return True
    return False


def render_template_paths(templates: list[str], slug: str, number: str) -> str:
    return ", ".join(tmpl.format(slug=slug, number=number) for tmpl in templates)


def find_required_section(body: str, *names: str) -> bool:
    pattern = r"(?im)^#{1,6}\s+(\d+\.?\s+)?(" + "|".join(re.escape(n) for n in names) + r")\b"
    return re.search(pattern, body) is not None


def find_acceptance_section(body: str) -> bool:
    return re.search(r"(?im)^#{1,6}\s+.*\bacceptance\b", body) is not None


def find_references_section(body: str) -> bool:
    return re.search(r"(?im)^#{1,6}\s+references\b", body) is not None


def adr_path(repo_root: Path, number: str) -> Optional[Path]:
    """Find an ADR-NNNN-*.md file under any docs/**/adrs/ directory."""
    for adrs_dir in repo_root.rglob("adrs"):
        if not adrs_dir.is_dir() or "docs" not in adrs_dir.parts:
            continue
        prefix = f"ADR-{number}-"
        for child in adrs_dir.iterdir():
            if child.is_file() and child.name.startswith(prefix) and child.name.endswith(".md"):
                return child
    return None


def emit_block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def emit_warn(message: str) -> None:
    print(json.dumps({"systemMessage": message}))
    sys.exit(0)


def check(rel_path: str, text: str, repo_root: Path, spec_re: re.Pattern,
          today: Optional[datetime.date] = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    m = spec_re.match(rel_path)
    if not m:
        return errors, warnings

    # Try to extract number + slug from the spec path
    name = rel_path.rsplit("/", 1)[-1].removesuffix(".md")
    name_m = re.match(r"^(\d{3,4})-([\w-]+)$", name)
    if name_m:
        number, slug = name_m.group(1), name_m.group(2)
    else:
        number, slug = "", name

    body = strip_frontmatter(text)
    fields = parse_frontmatter(text)

    if not ISSUE_RE.search(body):
        errors.append(
            "spec body must reference at least one GitHub issue (`#N`). "
            "Add `Tracks #<issue>.` near the top."
        )

    if not find_required_section(body, "Goal"):
        errors.append("missing required section `## Goal`.")

    if not find_acceptance_section(body):
        errors.append("missing required section: any heading containing `Acceptance`.")

    if not find_references_section(body):
        warnings.append(
            "no `## References` section found. References can be inline, "
            "but a dedicated section is recommended for traceability."
        )

    body_lower = body.lower()
    matched_triggers: set[str] = set()
    for phrases, label, templates in COMPANION_TRIGGERS:
        if label in matched_triggers:
            continue
        if any(p in body_lower for p in phrases):
            matched_triggers.add(label)
            if not companion_path_exists(repo_root, templates, slug, number):
                hint = render_template_paths(templates, slug, number)
                warnings.append(
                    f"spec mentions {label} concerns but no companion "
                    f"doc found at: {hint}"
                )

    referenced_adrs = set(ADR_REF_RE.findall(body))
    for adr_num in sorted(referenced_adrs):
        if adr_path(repo_root, adr_num) is None:
            errors.append(
                f"references `ADR-{adr_num}` but no matching file under "
                f"docs/**/adrs/ADR-{adr_num}-*.md exists."
            )

    if number:
        plan = find_plan(repo_root, number, slug)
        if plan is None:
            created = fields.get("created", "")
            today_iso = (today or datetime.date.today()).isoformat()
            gap = days_between(created, today_iso) if created else None
            if gap is None or gap > 7:
                warnings.append(
                    "no companion plan found under docs/**/plans/ matching "
                    f"`{number}` or `{slug}`. Plans can come later in the "
                    "same arc, but should land within 7 days of the spec."
                )

    return errors, warnings


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool = data.get("tool_name") or data.get("tool") or ""
    if tool and tool != "Write":
        return 0

    cfg = get_config()
    if cfg.repo_root is None:
        return 0

    raw = (
        data.get("tool_input", {}).get("file_path")
        or data.get("tool_response", {}).get("filePath")
        or ""
    )
    if not raw:
        return 0

    rel_path = normalize_path_to_repo(raw, cfg.repo_root)
    spec_re = re.compile(cfg.spec_pattern)
    if not spec_re.match(rel_path):
        return 0

    try:
        text = Path(raw).read_text(encoding="utf-8")
    except OSError:
        return 0

    errors, warnings = check(rel_path, text, cfg.repo_root, spec_re)
    if errors:
        bullet = "\n  - "
        msg = (
            f"spec_companion_check: {rel_path} fails the companion-doc gate."
            f"{bullet}" + bullet.join(errors)
        )
        sys.stderr.write(msg + "\n")
        emit_block(msg)
    if warnings:
        bullet = "\n  - "
        msg = (
            f"spec_companion_check: {rel_path} companion-doc warnings."
            f"{bullet}" + bullet.join(warnings)
        )
        sys.stderr.write(msg + "\n")
        emit_warn(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
