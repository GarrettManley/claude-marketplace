import io
import sys
from pathlib import Path
import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from instinct_cli import (
    cmd_status,
    cmd_import,
    cmd_export,
)
from storage import (
    get_global_instincts_dir,
    get_project_instincts_dir,
    get_project_id,
)
from instinct_schema import Instinct, format_instinct


@pytest.fixture
def tmp_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LEARNING_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/explicit/proj")
    return tmp_path


def _make_instinct(id_: str, confidence: float = 0.7, domain: str = "workflow") -> Instinct:
    return Instinct(
        id=id_,
        trigger="when X",
        confidence=confidence,
        domain=domain,
        source="test",
        source_repo=None,
        title=id_,
        action="Do the thing.",
        evidence="It works.",
    )


def test_status_empty(tmp_data, capsys):
    cmd_status()
    captured = capsys.readouterr()
    assert "0 total" in captured.out or "no instincts" in captured.out.lower()


def test_status_groups_by_scope(tmp_data, capsys):
    global_dir = get_global_instincts_dir() / "personal"
    global_dir.mkdir(parents=True)
    (global_dir / "g.yaml").write_text(format_instinct(_make_instinct("g")))
    project_dir = get_project_instincts_dir(get_project_id()) / "personal"
    project_dir.mkdir(parents=True)
    (project_dir / "p.yaml").write_text(format_instinct(_make_instinct("p")))
    cmd_status()
    captured = capsys.readouterr()
    assert "GLOBAL" in captured.out.upper()
    assert "PROJECT" in captured.out.upper()
    assert "g" in captured.out
    assert "p" in captured.out


def test_import_writes_to_inherited(tmp_data, tmp_path):
    src = tmp_path / "in.yaml"
    src.write_text(format_instinct(_make_instinct("imported")))
    cmd_import(str(src), scope="global")
    target_dir = get_global_instincts_dir() / "inherited"
    assert (target_dir / "imported.yaml").exists()


def test_export_writes_concatenated_file(tmp_data, tmp_path):
    global_dir = get_global_instincts_dir() / "personal"
    global_dir.mkdir(parents=True)
    (global_dir / "a.yaml").write_text(format_instinct(_make_instinct("a")))
    (global_dir / "b.yaml").write_text(format_instinct(_make_instinct("b")))
    out = tmp_path / "export.yaml"
    cmd_export(str(out), scope="global")
    text = out.read_text()
    assert "id: a" in text
    assert "id: b" in text


def test_import_missing_file_returns_nonzero(tmp_data, capsys):
    rc = cmd_import("/nonexistent/file.yaml", scope="global")
    assert rc != 0


def test_export_empty_scope_returns_nonzero(tmp_data, tmp_path):
    out = tmp_path / "empty.yaml"
    rc = cmd_export(str(out), scope="global")
    assert rc != 0  # no instincts to export


# --- Phase 2a: cmd_analyze ---

import json as _json

from instinct_cli import cmd_analyze
from storage import get_observations_file


def test_analyze_empty_observations(tmp_data, capsys):
    rc = cmd_analyze()
    assert rc == 0
    out = capsys.readouterr().out
    assert "0 records" in out
    assert "LEARNING_OBSERVE=on" in out  # surfaces the enablement hint


def test_analyze_reports_frequency_and_hotspots(tmp_data, capsys):
    obs_file = get_observations_file(get_project_id())
    obs_file.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {"timestamp": 1, "phase": "pre", "tool_name": "Edit",
         "tool_input": {"file_path": "/a.py"}, "session_id": "s"},
        {"timestamp": 2, "phase": "post", "tool_name": "Edit",
         "tool_input": {"file_path": "/a.py"}, "session_id": "s"},
        {"timestamp": 3, "phase": "pre", "tool_name": "Bash",
         "tool_input": {"command": "git status"}, "session_id": "s"},
        {"timestamp": 4, "phase": "post", "tool_name": "Bash",
         "tool_input": {"command": "git status"}, "session_id": "s"},
    ]
    with open(obs_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(_json.dumps(r) + "\n")
    rc = cmd_analyze()
    assert rc == 0
    out = capsys.readouterr().out
    assert "4 records" in out
    assert "Tool-use frequency" in out
    assert "Edit" in out
    assert "Bash" in out
    assert "/a.py" in out
    assert "git status" in out


# --- Phase 2b: cmd_synthesize ---

from instinct_cli import cmd_synthesize


def _seed_bash_observations(n: int = 6, command: str = "git status") -> None:
    obs_file = get_observations_file(get_project_id())
    obs_file.parent.mkdir(parents=True, exist_ok=True)
    with open(obs_file, "w", encoding="utf-8") as f:
        for _ in range(n):
            f.write(_json.dumps({
                "timestamp": 1, "phase": "pre", "tool_name": "Bash",
                "tool_input": {"command": command}, "session_id": "s",
            }) + "\n")


def test_synthesize_dry_run_writes_nothing(tmp_data, capsys):
    _seed_bash_observations()
    rc = cmd_synthesize(scope="project")  # dry-run is the default
    assert rc == 0
    out = capsys.readouterr().out
    assert "auto-bash-git-status" in out
    personal = get_project_instincts_dir(get_project_id()) / "personal"
    assert not personal.exists() or list(personal.glob("*.yaml")) == []


def test_synthesize_write_persists(tmp_data):
    _seed_bash_observations()
    rc = cmd_synthesize(scope="project", write=True)
    assert rc == 0
    personal = get_project_instincts_dir(get_project_id()) / "personal"
    assert (personal / "auto-bash-git-status.yaml").exists()


def test_synthesize_empty_observations(tmp_data, capsys):
    rc = cmd_synthesize(scope="project")
    assert rc == 0
    out = capsys.readouterr().out.lower()
    assert "0 candidate" in out or "no observation" in out


# --- Phase 2c / 3: new subcommands dispatch via main() ---

from instinct_cli import main


def test_main_detect_dump_observations(tmp_data, capsys):
    rc = main(["detect", "--dump-observations"])
    assert rc == 0
    assert "tool_frequency" in capsys.readouterr().out


def test_main_prune_dry_run(tmp_data):
    assert main(["prune", "--scope", "project"]) == 0


def test_main_promote_requires_id_or_auto(tmp_data):
    assert main(["promote"]) == 1  # neither id nor --auto


def test_main_evolve_dry_run(tmp_data):
    assert main(["evolve", "--scope", "project"]) == 0


def test_main_synthesize_nightly_apply_writes_report(tmp_data):
    _seed_bash_observations()  # seeds the fixture project's observations.jsonl
    rc = main(["synthesize-nightly", "--apply"])
    assert rc == 0
    assert (tmp_data / "last_mine_report.json").is_file()
