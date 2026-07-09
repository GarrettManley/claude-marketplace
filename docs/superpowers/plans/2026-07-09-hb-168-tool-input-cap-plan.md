# hb-168: Cap oversized tool_input at capture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Tracker:** hb-168 (harness beads ledger — `bd -C ~/.claude/harness-backlog show hb-168`). Marketplace #51 follow-up.

**Goal:** Bound the size of every observation the learning plugin captures, so `tool_input` can no longer persist multi-megabyte Write/Edit file bodies — while preserving the exact keys `analyze.py` reads.

**Architecture:** `observe.py` already caps `tool_response` at capture (`cap_tool_response`, whole-blob, marker). `tool_input` is captured **raw** at `_build_observation` (`observe.py:64`), so Write/Edit/MultiEdit embed full file `content` / `old_string` / `new_string`. That is the vector that grew `observations.jsonl` to 75.5 MB (rotated out 2026-07-07); the live file is small again but will re-accumulate the same way without a cap, and its size taxes every hook append (Defender re-scans the file on each write). This change is **forward-looking**: add `cap_tool_input` that recurses the payload and head-caps any over-length string to a plain 2000-char string. `file_path` (short) and `command` (its first two tokens — all `analyze.bash_command_prefixes` reads — sit within the head) survive unchanged, so no consumer breaks and no special-casing is needed. Scoped strictly to capture (per the bead); the pre-existing 30-day retention in `synthesize_nightly.py` already ages out any uncapped records written before this lands, so no nightly change is required.

**Tech Stack:** Python 3.12/3.13, stdlib only (`json`, `typing`). pytest. No new dependencies.

## Global Constraints

- **Edit the dev clone only:** `C:\Users\Garre\Workspace\claude-marketplace\` — never `~/.claude/plugins/…` (read-only install cache).
- **Stdlib only** — no new runtime dependency.
- **`observe.py` is single-copy and LF-only** — not vendored (no `check-vendored-sync` concern) and safe for multi-line `Edit` (no CRLF hazard).
- **Stage files explicitly per commit** — never `git add -A`, never stage the `tests/` dir wholesale; `__pycache__/*.pyc` must never be staged (the Fact-Forcing gate then blocks the `git rm`).
- **Conventional Commits, per-plugin scope:** `fix(learning): …`.
- **Keep `cap_tool_input` lean** — no marker dict, no defensive handling for inputs that can't occur. The one guard that *is* warranted is the recursion-depth bound: this hook consumes arbitrary tool payloads (a system boundary), and an unbounded recursive walk could raise `RecursionError` and crash the hook on every tool call.
- **Preserve behavior, don't special-case:** the only `tool_input` keys any consumer reads are `command` (`analyze.py:123`, via first two tokens) and `file_path` (`analyze.py:154` `edits[].file_path`, `:158` top-level). `detect.py` reads `command` **only indirectly**, through `analyze.bash_command_prefixes` — so it is not tool_input-independent; keep the preserve behavior intact when touching this. Both survive head-capping naturally (`file_path` is short; `command`'s first tokens are within the 2000-char head).
- **Tests run per-plugin-directory**; the `--fail-under=90` coverage floor is valid **only over the combined suite**. Never run `--fail-under` against `plugins/learning/tests` alone. All shell snippets below run via the **Bash tool / Git Bash**, not PowerShell.
- **Federation-router guardrail:** the Workspace hook router replays sec-research PT-5 on *Bash* calls — keep `npm/pip/cargo install` and `Stop-Process` literals out of Bash commands and commit messages.
- **Landing:** `land-policy: pr` — open a PR; the 5 required checks gate the merge. **This PR cuts no release** — the `fix(learning):` commits ship in learning's *next* `release.py` run; do **not** move any `learning-v*` tag as part of landing.

---

### Task 1: `cap_tool_input` + capture wiring + doc update

Add the cap, apply it at the single capture site (covers both `pre` and `post` phases), and update the README section that documents observation-size bounding.

**Files:**
- Modify: `plugins/learning/scripts/observe.py` (add `INPUT_MAX_CHARS`, `_MAX_DEPTH`, `cap_tool_input`; change the `tool_input` line in `_build_observation`)
- Modify: `plugins/learning/README.md` (the "Observation growth is bounded…" paragraph)
- Test: `plugins/learning/tests/test_observe.py` (append a `--- tool_input capture cap ---` section)

**Interfaces:**
- Consumes: nothing new (`json`, `typing.Any` already imported in `observe.py`).
- Produces:
  - `INPUT_MAX_CHARS: int = 2000`, `_MAX_DEPTH: int = 40` — module constants in `observe.py`.
  - `cap_tool_input(value: Any, max_chars: int = INPUT_MAX_CHARS, _depth: int = 0) -> Any` — recurses `dict`/`list`; head-caps any `str` longer than `max_chars` to `value[:max_chars]`; leaves everything else as-is; stops descending past `_MAX_DEPTH`. No other task depends on it (single-task plan).

- [ ] **Step 1: Write the failing tests**

Append to `plugins/learning/tests/test_observe.py`:

```python
# --- tool_input capture cap ---


def test_oversized_string_value_head_capped():
    from observe import INPUT_MAX_CHARS, cap_tool_input

    big = "x" * (INPUT_MAX_CHARS * 10)
    out = cap_tool_input({"file_path": "/big.py", "content": big})
    assert out["file_path"] == "/big.py"            # short → passes through
    assert isinstance(out["content"], str)          # plain string head, NOT a marker dict
    assert len(out["content"]) == INPUT_MAX_CHARS


def test_long_command_head_capped_but_stays_string():
    from observe import INPUT_MAX_CHARS, cap_tool_input

    long_cmd = "grep " + "a" * (INPUT_MAX_CHARS * 2)
    out = cap_tool_input({"command": long_cmd})
    assert isinstance(out["command"], str)          # analyze.py needs isinstance str
    assert len(out["command"]) == INPUT_MAX_CHARS
    assert out["command"].startswith("grep ")       # first two tokens preserved


def test_multiedit_nested_strings_capped_file_path_kept():
    from observe import INPUT_MAX_CHARS, cap_tool_input

    big = "y" * (INPUT_MAX_CHARS * 5)
    out = cap_tool_input(
        {"file_path": "/x.py",
         "edits": [{"file_path": "/x.py", "old_string": big, "new_string": big}]}
    )
    edit = out["edits"][0]
    assert edit["file_path"] == "/x.py"             # per-edit file_path survives
    assert len(edit["old_string"]) == INPUT_MAX_CHARS
    assert len(edit["new_string"]) == INPUT_MAX_CHARS


def test_small_tool_input_unchanged():
    from observe import cap_tool_input

    payload = {"file_path": "/x.py", "command": "git status"}
    assert cap_tool_input(payload) == payload       # nothing over the cap


def test_cap_tool_input_depth_bounded_no_recursionerror():
    from observe import cap_tool_input

    # Pathologically deep payload (arbitrary MCP tool_input could be). The
    # _MAX_DEPTH gate must stop descent so this returns instead of raising.
    deep: dict = {}
    node = deep
    for _ in range(5000):
        child: dict = {}
        node["k"] = child
        node = child
    out = cap_tool_input(deep)
    assert isinstance(out, dict)                     # returned, did not raise


def test_build_observation_caps_tool_input():
    from observe import INPUT_MAX_CHARS, _build_observation

    big = "w" * (INPUT_MAX_CHARS * 4)
    obs = _build_observation(
        {"tool_name": "Write", "tool_input": {"file_path": "/f", "content": big}},
        phase="pre",
    )
    assert obs["tool_input"]["file_path"] == "/f"
    assert len(obs["tool_input"]["content"]) == INPUT_MAX_CHARS


def test_analyze_still_reads_capped_records():
    # Crux contract: the two keys analyze.py extracts survive capping.
    from observe import INPUT_MAX_CHARS, _build_observation
    from analyze import bash_command_prefixes, file_hotspots

    big = "c" * (INPUT_MAX_CHARS * 6)
    write_obs = _build_observation(
        {"tool_name": "Write", "tool_input": {"file_path": "/hot.py", "content": big}},
        phase="pre",
    )
    bash_obs = _build_observation(
        {"tool_name": "Bash", "tool_input": {"command": "git status --porcelain"}},
        phase="pre",
    )
    assert file_hotspots([write_obs], top_n=5)[0][0] == "/hot.py"
    assert bash_command_prefixes([bash_obs], top_n=5)[0][0] == "git status"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest plugins/learning/tests/test_observe.py -q`
Expected: FAIL — `ImportError` (`cap_tool_input` / `INPUT_MAX_CHARS` not defined in `observe`). (Run the whole file — no `-k` filter, so no test is accidentally deselected.)

- [ ] **Step 3: Implement `cap_tool_input`**

In `plugins/learning/scripts/observe.py`, immediately **after** `cap_tool_response` and **before** `_build_observation`, insert:

```python
# Cap for stored tool_input payloads. Uncapped, Write/Edit tool_input embeds
# full file bodies (content / old_string / new_string) — a multi-MB-per-record
# bloat vector that regrows observations.jsonl, and file size taxes every hook
# append (Defender re-scans the file on each write). 2000 chars is ample: the
# only structural read is analyze.bash_command_prefixes, which uses a command's
# first two tokens (well within the head); file_path is short. Mirrors
# RESPONSE_MAX_CHARS. Unlike the response cap, this is per-string (not
# whole-blob) so analyze.py's by-key reads keep working.
INPUT_MAX_CHARS = 2000

# Recursion bound. tool_input is arbitrary JSON from any tool (incl. MCP), so a
# pathologically nested payload must not raise RecursionError out of this
# per-tool-call hook. Real tool_input nests 1-2 deep; 40 is far above that and
# far below Python's ~1000 limit.
_MAX_DEPTH = 40


def cap_tool_input(value: Any, max_chars: int = INPUT_MAX_CHARS, _depth: int = 0) -> Any:
    """Recursively head-cap oversized strings in a tool_input payload.

    Over-length strings become a plain string head (value[:max_chars]) — NOT a
    marker dict — so analyze.py's structural reads keep working: `command` stays
    a str whose first two tokens (all bash_command_prefixes uses) are preserved,
    and `file_path` is short enough to pass through untouched. No consumer reads
    content / old_string / new_string, so no truncation signal is needed. The
    _depth gate bounds recursion so arbitrary nesting can't crash the hook.
    """
    if isinstance(value, str):
        return value[:max_chars] if len(value) > max_chars else value
    if _depth >= _MAX_DEPTH:
        return value
    if isinstance(value, dict):
        return {k: cap_tool_input(v, max_chars, _depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [cap_tool_input(v, max_chars, _depth + 1) for v in value]
    return value
```

- [ ] **Step 4: Wire it into `_build_observation`**

In `plugins/learning/scripts/observe.py`, change the `tool_input` line inside `_build_observation` (the assignment currently reading `"tool_input": event.get("tool_input") or {},` — before this step's insertion it is line 64; use the quoted text as the anchor, not the number):

```python
        "tool_input": cap_tool_input(event.get("tool_input") or {}),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest plugins/learning/tests/test_observe.py -q`
Expected: PASS — the 7 new tests plus every pre-existing `observe` test (small inputs pass through unchanged, so `test_observation_recorded_to_project_jsonl`, `test_build_observation_shape`, etc. are unaffected).

- [ ] **Step 6: Update the README**

Read `plugins/learning/README.md` around the "Observation growth is bounded…" paragraph (≈ lines 185-190). Replace that paragraph with wording that reflects the new `tool_input` cap:

```markdown
Observation growth is bounded at capture and by nightly compaction. At capture,
`observe.py` truncates any `tool_response` payload over 2000 serialized chars
(to a `{"truncated": true, "text": ...}` marker) and head-caps any oversized
string inside `tool_input` (Write/Edit file bodies) to 2000 chars — `file_path`
and `command` are preserved so pattern analysis still works. The nightly
`synthesize-nightly --apply` compaction then rewrites each project's
`observations.jsonl` atomically, dropping records outside the retention window
and truncating oversized `tool_response` survivors.
```

- [ ] **Step 7: Commit**

```bash
git add plugins/learning/scripts/observe.py plugins/learning/tests/test_observe.py plugins/learning/README.md
git commit -m "fix(learning): cap oversized tool_input at capture (hb-168)"
```

---

## Verification

Positive-evidence completion gate — run each command via the **Bash tool / Git Bash**, record output + exit code inline before ticking. From repo root `C:\Users\Garre\Workspace\claude-marketplace`.

- [ ] **Touched suite green:**
  `python -m pytest plugins/learning/tests/test_observe.py -q`
  Expected: all pass (+7 new), exit 0.
  Evidence: _<paste tail + exit code>_

- [ ] **No learning-plugin regression:**
  `python -m pytest plugins/learning/tests -q`
  Expected: full learning suite passes, exit 0.
  Evidence: _<paste tail + exit code>_

- [ ] **New function lines covered (scoped read — NOT `--fail-under` alone):**
  `python -m coverage run -p -m pytest plugins/learning/tests -q && python -m coverage combine && python -m coverage report --include='*plugins/learning*'`
  Expected: `observe.py` row shows `cap_tool_input` lines executed (no new misses on the added lines).
  Evidence: _<paste observe.py row + exit code>_

- [ ] **End-to-end smoke (real subprocess, catches import/encoding issues unit tests miss):**
  ```bash
  set -euo pipefail
  tmp="$(mktemp -d)"
  big="$(python -c 'print("Z"*50000, end="")')"
  printf '{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"/smoke.py","content":"%s"},"session_id":"smoke"}' "$big" \
    | LEARNING_DATA_ROOT="$tmp" LEARNING_HOOK_PROFILE=strict LEARNING_OBSERVE=on CLAUDE_PROJECT_DIR=/smoke/proj \
      python plugins/learning/scripts/observe.py
  python - "$tmp" <<'PY'
  import glob, json, sys
  f = glob.glob(sys.argv[1] + "/**/observations.jsonl", recursive=True)[0]
  rec = json.loads(open(f, encoding="utf-8").read().splitlines()[0])
  c = rec["tool_input"]["content"]
  assert isinstance(c, str) and len(c) == 2000, (type(c), len(c))
  assert rec["tool_input"]["file_path"] == "/smoke.py"
  print("SMOKE OK: content capped to", len(c), "chars; file_path preserved")
  PY
  ```
  Expected: `SMOKE OK: content capped to 2000 chars; file_path preserved`, exit 0.
  Evidence: _<paste output + exit code>_

- [ ] **Static pre-merge gate green:**
  `bash scripts/verify.sh`
  Expected: every `[verify] OK` (ruff clean; `check-vendored-sync` unaffected), exit 0.
  Evidence: _<paste final lines + exit code>_

- [ ] **Combined coverage floor holds (mirrors CI — the real PR gate):**
  ```bash
  set -euo pipefail
  python -m coverage erase
  python -m coverage run -p -m pytest ci/tests -q
  for d in plugins/*/tests; do python -m coverage run -p -m pytest "$d" -q; done
  python -m coverage combine
  python -m coverage report --fail-under=90
  ```
  Expected: exit 0 (≥ 90% over the combined suite).
  Evidence: _<paste TOTAL row + exit code>_

- [ ] **Only intended files changed:** `git show --name-only HEAD` lists exactly `observe.py`, `test_observe.py`, `README.md`; `git status --porcelain` is empty (no `__pycache__` / `.pyc` slipped in).
  Evidence: _<paste output>_

## Retrospective

Closes hb-168.

_(Filled at deliver step 12 via `retrospective:plan-retrospective` — what worked, friction, and follow-ups. Placeholder until then.)_
