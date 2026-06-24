---
name: ledger-doctor
description: Inspect a campaign ledger for hash-chain integrity errors, identify the first broken block, and guide safe truncation to the nearest prior snapshot. Use when the user reports ledger corruption, unexpected Rust errors, or after a server crash mid-write.
version: 0.1.0
dependencies: []
---

# Ledger Doctor

## When to use

Use when the user reports ledger corruption, hits unexpected Rust
errors, or after a server crash mid-write — any time the campaign
ledger's hash chain may be broken.

Inspect and repair campaign ledger hash-chain integrity.

## Steps

### 1. Get the campaign ID

Ask the user which campaign to inspect if not provided. Campaign directories live at `campaigns/<id>/ledger/history.jsonl`.

### 2. Run the inspector

```bash
npx ts-node scripts/ledger-doctor.ts <campaign_id>
```

This reads every block in the ledger, recomputes SHA-256 hashes using the same payload formula as the Rust core (`core/src/ledger.rs:33-51`), and reports:
- Total blocks read
- First block with a broken `prev_hash` link
- First block with a hash mismatch (if data was tampered)
- The nearest `SNAPSHOT` block at or before the first broken block (safe truncation point)

### 3. Review the report

If the ledger is clean: "Ledger OK — N blocks, chain intact."

If corruption is found, the script reports:
- The index and data of the broken block
- Whether the break is a prev_hash link break (common after manual edit) or a hash mismatch (data tampering or write corruption)
- The last valid snapshot index to truncate to

### 4. Truncate (if repairing)

Run with the `--fix` flag to back up and truncate:

```bash
npx ts-node scripts/ledger-doctor.ts <campaign_id> --fix
```

The script will:
1. Create a timestamped backup: `history.jsonl.bak-<timestamp>`
2. Truncate the ledger at the last clean snapshot index
3. Print the new tail block index and hash

**Important:** After truncation, any in-memory game state that referenced blocks after the truncation point is gone. Restart the server before resuming play. The Rust `Verify` command (`core.exe --campaign <id> verify`) will confirm the tail block is valid after truncation.

### 5. Clear residual combat state

After truncating the ledger, delete `campaigns/<id>/combat_state.json` if present:

```bash
rm -f campaigns/<campaign_id>/combat_state.json
```

This file persists encounter state across server restarts **independently of the ledger** — truncating `history.jsonl` does not clear it. If stale, it causes `COMBAT_RECONSTRUCTED` telemetry on the next boot, silently restoring phantom combat from a prior session (see the "combat_state.json survives ledger truncation" pitfall in CLAUDE.md).

Only skip this step if you deliberately want to preserve a mid-combat snapshot and know the truncation point is within an active encounter you plan to continue.

## What the ledger doctor cannot do

- Reconstruct lost blocks — truncation is permanent.
- Fix corruption before the genesis block — if block 0 is broken, the entire ledger must be discarded.
- Repair mid-chain blocks without truncating everything after them — the hash chain is append-only by design.
