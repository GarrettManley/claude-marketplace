# hb-rap: Hook-error observability — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Tracker:** hb-rap (harness beads ledger — `bd -C ~/.claude/harness-backlog show hb-rap`). Marketplace #51 postmortem.

**Goal:** Make silently-swallowed hook errors visible. `run_with_flags` catches a hook's import/runtime error, prints it to stderr, and exits 0 — so `surface.py` crashed on every SessionStart for weeks unnoticed. Persist those errors to a marketplace-wide log, and surface a count + recent samples in the stewardship morning briefing the user actually reads.

**Architecture:** Two halves across a cross-plugin contract that is *a JSONL file at a conventional path, not a Python import*. **Write-side:** at `run_with_flags.py`'s two swallow points (import error ~L167, runtime error ~L209), best-effort-append the error to `<marketplace_data_root>/hooks-errors.jsonl` — never raising, since logging a swallowed error must not itself break the hook chain. **Read-side:** `stewardship/render_briefing.py` reads that log and renders a new `## Hook Errors` briefing section (mirroring its existing `read_instinct_report` + `render_instinct_section` pattern). The path resolver is *deliberately replicated* in both writer and reader (the same rationale `learning_data_root()` already documents), because `run_with_flags.py` is vendored into every plugin and must stay import-free.

**Tech Stack:** Python 3.12/3.13, stdlib only (`json`, `time`, `os`, `pathlib`). pytest. No new dependencies.

## Global Constraints

- **Edit the dev clone only:** `C:\Users\Garre\Workspace\claude-marketplace\` — never `~/.claude/plugins/…`.
- **`run_with_flags.py` is vendored 3× and canonical in `plugins/discipline/scripts/`.** Edit **only** the discipline copy, then run `python3 ci/check-vendored-sync.py --fix` to copy it to `learning` + `stewardship`. Never hand-edit the consumer copies (CI `check-vendored-sync` blocks drift).
- **Stdlib only.** No new runtime dependency.
- **`run_with_flags` must stay import-free of other plugins** — replicate the data-root resolver, don't import it.
- **The error-log append is best-effort and MUST NOT raise** — it sits on `run_with_flags`'s every-path-returns-0 contract. Wrap it in a bare `except Exception: pass`. Force `encoding="utf-8"` on the write (a cp1252 default console must not crash the log).
- **Writer and reader resolvers must agree** — both use `CLAUDE_MARKETPLACE_DATA_ROOT` → `%LOCALAPPDATA%/claude-marketplace` (win) → `$XDG_DATA_HOME/claude-marketplace` → `~/.local/share/claude-marketplace`, using `sys.platform == "win32"` (matching `learning_data_root`). A test pins that they resolve the same path for the same env.
- **Keep it lean** — no rotation, no severity levels, no elaborate handling (errors are rare; YAGNI). If the log ever grows pathological, that itself is what the briefing surfaces.
- **Coordinated release:** this change makes `fix:` commits to **discipline** (canonical `run_with_flags`), **learning** + **stewardship** (vendored copies), and **stewardship** (`render_briefing`) — `release.py` will bump all three on the next release. Land via PR; after a squash-merge, `git fetch --tags` and re-point any `*-v*` tag `release.py` bumps.
- **Stage files explicitly per commit** — never `git add -A`; no `__pycache__/*.pyc`. Tests run per-plugin-dir; combined `--fail-under=90` floor only over the full suite (delegate to CI); verify local coverage with `--source=`. All shell snippets run via the **Bash tool / Git Bash**.

---

### Task 1: Write-side — persist hook errors in `run_with_flags`

Append import/runtime errors to the marketplace hook-error log at the two swallow points, best-effort. Edit the canonical copy, then sync the vendored copies.

**Files:**
- Modify: `plugins/discipline/scripts/run_with_flags.py` (canonical — add `_marketplace_data_root`, `_append_hook_error`; call at both swallow points; add `json`, `time` imports)
- Sync (generated, do not hand-edit): `plugins/learning/scripts/run_with_flags.py`, `plugins/stewardship/scripts/run_with_flags.py` (via `ci/check-vendored-sync.py --fix`)
- Test: `plugins/discipline/tests/test_run_with_flags.py`

**Interfaces:**
- Produces:
  - `_marketplace_data_root() -> Path` — env `CLAUDE_MARKETPLACE_DATA_ROOT` → platform default under `claude-marketplace`.
  - `_append_hook_error(hook_name: str, error: str) -> None` — best-effort append of `{"ts", "hook", "error"}` JSONL to `<root>/hooks-errors.jsonl`; never raises.
  - Log contract: `<marketplace_data_root>/hooks-errors.jsonl`, one JSON object per line. Task 2's reader consumes this.

- [ ] **Step 1: Write the failing test**

Append to `plugins/discipline/tests/test_run_with_flags.py` (inside the test class if the existing tests are methods — match the surrounding style; these use `subprocess.run` on the real wrapper and a `CLAUDE_MARKETPLACE_DATA_ROOT` env pointing at `tmp_path`):

```python
    def test_runtime_error_appended_to_hook_error_log(self, tmp_path):
        import json as _json
        hook = tmp_path / "boom.py"
        hook.write_text("def main():\n    raise ValueError('kaboom')\n")
        env = {**os.environ, "CLAUDE_MARKETPLACE_DATA_ROOT": str(tmp_path / "mkt")}
        result = subprocess.run(
            [sys.executable, str(RUN_WITH_FLAGS), str(hook), "some:hook:id", "standard"],
            input="{}", capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0                       # chain not broken
        assert "runtime error" in result.stderr             # still prints (unchanged)
        log = tmp_path / "mkt" / "hooks-errors.jsonl"
        assert log.is_file()
        rec = _json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
        assert rec["hook"] == "boom.py"
        assert "kaboom" in rec["error"]

    def test_hook_error_log_write_failure_never_breaks_chain(self, tmp_path):
        # Point the data root at a path that can't be created (a file, not a dir),
        # so the append fails — the hook must still exit 0.
        hook = tmp_path / "boom2.py"
        hook.write_text("def main():\n    raise ValueError('x')\n")
        blocker = tmp_path / "blocker"
        blocker.write_text("i am a file, not a dir")
        env = {**os.environ, "CLAUDE_MARKETPLACE_DATA_ROOT": str(blocker / "sub")}
        result = subprocess.run(
            [sys.executable, str(RUN_WITH_FLAGS), str(hook), "some:hook:id", "standard"],
            input="{}", capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0                       # best-effort: no crash
```

If `RUN_WITH_FLAGS` / `sys` / `os` are not already module-level in the test file, add them (the existing subprocess tests already reference the wrapper path — reuse that constant; check the file header).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest plugins/discipline/tests/test_run_with_flags.py -q -k "hook_error_log or never_breaks_chain"`
Expected: FAIL — the log file is never created (no append wired yet).

- [ ] **Step 3: Add imports + the resolver + the append helper**

In `plugins/discipline/scripts/run_with_flags.py`, add `import json` and `import time` to the import block (keep alphabetical with the existing `import os` / `import shutil` / `import subprocess` group). Then add, after `MAX_STDIN_BYTES` (before `_read_stdin`):

```python
def _marketplace_data_root() -> Path:
    """Resolve the marketplace-wide data root (the hook-error log lives here).

    Replicated in stewardship/render_briefing.py (the reader) — the cross-plugin
    contract is a JSONL file at a conventional path, not a Python import, so this
    stays self-contained (run_with_flags is vendored into every plugin).
    """
    explicit = os.environ.get("CLAUDE_MARKETPLACE_DATA_ROOT")
    if explicit:
        return Path(explicit)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "claude-marketplace"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "claude-marketplace"
    return Path.home() / ".local" / "share" / "claude-marketplace"


def _append_hook_error(hook_name: str, error: str) -> None:
    """Best-effort append of a swallowed hook error to hooks-errors.jsonl.

    Never raises: logging an error the wrapper is deliberately swallowing must
    not itself break the hook chain (every path here returns 0).
    """
    try:
        root = _marketplace_data_root()
        root.mkdir(parents=True, exist_ok=True)
        rec = {"ts": time.time(), "hook": hook_name, "error": error}
        with open(root / "hooks-errors.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:  # noqa: BLE001 -- best-effort telemetry, never break the chain
        pass
```

- [ ] **Step 4: Call it at both swallow points**

In `_import_and_run_python`, at the import-error handler (currently prints `import error in ...`):

```python
    except Exception as e:  # noqa: BLE001
        _append_hook_error(script_path.name, f"import error: {e}")
        print(f"run_with_flags: import error in {script_path.name}: {e}", file=sys.stderr)
        return 0  # don't break the chain
```

and at the runtime-error handler (currently prints `runtime error in ...`):

```python
    except Exception as e:  # noqa: BLE001
        _append_hook_error(script_path.name, f"runtime error: {e}")
        print(f"run_with_flags: runtime error in {script_path.name}: {e}", file=sys.stderr)
        return 0  # don't break the chain
```

- [ ] **Step 5: Sync the vendored copies**

Run: `python3 ci/check-vendored-sync.py --fix`
Then confirm clean: `python3 ci/check-vendored-sync.py`
Expected: `--fix` copies the canonical file to `learning` + `stewardship`; the plain run prints `clean`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest plugins/discipline/tests/test_run_with_flags.py -q`
Expected: PASS — the 2 new tests plus every pre-existing `run_with_flags` test (the stderr prints and return-0 behavior are unchanged; the append is additive).

- [ ] **Step 7: Commit**

```bash
git add plugins/discipline/scripts/run_with_flags.py plugins/learning/scripts/run_with_flags.py plugins/stewardship/scripts/run_with_flags.py plugins/discipline/tests/test_run_with_flags.py
git commit -m "fix(discipline): persist swallowed hook errors to a marketplace log (hb-rap)"
```

(The learning + stewardship copies are byte-identical syncs of the discipline change; committing them together keeps `check-vendored-sync` green at every commit.)

---

### Task 2: Read-side — surface hook errors in the morning briefing

Read the log and render a `## Hook Errors` section, mirroring `render_briefing.py`'s existing instinct-report pattern.

**Files:**
- Modify: `plugins/stewardship/scripts/render_briefing.py` (add `marketplace_data_root`, `read_hook_errors`, `render_hook_errors_section`; wire into `render`/`build_sections`/`collect`/`derive_actions`)
- Modify: `plugins/stewardship/templates/morning-briefing.md` (add the `## Hook Errors` section + `{{HOOK_ERRORS_SECTION}}` token)
- Test: `plugins/stewardship/tests/test_render_briefing.py`

**Interfaces:**
- Consumes: the `<marketplace_data_root>/hooks-errors.jsonl` contract from Task 1.
- Produces: `marketplace_data_root() -> Path` (matches Task 1's resolver), `read_hook_errors(path=None) -> list[dict]`, `render_hook_errors_section(errors: list[dict]) -> str`.

- [ ] **Step 1: Write the failing tests**

Append to `plugins/stewardship/tests/test_render_briefing.py`:

```python
def test_render_hook_errors_section_empty():
    assert "no hook errors" in rb.render_hook_errors_section([]).lower()


def test_render_hook_errors_section_lists_recent():
    errors = [{"ts": 1.0, "hook": "surface.py", "error": "runtime error: boom"}]
    s = rb.render_hook_errors_section(errors)
    assert "1 hook error" in s
    assert "surface.py" in s


def test_read_hook_errors_missing_returns_empty(tmp_path):
    assert rb.read_hook_errors(tmp_path / "nope.jsonl") == []


def test_read_hook_errors_reads_and_skips_malformed(tmp_path):
    p = tmp_path / "hooks-errors.jsonl"
    p.write_text('{"hook": "a.py", "error": "x"}\nnot-json\n{"hook": "b.py"}\n',
                 encoding="utf-8")
    recs = rb.read_hook_errors(p)
    assert [r["hook"] for r in recs] == ["a.py", "b.py"]


def test_marketplace_root_matches_run_with_flags(monkeypatch, tmp_path):
    # Writer (run_with_flags) and reader (render_briefing) must resolve the same
    # path for the same env — the whole cross-plugin contract hinges on it.
    monkeypatch.setenv("CLAUDE_MARKETPLACE_DATA_ROOT", str(tmp_path / "shared"))
    import importlib.util
    rwf_path = (Path(rb.__file__).parent.parent.parent
                / "discipline" / "scripts" / "run_with_flags.py")
    spec = importlib.util.spec_from_file_location("_rwf_probe", rwf_path)
    rwf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rwf)
    assert rb.marketplace_data_root() == rwf._marketplace_data_root()
```

Also extend the existing `test_render_substitutes_all_tokens` (it asserts no `{{` remains) so it covers the new section — add `"hook_errors": "..."` to whatever `sections` dict that test builds, so the `{{HOOK_ERRORS_SECTION}}` token is exercised. (Read that test first; match its fixture shape.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest plugins/stewardship/tests/test_render_briefing.py -q -k "hook_error or marketplace_root or substitutes_all_tokens"`
Expected: FAIL — `AttributeError: module 'render_briefing' has no attribute 'render_hook_errors_section'` (and the token test leaves `{{HOOK_ERRORS_SECTION}}` unsubstituted).

- [ ] **Step 3: Add the resolver, reader, and renderer**

In `plugins/stewardship/scripts/render_briefing.py`, after `learning_data_root()` (which ends ~L97), add:

```python
def marketplace_data_root() -> Path:
    """Resolve the marketplace-wide data root — mirror of the resolver in the
    vendored run_with_flags.py (the writer). Replicated not imported, same
    cross-plugin-contract rationale as learning_data_root above.
    """
    explicit = os.environ.get("CLAUDE_MARKETPLACE_DATA_ROOT")
    if explicit:
        return Path(explicit)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "claude-marketplace"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "claude-marketplace"
    return Path.home() / ".local" / "share" / "claude-marketplace"


def read_hook_errors(path=None) -> list[dict]:
    """Read hook-error records from hooks-errors.jsonl; [] if absent/unreadable.

    Hook errors are rare in a healthy system, so the log stays small; a large
    count is itself the signal the briefing exists to surface.
    """
    p = Path(path) if path else (marketplace_data_root() / "hooks-errors.jsonl")
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

- [ ] **Step 4: Wire the section into the template + render + build_sections + collect + actions**

Template (`plugins/stewardship/templates/morning-briefing.md`) — add a section (e.g. after `## Horizon Scan`, before `## Learned Instincts`):

```markdown
## Hook Errors

{{HOOK_ERRORS_SECTION}}
```

`render_briefing.py`:
- In `render(...)`'s substitution map, add: `"{{HOOK_ERRORS_SECTION}}": sections["hook_errors"],`
- In `build_sections(data)`, add: `"hook_errors": render_hook_errors_section(data.get("hook_errors", [])),`
- In `collect(...)`, populate `data["hook_errors"] = read_hook_errors(hook_errors_path)` (thread a `hook_errors_path=None` kwarg through `collect`'s signature for test injection, mirroring how the other sources are injected).
- In `derive_actions(...)`, add a rule (after the instinct rule): when `data`/an `errors` count is non-zero, append `f"{n} hook error(s) logged overnight — investigate (see the marketplace hooks-errors.jsonl)."`. Thread the errors list/count into `derive_actions` the same way `instinct` is, or compute it in the caller and pass a count.

(Match the exact threading to how `instinct` already flows through `collect`→`build_sections`→`derive_actions`; read those three functions and follow the established seam rather than inventing a new one.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest plugins/stewardship/tests/test_render_briefing.py -q`
Expected: PASS — new section tests, the resolver-agreement test, the extended token test, and every pre-existing briefing test.

- [ ] **Step 6: Commit**

```bash
git add plugins/stewardship/scripts/render_briefing.py plugins/stewardship/templates/morning-briefing.md plugins/stewardship/tests/test_render_briefing.py
git commit -m "feat(stewardship): surface hook errors in the morning briefing (hb-rap)"
```

---

## Verification

Positive-evidence completion gate — run each command via the **Bash tool / Git Bash** from repo root, record output + exit code inline before ticking.

- [ ] **Both touched suites green:**
  `python -m pytest plugins/discipline/tests/test_run_with_flags.py plugins/stewardship/tests/test_render_briefing.py -q`
  Expected: all pass (+4 write-side, +5 read-side incl. the extended token test), exit 0.
  Evidence: _<paste tail + exit code>_

- [ ] **No plugin regression (both touched plugins):**
  `python -m pytest plugins/discipline/tests plugins/stewardship/tests -q`
  Expected: pass, exit 0.
  Evidence: _<paste tail + exit code>_

- [ ] **Vendored sync clean:**
  `python3 ci/check-vendored-sync.py`
  Expected: `clean` (all 3 `run_with_flags.py` byte-identical), exit 0.
  Evidence: _<paste output + exit code>_

- [ ] **End-to-end smoke (real wrapper → real log → real briefing read):**
  Point `CLAUDE_MARKETPLACE_DATA_ROOT` at a temp dir, run the real `run_with_flags.py` on a hook that raises, then read the log back via `render_briefing.read_hook_errors` and render the section — confirm the raised error appears.
  Expected: the section reports `1 hook error(s) logged` naming the failing hook, exit 0.
  Evidence: _<paste output + exit code>_

- [ ] **Static pre-merge gate green:**
  `bash scripts/verify.sh`
  Expected: every `[verify] OK` (ruff, `check-vendored-sync`, frontmatter, etc.), exit 0.
  Evidence: _<paste final lines + exit code>_

- [ ] **Coverage of new lines (scoped — NOT `--fail-under` alone):**
  `python -m coverage run --source=plugins/discipline/scripts,plugins/stewardship/scripts -m pytest plugins/discipline/tests plugins/stewardship/tests -q && python -m coverage report`
  Expected: `run_with_flags.py` + `render_briefing.py` rows show the new functions executed; no new misses on added lines.
  Evidence: _<paste rows + exit code>_

- [ ] **Combined coverage floor:** delegated to CI (`--fail-under=90` over the combined suite runs on the PR; unrelated plugins fail locally on Windows). This change is coverage-additive across discipline + stewardship.

- [ ] **Only intended files changed:** `git show --name-only` for both commits lists exactly the 4 + 3 files; `git status --porcelain` empty (no `__pycache__` / `.pyc`).
  Evidence: _<paste output>_

## Retrospective

Closes hb-rap.

_(Filled at deliver step 12 via `retrospective:plan-retrospective` — what worked, friction, and follow-ups. Placeholder until then.)_
