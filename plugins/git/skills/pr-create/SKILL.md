---
name: pr-create
description: Use when the user asks to create a pull request, open a PR, or submit changes for review. Detects the remote host (GitHub, Azure DevOps Repos, GitLab) and uses the matching CLI.
version: 0.2.0
dependencies: []
---

# Create Pull Request

Creates pull requests using the right CLI for whatever remote the repo points at. Pairs with `/commit-message` for the head commit and `/tech-writing` for the PR description.

## Step 1 — Detect the remote host

```bash
git remote get-url origin
```

| URL pattern | Host | CLI |
|---|---|---|
| `git@github.com:...` or `https://github.com/...` | GitHub | `gh` |
| `*@ssh.dev.azure.com:v3/...` or `https://*.dev.azure.com/...` or `*visualstudio.com*` | Azure DevOps Repos | `az repos pr create` |
| `git@gitlab.com:...` or `https://gitlab.com/...` (or self-hosted GitLab) | GitLab | `glab` |
| Bitbucket / other | Bitbucket / unsupported | Manual / web UI |

If the detected CLI isn't installed, surface that to the user before proceeding — don't fall back silently.

## Step 2 — Gather inputs

- **Summary** — imperative-mood description of the change (1 sentence; under 70 chars for the title)
- **Issue / work-item reference** if the project requires one (e.g., GitHub issue `#42`, Azure Boards `AB#6376`, JIRA `PROJ-123`)
- **Test plan** — how the change was validated (tests run, manual steps, devices used)
- **Target branch** — usually `main`; some projects use `develop`, `master`, or a release branch

## Step 3 — Pre-flight

Before running the create command:

1. Branch is pushed to the remote: `git push -u origin <branch>`.
2. No uncommitted changes that should be included.
3. The head commit's message passes the project's commit-message CI guard (run `/commit-message` if unsure).
4. If the project has a multi-lens review process (e.g., the `review` plugin's `/reviewer-personas`), run it and write the completion token first.

## Step 4 — Create the PR

### GitHub (`gh`)

```bash
gh pr create --title "<title>" --body "$(cat <<'EOF'
## Summary
- <bullet describing the change>
- <additional bullet if needed>

## Test plan
- [ ] <test step or validation performed>
- [ ] <additional test step>

Closes #<issue>
EOF
)"
```

Substitute `Closes` with `Fixes` or `Refs` depending on intent. GitHub auto-closes referenced issues on merge for `Closes` / `Fixes`.

### Azure DevOps Repos (`az repos pr create`)

```bash
az repos pr create \
  --title "<title> AB#<work-item-id>" \
  --description "$(cat <<'EOF'
## Summary
- <bullet describing the change>
- <additional bullet if needed>

## Test plan
- [ ] <test step or validation performed>

Issue: <full ADO work-item URL>
EOF
)" \
  --target-branch main
```

Azure DevOps doesn't auto-link from `AB#<id>` in the body — you need the full URL, or you can link the PR to the work item after creation via `az boards work-item update`.

### GitLab (`glab`)

```bash
glab mr create --title "<title>" --description "$(cat <<'EOF'
## Summary
- <bullet describing the change>

## Test plan
- [ ] <test step>

Closes #<issue>
EOF
)" --target-branch main
```

GitLab uses "Merge Request" terminology and `glab mr` instead of `glab pr`.

## Title format

For all three:

```
<type>(<scope>): <Summary>
```

If the project requires a work-item reference in the title (e.g., Azure Boards `AB#<id>`), append it:

```
<type>(<scope>): <Summary> AB#<id>
```

The full title must fit the project's length cap (commonly 70 chars).

## Project-specific guards

Some projects enforce additional rules via CI on top of these defaults:
- A regex check for `AB#<id>` or `JIRA-<id>` in the title
- A full-URL reference to the issue tracker in the body
- A "reviewer token" required before PR creation (paired with the `review` plugin)

Read the project's PR CI workflow file (`.github/workflows/pr-*.yml`, `.azuredevops/pipelines/*.yml`, or `.gitlab-ci.yml`) to know what additional patterns must match.

## Common mistakes

| Mistake | Why it fails | Fix |
|---|---|---|
| `gh pr create` against a non-GitHub remote | Wrong CLI for the host | Detect remote first, pick CLI second |
| Title misses required work-item ref | Project's CI guard rejects PR creation | Read the guard's regex; include exact pattern in title |
| Body has the work-item ID but not the full URL | Some projects require a full URL for auto-linking | Use the full URL form per the project's convention |
| Pushing the branch after running `gh pr create` | `gh` requires the branch to exist on the remote | `git push -u origin <branch>` first |
| Inline body string with shell quoting | Special characters break the command | Use HEREDOC (`$(cat <<'EOF' ... EOF\n)`) — single quotes prevent variable expansion |
