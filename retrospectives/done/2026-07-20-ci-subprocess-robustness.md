# Retrospective: CI gate/test subprocess robustness (hb-duz, hb-4d1)

**Plan:** `~/.claude/plans/... ` → `docs/superpowers/plans/2026-07-20-ci-subprocess-robustness.md`
**Commits:** `fbe093d`, `1066040`, `c3174aa`, `26efd07`, `9a5c2e8` (branch `fix/ci-subprocess-robustness`)
**Date:** 2026-07-20

## Outcome

Delivered two of a three-bead bundle via `/deliver`. **hb-duz:** `check-notice.py` now fails loud on a `git grep` failure instead of silently passing the NOTICE gate (a gate that false-passes on error is worse than none). **hb-4d1:** `stdin=subprocess.DEVNULL` on the git-plugin init test subprocesses. **hb-lv9 de-scoped** — empirically unreproducible as diagnosed. Full gate green; no version bump. Lands via PR (`land-policy: pr`).

## What worked

- **Reproduce-before-trust beat a confident-but-wrong bead diagnosis.** hb-lv9's bead asserted a specific root cause (deleted-cwd → Popen OSError, from a chdir-leaking test). The SCALED plan review flagged it as unverifiable, and a controller-run reproduction settled it empirically: minimal WSL repro shows `git init <abspath>` under a deleted cwd returns rc=0 (no OSError); the full combined invocation is 100% green; and no `chdir`-leaker exists (all `chdir` is auto-restoring `monkeypatch.chdir`). De-scoping beat shipping cwd= edits whose regression could never be made RED.
- **The SCALED plan review caught a real pre-execution bug.** The hb-duz test pointed `git grep` at a `tmp_path` that sits *inside* the dev host's home git repo, so it would ascend and exit 0/1 instead of the intended "not a repo" (128) — the test would never fail on the Windows host. Fixed with `GIT_CEILING_DIRECTORIES` before writing a line of implementation.
- **Wider-scope whole-branch code review paid for itself.** `silent-failure-hunter` caught that my `returncode >= 2` guard missed *negative* signal codes (SIGKILL → -9 < 2), which re-opened the exact hb-duz silent-pass class — and that a setup commit lacked `check=True`. Both were gaps in my own fix.
- **Inline execution on the nested clone** sidestepped the subagent-edits-wrong-checkout class this repo's retros repeatedly record; independent review value was preserved by the Phase C whole-branch pass.

## Friction / bugs

- **Built a TDD plan on an unreproduced diagnosis (hb-lv9).**
  - *Root cause:* took the bead's confident root-cause narrative as ground truth and wrote a fix+regression around it.
  - *How caught:* adversarial plan review (cross-agent disagreement) + controller empirical reproduction.
  - *Rule:* reproduce the *actual* failure before writing a fix plan, even when a tracker gives a specific, confident diagnosis. A regression that can't be shown RED guards nothing.
- **`returncode >= 2` missed negative signal codes.**
  - *Root cause:* modelled git error codes as "≥2" and forgot POSIX signal termination yields negative returncodes.
  - *How caught:* silent-failure-hunter in the whole-branch review.
  - *Rule:* for "fail on any subprocess failure," guard `returncode not in (SUCCESS_CODES)`, never `>= threshold`.
- **Test isolation from an ambient parent git repo.**
  - *Root cause:* `%TEMP%` sits under the home git repo; `git -C <tmp>` ascends into it.
  - *Rule:* any test invoking git in a tmp dir must set `GIT_CEILING_DIRECTORIES=tmp.parent` — the repo already had this exact guard in `plugins/git/tests/test_init.py`; reuse it.
- **cp1252 console mangled an em-dash in a source comment** (rendered `�`).
  - *Rule (known):* keep non-ASCII out of source comments/literals; use ASCII or `\uXXXX`.

## Concrete improvements

- hb-duz + hb-4d1 fixes — done (branch `fix/ci-subprocess-robustness`, PR pending authorization).
- hb-lv9 — kept open; bead updated with full reproduction findings; needs the original failing OS/git-version/invocation.
- Filed during the broader sweep: **hb-64f** (P2, `pre_commit_audit.ps1` descends into the nested marketplace clone, forcing verify-override on every Workspace commit) and **hb-sb1** (P3, harden deliver Phase D closing pass against mid-run session death — the pattern behind six catch-up retros this session).
