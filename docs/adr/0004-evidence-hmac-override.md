# 0004. HMAC-signed override token for evidence-discipline hard blocks

**Status:** Accepted

## Context

The `evidence` plugin ships a `secret_scan.py` PreToolUse hook (exit code 2 = hard block) that
intercepts `Bash`, `Edit`, `Write`, `MultiEdit`, and `WebFetch` inputs and rejects any containing
recognized credential patterns (AWS access key IDs, GitHub PATs, OpenAI/Anthropic keys, private
key blocks, and similar).

Hard blocks without an escape hatch create two failure modes: legitimate operations involving
credential-shaped test fixtures or redacted values are permanently unworkable, and users trained
into the habit of setting a plain boolean env var (e.g. `SECRET_SCAN_DISABLE=1`) tend to leave it
set long-term, defeating the gate entirely. A warn-and-log alternative was rejected on similar
grounds — a warning with no consequence is routinely ignored.

The design goal is an override that is:

- **Narrow in scope** — a token encodes a specific `action`, so a token issued for `secret_scan`
  cannot bypass a future `scope_binding` gate.
- **Short-lived** — TTL is caller-specified at issuance, capped at 4 hours (`MAX_TTL_SECONDS`).
- **Use-limited** — caller specifies `--uses N` (cap: 5); the hook calls `redeem_token()` which
  decrements and persists the count in a sidecar file next to the key
  (`~/.claude/evidence-override-key.redemptions.json`).
- **Auditable** — every redemption attempt (success or failure) writes to stderr; no silent bypass.
- **Revocable by rotation** — overwriting the key file immediately invalidates all outstanding
  tokens because signatures no longer verify.

## Decision

Override tokens are HMAC-SHA256 signed grants implemented in `plugins/evidence/scripts/evidence_hmac.py`.
A token is a compact `<base64url-payload>.<base64url-sig>` string. The payload carries `action`,
`nbf`, `exp`, `max_uses`, and a random `nonce`. The signing key lives outside any git-tracked
directory at `~/.claude/evidence-override-key` (CSPRNG, ≥32 bytes, permissions 600/user-ACL on
Windows). The path is overridable via `EVIDENCE_OVERRIDE_KEY`.

To bypass a false-positive block:

```bash
# Issue a one-use, 5-minute token
python <plugin>/scripts/evidence_hmac.py issue secret_scan --ttl 300 --uses 1

# Re-run with the token in the environment
EVIDENCE_OVERRIDE_TOKEN=<token> <blocked-command>
```

`secret_scan.py` calls `redeem_token()` (not bare `verify_token()`), which validates the
signature, TTL, and action match, then atomically decrements the use counter before allowing the
tool call through. If `evidence_hmac.py` cannot be imported (e.g. plugin misconfiguration),
`check_override()` returns `False` and the block stands — fail-closed.

The key is generated once per machine by `scripts/init.sh` (bash) or `scripts/init.ps1`
(PowerShell). Rotation = overwrite the key; no versioning machinery exists by design.

## Consequences

- A false-positive block requires one CLI command to issue a token and one env var to carry it.
  The workflow is intentionally more friction than a plain flag — that friction is the point.
- Tokens cannot be forged without the key file. A token for `secret_scan` cannot grant access to
  any other named action.
- The `--uses 1` default means a token reused across multiple tool calls fails on the second
  attempt; the caller must issue a higher-use token intentionally.
- No-override gates (e.g. a downstream project-level framework's submission or commit-secret
  checks) must not call `redeem_token()` — `evidence_hmac.py` allows override on every action
  it knows about, so those gates must enforce the no-override invariant themselves.
- Key rotation invalidates all outstanding tokens with no grace period. For long-running
  sessions that hold valid tokens, coordinate rotation to a session boundary.

## Scope-binding gate (shipped 2026-06-25, opt-in)

The `scope_binding` action is now backed by a ready-made hook,
`plugins/evidence/hooks/scope_bind.py`. It relays `scope_binding.py`'s
`check_url`/`check_path` verdicts to confine `WebFetch` (only when the manifest declares
`hosts`) and `Edit`/`Write`/`MultiEdit` (only when it declares `path_prefixes`); Bash,
WebSearch, and Read are intentionally not gated.

Following the per-action token design above, a `secret_scan` token cannot bypass it and vice
versa. The hook is **registered in the plugin's `hooks.json` but off by default** — it is a
no-op unless `EVIDENCE_SCOPE_ENFORCE` is on **and** a manifest is loaded (the same env-gated
opt-in the `learning` plugin uses). This keeps enabling the evidence plugin from imposing any
enforcement, and prevents a stray `.claude/evidence-scope.yaml` from silently activating it.
A pure project-`settings.json` opt-in was rejected: `${CLAUDE_PLUGIN_ROOT}` is not available
outside a plugin's own hooks, the install path is version-pinned, and the hook depends on its
`scripts/` siblings.
