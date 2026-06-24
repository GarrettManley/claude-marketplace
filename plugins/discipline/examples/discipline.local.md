---
# Example .claude/discipline.local.md
# Drop this file in your project's .claude/ dir to configure the
# discipline@garrettmanley plugin. All keys are optional; defaults
# come from git auto-detection or sensible fallbacks.

# Auto-detected from `git remote get-url origin` if not set.
repo: your-org/your-repo

# Auto-detected from `git symbolic-ref refs/remotes/origin/HEAD` if not set.
main-branch: master

# Comma-separated. TS/JS/Rust default. Add or replace as needed.
source-extensions: .ts, .tsx, .js, .jsx, .mjs, .cjs, .rs

# Regex matching spec doc paths (for spec_companion_check).
# Default: ^docs/.*\d{3,4}-[\w-]+\.md$
spec-pattern: ^docs/engineering/\d{3}-[\w-]+\.md$

# Regex matching plan doc paths (for plan_issue_check).
# Default also covers .claude/plans/ plan-mode files:
#   (?:^docs/.*plans?/\d{4}-\d{2}-\d{2}-.+\.md$)|(?:(?:^|/)\.claude/plans/[^/]+\.md$)
plan-pattern: ^docs/engineering/plans/\d{4}-\d{2}-\d{2}-.+\.md$

# Regex matching a beads issue id for plan citations (for plan_issue_check).
# Default: \b(?:bd|hb)-[0-9a-z]+(?:\.\d+)?\b  — accepts hb-9yw.4, bd-abc1, etc.
bd-id-pattern: \b(?:bd|hb)-[0-9a-z]+(?:\.\d+)?\b

# Beads ledger dir. Set to enable `bd close` auto-close of `Closes <bd-id>`
# markers in a plan's Retrospective (mirrors the gh auto-close). Unset = disabled.
bd-ledger: .beads

# Block in-flight plans missing `## Value Justification` section.
# Off by default; turn on for projects that adopt the impact*confidence/effort scoring.
require-value-justification: true

# Required YAML frontmatter fields on docs/**/*.md.
# Empty (default) disables the lint entirely.
require-frontmatter-fields: status, author, created, diataxis

# Path prefixes the frontmatter lint skips.
# Default: node_modules/, dist/, build/, vendor/
frontmatter-skip-prefixes: docs/engineering/templates/, docs/superpowers/, docs/historical-plans/, node_modules/

# Pitfalls pointer config — both required to enable.
pitfalls-root: docs/engineering/pitfalls
# Format: path-or-prefix=area-slug; multiple separated by `;`.
# Keys ending in `/` are prefix matches; bare keys are exact.
pitfalls-routes: src/dm.ts=dm-cycle; src/actor.ts=dm-cycle; src/state-sync.ts=state-sync; src/server.ts=server-and-auth; src/llm/=llm-and-classifier; core/src/=rust-core; tests/=tests-and-tooling

# SessionStart hook toggles. Both default to true.
inject-issues: true
inject-branch-state: true
---

# Discipline plugin configuration for {project-name}

(Optional free-text body for documenting project-specific intent.
Only the YAML frontmatter is parsed by the hooks.)
