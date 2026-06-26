# Stewardship Nightly Steward — Scheduler Wiring

The nightly steward runs four cross-platform Python scripts in sequence:

| Script | Purpose | Key flag |
|---|---|---|
| `scripts/drift_check.py` | Verify context-file `verification_cmd:` claims | `--dir PATH` to override context dir |
| `scripts/auto_memory_housekeep.py` | Rotate stale auto-memory entries | `--apply` to actually archive (default is dry-run) |
| `scripts/horizon_scan_schedule.py` | Surface a "horizon-scan DUE" reminder on a monthly cadence (a deterministic check — the scan itself stays interactive) | `--interval-days N` (default 30); `--mark-done` to reset after a scan |
| `scripts/render_briefing.py` | Render `templates/morning-briefing.md` to `~/.claude/stewardship/briefing/<date>.md` from the other three scripts' `--json` output | `--stdout` to also print; `--date YYYY-MM-DD` to override |

All four scripts are pure Python 3 and run identically on all platforms. Only the
scheduler wiring differs per OS; each install line below sequences all four with `&&`.

---

## Windows — Task Scheduler (`register_nightly.ps1`)

`scripts/register_nightly.ps1` creates (or replaces) a Task Scheduler entry
named **`stewardship-nightly-steward`** that fires daily at 03:00 local time.

### Install

```powershell
# From a PowerShell 7 prompt in the plugin's scripts/ directory:
.\register_nightly.ps1                 # 03:00, dry-run housekeep
.\register_nightly.ps1 -At "02:30"    # custom time
.\register_nightly.ps1 -ApplyHousekeep  # actually archive stale memory
```

The script writes a stable wrapper (`run-nightly.ps1`) and a log file to
`%LOCALAPPDATA%\stewardship-plugin\logs\`.

### Verify

```powershell
Get-ScheduledTask -TaskName "stewardship-nightly-steward"
Start-ScheduledTask -TaskName "stewardship-nightly-steward"  # smoke-test
Get-Content "$env:LOCALAPPDATA\stewardship-plugin\logs\nightly.log" -Tail 40
```

### Remove

```powershell
.\register_nightly.ps1 -Unregister
```

---

## Linux — cron

`scripts/nightly-scheduler.cron.template` contains a documented crontab line
that fires at 03:00 local time.

### Install

```bash
PLUGIN_PATH="$HOME/.claude/plugins/stewardship"  # adjust as needed
LOG_DIR="$HOME/.local/share/stewardship-plugin/logs"
mkdir -p "$LOG_DIR"

LINE="0 3 * * * /usr/bin/env python3 \"$PLUGIN_PATH/scripts/drift_check.py\" >> \"$LOG_DIR/nightly.log\" 2>&1 && /usr/bin/env python3 \"$PLUGIN_PATH/scripts/auto_memory_housekeep.py\" >> \"$LOG_DIR/nightly.log\" 2>&1 && /usr/bin/env python3 \"$PLUGIN_PATH/scripts/horizon_scan_schedule.py\" >> \"$LOG_DIR/nightly.log\" 2>&1"
(crontab -l 2>/dev/null; echo "$LINE") | crontab -
```

To pass `--apply` to housekeeping, append it to the `auto_memory_housekeep.py`
invocation in the line above.

### Verify

```bash
crontab -l | grep stewardship
tail -40 "$HOME/.local/share/stewardship-plugin/logs/nightly.log"
```

### Remove

```bash
crontab -l | grep -v 'stewardship' | crontab -
```

---

## macOS — launchd (LaunchAgent)

`scripts/com.claude.stewardship.nightly.plist.template` is a LaunchAgent plist
that fires at 03:00 local time via `StartCalendarInterval`.

### Install

```bash
PLUGIN_PATH="$HOME/.claude/plugins/stewardship"  # adjust as needed
LOG_DIR="$HOME/Library/Logs/stewardship-plugin"
mkdir -p "$LOG_DIR"

# Substitute placeholders and copy into LaunchAgents:
sed \
  -e "s|PLUGIN_PATH|$PLUGIN_PATH|g" \
  -e "s|LOG_DIR|$LOG_DIR|g" \
  "$PLUGIN_PATH/scripts/com.claude.stewardship.nightly.plist.template" \
  > ~/Library/LaunchAgents/com.claude.stewardship.nightly.plist

launchctl load -w ~/Library/LaunchAgents/com.claude.stewardship.nightly.plist
```

To pass `--apply` to housekeeping, either edit the substituted plist to add the
flag to the shell command, or write a small wrapper script and point
`ProgramArguments` at it.

### Verify

```bash
launchctl list | grep stewardship
tail -40 "$HOME/Library/Logs/stewardship-plugin/nightly.log"
```

To trigger immediately without waiting for 03:00:

```bash
launchctl start com.claude.stewardship.nightly
```

### Remove

```bash
launchctl unload -w ~/Library/LaunchAgents/com.claude.stewardship.nightly.plist
rm ~/Library/LaunchAgents/com.claude.stewardship.nightly.plist
```

---

## Notes

- **Time zone**: all schedulers fire at 03:00 in the *local* system time zone.
  On cron you can override with a `TZ=` line above the entry. On launchd and
  Task Scheduler the system timezone applies.
- **Missed runs**: if the machine is asleep at 03:00, Task Scheduler
  (`-StartWhenAvailable`) will catch up on next wake; cron and launchd will
  skip the missed run.
- **Log rotation**: the log file grows unbounded. Add `logrotate` (Linux) or a
  periodic `newsyslog` entry (macOS) if you need rotation.
- **--apply flag**: the default for `auto_memory_housekeep.py` is dry-run
  (report only). Review the dry-run output in the log before enabling `--apply`
  in the scheduler entry.
