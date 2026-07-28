import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("lint_model_ids", ROOT / "ci" / "lint-model-ids.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def _write(tmp_path, rel, text):
    f = tmp_path / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")

def test_flags_stale_dated_claude_id(tmp_path):
    _write(tmp_path, "plugins/x/README.md", "use claude-sonnet-4-6 here")
    findings = mod.scan_tree(tmp_path)
    assert any("claude-sonnet-4-6" in x for x in findings)

def test_flags_retired_runtime_refs(tmp_path):
    _write(tmp_path, "plugins/x/hook.py", "path = 'src/llm/ollama.ts'  # OLLAMA_URL")
    findings = mod.scan_tree(tmp_path)
    assert len(findings) >= 2  # one finding per pattern match

def test_allows_changelogs_and_adrs(tmp_path):
    _write(tmp_path, "plugins/x/CHANGELOG.md", "historical claude-opus-4-8 note")
    _write(tmp_path, "docs/adr/0001-old.md", "historical claude-opus-4-8 note")
    assert mod.scan_tree(tmp_path) == []

def test_current_ids_pass(tmp_path):
    _write(tmp_path, "plugins/x/SKILL.md", "claude-opus-5 claude-sonnet-5 claude-haiku-4-5 claude-fable-5")
    assert mod.scan_tree(tmp_path) == []

def test_tolerates_missing_roots(tmp_path):
    _write(tmp_path, "plugins/x/SKILL.md", "clean")
    assert mod.scan_tree(tmp_path) == []  # no docs/, templates/, README.md present

def test_main_exit_codes(tmp_path, capsys):
    _write(tmp_path, "plugins/x/README.md", "claude-opus-4-8")
    assert mod.main([str(tmp_path)]) == 1
    assert "claude-opus-4-8" in capsys.readouterr().out
    _write(tmp_path, "plugins/x/README.md", "claude-opus-5")
    assert mod.main([str(tmp_path)]) == 0
