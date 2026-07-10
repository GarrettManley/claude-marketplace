# hb-rap: Hook-error observability — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Tracker:** hb-rap (harness beads ledger — `bd -C ~/.claude/harness-backlog show hb-rap`). Marketplace #51 postmortem.

**Goal:** Make silently-swallowed hook errors visible. `run_with_flags` catches a hook's import/runtime error, prints it to stderr, and returns 0 — so `surface.py` crashed on every SessionStart for weeks unnoticed. Persist those errors to a bounded log and surface a count + recent samples in the stewardship morning briefing.

**Architecture (revised after adversarial plan review — see `.review.md`).** **Write-side:** at `run_with_flags.py`'s two runtime swallow points (import error ~L167, runtime error ~L209), best-effort-append the error to `<learning_data_root>/hooks-errors.jsonl` — a **bounded** ring buffer (keep the last `_MAX_HOOK_ERRORS`), atomic, UTF-8, never raising (logging a swallowed error must not break the hook chain). **Read-side:** `stewardship/render_briefing.py` reads that log and renders a `## Hook Errors` briefing section, **reusing its existing `learning_data_root()`** (no new env var, no second resolver). The path resolver is replicated in the writer only (`run_with_flags` is vendored into every plugin and must stay import-free); a test pins the writer's replica equal to `render_briefing.learning_data_root()`.

**Out of scope (explicit):** the third swallow point (`main`'s "hook script not found", ~L83) — that is a plugin *packaging/config* error (wrong path in hooks.json), a different class with different remediation than a hook's own runtime failure; not this bead. The `_spawn_shell`/`_spawn_generic` paths are not swallowed (they propagate the child's returncode), so they are already non-silent.

**Tech Stack:** Python 3.12/3.13, stdlib only (`json`, `time`, `os`, `tempfile`, `pathlib`). pytest. No new dependencies.

## Global Constraints

- **Edit the dev clone only:** `C:\Users\Garre\Workspace\claude-marketplace\`.
- **`run_with_flags.py` is vendored 3× and canonical in `plugins/discipline/scripts/`.** Edit **only** the discipline copy, then `python3 ci/check-vendored-sync.py --fix` to update `learning` + `stewardship`. Never hand-edit the consumer copies.
- **`run_with_flags` stays import-free of other plugins** — replicate `learning_data_root`'s resolution, don't import it.
- **Storage path = `learning_data_root()/hooks-errors.jsonl`** — reuse the *existing* resolver (env `LEARNING_DATA_ROOT` → `%LOCALAPPDATA%/claude-marketplace/learning` (win, via `sys.platform == "win32"`) → `$XDG_DATA_HOME/claude-marketplace/learning` → `~/.local/share/claude-marketplace/learning`). No new env var. (Semantic note: marketplace-wide errors nest under `learning/`; accepted to reuse the tested resolver.)
- **The append is best-effort and MUST NOT raise** (`run_with_flags`'s every-path-returns-0 contract): wrap in `except Exception: pass`. Force `encoding="utf-8"`. Atomic (tempfile + `os.replace`). **Bounded** to the last `_MAX_HOOK_ERRORS = 200` records — a hook that fails every invocation must not grow the file without bound (the hb-168 large-file/AV-rescan lesson). Concurrency: a lost record under simultaneous appends is acceptable for best-effort telemetry; atomicity prevents corruption, not lost updates.
- **TEST ISOLATION (was a CRITICAL):** every test that reaches a swallow point must set `LEARNING_DATA_ROOT` to a `tmp_path`, or it appends synthetic records into the developer's real log. Add an **autouse fixture** to `discipline/tests/test_run_with_flags.py`, `stewardship/tests/test_run_with_flags.py`, and `learning/tests/test_coverage_gaps.py`'s `TestRunWithFlags`.
- **Per-plugin release commits (was a CRITICAL):** `release.py` bumps by commit **scope**, not changed files. The vendored sync must ship as separate `fix(discipline)` + `fix(learning)` + `fix(stewardship)` commits, each staging its own `run_with_flags.py` copy, or `learning` (whose copy wraps `surface.py`) never bumps.
- **Stage files explicitly per commit** — never `git add -A`; no `__pycache__/*.pyc`. Tests run per-plugin-dir; combined `--fail-under=90` floor only over the full suite (delegate to CI); verify local coverage with `--source=`. All shell snippets run via the **Bash tool / Git Bash**.

---

### Task 1: Write-side — persist hook errors (bounded) in `run_with_flags`

**Files:**
- Modify: `plugins/discipline/scripts/run_with_flags.py` (canonical — add `_learning_data_root`, `_MAX_HOOK_ERRORS`, `_append_hook_error`; call at both runtime swallow points; add `json`, `time`, `tempfile` imports)
- Sync (generated): `plugins/learning/scripts/run_with_flags.py`, `plugins/stewardship/scripts/run_with_flags.py` (via `--fix`; the stewardship copy is committed in Task 2)
- Modify (test isolation): `plugins/discipline/tests/test_run_with_flags.py`, `plugins/learning/tests/test_coverage_gaps.py`

**Interfaces:**
- Produces: `_learning_data_root() -> Path` (replica of `render_briefing.learning_data_root`), `_append_hook_error(hook_name: str, error: str) -> None` (best-effort bounded append), and the log contract `<learning_data_root>/hooks-errors.jsonl` (JSONL of `{"ts","hook","error"}`) that Task 2 reads.

- [ ] **Step 1: Add the autouse isolation fixtures (do this FIRST — prevents real-log pollution while running the new tests)**

In `plugins/discipline/tests/test_run_with_flags.py`, add (module level, near the top):

```python
@pytest.fixture(autouse=True)
def _isolate_hook_error_log(monkeypatch, tmp_path):
    # run_with_flags now appends hook errors under LEARNING_DATA_ROOT; keep every
    # test in this file off the developer's real log.
    monkeypatch.setenv("LEARNING_DATA_ROOT", str(tmp_path / "learning-data"))
```

(If the file's subprocess tests build `env=` explicitly rather than inheriting `os.environ`, thread `LEARNING_DATA_ROOT` into that dict instead — read the existing `test_python_hook_runtime_error_does_not_break_chain` to see how env is passed, and match it.) Add the same autouse fixture to `plugins/learning/tests/test_coverage_gaps.py` for its `TestRunWithFlags` class (as a method-level `@pytest.fixture(autouse=True)` inside the class, or a module fixture if the tests are functions). Ensure `pytest` is imported.

- [ ] **Step 2: Write the failing tests**

Append to `plugins/discipline/tests/test_run_with_flags.py` (use the existing wrapper-path constant — it is named **`WRAPPER`** in this file, not `RUN_WITH_FLAGS`; reuse the same subprocess idiom the sibling runtime-error test uses):

```python
    def test_runtime_error_appended_to_hook_error_log(self, tmp_path):
        import json as _json
        hook = tmp_path / "boom.py"
        hook.write_text("def main():\n    raise ValueError('kaboom')\n")
        result = _run_wrapper(hook, "some:hook:id", "standard")  # match the file's helper/idiom
        assert result.returncode == 0
        assert "runtime error" in result.stderr
        # LEARNING_DATA_ROOT is redirected by the autouse fixture:
        log = Path(os.environ["LEARNING_DATA_ROOT"]) / "learning" / "hooks-errors.jsonl"
        # (the resolver appends the platform 'learning' suffix only for defaults;
        #  when LEARNING_DATA_ROOT is set it is used verbatim — assert against the
        #  resolver, see below)
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("_rwf", WRAPPER)
        rwf = module_from_spec(spec); spec.loader.exec_module(rwf)
        log = rwf._learning_data_root() / "hooks-errors.jsonl"
        assert log.is_file()
        rec = _json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
        assert rec["hook"] == "boom.py" and "kaboom" in rec["error"]

    def test_hook_error_log_append_is_bounded(self, tmp_path):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("_rwf2", WRAPPER)
        rwf = module_from_spec(spec); spec.loader.exec_module(rwf)
        for i in range(rwf._MAX_HOOK_ERRORS + 50):
            rwf._append_hook_error("h.py", f"e{i}")
        log = rwf._learning_data_root() / "hooks-errors.jsonl"
        lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == rwf._MAX_HOOK_ERRORS          # ring buffer holds

    def test_hook_error_log_write_failure_never_breaks_chain(self, tmp_path):
        hook = tmp_path / "boom2.py"
        hook.write_text("def main():\n    raise ValueError('x')\n")
        blocker = tmp_path / "blocker"; blocker.write_text("not a dir")
        # Redirect the log root under a *file*, so mkdir/append fails; hook still exits 0.
        import subprocess, sys
        env = {**os.environ, "LEARNING_DATA_ROOT": str(blocker / "sub")}
        result = subprocess.run([sys.executable, str(WRAPPER), str(hook), "id", "standard"],
                                input="{}", capture_output=True, text=True, env=env)
        assert result.returncode == 0
```

(Match `_run_wrapper`/`WRAPPER` to whatever the file actually defines — the second and third tests import the wrapper module directly, which works because `run_with_flags` self-inserts its `scripts/` dir on `sys.path` at import. `os`, `Path`, `pytest`, `WRAPPER` must be importable in the test module.)

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest plugins/discipline/tests/test_run_with_flags.py -q -k "hook_error_log or is_bounded or never_breaks_chain"`
Expected: FAIL — `AttributeError: module '_rwf' has no attribute '_append_hook_error'` / `_MAX_HOOK_ERRORS`.

- [ ] **Step 4: Implement the resolver + bounded append**

In `plugins/discipline/scripts/run_with_flags.py`, add `import json`, `import time`, `import tempfile` to the import block. Then add (after `MAX_STDIN_BYTES`):

```python
_MAX_HOOK_ERRORS = 200  # ring-buffer cap: a hook that fails every call can't grow the log unbounded


def _learning_data_root() -> Path:
    """Resolve the learning plugin's data root — a byte-for-byte replica of
    stewardship/render_briefing.py's learning_data_root(). Replicated not
    imported: run_with_flags is vendored into every plugin and must stay
    self-contained. A test pins this equal to the render_briefing copy.
    """
    explicit = os.environ.get("LEARNING_DATA_ROOT")
    if explicit:
        return Path(explicit)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "claude-marketplace" / "learning"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "claude-marketplace" / "learning"
    return Path.home() / ".local" / "share" / "claude-marketplace" / "learning"


def _append_hook_error(hook_name: str, error: str) -> None:
    """Best-effort, bounded, atomic append of a swallowed hook error.

    Never raises (every path in this wrapper returns 0). Keeps the last
    _MAX_HOOK_ERRORS records so a hook failing on every invocation can't grow
    the file without bound. A lost record under concurrent appends is acceptable
    for telemetry; the tempfile+os.replace makes each write corruption-free.
    """
    try:
        root = _learning_data_root()
        root.mkdir(parents=True, exist_ok=True)
        log = root / "hooks-errors.jsonl"
        prior = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
        rec = json.dumps({"ts": time.time(), "hook": hook_name, "error": error})
        lines = prior[-(_MAX_HOOK_ERRORS - 1):] + [rec]
        fd, tmp = tempfile.mkstemp(dir=str(root), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, log)
    except Exception:  # noqa: BLE001 -- best-effort telemetry, never break the chain
        pass
```

- [ ] **Step 5: Call it at both runtime swallow points**

In `_import_and_run_python`, add the append before each `print(...)`:

```python
    except Exception as e:  # noqa: BLE001  (import handler)
        _append_hook_error(script_path.name, f"import error: {e}")
        print(f"run_with_flags: import error in {script_path.name}: {e}", file=sys.stderr)
        return 0
```
```python
    except Exception as e:  # noqa: BLE001  (runtime handler)
        _append_hook_error(script_path.name, f"runtime error: {e}")
        print(f"run_with_flags: runtime error in {script_path.name}: {e}", file=sys.stderr)
        return 0
```

- [ ] **Step 6: Sync the vendored copies + run the tests**

```bash
python3 ci/check-vendored-sync.py --fix   # updates learning + stewardship copies
python3 ci/check-vendored-sync.py         # confirm: clean
python -m pytest plugins/discipline/tests/test_run_with_flags.py plugins/learning/tests/test_coverage_gaps.py -q
```
Expected: `clean`; all pass (new + pre-existing; the isolation fixtures keep the real log untouched).

- [ ] **Step 7: Commit — per-plugin scope (discipline canonical, then learning sync)**

```bash
git add plugins/discipline/scripts/run_with_flags.py plugins/discipline/tests/test_run_with_flags.py
git commit -m "fix(discipline): persist swallowed hook errors to a bounded log (hb-rap)"
git add plugins/learning/scripts/run_with_flags.py plugins/learning/tests/test_coverage_gaps.py
git commit -m "fix(learning): sync vendored run_with_flags + isolate hook-error log in tests (hb-rap)"
```

(The stewardship `run_with_flags.py` copy is now byte-identical in the working tree but **uncommitted** — `check-vendored-sync` compares files so it stays green; it is committed in Task 2 under `fix(stewardship)`.)

---

### Task 2: Read-side — surface hook errors in the morning briefing

**Files:**
- Modify: `plugins/stewardship/scripts/render_briefing.py` (add `read_hook_errors`, `render_hook_errors_section`; wire into `render`/`build_sections`/`collect`; **reuse** the existing `learning_data_root()`)
- Modify: `plugins/stewardship/templates/morning-briefing.md` (add `## Hook Errors` + `{{HOOK_ERRORS_SECTION}}`)
- Modify: `plugins/stewardship/README.md` (mention the new section)
- Commit (sync): `plugins/stewardship/scripts/run_with_flags.py` (the Task-1 `--fix` output)
- Test: `plugins/stewardship/tests/test_render_briefing.py`, and add the isolation fixture to `plugins/stewardship/tests/test_run_with_flags.py`

**Interfaces:**
- Consumes: `<learning_data_root>/hooks-errors.jsonl` from Task 1.
- Produces: `read_hook_errors(path=None) -> list[dict]`, `render_hook_errors_section(errors: list[dict]) -> str`.

- [ ] **Step 1: Isolation fixture + failing tests**

Add the autouse isolation fixture (as in Task 1 Step 1) to `plugins/stewardship/tests/test_run_with_flags.py`. Then append to `plugins/stewardship/tests/test_render_briefing.py`:

```python
def test_render_hook_errors_section_empty():
    assert "no hook errors" in rb.render_hook_errors_section([]).lower()


def test_render_hook_errors_section_lists_recent():
    s = rb.render_hook_errors_section([{"ts": 1.0, "hook": "surface.py",
                                        "error": "runtime error: boom"}])
    assert "1 hook error" in s and "surface.py" in s


def test_read_hook_errors_missing_returns_empty(tmp_path):
    assert rb.read_hook_errors(tmp_path / "nope.jsonl") == []


def test_read_hook_errors_reads_and_skips_malformed(tmp_path):
    p = tmp_path / "hooks-errors.jsonl"
    p.write_text('{"hook":"a.py"}\nnot-json\n{"hook":"b.py"}\n', encoding="utf-8")
    assert [r["hook"] for r in rb.read_hook_errors(p)] == ["a.py", "b.py"]


def test_writer_reader_resolve_same_root(monkeypatch, tmp_path):
    monkeypatch.setenv("LEARNING_DATA_ROOT", str(tmp_path / "shared"))
    from importlib.util import spec_from_file_location, module_from_spec
    rwf_path = (Path(rb.__file__).parent.parent.parent
                / "discipline" / "scripts" / "run_with_flags.py")
    spec = spec_from_file_location("_rwf_probe", rwf_path)
    rwf = module_from_spec(spec); spec.loader.exec_module(rwf)
    assert rb.learning_data_root() == rwf._learning_data_root()
```

Also extend `test_render_substitutes_all_tokens`: add `{{HOOK_ERRORS_SECTION}}` to that test's local template string **and** a `"hook_errors"` entry to its `sections` dict — otherwise the token is either a `KeyError` in `render` or never exercised (it currently passes vacuously if only the dict is extended).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest plugins/stewardship/tests/test_render_briefing.py -q -k "hook_error or same_root or substitutes_all_tokens"`
Expected: FAIL — `AttributeError: ... render_hook_errors_section`.

- [ ] **Step 3: Add reader + renderer (reuse the existing `learning_data_root`)**

In `plugins/stewardship/scripts/render_briefing.py`, after `read_instinct_report` (~L112), add:

```python
def read_hook_errors(path=None) -> list[dict]:
    """Read hook-error records from hooks-errors.jsonl; [] if absent/unreadable.

    Bounded at the source (run_with_flags keeps a ring buffer), so this reads a
    small file. A large count is itself the signal the briefing exists to raise.
    """
    p = Path(path) if path else (learning_data_root() / "hooks-errors.jsonl")
    if not p.is_file():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def render_hook_errors_section(errors: list[dict]) -> str:
    if not errors:
        return "No hook errors logged."
    lines = [f"**{len(errors)} hook error(s) logged** (most recent shown):"]
    for rec in errors[-5:]:
        hook = rec.get("hook", "?")
        raw = str(rec.get("error", ""))
        err = raw.splitlines()[0][:160] if raw else ""
        lines.append(f"- `{hook}` — {err}")
    return "\n".join(lines)
```

- [ ] **Step 4: Wire the section (template + render + build_sections + collect). No `derive_actions` rule.**

- Template (`plugins/stewardship/templates/morning-briefing.md`) — after `## Horizon Scan`, before `## Learned Instincts`:
  ```markdown
  ## Hook Errors

  {{HOOK_ERRORS_SECTION}}
  ```
- `render(...)` substitution map: add `"{{HOOK_ERRORS_SECTION}}": sections["hook_errors"],`
- `build_sections(data)`: add `"hook_errors": render_hook_errors_section(data.get("hook_errors") or []),` (the `or []` guards the pre-existing `test_build_sections_degrades_on_error`, which passes no `hook_errors` key).
- `collect(...)`: add a `hook_errors_path=None` keyword (mirroring the other injectable source paths) and set `hook_errors` in its returned dict, e.g. `"hook_errors": read_hook_errors(hook_errors_path)`. Read `collect`'s real body first and match how `instinct_report` is threaded.
- **Do not** add a `derive_actions` rule — the section already shows the count (review: gold-plating).
- `plugins/stewardship/README.md`: add "Hook Errors" to the morning-briefing section list.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest plugins/stewardship/tests/test_render_briefing.py plugins/stewardship/tests/test_run_with_flags.py -q`
Expected: PASS — new section/reader/agreement tests, the extended token test, and all pre-existing briefing + wrapper tests.

- [ ] **Step 6: Commit — `fix(stewardship)` (sync copy + read-side together)**

```bash
git add plugins/stewardship/scripts/run_with_flags.py plugins/stewardship/scripts/render_briefing.py plugins/stewardship/templates/morning-briefing.md plugins/stewardship/README.md plugins/stewardship/tests/test_render_briefing.py plugins/stewardship/tests/test_run_with_flags.py
git commit -m "fix(stewardship): sync run_with_flags + surface hook errors in the morning briefing (hb-rap)"
```

---

## Verification

Positive-evidence completion gate — run via the **Bash tool / Git Bash**, record output + exit code inline before ticking.

- [ ] **All touched suites green:**
  `python -m pytest plugins/discipline/tests/test_run_with_flags.py plugins/learning/tests/test_coverage_gaps.py plugins/stewardship/tests/test_render_briefing.py plugins/stewardship/tests/test_run_with_flags.py -q`
  Expected: pass, exit 0. Evidence: _<paste tail + exit>_

- [ ] **No regression in the three touched plugins:**
  `python -m pytest plugins/discipline/tests plugins/learning/tests plugins/stewardship/tests -q`
  Expected: pass, exit 0. Evidence: _<paste tail + exit>_

- [ ] **Vendored sync clean:** `python3 ci/check-vendored-sync.py` → `clean`, exit 0. Evidence: _<…>_

- [ ] **Real log NOT polluted by the test run:** after the full run above, `test -f "$LOCALAPPDATA/claude-marketplace/learning/hooks-errors.jsonl" && echo POLLUTED || echo clean` (Git Bash: `ls "$LOCALAPPDATA/claude-marketplace/learning/hooks-errors.jsonl"`). Expected: the real log is absent or unchanged (isolation held). Evidence: _<…>_

- [ ] **Per-plugin release commits present:** `git log --oneline main..HEAD` shows `fix(discipline)`, `fix(learning)`, `fix(stewardship)` commits (so `release.py` bumps all three). Optionally `python3 ci/release.py --dry-run` shows all three queued. Evidence: _<…>_

- [ ] **End-to-end smoke:** point `LEARNING_DATA_ROOT` at a temp dir, run the real `run_with_flags.py` on a hook that raises, then `render_briefing.read_hook_errors()` + `render_hook_errors_section()` — confirm the raised error appears in the rendered section. Evidence: _<…>_

- [ ] **Static gate:** `bash scripts/verify.sh` → all `[verify] OK`, exit 0. Evidence: _<…>_

- [ ] **Coverage of new lines (scoped):** `python -m coverage run --source=plugins/discipline/scripts,plugins/stewardship/scripts -m pytest plugins/discipline/tests plugins/stewardship/tests -q && python -m coverage report` → `run_with_flags.py` + `render_briefing.py` new lines covered. (Combined ≥90% floor delegated to CI.) Evidence: _<…>_

- [ ] **Only intended files changed:** `git show --name-only` per commit; `git status --porcelain` empty. Evidence: _<…>_

## Retrospective

Closes hb-rap.

_(Filled at deliver step 12 via `retrospective:plan-retrospective`. Placeholder until then.)_
