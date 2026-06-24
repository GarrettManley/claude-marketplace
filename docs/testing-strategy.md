---
status: active
author: GarrettManley
created: 2026-06-23
diataxis: explanation
---

# Testing strategy

How this marketplace verifies its plugins. The corpus is mixed-language — Python
hooks/scripts, plus bash and PowerShell hooks — so the strategy splits by what
each language can be tested for, and CI runs the whole thing across a tri-OS
matrix.

The short version:

- **Python** gets unit tests under `coverage.py` with a **>=90% line-coverage
  gate**.
- **bash / PowerShell** get **behavioral (subprocess) tests** plus static
  analysis (`shellcheck` / `PSScriptAnalyzer`). They are deliberately **not**
  line-coverage gated — see below.
- An **agent-contract suite** structurally validates every `*.agent.md`.

## Why coverage is Python-only

`coverage.py` instruments the CPython interpreter; it cannot see lines executed
inside a `bash` or `pwsh` child process. Chasing a coverage number for shell code
would mean either a bespoke shell-coverage tool (fragile) or contorting hooks to
be importable Python (defeats the point). Instead, shell hooks are verified two
ways:

1. **Behavioral tests** — a Python test invokes the hook as a subprocess with a
   crafted stdin/argv/env and asserts on exit code and output. This tests the
   contract the harness actually depends on (does exit-2 block? does the right
   JSON come out of stdout?), not internal line execution.
2. **Static analysis** — `shellcheck -S warning` on every `*.sh`, and
   `PSScriptAnalyzer` (with the repo's `PSScriptAnalyzerSettings.psd1`) on every
   `*.ps1`.

This split is documented inline in `.coveragerc`: the `[run] source` is `ci` and
`plugins`, and the 90% `--fail-under` is understood to be **over the Python
corpus only**.

## The per-directory pytest pattern

You cannot collect the whole repo with a single `pytest` from the root. Two
structural facts force a per-directory loop:

1. **Duplicate test basenames.** Many plugins ship the same filenames — there are
   five `test_init.py` (discipline, evidence, git, orchestration, stewardship), a
   `test_storage.py`, a `test_hooks.py`, and a `conftest.py` in every plugin
   `tests/` directory. Under pytest's default import mode, same-named modules
   collide in `sys.modules`.
2. **Per-plugin `conftest.py` sys.path setup.** Each plugin's `conftest.py`
   inserts *its own* `scripts/` and `hooks/` directories onto `sys.path` so the
   tests can `import` the hook modules. Example
   (`plugins/discipline/tests/conftest.py`):

   ```python
   _PLUGIN_ROOT = Path(__file__).parent.parent
   sys.path.insert(0, str(_PLUGIN_ROOT / "scripts"))
   sys.path.insert(0, str(_PLUGIN_ROOT / "hooks"))
   ```

   If two plugins were collected in one process, their `sys.path` and any
   same-named hook modules would cross-contaminate.

Two mitigations work together:

- `pytest.ini` sets `--import-mode=importlib`, which lets same-basename modules
  coexist without rewriting `sys.path` for collection. This handles a single
  directory's worth of duplicates.
- **CI still loops one directory at a time.** Each plugin's `tests/` runs in its
  own `pytest` process so its `conftest.py` `sys.path` setup is isolated, and
  per-process coverage data files (`coverage run -p`) are merged at the end with
  `coverage combine`.

The CI step (`.github/workflows/ci.yml`) is:

```bash
python -m coverage erase
python -m coverage run -p -m pytest ci/tests -q
for d in plugins/*/tests; do
  if [ -d "$d" ]; then
    python -m coverage run -p -m pytest "$d" -q
  fi
done
python -m coverage combine
python -m coverage report --fail-under=90
```

`coverage run -p` writes a parallel-tagged data file per run; `coverage combine`
merges them. `.coveragerc` has `parallel = true` and a `[paths]` section that
maps per-OS checkout directories so the **ubuntu and windows** legs combine into
one total — important because `sys.platform`-guarded branches only execute on
their own OS, and both need to count toward the 90% gate.

## The agent-contract suite

`ci/tests/test_agent_contract.py` (backed by helpers in `ci/agent_contract.py`)
is a repo-wide invariant over every `plugins/*/agents/*.agent.md`. Agents are
markdown role-prompts with no executable code, so there is no CI-safe way to
exercise their *runtime* behavior (that needs a live model). What it enforces is
the **structural** contract, parametrized over a glob so new agents are covered
automatically:

- Required frontmatter fields are present and non-empty (`name`, `description`,
  `tools`).
- `name` matches the filename stem (filename minus `.agent.md`).
- The body is not a stub (has at least one markdown heading).
- The agent is registered in `docs/skill-index.md`, and the index's
  `## Agents (N)` count matches the number of agent files on disk.

A floor assertion (`len(AGENTS) >= 20`) guards against a glob that silently finds
nothing. It lives in `ci/tests/` rather than under any one plugin because it
spans all agent-bearing plugins.

## Config reference

### `pytest.ini`

```ini
[pytest]
addopts = --import-mode=importlib -q
testpaths =
    ci/tests
    plugins
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

`--import-mode=importlib` is the key line: it lets duplicate test basenames and
duplicate `conftest.py` files coexist without `sys.path` collisions.

### `.coveragerc`

- `[run] source = ci, plugins`; `omit` excludes `*/tests/*`, caches, virtualenvs,
  and `node_modules`.
- `parallel = true` so `coverage run -p` + `coverage combine` works.
- `[report] exclude_lines` skips the usual unreachable lines (`pragma: no cover`,
  `__repr__`, `raise NotImplementedError`, `if __name__ == "__main__":`,
  `if TYPE_CHECKING:`, `@abstractmethod`).
- `[paths] source` maps per-OS checkout paths so the ubuntu + windows runs merge
  on `coverage combine`.

## Running it locally

Install the dev toolchain (`pytest`, `coverage`, `ruff`, `PyYAML` — runtime
plugins are stdlib-only):

```bash
python3 -m pip install -r requirements-dev.txt
```

Run the pre-merge gate (lint + structural validators — the non-test half of CI):

```bash
bash scripts/verify.sh
```

`scripts/verify.sh` runs, in order: `lint-no-bare-python`, `ruff check`,
`check-versions --check`, `validate-plugins`, `verify_hook_runtime_controls`,
`check-vendored-sync`, `lint-frontmatter`, `gen-skill-index --check`, and
`check-notice`. It exits non-zero on the first failure.

Run the tests and the coverage gate with the same per-directory loop CI uses:

```bash
python3 -m coverage erase
python3 -m coverage run -p -m pytest ci/tests -q
for d in plugins/*/tests; do
  [ -d "$d" ] && python3 -m coverage run -p -m pytest "$d" -q
done
python3 -m coverage combine
python3 -m coverage report --fail-under=90
```

Note: a *local* `coverage combine` merges only your machine's runs, so the
platform-guarded total reflects one OS. The full ubuntu + windows total is what
the CI matrix produces. To run a single plugin's tests while iterating:

```bash
python3 -m pytest plugins/<plugin>/tests -q
```

### Static analysis

CI runs these on the relevant OS leg; to mirror locally:

```bash
# bash (Linux/macOS or WSL)
find . -path ./.git -prune -o -name '*.sh' -print0 | xargs -0 -r shellcheck -S warning
```

```powershell
# PowerShell (Windows)
Get-ChildItem -Recurse -Filter *.ps1 |
  Where-Object { $_.FullName -notmatch '\\\.git\\' } |
  ForEach-Object { Invoke-ScriptAnalyzer -Path $_.FullName -Settings ./PSScriptAnalyzerSettings.psd1 }
```

## CI matrix

`.github/workflows/ci.yml` runs verification on push to `main` and on every pull
request, across `ubuntu-latest`, `windows-latest`, and `macos-latest` × Python
`3.12` and `3.13`. ubuntu and windows are required; macOS is
`continue-on-error` (proves portability without blocking on runner flakiness).
The workflow is verification-only — it never tags or publishes; releases stay
local via `ci/release.py`.
