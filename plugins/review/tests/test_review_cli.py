import review_cli

_PERSONA = """---
name: security-auditor
description: |
  Trust boundaries.
tools: Read, Grep, Glob, Bash
---

# Security Auditor

- **Pushback triggers:**
  - {trigger}
- **NOT covered:** business logic.
- **Severity rubric:**
  - `blocker` — exploitable without auth
- **Last updated:** {ver} — {reason}
"""


def _persona(trigger="Permissions broader than needed", ver="0.1.0", reason="initial"):
    return _PERSONA.format(trigger=trigger, ver=ver, reason=reason)


def _seed_agents(tmp_path):
    a = tmp_path / "agents"
    a.mkdir()
    (a / "security-auditor.agent.md").write_text(_persona(), encoding="utf-8")
    return a


def _seed_proposal(tmp_path, text, name="security-auditor"):
    d = tmp_path / "proposed"
    d.mkdir(exist_ok=True)
    (d / f"{name}.agent.md").write_text(text, encoding="utf-8")
    return d


def test_ingest_dry_run_writes_nothing(tmp_path, capsys):
    agents = _seed_agents(tmp_path)
    proposed = _seed_proposal(tmp_path, _persona(trigger="New trigger", ver="1.2.0", reason="from s cycle"))
    before = (agents / "security-auditor.agent.md").read_text(encoding="utf-8")
    rc = review_cli.main(["evolve", "--ingest", str(proposed), "--agents-dir", str(agents)])
    assert rc == 0
    assert "dry-run" in capsys.readouterr().out
    assert (agents / "security-auditor.agent.md").read_text(encoding="utf-8") == before


def test_ingest_apply_writes(tmp_path):
    agents = _seed_agents(tmp_path)
    proposed = _seed_proposal(tmp_path, _persona(trigger="New trigger", ver="1.2.0", reason="from s cycle"))
    rc = review_cli.main(["evolve", "--ingest", str(proposed), "--agents-dir", str(agents), "--apply"])
    assert rc == 0
    assert "New trigger" in (agents / "security-auditor.agent.md").read_text(encoding="utf-8")


def test_ingest_defers_unknown_persona(tmp_path, capsys):
    agents = _seed_agents(tmp_path)
    proposed = _seed_proposal(
        tmp_path, _persona().replace("security-auditor", "data-architect"), name="data-architect")
    rc = review_cli.main(["evolve", "--ingest", str(proposed), "--agents-dir", str(agents)])
    assert rc == 1
    assert "deferred" in capsys.readouterr().out.lower()


def test_ingest_rejects_invalid_persona_and_writes_nothing(tmp_path):
    agents = _seed_agents(tmp_path)
    broken = _persona().replace("- **Severity rubric:**", "- **Notes:**")
    proposed = _seed_proposal(tmp_path, broken)
    before = (agents / "security-auditor.agent.md").read_text(encoding="utf-8")
    rc = review_cli.main(["evolve", "--ingest", str(proposed), "--agents-dir", str(agents), "--apply"])
    assert rc == 1
    assert (agents / "security-auditor.agent.md").read_text(encoding="utf-8") == before


def test_ingest_empty_dir(tmp_path, capsys):
    agents = _seed_agents(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    rc = review_cli.main(["evolve", "--ingest", str(empty), "--agents-dir", str(agents)])
    assert rc == 1
    assert "no" in capsys.readouterr().out.lower()


def test_ingest_no_change(tmp_path, capsys):
    agents = _seed_agents(tmp_path)
    proposed = _seed_proposal(tmp_path, _persona())  # identical to seeded
    rc = review_cli.main(["evolve", "--ingest", str(proposed), "--agents-dir", str(agents)])
    assert rc == 0
    assert "no change" in capsys.readouterr().out.lower()


def test_ingest_warns_on_unchanged_last_updated(tmp_path, capsys):
    agents = _seed_agents(tmp_path)
    # trigger differs but Last updated line is identical -> warn
    proposed = _seed_proposal(tmp_path, _persona(trigger="Different trigger"))
    rc = review_cli.main(["evolve", "--ingest", str(proposed), "--agents-dir", str(agents)])
    assert rc == 0
    assert "last updated" in capsys.readouterr().out.lower()


def test_bare_evolve_usage(capsys):
    rc = review_cli.main(["evolve"])
    assert rc == 1
    assert "--ingest" in capsys.readouterr().out


# --- #12: scaffold a new archetype persona ------------------------------------

import persona  # noqa: E402  (conftest puts scripts/ on sys.path)


def test_scaffold_dry_run_writes_nothing(tmp_path, capsys):
    agents = tmp_path / "agents"
    agents.mkdir()
    rc = review_cli.main(["scaffold", "concurrency-reviewer", "--agents-dir", str(agents)])
    out = capsys.readouterr().out
    assert rc == 0 and "dry-run" in out
    assert not (agents / "concurrency-reviewer.agent.md").exists()
    assert "name: concurrency-reviewer" in out


def test_scaffold_apply_writes_valid_persona(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    rc = review_cli.main(["scaffold", "concurrency-reviewer", "--agents-dir", str(agents), "--apply"])
    assert rc == 0
    f = agents / "concurrency-reviewer.agent.md"
    assert f.exists()
    assert persona.validate_persona(f.read_text(encoding="utf-8"), "concurrency-reviewer") == []


def test_scaffold_rejects_existing_persona(tmp_path, capsys):
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "security-auditor.agent.md").write_text("existing", encoding="utf-8")
    rc = review_cli.main(["scaffold", "security-auditor", "--agents-dir", str(agents), "--apply"])
    out = capsys.readouterr().out
    assert rc == 1 and "already exists" in out.lower()
    assert (agents / "security-auditor.agent.md").read_text(encoding="utf-8") == "existing"


def test_scaffold_rejects_bad_name(tmp_path, capsys):
    agents = tmp_path / "agents"
    agents.mkdir()
    rc = review_cli.main(["scaffold", "Bad Name!", "--agents-dir", str(agents)])
    assert rc == 1 and "name" in capsys.readouterr().out.lower()


def test_scaffold_with_description(tmp_path, capsys):
    agents = tmp_path / "agents"
    agents.mkdir()
    review_cli.main(["scaffold", "perf-reviewer", "--agents-dir", str(agents),
                     "--description", "Use when reviewing latency claims."])
    assert "Use when reviewing latency claims." in capsys.readouterr().out


def test_skeleton_is_valid():
    content = review_cli._PERSONA_SKELETON.format(
        name="x-reviewer", title="X Reviewer", description="d")
    assert persona.validate_persona(content, "x-reviewer") == []


def test_ingest_mixed_batch_defers_unknown_and_processes_valid(tmp_path, capsys):
    """Test that in a single ingest call, unknown personas are deferred and valid ones are still processed.

    Exercises BOTH the skip-path (unknown persona continue) and normal-path (valid persona processing)
    within the SAME _ingest() invocation.
    """
    agents = _seed_agents(tmp_path)
    proposed = _seed_proposal(tmp_path, _persona(trigger="Modified trigger"), name="security-auditor")
    # Add a second file to the proposed dir with an unknown persona (name mismatch)
    _seed_proposal(
        tmp_path,
        _persona().replace("security-auditor", "data-architect"),
        name="data-architect"
    )
    # Run in dry-run mode (default)
    rc = review_cli.main(["evolve", "--ingest", str(proposed), "--agents-dir", str(agents)])
    out = capsys.readouterr().out
    # Unknown persona should be deferred (mentioned in output)
    assert "deferred" in out.lower()
    # Valid persona should still be processed: with a change, should show diff, not fail
    assert "modified trigger" in out.lower() or "security-auditor" in out.lower()


def test_ingest_mixed_batch_apply_writes_valid_and_skips_deferred(tmp_path, capsys):
    """Same mixed-batch scenario, but with --apply: the valid persona is actually written to
    disk even though the unknown persona in the same batch is deferred, and nothing is created
    for the deferred one.
    """
    agents = _seed_agents(tmp_path)
    proposed = _seed_proposal(tmp_path, _persona(trigger="Modified trigger"), name="security-auditor")
    _seed_proposal(
        tmp_path,
        _persona().replace("security-auditor", "data-architect"),
        name="data-architect",
    )
    rc = review_cli.main(["evolve", "--ingest", str(proposed), "--agents-dir", str(agents), "--apply"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "deferred" in out.lower()
    assert not (agents / "data-architect.agent.md").exists()
    assert "Modified trigger" in (agents / "security-auditor.agent.md").read_text(encoding="utf-8")
