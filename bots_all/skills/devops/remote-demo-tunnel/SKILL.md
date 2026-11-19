---
name: remote-demo-tunnel
description: "Use when a remote customer must reach a local web service."
version: 1.0.0
platforms: [windows]
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [tunneling, cloudflared, remote-demo, windows, autostart, customer-trial]
    related_skills: [trading-strategy-saas]
---

# Remote demo tunnel (customer reaches a local service from the internet)

## When to Use

When the user says "customer is remote, let them try it", "make it accessible outside my machine", or asks to hand a trial URL + login to an external party — a locally-served web app must be reachable over the public internet without the customer knowing anything about your network. NOT for: LAN-only delivery (bind 0.0.0.0 and share the LAN IP), or long-lived production exposure (use a Cloudflare named tunnel / real domain and say so plainly).

Class of task: "I want the customer to try it" / "customer is remote, make it all work" — a locally-running web service (fixed port, usually 127.0.0.1-bound) must be reachable by a customer on an arbitrary internet, no installs, no VPN knowledge. The deliverable is ONE public HTTPS link + ONE credential pair + a link file that stays current.

## Standing rules

- **The link file IS the customer hand-off, not the link you last saw.** A Cloudflare quick-tunnel hostname changes every (re)start. So: the link is written to a fixed txt file (desktop + project dir) by an auto-refresh script after every tunnel (re)start, and operator/courier ALWAYS reads that txt before sending — never forward a remembered link.
- **The public entry stays read-mostly-safe**: the trial account is pre-seeded with the demo state (a saved EA/profile, one run history row, dry-run executor), so the customer can click everything without funds risk.

## Procedure (order matters; each step verified before the next)

1. **Service binds all interfaces**: launch with `0.0.0.0` (env-overridable host, e.g. `JINCE_SASS_HOST`), not `127.0.0.1` — the tunnel targets loopback but LAN customers should also work (`http://<lan-ip>:port`), and it proves non-loopback binding. Verify: `netstat` shows `0.0.0.0:port`, and a probe to `http://<lan-ip>:port/healthz` returns 200 (self-conn via LAN IP, not 127.0.0.1).
2. **Start the quick tunnel** (no account needed): `"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --no-autoupdate --url http://127.0.0.1:<port>` — run via PowerShell `Start-Process -WindowStyle Hidden` so it survives the shell. The stdout box prints `https://<slug>.trycloudflare.com`; if stdout was lost, redirect to a log file and grep `https://[a-z0-9-]+\.trycloudflare\.com`.
3. **Verify customer-perspective end to end**: GET the public URL's root (200 + the app's real markers, e.g. a panel id) AND its `/healthz` through the tunnel — not just the local port. The link only "works" when both pass.
4. **Ship the auto-refresh + watchdog trio**: (a) `_refresh_link.py` — grep the tunnel log for the current URL, write it into the fixed link txt files with credentials + "read this before sending" note; (b) `_watchdog.py` — loop every ~60s: ensure service port (restart with project venv python if down), ensure tunnel process alive (restart if down), re-run the link refresh; (c) both as hidden detached processes. The watchdog is the reason a restart doesn't strand the customer.
5. **Windows autostart without admin**: the Startup folder (`C:\Users\<user>\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\`) accepts a plain .bat at login — no admin needed. A `schtasks /Create ... /SC ONLOGON` for a *system* task WILL fail access-denied on non-admin shells; don't waste cycles, use the Startup folder. Also drop a one-click .bat on the Desktop for manual recovery.
6. **Hand the customer exactly**: public URL, login, what to click, and the two caveats — (a) quick-tunnel link dies when the host machine's service/隧道 stops; the link file auto-refreshes on recovery, re-read it; (b) for a STABLE branded link the owner must create a Cloudflare named tunnel (account required) — state that plainly rather than promising permanence.

## Pitfalls (cost time if ignored)

- **Windows process management from git-bash is the minefield — use Python `subprocess` + a helper script, not shell one-liners.** Three traps hit hard: (1) `wmic process ... /format:list` splits PID and CommandLine on SEPARATE lines, so line-grep for `ProcessId=` finds nothing — parse with a re.split on the pattern `ProcessId=(\d+)` over the whole output; (2) wmic/tasklist output is GBK — decode with `encoding='utf-8', errors='ignore'` and never `text=True` (default locale decode crashes on the Chinese Windows UI strings); guard `r.stdout` with `or ""` (a no-match tasklist filter returns empty/None); (3) `cmd //c "..."` in git-bash gets eaten by MSYS (prints the welcome banner) — use single-slash `taskkill /F /PID <pid>` native form or route through a Python script. A watchdog that crashes on its own process-probe every cycle is a silent no-op: after (re)writing process checks, run ONE probe cycle that prints what it saw (alive/started/link) before leaving it unattended, and if multiple watchdog copies exist (old interpreter, old code), kill all but one — a buggy stale copy will fight the fixed one; tell copies apart by the interpreter path in their command line, not the process name. Launch dedup: a hidden `Start-Process` started from a shell that later exited still leaves its watchdog alive, so "I started one" usually means "there are now two" — before leaving a loop unattended, list all matching processes, kill every copy, start exactly one, and confirm the survivor PID plus the service + link are green..
- **Never start the service with the bare global/uv interpreter when the app needs venv deps** (fastapi/sqlalchemy in `.venv`) — the process starts and dies silently; `netstat` shows nothing and the restart loop looks like "watchdog didn't start the service". Start with `.venv/Scripts/python.exe` (or `uv run`) and confirm the port by healthz, not by process existence.
- **`taskkill` is approval-gated in this environment**: batch the kill into a single command and accept the auto-approval notice; splitting kill-then-restart across many calls burns turns. Kill the specific PID from `netstat -ano | grep :PORT | awk '{print $5}'`, never `taskkill /IM python.exe` (collateral).
- **A backgrounded tunnel whose stdout you didn't capture loses the link.** Redirect to a log file BEFORE starting, or the only record of the URL is gone when the box redraws; keep the refresh script grepping that log so re-starts auto-heal the link file.
- **After any restart, the tunnel hostname changes** — the link txt refresh must run as part of the restart procedure itself (watchdog does this), and the operator's habit must be "read the txt", never "reuse last link".
- **Firewall rules are optional for the tunnel** (it connects OUT to Cloudflare, not in); don't get stuck on `New-NetFirewallRule` access-denied — it's not on the critical path for quick-tunnel delivery.
