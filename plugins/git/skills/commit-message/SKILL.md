---
name: commit-message
description: Use when writing, formatting, or fixing a git commit message, or when a commit fails a project's commit-message CI check.
version: 0.2.0
dependencies: []
---

# Commit Message Formatter

Format commit messages that follow the [Conventional Commits](https://www.conventionalcommits.org/) spec. Many projects layer additional rules on top — header length caps, required body, a `Tested:` block — via a CI guard (often a GitHub Action or pre-commit hook). This skill handles the universal shape; the project-specific extensions go in your project's `.claude/skills/commit-message/` fork.

## Header line

```
<type>(<scope>): <Summary>
```

- **`type`** (required, lowercase): one of `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`, `build`. Some projects add custom types (`hotfix`, `wip`) — check your project's `.commitlintrc` or guard script.
- **`scope`** (optional, parenthesized): the affected module, e.g. `(api)`, `(auth)`, `(ui)`. Keep scope short — long scopes push the header past the length cap.
- **One space** after the colon, then the summary.
- **Summary:** imperative mood, starts with an uppercase letter, no trailing period.
- **Length cap:** Most projects enforce 50–72 character headers. **Count before outputting.** Long scope names and verbose summaries are the most common CI failure.

## Body

- Separated from the header by **one blank line**.
- Explain *what* changed and *why* — not *how*. The diff shows how.
- Wrap at ~72 characters per line.
- Reference issue trackers if the project uses them (e.g., `Closes #42`, `Fixes JIRA-123`, `AB#6376` for Azure Boards).

## Trailers (optional)

Trailers go at the end, after a blank line:

```
Closes #42
Co-authored-by: Name <email@example.com>
Signed-off-by: Name <email@example.com>
```

**Check your project's policy on `Co-authored-by`.** Some teams use it to attribute pair-programming or AI assistance; others ban it because the assumption is implicit (e.g., "all devs use Claude — it's assumed"). When in doubt, omit it.

## Project-specific extensions

Some projects require additional structured blocks after the body — a `Tested:` block (firmware), a `Risk:` block (high-stakes systems), a `Reviewed-by:` trailer. These are project conventions; they live in the project-local fork of this skill alongside the project's CI guard regex.

When a CI guard rejects a commit, read the guard's regex (usually in `.github/workflows/commit-message-*.yml` or `.git/hooks/commit-msg`) and write a header that matches exactly.

## Self-Validation Checklist

Before outputting:

1. Header matches `<type>(<scope>): <Summary>` exactly. Type is lowercase. Summary starts uppercase, no trailing period.
2. Header length is under the project's cap (default: 72; common: 50 for the type+scope, 72 total).
3. A blank line separates header from body.
4. Body explains what and why, not how.
5. If the project has a CI guard, your message matches its regex.

## Example — generic project

```
fix(auth): Reject expired refresh tokens at the gateway

The gateway previously forwarded expired refresh tokens to the auth
service, which then returned a 401. This added a latency hop and a
spurious error log. Reject at the gateway with a 401 directly.

Closes #284
```

## Example — firmware project with Tested block

```
fix(ota): Prevent double-free on aborted download

The OTA buffer was freed in both the error handler and the cleanup
path, causing a hard fault when the download was cancelled mid-chunk.
Guard the second free with a NULL check and set the pointer to NULL
after the first free.

Tested:
- How: Triggered OTA abort via test server mid-transfer; confirmed no fault after 50 cycles
- Hardware: <device> rev C
- Test Equipment: <debugger>, <power supply>
```

The `Tested:` block here is a project-specific extension. Generic Conventional Commits doesn't require it.

## Negative Example — common mistake

```
Fix(ota): prevent double-free on aborted download.
```

Failures: (1) type `Fix` is uppercase — must be lowercase `fix`; (2) summary starts with lowercase `p` — must start uppercase; (3) trailing period on summary; (4) no body.

## Validate Mode

Validate an existing commit message against a rule set without writing a new one.

```bash
# Validate HEAD (replace <ver> with the installed plugin version)
bash ~/.claude/plugins/cache/garrettmanley/git/<ver>/skills/commit-message/scripts/validate.sh HEAD

# Validate a specific SHA
bash ~/.claude/plugins/cache/garrettmanley/git/<ver>/skills/commit-message/scripts/validate.sh abc1234

# Use a project-local rule set
bash ~/.claude/plugins/cache/garrettmanley/git/<ver>/skills/commit-message/scripts/validate.sh HEAD \
  --rules .claude/commit-message-rules.yaml
```

The `<ver>` token is the installed semver (e.g., `0.1.0`). Find it with:
```bash
ls ~/.claude/plugins/cache/garrettmanley/git/
```

**Rule set resolution (in order):**
1. `--rules <path>` if provided
2. `<git-root>/.claude/commit-message-rules.yaml` (project-local)
3. `rules.example.yaml` bundled with this skill (Conventional Commits defaults only)

**Rule set format** (`commit-message-rules.yaml`):

```yaml
header:
  pattern: "^(feat|fix|docs|...)\\([^)]+\\)?: [A-Z]"  # regex
  max_length: 72

body:
  required: true
  min_lines_before_trailer: 1

trailers:
  Tested:                        # trailer name
    required: true
    must_contain:
      - "- How:"
      - "- Hardware:"
      - "- Test Equipment:"
```

See `rules.example.yaml` for an annotated starter template.

**Exit codes:** `0` = valid, `1` = validation failed (diagnostic on stderr), `2` = usage error.

## Required Inputs

The user must provide (or you must gather from context):
- **What changed** — files or modules affected
- **Why it changed** — motivation, bug being fixed, requirement met
- **Issue / work-item reference** if the project requires one
