# evidence@garrettmanley

Evidence-discipline workflow for projects where claims must be substantiated. Provides two
model-invoked skills (citation discipline, verification-trace discipline), a defense-in-depth
`PreToolUse` hook that blocks tool inputs containing credential patterns, and an HMAC-signed
override token framework for auditable exception handling. A reusable scope-binding scaffold
is included for projects that need to constrain network and filesystem access to a defined
engagement scope.

Designed for security research and any engineering context where undocumented claims,
stale memory, and accidental secret leakage are real risks.

## Install

```
/plugin marketplace add garrettmanley/claude-marketplace
/plugin enable evidence@garrettmanley
```

## Components

### Skills

| Skill | Description |
|-------|-------------|
| `citation-seeker` | Use before generating public documentation, specs, blog posts, or any architectural claim that should hold up under scrutiny. Enforces tiered authoritative citations: Tier 1 (RFCs/official docs/peer-reviewed), Tier 2 (expert sources/standards). A claim with no evidence must be rewritten as a hypothesis or removed. |
| `truth-seeker` | Use before updating context files, documentation, or making any load-bearing claim future work will rely on. Enforces mandatory verification traces — every fact must carry an internal proof (command output) or an external Tier 1/2 citation. Flags stale-memory recalls and requires re-verification before acting on them. |

### Hooks

| Hook | Event | Matcher | Active by default |
|------|-------|---------|-------------------|
| `secret_scan.py` | `PreToolUse` | `Bash\|Edit\|Write\|MultiEdit\|WebFetch` | Yes |

`secret_scan.py` scans tool inputs for 14 credential patterns: AWS access key IDs, AWS secrets,
GitHub PATs (classic, OAuth, user, server, refresh), OpenAI API keys, Anthropic API keys, Stripe
live keys, Slack bot/user tokens, generic Bearer tokens, and PEM private key blocks. On a hit it
exits `2` (block) and prints which pattern matched, showing only the first 8 characters of each
match. An HMAC override token bypasses the block when `EVIDENCE_OVERRIDE_TOKEN` is set and a
valid token for action `secret_scan` is present.

### Scripts / libraries

| Script | Role |
|--------|------|
| `evidence_hmac.py` | HMAC-SHA256 signed override token library + CLI (`issue`, `verify`, `redeem` subcommands). Caps: TTL ≤ 4 hours, uses ≤ 5. Redemptions tracked in a sidecar file to prevent replay. |
| `scope_binding.py` | Reusable host/path scope checker. Loads `.claude/evidence-scope.yaml` from the project root; permissive (returns `True`) when no manifest is present. Wildcard subdomain patterns (`*.example.com`) supported. |

## Init / Setup

The plugin ships `scripts/init.sh` (macOS/Linux) and `scripts/init.ps1` (Windows, requires
PowerShell 7+). Both generate the HMAC override key at `~/.claude/evidence-override-key` if it
does not already exist. Both are idempotent — running them again does nothing unless `--force` /
`-Force` is passed.

**macOS / Linux:**

```bash
bash "$(claude plugin root evidence@garrettmanley)/scripts/init.sh"
# Optional flags:
#   --force    Regenerate key (invalidates all outstanding tokens)
#   --quiet    Suppress status output
```

**Windows (PowerShell 7+):**

```powershell
& "$(claude plugin root evidence@garrettmanley)/scripts/init.ps1"
# Optional flags:
#   -Force     Regenerate key (invalidates all outstanding tokens)
#   -Quiet     Suppress status output
```

What init does:

1. Creates `~/.claude/` if absent.
2. Writes 64 hex characters (32 bytes from `secrets.token_hex`) to
   `~/.claude/evidence-override-key`.
3. Restricts file permissions: `chmod 600` on Unix; `icacls` inheritance-removed,
   current user read/write-only on Windows.

The key file must live outside any git-tracked directory. The default location under
`~/.claude/` satisfies this.

## Usage

### Skills

Invoke skills by name during a session:

```
/evidence:citation-seeker
```
> Use before drafting an ADR, spec, threat model, or blog post. Invokes the research
> protocol: RFCs and standards first, official vendor docs second, peer-reviewed papers
> third. Claims with no Tier 1/2 source must become explicit hypotheses.

```
/evidence:truth-seeker
```
> Use before editing a context file (`CLAUDE.md`, `AGENTS.md`, `.claude/`) or making a
> load-bearing claim. Requires a verification trace — terminal command output or a
> primary-source URL with the relevant excerpt — for each fact before it lands.

### Secret-scan override

When the secret-scan hook fires on a false positive or a known-safe test fixture:

1. Issue a short-lived token:

   ```bash
   python scripts/evidence_hmac.py issue secret_scan --ttl 60 --uses 1
   ```

2. Re-run the blocked operation with the token in the environment:

   ```bash
   EVIDENCE_OVERRIDE_TOKEN=<token> <your-command>
   ```

The hook logs `override token redeemed; allowing` to stderr and exits `0`. The token is
consumed; reuse with a burned nonce is rejected.

### Scope binding

For projects that need to constrain tool use to an explicit scope, add a manifest at
`.claude/evidence-scope.yaml`:

```yaml
name: engagement-2026-q2
hosts:
  - example.com
  - "*.example.com"
deny_hosts:
  - internal.example.com
path_prefixes:
  - /opt/data/engagement-2026/
```

Then in a custom hook or script:

```python
from scope_binding import check_url, check_path

ok, reason = check_url("https://api.example.com/v1/resource")
if not ok:
    raise RuntimeError(f"out of scope: {reason}")
```

When no manifest is present, both `check_url` and `check_path` return `(True, "no scope
manifest loaded; permissive mode")`. Scope enforcement is fully opt-in.

## Configuration

| Env var | Default | Effect |
|---------|---------|--------|
| `EVIDENCE_OVERRIDE_KEY` | `~/.claude/evidence-override-key` | Path to the HMAC signing key file. Override to use a non-default location. |
| `EVIDENCE_OVERRIDE_TOKEN` | _(unset)_ | When set, `secret_scan.py` attempts to redeem this token for action `secret_scan`. A valid, non-exhausted token bypasses the block. |
| `EVIDENCE_SCOPE_PATH` | _(auto-detect from git root)_ | Explicit path to the scope manifest. Overrides the default `<repo_root>/.claude/evidence-scope.yaml` search. |

### Override token mechanics

- **Issuance caps (enforced at issue time):** TTL ≤ 14400 s (4 hours), uses ≤ 5.
- **Redemption persistence:** sidecar file `<keypath>.redemptions.json` tracks
  `{nonce: uses_remaining}`. Exhausted nonces are kept at `0` — deleting the sidecar
  would un-burn every outstanding token, so leave it alone.
- **Rotation:** overwrite the key file (re-run init with `--force` / `-Force`). Every
  outstanding token fails immediately; the redemptions sidecar becomes irrelevant and
  can be deleted.
- **CLI reference:** `evidence_hmac.py issue <action> [--ttl S] [--uses N]`,
  `verify <action> <token>` (validates without consuming a use),
  `redeem <action> <token>` (validates and consumes one use).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `secret_scan` fires on a test fixture or documentation sample | Issue a one-use, short-TTL token and set `EVIDENCE_OVERRIDE_TOKEN` for the blocked operation. Alternatively, refactor the fixture to avoid the triggering pattern entirely (e.g., replace with a clearly inert placeholder string). |
| `Override key not found at ~/.claude/evidence-override-key` | Run the init script for your platform (see Init / Setup above). If the file exists at a non-default path, set `EVIDENCE_OVERRIDE_KEY` to the actual path. |
| Token verification returns `signature mismatch (wrong key or tampered token)` | The key file changed (rotation or manual edit) after the token was issued. Re-issue the token with the current key. |
| `token already exhausted (nonce=...)` | The token's use count hit zero. Issue a new token. Do not delete the redemptions sidecar to reclaim uses — that un-burns all outstanding tokens. |

## Cross-platform notes

| Concern | macOS / Linux | Windows |
|---------|---------------|---------|
| Init script | `scripts/init.sh` — uses `chmod 600` to restrict key permissions | `scripts/init.ps1` (requires PowerShell 7+) — uses `icacls /inheritance:r /grant:r` for equivalent restrictions |
| `python3` discovery | `init.sh` requires `python3` on `PATH` | `init.ps1` tries `python3`, `python`, then `py` in order |
| Key path | `~/.claude/evidence-override-key` | `%USERPROFILE%\.claude\evidence-override-key` |
| `chmod 600` equivalent | Built into `init.sh` | `icacls` built into `init.ps1`; run manually: `icacls $HOME\.claude\evidence-override-key /inheritance:r /grant:r "$env:USERNAME:(R,W)"` |
| Secret-scan hook invocation | `uv run --no-project "${CLAUDE_PLUGIN_ROOT}/hooks/secret_scan.py"` | Same command — Claude Code resolves `CLAUDE_PLUGIN_ROOT` on both platforms |

## Relationship to more opinionated project-level frameworks

A dedicated security-research framework may enforce constraints this plugin does not provide:
no-override gates (some actions cannot be bypassed by a signed token), venue-specific scope
normalization, project-specific schemas (trace IDs, finding-status workflow, an audit ledger).

The plugin's primitives are a subset of, not a replacement for, such a framework. If a project
already ships more sophisticated enforcement, the recommended integration is:

- Use `evidence:citation-seeker` and `evidence:truth-seeker` as supplementary discipline for
  documentation tasks.
- Leave the hook architecture, HMAC system, and scope-binding in the project-level framework.

If starting greenfield with no existing framework, this plugin is a reasonable starting point for
all components.

## Running tests

```bash
python3 -m pytest plugins/evidence/tests
```

Covers: HMAC issuance caps, expiry, tamper detection, exhaustion persistence, every
`secret_scan` pattern, scope-binding host matching, and init script behavior.
