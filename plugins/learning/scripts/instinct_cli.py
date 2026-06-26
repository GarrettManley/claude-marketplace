"""Learning instinct CLI: status / import / export subcommands.

Delegated to by `/instinct-status`, `/instinct-import`, `/instinct-export`
slash commands. Phase 1 implements the read + manual-transfer surface.
Phase 2 adds auto-creation; Phase 3 adds evolve/promote/prune.

Adapted from affaan-m/everything-claude-code @ 4774946d,
skills/continuous-learning-v2/scripts/instinct-cli.py (subset).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from instinct_schema import (  # noqa: E402
    Instinct,
    format_instinct,
    parse_instinct,
    parse_multi_instinct_file,
)
from detect import cmd_detect  # noqa: E402
from evolve import cmd_evolve  # noqa: E402
from promote import cmd_promote  # noqa: E402
from prune import cmd_prune  # noqa: E402
from storage import (  # noqa: E402
    get_global_instincts_dir,
    get_project_id,
    get_project_instincts_dir,
    list_instinct_files,
)


def _load_all_instincts(directory: Path) -> list[Instinct]:
    out: list[Instinct] = []
    for f in list_instinct_files(directory):
        try:
            out.append(parse_instinct(f.read_text(encoding="utf-8")))
        except (ValueError, OSError) as e:
            print(f"  [skip] {f.name}: {e}", file=sys.stderr)
    return out


def _scope_dirs(scope: str) -> list[Path]:
    if scope == "global":
        base = get_global_instincts_dir()
        return [base / "personal", base / "inherited"]
    base = get_project_instincts_dir(get_project_id())
    return [base / "personal", base / "inherited"]


def _print_by_domain(instincts: list[Instinct], *, scope: str) -> None:
    by_domain: dict[str, list[Instinct]] = {}
    for i in instincts:
        by_domain.setdefault(i.domain, []).append(i)
    for domain, items in sorted(by_domain.items()):
        print(f"  ### {domain.upper()} ({len(items)})")
        for inst in sorted(items, key=lambda x: -x.confidence):
            bar_len = int(inst.confidence * 10)
            bar = "█" * bar_len + "░" * (10 - bar_len)
            print(f"    {bar}  {int(inst.confidence * 100)}%  {inst.id} [{scope}]")
            print(f"              trigger: {inst.trigger}")


def cmd_status() -> int:
    project_instincts: list[Instinct] = []
    for d in _scope_dirs("project"):
        project_instincts.extend(_load_all_instincts(d))
    global_instincts: list[Instinct] = []
    for d in _scope_dirs("global"):
        global_instincts.extend(_load_all_instincts(d))
    total = len(project_instincts) + len(global_instincts)
    print("=" * 60)
    print(f"  INSTINCT STATUS - {total} total")
    print("=" * 60)
    print()
    pid = get_project_id()
    print(f"  Project: {pid}")
    print(f"  Project instincts: {len(project_instincts)}")
    print(f"  Global instincts:  {len(global_instincts)}")
    print()
    if not total:
        print("  no instincts found yet. Phase 1 ships the schema + storage;")
        print("  Phase 2 adds auto-creation from observations.")
        return 0
    if project_instincts:
        print(f"## PROJECT-SCOPED ({pid})")
        _print_by_domain(project_instincts, scope="project")
    if global_instincts:
        print()
        print("## GLOBAL (apply to all projects)")
        _print_by_domain(global_instincts, scope="global")
    return 0


def cmd_import(file_path: str, *, scope: str = "global") -> int:
    src = Path(file_path)
    if not src.is_file():
        print(f"[import] file not found: {file_path}", file=sys.stderr)
        return 1
    try:
        text = src.read_text(encoding="utf-8")
        instincts = parse_multi_instinct_file(text)
    except (ValueError, OSError) as e:
        print(f"[import] parse failed: {e}", file=sys.stderr)
        return 1
    if scope == "global":
        target_dir = get_global_instincts_dir() / "inherited"
    else:
        target_dir = get_project_instincts_dir(get_project_id()) / "inherited"
    target_dir.mkdir(parents=True, exist_ok=True)
    for inst in instincts:
        out_file = target_dir / f"{inst.id}.yaml"
        out_file.write_text(format_instinct(inst), encoding="utf-8")
        print(f"[import] {inst.id} -> {out_file}")
    print(f"[import] {len(instincts)} instinct(s) imported to {scope} scope")
    return 0


def cmd_export(file_path: str, *, scope: str = "global") -> int:
    instincts: list[Instinct] = []
    for d in _scope_dirs(scope):
        instincts.extend(_load_all_instincts(d))
    if not instincts:
        print(f"[export] no {scope} instincts to export", file=sys.stderr)
        return 1
    out = Path(file_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    parts = [format_instinct(inst) for inst in instincts]
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"[export] {len(instincts)} instinct(s) -> {out}")
    return 0


def cmd_analyze() -> int:
    """Report tool-use patterns from observations.jsonl.

    Manual-review workflow: read the report, decide which patterns warrant
    an instinct, then create the YAML file and import via /instinct-import.
    Does not auto-create instincts.
    """
    from analyze import (
        load_observations,
        tool_frequency,
        pre_post_sequences,
        bash_command_prefixes,
        file_hotspots,
    )
    records = load_observations()
    print("=" * 60)
    print(f"  OBSERVATION ANALYSIS - {len(records)} records")
    print("=" * 60)
    if not records:
        print()
        print("  no observations recorded yet. Enable with:")
        print("    export LEARNING_HOOK_PROFILE=strict")
        print("    export LEARNING_OBSERVE=on")
        return 0

    freq = tool_frequency(records)
    print()
    print("## Tool-use frequency (pre-phase)")
    for name, count in sorted(freq.items(), key=lambda kv: -kv[1]):
        print(f"  {count:>5}  {name}")

    seqs = pre_post_sequences(records)
    if seqs:
        print()
        print("## Tool-pair sequences (B fires within 30s after A, same session)")
        top = sorted(seqs.items(), key=lambda kv: -kv[1])[:10]
        for (a, b), count in top:
            print(f"  {count:>5}  {a} -> {b}")

    bash = bash_command_prefixes(records, top_n=10)
    if bash:
        print()
        print("## Top Bash command prefixes")
        for prefix, count in bash:
            print(f"  {count:>5}  {prefix}")

    hotspots = file_hotspots(records, top_n=10)
    if hotspots:
        print()
        print("## File hotspots (Edit/Write/MultiEdit)")
        for path, count in hotspots:
            print(f"  {count:>5}  {path}")

    print()
    print("Auto-create instincts from these patterns with `synthesize`, or write a")
    print("YAML file by hand and load it via `/instinct-import`.")
    return 0


def cmd_synthesize(
    *,
    scope: str = "project",
    min_support: int = 5,
    min_consistency: float = 0.5,
    write: bool = False,
) -> int:
    """Auto-create instincts from frequency patterns in observations.jsonl.

    Dry-run by default (prints candidates, writes nothing). Pass write=True to
    persist them to the scope's `personal/` directory. Phase 2b.
    """
    from analyze import load_observations
    from synthesize import synthesize, get_target_dir, write_instincts

    records = load_observations()
    candidates = synthesize(
        records, min_support=min_support, min_consistency=min_consistency
    )
    print("=" * 60)
    print(f"  INSTINCT SYNTHESIS - {len(candidates)} candidate(s) "
          f"from {len(records)} observation(s)")
    print("=" * 60)
    if not candidates:
        print()
        if not records:
            print("  no observations recorded yet. Enable with:")
            print("    export LEARNING_HOOK_PROFILE=strict")
            print("    export LEARNING_OBSERVE=on")
        else:
            print(f"  no patterns met the thresholds "
                  f"(min_support={min_support}, min_consistency={min_consistency}).")
        return 0

    print()
    for inst in candidates:
        print(f"  {int(inst.confidence * 100):>3}%  [{inst.domain}]  {inst.id}")
        print(f"        {inst.title}")

    target_dir = get_target_dir(scope)
    counts = write_instincts(candidates, target_dir, dry_run=not write)
    print()
    if write:
        print(f"[synthesize] {counts['written']} written, {counts['updated']} updated, "
              f"{counts['skipped']} skipped -> {target_dir}")
    else:
        print(f"[synthesize] dry-run: {counts['written']} new, {counts['updated']} would update, "
              f"{counts['skipped']} preserved. Re-run with --write to persist.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="instinct_cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="show all instincts")
    p_import = sub.add_parser("import", help="import instincts from file")
    p_import.add_argument("file", help="path to YAML instinct file")
    p_import.add_argument("--scope", choices=["global", "project"], default="global")
    p_export = sub.add_parser("export", help="export instincts to file")
    p_export.add_argument("file", help="output path")
    p_export.add_argument("--scope", choices=["global", "project"], default="global")
    sub.add_parser("analyze", help="report tool-use patterns from observations.jsonl")
    p_syn = sub.add_parser("synthesize", help="auto-create instincts from observation patterns")
    p_syn.add_argument("--scope", choices=["global", "project"], default="project")
    p_syn.add_argument("--min-support", type=int, default=5)
    p_syn.add_argument("--min-consistency", type=float, default=0.5)
    p_syn.add_argument("--write", action="store_true", help="persist (default: dry-run)")

    p_detect = sub.add_parser("detect", help="Claude-driven correction/preference detection (Phase 2c)")
    p_detect.add_argument("--scope", choices=["global", "project"], default="project")
    p_detect.add_argument("--dump-observations", action="store_true",
                          help="emit a JSON observation summary for Claude to reason over")
    p_detect.add_argument("--ingest", metavar="FILE", help="ingest Claude-authored candidate instincts")
    p_detect.add_argument("--apply", action="store_true", help="persist (default: dry-run)")

    p_prune = sub.add_parser("prune", help="decay-prune machine instincts below the floor (Phase 3)")
    p_prune.add_argument("--scope", choices=["global", "project"], default="project")
    p_prune.add_argument("--apply", action="store_true", help="delete (default: dry-run; snapshots first)")

    p_promote = sub.add_parser("promote", help="promote a project instinct to the global store (Phase 3)")
    p_promote.add_argument("id", nargs="?", help="instinct id to promote (omit when using --auto)")
    p_promote.add_argument("--auto", action="store_true",
                           help="auto-promote instincts widespread across projects with high confidence")
    p_promote.add_argument("--scope", choices=["global", "project"], default="project")
    p_promote.add_argument("--apply", action="store_true", help="apply (default: dry-run; snapshots first)")

    p_evolve = sub.add_parser("evolve", help="cluster + merge near-duplicate instincts (Phase 3)")
    p_evolve.add_argument("--scope", choices=["global", "project"], default="project")
    p_evolve.add_argument("--apply", action="store_true", help="merge (default: dry-run; snapshots first)")

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.cmd == "status":
        return cmd_status()
    if args.cmd == "import":
        return cmd_import(args.file, scope=args.scope)
    if args.cmd == "export":
        return cmd_export(args.file, scope=args.scope)
    if args.cmd == "analyze":
        return cmd_analyze()
    if args.cmd == "synthesize":
        return cmd_synthesize(
            scope=args.scope,
            min_support=args.min_support,
            min_consistency=args.min_consistency,
            write=args.write,
        )
    if args.cmd == "detect":
        return cmd_detect(
            scope=args.scope,
            dump_observations=args.dump_observations,
            ingest_path=args.ingest,
            apply=args.apply,
        )
    if args.cmd == "prune":
        return cmd_prune(scope=args.scope, apply=args.apply)
    if args.cmd == "promote":
        return cmd_promote(args.id, scope=args.scope, auto=args.auto, apply=args.apply)
    if args.cmd == "evolve":
        return cmd_evolve(scope=args.scope, apply=args.apply)
    return 2


if __name__ == "__main__":
    sys.exit(main())
