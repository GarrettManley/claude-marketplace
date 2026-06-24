## What / why

<!-- One or two sentences on what this changes and why. -->

## Linked issue

<!-- e.g. Closes #123. If there's no issue, say why this is small enough not to need one. -->

## Checklist

- [ ] Conventional-commit PR title (`type(scope): description`) — scope attributes the change to a plugin for `ci/release.py`
- [ ] Ran `bash scripts/verify.sh` from the repo root and it exits 0
- [ ] Added or updated tests for any changed behavior (≥90% line coverage gate)
- [ ] Updated `CHANGELOG.md` (root, under `## [Unreleased]`) and/or the affected `plugins/<name>/CHANGELOG.md`
- [ ] Bumped `plugins/<name>/.claude-plugin/plugin.json` version if a plugin changed, then ran `python3 ci/check-versions.py --fix` to sync `marketplace.json`
- [ ] If adding or renaming a skill/agent: ran `python3 ci/gen-skill-index.py --write` and staged `docs/skill-index.md`
- [ ] If editing vendored hook runtime files: edited the canonical copy in `plugins/discipline/scripts/` and ran `python3 ci/check-vendored-sync.py --fix`
- [ ] No secrets, machine-specific paths, corporate identifiers, or private project names in any changed file
