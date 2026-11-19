# Exposing the locally-run SaaS to a REMOTE customer

When the user wants a customer to try the running demo from outside the machine (客户远程体验), the deliverable is: ONE public HTTPS link + ONE prefilled demo credential + a mechanism that keeps both alive and self-heals. Never hand out the LAN IP or a raw port.

## 1. Make the service reachable
1. Back up the sqlite db file (timestamped copy) before any restart.
2. Start the service bound to `0.0.0.0` (env-var-overridable host), not `127.0.0.1` — LAN fallback works, the tunnel still connects via loopback.
3. Kill the old PID via `netstat -ano | grep :PORT`, restart with the project's **venv** python (a bare/uv interpreter lacks the app's deps and the service silently fails to start), poll `/healthz` to 200 before declaring it live.

## 2. Cloudflare quick tunnel (no account, no port-forwarding)
- `cloudflared tunnel --no-autoupdate --url http://127.0.0.1:PORT` — no login needed; preflight warnings (QUIC/7844 blocked → "degraded transport, http2") are harmless.
- **The link is VOLATILE:** every tunnel restart mints a NEW `https://<random>.trycloudflare.com` link. So the link must be treated as a value, not a constant: redirect the tunnel log to a file, grep `https://[a-z0-9-]+\.trycloudflare\.com` out of it (link takes ~5-10s to propagate), and write the current link + demo credentials into a link txt that the operator reads BEFORE sending it anywhere (desktop copy + project-root copy). A refresh script runs on every watchdog cycle so the txt never goes stale.
- Verify customer-perspective, not server-perspective: GET the tunnel URL itself (`/` 200 + a healthz through the tunnel). The tunnel stays up as long as the cloudflared process lives; the service dying does NOT kill the tunnel.
- A fixed/permanent link requires a Cloudflare account + named tunnel — state that upgrade path plainly; do not present a quick tunnel as permanent.

## 3. Watchdog (service + tunnel + link refresh, one loop)
Single Python loop, ~60s cadence: (a) ensure service (port check → `Popen` the venv-python server detached with `CREATE_NO_WINDOW`), (b) ensure tunnel (process-name check → `Popen` cloudflared with `-logfile`), (c) refresh the link txt. Launch it detached/minimized so it survives shell exit. Liveness checks on Windows: see the GBK/`tasklist` pitfall in SKILL.md — a probe that crashes kills the whole auto-restart loop.

## 4. Autostart without admin
`schtasks /Create /SC ONLOGON` is admin-only and gets refused in a normal user session. Use the **per-user Startup folder** instead: copy a .bat into `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\` (runs at every login, no elevation). Also drop a .bat on the desktop as the manual "一键恢复" fallback.

## 5. Customer-side readiness
- Prefill the demo customer with a working scene (bound demo market account, a saved EA, at least one run record) so first login shows something — don't point the customer at an empty app.
- The link txt carries: link, demo credentials, and the navigation path (which tab, which panel). It doubles as the support script.
- Fund safety: the remote customer must never reach real funds through the UI — default stays dry-run; the live path only exists behind the three-gate rule in SKILL.md (platform env switch + customer flag + terminal-account match).

## Windows tooling quirks (this host)
- PowerShell applets hang past timeouts — use git-bash-native equivalents: `ipconfig` (via python subprocess for reliable capture), `netstat -ano`, `tasklist`, `wmic process where "name='python.exe'" get processid,commandline /format:list`.
- `wmic /format:list` puts pid and commandline on separate lines — parse with `re.split(r'ProcessId=(\d+)', text)`, never line-grep.
- GBK console output + MSYS mangled UTF-8 bodies: for any CJK payload use python `json`/`urllib`, never `curl -d` from git-bash.
