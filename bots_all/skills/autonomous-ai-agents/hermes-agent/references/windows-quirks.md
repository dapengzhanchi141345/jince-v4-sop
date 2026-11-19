# Windows-Specific Quirks

Hermes runs natively on Windows (PowerShell, cmd, Windows Terminal, git-bash
mintty, VS Code integrated terminal). Most of it just works, but a handful
of differences between Win32 and POSIX have bitten us — document new ones
here as you hit them so the next person (or the next session) doesn't
rediscover them from scratch.

### Input / Keybindings

**Alt+Enter doesn't insert a newline** — Windows Terminal (and mintty) grab it
for fullscreen before prompt_toolkit sees it. Use **Ctrl+Enter** instead (the
CLI binds it to newline on Windows; raw Ctrl+J does the same, harmlessly).
To inspect how your terminal reports a keystroke, run
`python scripts/keystroke_diagnostic.py` from the repo root.

### Config / Files

**HTTP 400 "No models provided" on first run** — `config.yaml` was saved with
a UTF-8 BOM (Notepad does this). Re-save as UTF-8 without BOM;
`hermes config edit` writes correctly.

### `execute_code` / Sandbox

**WinError 10106** from the sandbox child process — it can't create an
`AF_INET` socket. Root cause is usually Hermes's env scrubber dropping
`SYSTEMROOT`/`WINDIR`/`COMSPEC` (Python's `socket` needs `SYSTEMROOT` to find
`mswsock.dll`), not a broken Winsock LSP. The `_WINDOWS_ESSENTIAL_ENV_VARS`
allowlist in `tools/code_execution_env.py` covers it; if you still hit it,
echo `os.environ` inside an `execute_code` block to confirm `SYSTEMROOT` is set.

### Testing on Windows

Prepare the checkout through PM first. With its Python 3.14, build an independent
test environment at a fresh path:

```powershell
python -m pm.build_env --source . --out .venv --group dev --group test
```

The output must not exist. Before regeneration, stop its processes and explicitly
remove only that disposable environment. Do not install into the application
payload or modify a selected dependency generation.

Run the canonical runner through Git Bash:

```bash
scripts/run_tests.sh tests/foo/test_bar.py -v --tb=short
```

The runner discovers `.venv/Scripts/python.exe`, clears credentials and
`PYTHONPATH`, and isolates each test file. For an external test environment,
set `HERMES_PYTHON` to its Python executable. PM shell activation alone does
not supply pytest after the runner clears `PYTHONPATH`.

### Path / Filesystem

**Line endings.** Git may warn `LF will be replaced by CRLF`. Cosmetic — the
repo's `.gitattributes` normalizes. Don't let editors auto-convert committed
POSIX-newline files to CRLF.

**Forward slashes work almost everywhere.** `C:/Users/...` is accepted by
every Hermes tool and most Windows APIs. Prefer forward slashes in code
and logs — avoids shell-escaping backslashes in bash.

**git-bash eats unquoted `(` in echo/label text.**
`echo === RUN_A(should print 3 lines) ===` dies with `syntax error near
unexpected token (` — `(` is a metacharacter even when preceded by CJK
characters. Quote any echo argument containing parentheses, or use a
placeholder that has no metacharacters. (Hit 3x in one session while
running verification sequences.)

**patch/write_file intermittent timeouts on E:\ data drive** — the
file-editing tools occasionally time out (30s/60s) writing or patching
files under `E:\workbuddy` (antivirus indexing contention). Don't
retry-loop the same tool: fall back to `write_file` into the scratch
dir, then `shutil.copyfile` via terminal to the target. The scratch
write succeeds and the copy is atomic enough for the scripts involved.

**No-tzdata local Pythons crash scripts that import ZoneInfo at top
level** (3.13.12 and hermes-tools 3.14.x both lack the `tzdata` pip
package on this host; the cron wrapper's python has it). When verifying
a no_agent cron script locally that uses `bjt_now()`/ZoneInfo, expect a
`ZoneInfoNotFoundError` traceback from a bare run — that is an
interpreter gap, not a script bug. Verify the changed logic in isolation
(exec the function body with `bjt_now` mocked) or run under the cron
wrapper's interpreter; do not "fix" the script or the cron job on this
evidence.

