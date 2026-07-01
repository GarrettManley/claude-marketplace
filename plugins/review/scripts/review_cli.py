#!/usr/bin/env python3
"""review_cli — automate the reviewer-personas Post-Cycle Update Protocol.

`evolve --ingest <dir>` ingests Claude-authored full-persona rewrites: it
validates each file's structure, shows a dry-run diff, and (with --apply)
atomic-writes them. The judgment (what to refine) lives in
commands/review-evolve.md; this script is the mechanical, testable half.

Target defaults to project-local `.claude/agents/` (adopter-safe — never the
read-only install cache). The maintainer passes `--agents-dir
plugins/review/agents/` to sharpen the shipped library. Dry-run is the default;
git is the snapshot — there is no .snapshots/ backup, so run --apply on a clean
target tree (a mid-batch I/O failure can leave earlier files written; recover
with `git checkout`).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import persona

_DEFAULT_AGENTS_DIR = Path(".claude/agents")
_SUFFIX = ".agent.md"

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_DEFAULT_DESCRIPTION = ("Use when <triggering conditions>. Catches <the concrete patterns "
                        "this archetype flags>.")
_PERSONA_SKELETON = """\
---
name: {name}
description: |
  {description}
tools: Read, Grep, Glob, Bash
---

# {title} — <short tagline>

Archetype — <one-line note on what this reviewer is>.

- **Cares about:** <the 1–2 things this reviewer prioritizes; the lens it reads everything through>
- **Feedback style:** <how findings are phrased>
- **Knowledge:** <domain knowledge this persona has, and what is out of its depth>
- **Pushback triggers:**
  - <Trigger 1 — specific enough that another reader can recognize when it fires>
  - <Trigger 2>
  - <Trigger 3>
- **NOT covered:** <the lanes this reviewer stays out of — this boundary defines false positives. Mandatory.>
- **Severity rubric:**
  - `blocker` — <a finding that should stop a merge>
  - `must_fix` — <a finding that must be addressed before publication>
  - `nit` — <nice to fix, not a gate>
  - `signal` — <a current non-issue that worsens under foreseeable change>
  - `praise` — <a pattern to call out positively>
- **Source:** Archetype — scaffolded; fill in pushback triggers from real review catches.
- **Last updated:** <YYYY-MM-DD> — scaffolded skeleton.
"""


def _ingest(ingest_dir: Path, agents_dir: Path, apply: bool) -> int:
    proposals = sorted(Path(ingest_dir).glob(f"*{_SUFFIX}"))
    if not proposals:
        print(f"no *{_SUFFIX} files in {ingest_dir}")
        return 1

    planned: list[tuple[str, Path, str, str]] = []  # stem, target, old, new
    deferred: list[str] = []  # unknown personas
    validation_errors: list[str] = []  # invalid content
    for p in proposals:
        stem = p.name[: -len(_SUFFIX)]
        target = agents_dir / f"{stem}{_SUFFIX}"
        new_text = p.read_text(encoding="utf-8")
        if not target.exists():
            deferred.append(
                f"{stem}: unknown persona; new-archetype scaffolding is deferred "
                f"(see D3 follow-up). Target {target} does not exist."
            )
            continue
        validation_errors.extend(f"{stem}: {e}" for e in persona.validate_persona(new_text, stem))
        planned.append((stem, target, target.read_text(encoding="utf-8"), new_text))

    if deferred:
        print("ingest deferred:")
        for d in deferred:
            print(f"  - {d}")

    if validation_errors:
        print("ingest rejected:")
        for e in validation_errors:
            print(f"  - {e}")
        return 1

    if not planned:
        # No valid personas to process (only deferred ones)
        return 1

    for stem, target, old, new in planned:
        if old == new:
            print(f"{stem}: no change")
            continue
        if persona.last_updated_line(old) == persona.last_updated_line(new):
            print(f"warning: {stem}: **Last updated** line unchanged — did you forget to bump it?")
        if apply:
            persona.atomic_write(target, new)
            print(f"wrote {stem}")
        else:
            print(persona.render_diff(old, new, f"{agents_dir}/{stem}{_SUFFIX}"))
    if not apply:
        print("dry-run: pass --apply to write (run on a clean target tree).")
    return 0


def cmd_evolve(*, ingest_dir: str | None, apply: bool, agents_dir: Path) -> int:
    if not ingest_dir:
        print("evolve: pass --ingest <dir> (a dir of Claude-authored <name>.agent.md rewrites).")
        return 1
    return _ingest(Path(ingest_dir), agents_dir, apply)


def cmd_scaffold(name, *, description, apply, agents_dir) -> int:
    """Create a new archetype persona skeleton (valid-but-placeholdered) for the human to fill."""
    if not _NAME_RE.match(name):
        print(f"scaffold: invalid persona name {name!r} — use a lowercase slug "
              "(e.g. concurrency-reviewer).")
        return 1
    target = Path(agents_dir) / f"{name}{_SUFFIX}"
    if target.exists():
        print(f"scaffold: persona {name!r} already exists at {target}; "
              "use /review-evolve to refine it.")
        return 1
    content = _PERSONA_SKELETON.format(
        name=name,
        title=name.replace("-", " ").title(),
        description=description or _DEFAULT_DESCRIPTION,
    )
    errors = persona.validate_persona(content, name)
    if errors:  # pragma: no cover - the skeleton is pinned valid by test_skeleton_is_valid
        print("scaffold: internal error — skeleton failed validation:")
        for e in errors:
            print(f"  - {e}")
        return 1
    if apply:
        Path(agents_dir).mkdir(parents=True, exist_ok=True)
        persona.atomic_write(target, content)
        print(f"scaffolded {name} -> {target}. Fill its pushback triggers, then commit.")
    else:
        print(content)
        print("dry-run: pass --apply to write.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="review_cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("evolve", help="automate the Post-Cycle Update Protocol")
    p.add_argument("--ingest", metavar="DIR", help="dir of Claude-authored full-persona rewrites")
    p.add_argument("--apply", action="store_true", help="write (default: dry-run diff)")
    p.add_argument("--agents-dir", default=str(_DEFAULT_AGENTS_DIR),
                   help="target persona dir (default: .claude/agents; maintainer: plugins/review/agents)")

    s = sub.add_parser("scaffold", help="create a new archetype persona skeleton")
    s.add_argument("name", help="persona slug (== filename stem), e.g. concurrency-reviewer")
    s.add_argument("--description", help="frontmatter description (default: a placeholder)")
    s.add_argument("--apply", action="store_true", help="write (default: print the skeleton)")
    s.add_argument("--agents-dir", default=str(_DEFAULT_AGENTS_DIR),
                   help="target persona dir (default: .claude/agents; maintainer: plugins/review/agents)")

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.cmd == "evolve":
        return cmd_evolve(ingest_dir=args.ingest, apply=args.apply, agents_dir=Path(args.agents_dir))
    if args.cmd == "scaffold":
        return cmd_scaffold(args.name, description=args.description,
                            apply=args.apply, agents_dir=Path(args.agents_dir))
    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
