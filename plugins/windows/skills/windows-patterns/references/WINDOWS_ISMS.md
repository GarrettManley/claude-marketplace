# Windows-Isms: Things That Bite You

Cross-platform code that "should just work" but doesn't on Windows. Checklist when porting from Linux/macOS or when authoring new Windows-aware code.

## CRLF line endings

Windows files default to `\r\n`. This breaks:

- **Multi-line string matching**: `Edit` tool's `old_string` arrives with `\n`-only line breaks but the file has `\r\n`. The match fails silently. Workaround: single-line edits, or `Write` for full rewrites, or use a Python script that opens with `'rb'` to do binary replace.
- **Shell heredocs** in Bash: a `<<EOF` block written from Windows can have `\r\n` in it, which makes the closing `EOF\r` not match the opening `EOF`.
- **Hash digests on text files** vary between machines if `core.autocrlf` is converting on checkout.

Mitigation:
- Set `core.autocrlf` to `true` (current global setting) so files commit as `\n` but check out as `\r\n` on Windows.
- For files that MUST stay `\n` (shell scripts, makefiles, Python that uses `# -*- coding: utf-8 -*-` style parsing), add to `.gitattributes`:
  ```
  *.sh text eol=lf
  *.py text eol=lf
  ```

## File encoding (UTF-8 with vs without BOM)

| Tool | Default | Reads UTF-8 with BOM? | Reads UTF-8 without BOM? |
|------|---------|----------------------|--------------------------|
| Python 3 (`open(..., encoding='utf-8')`) | UTF-8 no-BOM | Treats BOM as visible char | Yes |
| PowerShell 5.1 | ANSI | Yes | **No (mojibake!)** |
| PowerShell 7+ | UTF-8 no-BOM | Yes (BOM stripped) | Yes |
| Node.js / npm scripts | UTF-8 no-BOM | Treats BOM as visible char | Yes |
| .NET (`File.ReadAllText`) | UTF-8 with detected BOM | Yes | Yes |

Rules:
- **PS 5.1 scripts with non-ASCII chars**: save as UTF-8 with BOM.
- **Python source files**: save as UTF-8 without BOM (BOM in the first line breaks `#!/usr/bin/env python3`).
- **JSON files**: UTF-8 without BOM (RFC 8259 says no BOM).
- **YAML / Markdown / config files**: UTF-8 without BOM.

## Path separators

Windows accepts both `\` and `/` in most contexts but with gotchas:

- **In strings**: `"C:\Users\..."` requires double backslash escape in JSON / Python / etc. Use `"C:/Users/..."` or raw strings (`r"C:\Users\..."` in Python).
- **In Bash on Windows (Git Bash)**: paths get translated. `/c/Users/...` is `C:\Users\...`. Be careful when passing paths between bash and Windows-native tools.
- **In settings.json**: backslashes need double-escape: `"C:\\Users\\..."`.
- **In Python's `Path`**: just use forward slashes. `Path("C:/Users/...").resolve()` works fine.

## Environment variables

PowerShell uses `$env:NAME`, NOT `$NAME` or `%NAME%`:

```powershell
$env:USERPROFILE          # read
$env:MY_VAR = "value"     # write (current process)
[Environment]::SetEnvironmentVariable('MY_VAR', 'value', 'User')   # persist (User scope)
[Environment]::SetEnvironmentVariable('MY_VAR', 'value', 'Machine') # persist (Machine scope, requires admin)
```

In bash on Windows: `$USERPROFILE`, `$LOCALAPPDATA`, `$APPDATA` work, but watch for path translation (the value is in Windows form like `C:\Users\<username>`).

## /tmp doesn't exist on Windows

Python on Windows does NOT resolve `/tmp/foo` to anything sensible. Use:

```python
import tempfile, os
tmp = tempfile.gettempdir()  # → C:\Users\<username>\AppData\Local\Temp on Windows
# or
tmp = os.environ['LOCALAPPDATA'] + r'\Temp'
```

In bash on Windows: `/tmp/foo` works in Bash itself (Git Bash maps it), but ANY tool you pipe to that's a Windows-native binary (`python`, `node`, etc.) won't resolve it.

## `find` vs PowerShell `Get-ChildItem`

`find` exists in Git Bash but is the Bash one, not Windows `find.exe` (which is a wholly different tool — it's a string search). Disambiguate:

```bash
# explicit path
/usr/bin/find /some/path -name '*.ts'

# or use the dedicated tool
Get-ChildItem -Path . -Filter *.ts -Recurse
```

Better: use Glob/Grep tools rather than shelling out to either find variant.

## Process killing

`kill -9 <pid>` works in Git Bash for Bash-owned processes but won't kill a Windows-native process from Bash. Use:

```bash
taskkill /F /PID <pid>
# or
Stop-Process -Id <pid> -Force
```

## File locks

Windows holds file locks much more aggressively than Linux. Common bites:
- Can't `git checkout` a file that's open in another process.
- `git worktree remove` fails with "Permission denied" if anything has a handle.
- Workaround: close the editor / IDE before destructive git ops, or use the PowerShell fallback documented in `discipline:finish-and-push`.

## Multi-line commands in Edit

Mentioned above but worth repeating: `Edit` with multi-line `old_string` on a Windows-CRLF file tends to silently fail. Symptoms: edit reports success but no change in file.

Fix: single-line edits, OR use `Write` to rewrite the whole file, OR use a Python script that opens binary and does the replace exactly.
