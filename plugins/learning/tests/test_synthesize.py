import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from synthesize import (  # noqa: E402
    confidence,
    slugify,
    workflow_instincts_from_sequences,
    bash_instincts_from_prefixes,
    synthesize,
    write_instincts,
    get_target_dir,
)
from instinct_schema import parse_instinct, format_instinct, Instinct  # noqa: E402
from storage import get_project_instincts_dir, get_project_id  # noqa: E402


@pytest.fixture
def tmp_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LEARNING_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/explicit/proj")
    return tmp_path


# --- confidence model ---


def test_confidence_within_unit_interval():
    for n in (1, 5, 50, 5000):
        for p in (0.0, 0.5, 1.0):
            c = confidence(n, p)
            assert 0.0 <= c <= 1.0


def test_confidence_capped_at_max():
    # Huge support + perfect consistency must not exceed the cap.
    assert confidence(10_000, 1.0, max_conf=0.85) == 0.85


def test_confidence_monotonic_in_support():
    a = confidence(5, 0.8)
    b = confidence(50, 0.8)
    assert b > a


def test_confidence_monotonic_in_consistency():
    a = confidence(20, 0.5)
    b = confidence(20, 0.9)
    assert b > a


# --- slugify ---


def test_slugify_lowercases_and_replaces_nonalnum():
    assert slugify("git status") == "git-status"
    assert slugify("Bash") == "bash"
    assert slugify("npm run build:prod") == "npm-run-build-prod"


def test_slugify_strips_and_collapses_separators():
    assert slugify("  git   log  ") == "git-log"


# --- workflow candidates ---


def test_workflow_excludes_below_min_support():
    seqs = {("Grep", "Edit"): 3}  # below default min_support=5
    out = workflow_instincts_from_sequences(seqs, min_support=5, min_consistency=0.5)
    assert out == []


def test_workflow_excludes_below_min_consistency():
    # Grep -> Edit happens 6 times but Grep -> Bash happens 6 times too: p = 0.5
    seqs = {("Grep", "Edit"): 6, ("Grep", "Bash"): 6}
    out = workflow_instincts_from_sequences(seqs, min_support=5, min_consistency=0.6)
    assert out == []


def test_workflow_emits_instinct_for_strong_pair():
    seqs = {("Grep", "Edit"): 8, ("Grep", "Bash"): 2}  # p = 0.8, n = 8
    out = workflow_instincts_from_sequences(seqs, min_support=5, min_consistency=0.5)
    assert len(out) == 1
    inst = out[0]
    assert isinstance(inst, Instinct)
    assert inst.id == "auto-seq-grep-edit"
    assert inst.domain == "workflow"
    assert inst.source == "auto-frequency"
    assert 0.0 < inst.confidence <= 0.85


def test_workflow_id_is_deterministic():
    seqs = {("Grep", "Edit"): 8, ("Grep", "Bash"): 2}
    a = workflow_instincts_from_sequences(seqs, min_support=5, min_consistency=0.5)[0]
    b = workflow_instincts_from_sequences(seqs, min_support=5, min_consistency=0.5)[0]
    assert a.id == b.id


# --- bash candidates ---


def test_bash_excludes_below_min_support():
    out = bash_instincts_from_prefixes({"git status": 3}, min_support=5)
    assert out == []


def test_bash_emits_tooling_instinct():
    out = bash_instincts_from_prefixes({"git status": 12}, min_support=5)
    assert len(out) == 1
    inst = out[0]
    assert inst.id == "auto-bash-git-status"
    assert inst.domain == "tooling"
    assert inst.source == "auto-frequency"


def test_bash_ceiling_lower_than_workflow():
    # Bash confidence ceiling is intentionally lower than the workflow cap.
    out = bash_instincts_from_prefixes({"git status": 100_000}, min_support=5)
    assert out[0].confidence < 0.85


# --- synthesize (records adapter) ---


def test_synthesize_combines_workflow_and_bash():
    records = []
    # 6 immediate Grep(post) -> Edit(pre) pairs, distinct sessions to keep them immediate
    for i in range(6):
        sid = f"s{i}"
        records.append({"timestamp": 1.0, "phase": "post", "tool_name": "Grep", "session_id": sid})
        records.append({"timestamp": 2.0, "phase": "pre", "tool_name": "Edit", "session_id": sid})
    # 6 git status bash invocations
    for i in range(6):
        records.append({"phase": "pre", "tool_name": "Bash", "tool_input": {"command": "git status"}, "session_id": "b"})
    out = synthesize(records, min_support=5, min_consistency=0.5)
    ids = {i.id for i in out}
    assert "auto-seq-grep-edit" in ids
    assert "auto-bash-git-status" in ids


def test_synthesize_empty_records():
    assert synthesize([], min_support=5, min_consistency=0.5) == []


# --- writer ---


def _auto_instinct(iid: str = "auto-seq-grep-edit") -> Instinct:
    return Instinct(
        id=iid, trigger="after using Grep", confidence=0.7,
        domain="workflow", source="auto-frequency", source_repo=None,
        title="Edit often follows Grep", action="Use Edit after Grep.",
        evidence="Observed 8 times.",
    )


def test_get_target_dir_project_is_personal(tmp_data):
    d = get_target_dir("project")
    assert d == get_project_instincts_dir(get_project_id()) / "personal"


def test_write_dry_run_writes_nothing(tmp_data):
    target = get_target_dir("project")
    counts = write_instincts([_auto_instinct()], target, dry_run=True)
    assert counts["written"] == 1
    assert not target.exists() or list(target.glob("*.yaml")) == []


def test_write_persists_file(tmp_data):
    target = get_target_dir("project")
    counts = write_instincts([_auto_instinct()], target, dry_run=False)
    assert counts["written"] == 1
    f = target / "auto-seq-grep-edit.yaml"
    assert f.is_file()
    parsed = parse_instinct(f.read_text(encoding="utf-8"))
    assert parsed.id == "auto-seq-grep-edit"


def test_write_is_idempotent(tmp_data):
    target = get_target_dir("project")
    write_instincts([_auto_instinct()], target, dry_run=False)
    counts = write_instincts([_auto_instinct()], target, dry_run=False)
    assert counts["updated"] == 1
    assert counts["written"] == 0
    assert len(list(target.glob("*.yaml"))) == 1


def test_write_preserves_non_auto_file(tmp_data):
    target = get_target_dir("project")
    target.mkdir(parents=True, exist_ok=True)
    manual = Instinct(
        id="auto-seq-grep-edit", trigger="t", confidence=0.95,
        domain="workflow", source="manual", source_repo=None,
        title="Hand-tuned", action="Do the careful thing.", evidence="Human verified.",
    )
    f = target / "auto-seq-grep-edit.yaml"
    f.write_text(format_instinct(manual), encoding="utf-8")
    counts = write_instincts([_auto_instinct()], target, dry_run=False)
    assert counts["skipped"] == 1
    # The human-authored content survives untouched.
    assert parse_instinct(f.read_text(encoding="utf-8")).source == "manual"


def test_write_overwrites_claude_detected_file(tmp_data):
    # claude-detected is a machine source: re-derivation must reinforce/overwrite it,
    # NOT preserve it as if human-authored (was the bug: only auto-* was overwritten).
    target = get_target_dir("project")
    target.mkdir(parents=True, exist_ok=True)
    detected = Instinct(
        id="auto-seq-grep-edit", trigger="t", confidence=0.4,
        domain="workflow", source="claude-detected", source_repo=None,
        title="old", action="stale action", evidence="stale evidence",
    )
    f = target / "auto-seq-grep-edit.yaml"
    f.write_text(format_instinct(detected), encoding="utf-8")
    counts = write_instincts([_auto_instinct()], target, dry_run=False)
    assert counts["updated"] == 1
    assert parse_instinct(f.read_text(encoding="utf-8")).action == "Use Edit after Grep."


def test_write_stamps_last_reinforced(tmp_data):
    target = get_target_dir("project")
    counts = write_instincts([_auto_instinct()], target, dry_run=False)
    assert counts["written"] == 1
    parsed = parse_instinct((target / "auto-seq-grep-edit.yaml").read_text(encoding="utf-8"))
    assert parsed.last_reinforced is not None and parsed.last_reinforced > 0


def test_write_leaves_no_temp_files(tmp_data):
    # Atomic write must not leave partial/temp artifacts behind.
    target = get_target_dir("project")
    write_instincts([_auto_instinct()], target, dry_run=False)
    leftovers = [p.name for p in target.iterdir() if not p.name.endswith(".yaml")]
    assert leftovers == []
