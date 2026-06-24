"""Tests for the memory_tracker_check PostToolUse hook.

The hook warns (never blocks) when an auto-memory file with frontmatter
`type: project` cites no tracker id (a beads `hb-`/`bd-` id or a GitHub `#N`).

Driven the way Claude Code drives it: a PostToolUse JSON payload on stdin; it
emits a `{"systemMessage": ...}` JSON on stdout (and always `sys.exit(0)`), or
nothing on pass.
"""
import io
import json

import pytest

# conftest puts the plugin's scripts/ and hooks/ on sys.path.
import discipline_config
import memory_tracker_check


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #
def _run(monkeypatch, payload):
    """Invoke main() with `payload` on stdin; return emitted stdout ('' == pass)."""
    discipline_config.get_config.cache_clear()
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    with pytest.raises(SystemExit) as exc:
        memory_tracker_check.main()
    assert exc.value.code == 0
    return out.getvalue()


def _run_raw_stdin(monkeypatch, raw_text):
    """Like _run but puts arbitrary (possibly non-JSON) text on stdin."""
    discipline_config.get_config.cache_clear()
    monkeypatch.setattr("sys.stdin", io.StringIO(raw_text))
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    with pytest.raises(SystemExit) as exc:
        memory_tracker_check.main()
    assert exc.value.code == 0
    return out.getvalue()


def _payload(path):
    return {"tool_input": {"file_path": str(path)}}


def _is_warn(out):
    return bool(out) and "systemMessage" in json.loads(out.splitlines()[0])


def _is_block(out):
    return bool(out) and json.loads(out.splitlines()[0]).get("decision") == "block"


_MEMDIR = ".claude/projects/C--Users-Example/memory"


def _write_mem(tmp_path, body, name="project_x.md", subdir=_MEMDIR, *, encoding="utf-8", raw_bytes=None):
    d = tmp_path / subdir if subdir else tmp_path
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    if raw_bytes is not None:
        f.write_bytes(raw_bytes)
    else:
        f.write_text(body, encoding=encoding)
    return f


def _fm(meta_type, body="", *, nested=True):
    """Build a memory file: frontmatter (type nested under metadata by default) + body."""
    if nested:
        block = f"name: example\nmetadata:\n  node_type: memory\n  type: {meta_type}\n"
    else:
        block = f"name: example\ntype: {meta_type}\n"
    return f"---\n{block}---\n\n{body}\n"


@pytest.fixture
def hermetic(clean_env, monkeypatch):
    """No git auto-detection so path normalization is deterministic regardless of cwd."""
    monkeypatch.setattr(discipline_config, "_detect_git_root", lambda: None)
    monkeypatch.setattr(discipline_config, "_detect_repo", lambda: None)
    return monkeypatch


# --------------------------------------------------------------------------- #
# Core rule — type:project must cite a tracker id
# --------------------------------------------------------------------------- #
def test_project_with_beads_tracker_passes(hermetic, tmp_path):
    body = "Tracker: hb-9yw.6 (closed), under epic [[x]] hb-9yw."
    assert _run(hermetic, _payload(_write_mem(tmp_path, _fm("project", body)))) == ""


def test_project_with_bd_tracker_passes(hermetic, tmp_path):
    assert _run(hermetic, _payload(_write_mem(tmp_path, _fm("project", "Tracker: bd-abc1.")))) == ""


def test_project_with_github_issue_passes(hermetic, tmp_path):
    assert _run(hermetic, _payload(_write_mem(tmp_path, _fm("project", "Tracker: #123.")))) == ""


def test_project_without_tracker_warns(hermetic, tmp_path):
    body = "We finished the thing. All done."
    assert _is_warn(_run(hermetic, _payload(_write_mem(tmp_path, _fm("project", body)))))


def test_nested_metadata_type_is_detected(hermetic, tmp_path):
    """Proves the block scan reads `type:` indented under `metadata:` (the real shape)."""
    f = _write_mem(tmp_path, _fm("project", "No tracker id anywhere here.", nested=True))
    assert _is_warn(_run(hermetic, _payload(f)))


def test_top_level_type_is_detected(hermetic, tmp_path):
    f = _write_mem(tmp_path, _fm("project", "No tracker id anywhere here.", nested=False))
    assert _is_warn(_run(hermetic, _payload(f)))


def test_quoted_type_project_is_detected(hermetic, tmp_path):
    """A quoted scalar `type: "project"` must still be recognised (matches _parse_frontmatter)."""
    text = '---\nname: x\nmetadata:\n  type: "project"\n---\n\nNo tracker id.\n'
    assert _is_warn(_run(hermetic, _payload(_write_mem(tmp_path, text))))


# --------------------------------------------------------------------------- #
# Out of scope — other types, other paths, the index file
# --------------------------------------------------------------------------- #
def test_reference_type_is_ignored(hermetic, tmp_path):
    """type:reference is out of the convention's scope — no tracker required."""
    assert _run(hermetic, _payload(_write_mem(tmp_path, _fm("reference", "Static facts, no id.")))) == ""


def test_node_type_project_is_not_read_as_type(hermetic, tmp_path):
    """`node_type: project` must NOT satisfy the `type:` anchor (no real `type:` line here).

    Discriminating: fails under an unanchored regex, passes under the real `^[ \\t]*type:` one.
    """
    text = "---\nname: example\nmetadata:\n  node_type: project\n---\n\nNo id.\n"
    assert _run(hermetic, _payload(_write_mem(tmp_path, text))) == ""


def test_body_prose_type_project_does_not_trigger(hermetic, tmp_path):
    """A literal 'type: project' line in the BODY must not count — only frontmatter."""
    body = "type: project\nThis line is prose, not frontmatter. No tracker id."
    assert _run(hermetic, _payload(_write_mem(tmp_path, _fm("reference", body)))) == ""


def test_type_project_management_does_not_trigger(hermetic, tmp_path):
    """The value is end-anchored, so `project-management` is not `project`."""
    text = "---\nname: x\nmetadata:\n  type: project-management\n---\n\nNo id.\n"
    assert _run(hermetic, _payload(_write_mem(tmp_path, text))) == ""


def test_type_projects_does_not_trigger(hermetic, tmp_path):
    text = "---\nname: x\nmetadata:\n  type: projects\n---\n\nNo id.\n"
    assert _run(hermetic, _payload(_write_mem(tmp_path, text))) == ""


def test_non_memory_path_is_skipped(hermetic, tmp_path):
    """A type:project doc outside a memory/ dir is ignored even without a tracker."""
    f = _write_mem(tmp_path, _fm("project", "No id."), subdir="docs")
    assert _run(hermetic, _payload(f)) == ""


def test_memory_index_file_is_skipped(hermetic, tmp_path):
    """MEMORY.md is the curated index, not a typed memory file."""
    f = _write_mem(tmp_path, _fm("project", "No id."), name="MEMORY.md")
    assert _run(hermetic, _payload(f)) == ""


# --------------------------------------------------------------------------- #
# Tracker-id presence: precision of the citation check
# --------------------------------------------------------------------------- #
def test_hyphenated_words_are_not_tracker_ids(hermetic, tmp_path):
    """Ordinary hyphenated words must not satisfy the citation, or the rule is toothless."""
    body = "We wire claude-code and pre-commit end-to-end. No real tracker."
    assert _is_warn(_run(hermetic, _payload(_write_mem(tmp_path, _fm("project", body)))))


def test_hex_color_is_not_a_github_citation(hermetic, tmp_path):
    """`#1a2b3c` (a hex color) must not pass as a `#N` issue citation."""
    body = "Brand color is #1a2b3c and accent #0f0. No tracker."
    assert _is_warn(_run(hermetic, _payload(_write_mem(tmp_path, _fm("project", body)))))


def test_id_in_frontmatter_description_satisfies(hermetic, tmp_path):
    """Citing the id anywhere (here, the description) satisfies the presence check."""
    text = (
        "---\nname: example\ndescription: advances hb-9yw.6\n"
        "metadata:\n  type: project\n---\n\nProse with no id in the body.\n"
    )
    assert _run(hermetic, _payload(_write_mem(tmp_path, text))) == ""


def test_id_inside_code_fence_satisfies(hermetic, tmp_path):
    """Intentional lenience: an id anywhere in the text (incl. a code fence) counts."""
    body = "Run it:\n\n```\nbd close hb-9yw.6\n```\n"
    assert _run(hermetic, _payload(_write_mem(tmp_path, _fm("project", body)))) == ""


# --------------------------------------------------------------------------- #
# Robustness — frontmatter, encoding, payload shape, never-block
# --------------------------------------------------------------------------- #
def test_no_frontmatter_is_skipped(hermetic, tmp_path):
    f = _write_mem(tmp_path, "Just a body, no frontmatter, type project mentioned.")
    assert _run(hermetic, _payload(f)) == ""


def test_unclosed_frontmatter_is_skipped(hermetic, tmp_path):
    f = _write_mem(tmp_path, "---\nmetadata:\n  type: project\n(no closing fence)\n")
    assert _run(hermetic, _payload(f)) == ""


def test_bom_file_still_warns(hermetic, tmp_path):
    """A UTF-8 BOM must not silently disable the check (utf-8-sig strips it)."""
    f = _write_mem(tmp_path, _fm("project", "No tracker id."), encoding="utf-8-sig")
    assert _is_warn(_run(hermetic, _payload(f)))


def test_crlf_file_still_warns(hermetic, tmp_path):
    """CRLF line endings must not break frontmatter detection."""
    crlf = _fm("project", "No tracker id.").replace("\n", "\r\n").encode("utf-8")
    f = _write_mem(tmp_path, None, raw_bytes=crlf)
    assert _is_warn(_run(hermetic, _payload(f)))


def test_tool_response_filepath_fallback_warns(hermetic, tmp_path):
    """The tool_response.filePath fallback (no tool_input.file_path) is exercised."""
    f = _write_mem(tmp_path, _fm("project", "No tracker id."))
    assert _is_warn(_run(hermetic, {"tool_response": {"filePath": str(f)}}))


def test_missing_path_is_skipped(hermetic):
    assert _run(hermetic, {"tool_input": {}}) == ""


def test_nonexistent_file_is_skipped(hermetic, tmp_path):
    """A memory-shaped path that isn't on disk (delete/rename race) exits cleanly."""
    ghost = tmp_path / _MEMDIR / "gone.md"
    assert _run(hermetic, _payload(ghost)) == ""


def test_malformed_stdin_is_skipped(hermetic):
    assert _run_raw_stdin(hermetic, "not json at all") == ""


def test_warning_is_never_a_block(hermetic, tmp_path):
    """The hardest invariant: a violation warns, it must never emit a block decision."""
    out = _run(hermetic, _payload(_write_mem(tmp_path, _fm("project", "No id."))))
    assert _is_warn(out)
    assert not _is_block(out)


def test_warning_message_names_the_file(hermetic, tmp_path):
    f = _write_mem(tmp_path, _fm("project", "No id."), name="project_named.md")
    out = _run(hermetic, _payload(f))
    msg = json.loads(out.splitlines()[0])["systemMessage"]
    assert "no tracker id" in msg
    assert "project_named.md" in msg
