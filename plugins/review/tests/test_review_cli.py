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


def test_ingest_rejects_unknown_persona(tmp_path, capsys):
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
