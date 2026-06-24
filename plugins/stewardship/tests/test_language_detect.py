import pytest
from pathlib import Path
import sys
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from language_detect import detect_language, find_project_root, LANGUAGES


@pytest.fixture
def ts_project(tmp_path):
    (tmp_path / "tsconfig.json").write_text("{}")
    (tmp_path / "package.json").write_text('{"name":"x"}')
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.ts").write_text("")
    return tmp_path


@pytest.fixture
def py_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "mod.py").write_text("")
    return tmp_path


@pytest.fixture
def rs_project(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.rs").write_text("")
    return tmp_path


class TestDetectLanguage:
    def test_ts_file(self, ts_project):
        f = ts_project / "src" / "a.ts"
        assert detect_language(f) == "typescript"

    def test_tsx_file(self, ts_project):
        f = ts_project / "src" / "a.tsx"
        f.write_text("")
        assert detect_language(f) == "typescript"

    def test_js_file_in_ts_project(self, ts_project):
        f = ts_project / "src" / "a.js"
        f.write_text("")
        assert detect_language(f) == "typescript"

    def test_py_file(self, py_project):
        f = py_project / "pkg" / "mod.py"
        assert detect_language(f) == "python"

    def test_rs_file(self, rs_project):
        f = rs_project / "src" / "main.rs"
        assert detect_language(f) == "rust"

    def test_unknown_extension(self, tmp_path):
        f = tmp_path / "x.md"
        f.write_text("")
        assert detect_language(f) is None

    def test_known_ext_no_marker(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("")
        # No pyproject.toml — should still detect by extension
        assert detect_language(f) == "python"


class TestFindProjectRoot:
    def test_finds_tsconfig_dir(self, ts_project):
        f = ts_project / "src" / "a.ts"
        assert find_project_root(f, "typescript") == ts_project

    def test_finds_pyproject_dir(self, py_project):
        f = py_project / "pkg" / "mod.py"
        assert find_project_root(f, "python") == py_project

    def test_finds_cargo_dir(self, rs_project):
        f = rs_project / "src" / "main.rs"
        assert find_project_root(f, "rust") == rs_project

    def test_no_marker_returns_none(self, tmp_path):
        f = tmp_path / "deep" / "nest" / "a.py"
        f.parent.mkdir(parents=True)
        f.write_text("")
        # No pyproject anywhere — return None
        assert find_project_root(f, "python") is None


def test_languages_defined():
    assert "typescript" in LANGUAGES
    assert "python" in LANGUAGES
    assert "rust" in LANGUAGES
