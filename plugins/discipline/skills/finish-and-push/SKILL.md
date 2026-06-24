---
name: finish-and-push
description: Close out a feature branch using the standard rebase-onto-main + FF-merge + push routine. User-invocable only (disable-model-invocation true) because pushing is hard-to-reverse. Use after a logical task cluster lands on a feature branch and tests are green.
version: 0.6.0
dependencies: []
disable-model-invocation: true
---

# Finish and Push

End-to-end branch close-out: rebase, recheck, code-review, sign-off, FF-merge,
push, delete branch, prune worktree.

**This skill is user-invocable only** (`disable-model-invocation: true`).
Pushing to origin's main branch is hard-to-reverse; the user must opt in.

## Configuration

The skill reads project config from `.claude/discipline.local.md` if present:

```markdown
---
main-branch: master                  # default: auto-detected from origin/HEAD
recheck-command: npm run check       # default: npm test
finish-extra-command: node scripts/run-gameplay-tests.mjs  # optional
finish-extra-trigger-paths: src/dm.ts, src/llm/, src/bus.ts  # optional
---
```

If `.claude/discipline.local.md` is missing, defaults apply: `main` branch, `npm test` (or `cargo test` if `Cargo.toml` exists, or `pytest` if `pyproject.toml` does).

## Preconditions

- All work committed on the feature branch.
- Branch is short-lived (e.g. `feat/...` or `fix/...`); the project's main branch is the integration target.
- Standard test/check commands have run green at the branch tip.

If any precondition is unmet, **stop and report**. Do not push.

## Steps

### 1. Capture state

```bash
git status --short
git log --oneline <main>..HEAD
git log --oneline -1
```

Report:
- Current branch name
- Number of unpushed commits ahead of main
- Whether working tree is clean

### 2. Rebase onto main

```bash
git fetch origin <main>
git rebase origin/<main>
```

If the rebase fails with conflicts, **stop**. Report the conflicting
files and ask the user how to proceed. Do not auto-resolve.

### 3. Re-run gates after rebase

A rebase can re-introduce incompatibilities. Run the project's recheck
command (from `.claude/discipline.local.md` if configured, otherwise the
default for the project type).

If the project has a `finish-extra-command` configured AND any committed
file matches `finish-extra-trigger-paths`, run that too (e.g. an
expensive integration suite).

If any gate fails, **stop and report**. The user decides whether to
fix-forward or abort.

### 4. Subagent code review

Invoke the `pr-review-toolkit:code-reviewer` agent (or equivalent) with
the diff against main:

```bash
git diff <main>..HEAD
```

Pass that diff plus a short description of the task. Wait for the agent's
verdict. If it surfaces blocking issues, **stop and report** to the user.

### 5. User sign-off gate

Pause and ask the user explicitly: "Code review clean. Ready to FF-merge,
push, and delete `<branch>`?"

Do NOT proceed without an affirmative reply. This is the explicit
"hard-to-reverse" gate.

### 6. FF-merge to main

```bash
git checkout <main>
git merge --ff-only <branch>
```

Use `--ff-only`, never `--squash`. This preserves git-log granularity.

If the FF-merge fails (main moved during review), restart from step 2.

### 7. Push

```bash
git push origin <main>
```

### 8. Delete the branch

```bash
git branch -d <branch>
```

Use `-d` (safe), not `-D`. If git refuses because the branch isn't fully
merged, stop and investigate — `--ff-only` should have made `-d` safe.

### 9. Worktree cleanup (if applicable)

If the branch was developed in a worktree under `.worktrees/`:

```bash
git worktree remove --force .worktrees/<branch>
git worktree prune
```

If `worktree remove` fails with "Permission denied" (Windows-specific):

```bash
powershell -Command "Remove-Item -Recurse -Force '.worktrees/<branch>'"
git worktree prune
```

Then clear empty parent dirs that survive cleanup:

```bash
powershell -Command "Get-ChildItem .worktrees -Directory | Where-Object { (Get-ChildItem $_.FullName -Recurse -File).Count -eq 0 } | Remove-Item -Recurse -Force"
```

### 10. Invoke the finishing skill

If `superpowers:finishing-a-development-branch` is available, invoke it
to handle remaining repo-hygiene checks.

### 11. Report

State to the user:
- Commits delivered (count + range, e.g. `affb722..4cce5eb`)
- Origin main is now at: `<sha>` (`git rev-parse origin/<main>`)
- Branch deleted
- Worktree pruned (if applicable)

## Anti-patterns

- **`--squash`**: never. Preserves git-log fidelity over GitHub history.
- **`--no-verify`**: never. If a hook fails, fix it.
- **Pushing without user sign-off**: step 5 is a hard gate.
- **Skipping the rebase + recheck**: if the branch is more than a day old,
  main may have moved; merging without rebase risks landing stale code.
- **Force-pushing main**: never. Warn the user first.

## When to use vs not

USE this skill when:
- A logical task cluster (one or more commits) is complete on a feature branch.
- Tests are green at the branch tip.
- You're ready to land in one push.

DO NOT use this skill when:
- Main has diverged in a way you don't understand (manual review first).
- The branch has unfinished work-in-progress commits (squash or finish first).
- You're partway through a multi-step landing across several branches
  (each branch's close-out is separate).
