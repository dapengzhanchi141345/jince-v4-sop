---
name: hermes-agent
description: "Use, configure, theme, extend, and orchestrate Hermes Agent."
version: 3.2.0
author: Hermes Agent + Teknium
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, setup, configuration, multi-agent, spawning, cli, gateway, bots, bot-mode, features, themes, skins, desktop-plugins, tui-widgets, petdex, development]
    homepage: https://github.com/NousResearch/hermes-agent
    related_skills: [claude-code, codex, opencode]
---

# Hermes Agent

Hermes Agent is an open-source AI agent framework by Nous Research that runs in your terminal, a native desktop app, messaging platforms, and IDEs. It's in the same category as Claude Code (Anthropic), Codex (OpenAI), and OpenClaw — autonomous coding and task-execution agents that use tool calling to interact with your system. Hermes works with any LLM provider (OpenRouter, Anthropic, OpenAI, Google, DeepSeek, xAI, local models, and 20+ others) and runs on Linux, macOS, Windows, and WSL.

What makes Hermes different:

- **Self-improving through skills** — Hermes learns from experience by saving reusable procedures as skills that load into future sessions.
- **Persistent memory across sessions** — remembers who you are, your preferences, environment details, and lessons learned. Pluggable memory backends.
- **Multi-platform gateway** — the same agent runs on Telegram, Discord, Slack, WhatsApp, iMessage, Signal, Matrix, Teams, Email, and a dozen more platforms with full tool access, not just chat.
- **Many surfaces** — the same agent core drives the CLI, the Ink TUI, a native Electron desktop app, a web dashboard, and an ACP server for IDEs (VS Code / Zed / JetBrains).
- **Provider-agnostic** — swap models and providers mid-workflow; credential pools rotate across multiple API keys automatically.
- **Profiles** — run multiple independent Hermes instances with isolated configs, sessions, skills, and memory.
- **Extensible & themeable** — plugins, MCP servers, custom tools, webhook triggers, cron scheduling, skins that theme every surface, desktop UI plugins, TUI widgets, and pet mascots.

**This skill is a hub.** The body covers identity, quick start, spawning/orchestration, and hard invariants. Everything else lives in reference files — **load the matching reference (below) before answering**; do not answer detail questions from the body alone.

**Docs:** https://hermes-agent.nousresearch.com/docs/

## Scope & Verification

This skill is a concise operating guide, not the complete source of truth for every Hermes feature. If a Hermes feature, command, or setting is not mentioned here or in a reference, do not treat that absence as evidence that it does not exist. Check the live repository and official docs before giving a negative answer.

Good verification targets, cheapest first:

- **Every shipped feature, one line each: https://hermes-agent.nousresearch.com/docs/llms.txt.** Start here for any "can Hermes do X?" or "how do I do X?" — it indexes the entire documentation set with a link to the page that answers. It is generated from the docs tree on every build, so it is never behind the product. Fetch it with `web_extract`, or `curl -s https://hermes-agent.nousresearch.com/docs/llms.txt` when web tools are off. The whole documentation set in one file is at `/docs/llms-full.txt`.
- CLI commands: `hermes --help`, `hermes <command> --help`, and `hermes_cli/main.py`
- Source tree: https://github.com/NousResearch/hermes-agent

Never answer "Hermes can't do that" from memory. Hermes ships far more than this skill body describes, and the index exists so a negative answer is always checkable.

## Quick Start

```bash
# Install (shell installer — bootstraps PM, Python, dependencies, and the launcher)
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

# Interactive chat (default surface; set display.interface: tui to launch the Ink TUI instead)
hermes

# Single query
hermes chat -q "What is the capital of France?"

# Setup wizard  /  pick model+provider  /  health check
hermes setup
hermes model
hermes doctor

# Other surfaces
hermes desktop                 # launch the native desktop app (alias: hermes gui)
hermes dashboard               # web admin panel + embedded chat
hermes proxy                   # OpenAI-compatible local proxy backed by your OAuth provider
```

## Key Paths

```
~/.hermes/config.yaml       Main configuration (settings — never secrets)
~/.hermes/.env              API keys and secrets ONLY (under $HERMES_HOME if set)
$HERMES_HOME/skills/        Installed skills
~/.hermes/skins/            Custom themes (see references/themes.md)
~/.hermes/desktop-plugins/  Desktop app UI plugins (see references/desktop-plugins.md)
~/.hermes/tui-widgets/      TUI widget apps (see references/tui-widgets.md)
~/.hermes/pets/             Installed pet mascots (see references/petdex.md)
~/.hermes/state.db          Canonical session store (SQLite + FTS5)
~/.hermes/sessions/         Gateway routing index, request dumps, *.jsonl transcripts
~/.hermes/logs/             Gateway and error logs
~/.hermes/auth.json         OAuth tokens and credential pools
~/.hermes/hermes-agent/     Source code (if git-installed)
```

Profiles use `~/.hermes/profiles/<name>/` with the same layout. When a profile is active, resolve the real home from `$HERMES_HOME` — never hardcode `~/.hermes`.

## Routing Table — load the reference for the task

| User wants... | Load |
|---|---|
| **Anything not listed below — "can Hermes do X?", "how do I set up X?"** | **https://hermes-agent.nousresearch.com/docs/llms.txt** |
| Bots that chat, run routines, or message each other; the Bots tab | docs: `/user-guide/bot-mode` |
| Bot Mode group chat rooms (hosted_rooms): user sees "two groups"/duplicate names, renaming a room, who is a member, cron delivery target into a room | `references/bot-chat-groups.md` |
| 新建一个多智能体 bot profile（金策加岗式：骨架复制+洗残留+配key+群注册+重启） | `references/new-profile-bot.md` |
| CLI commands, subcommands, flags, "how do I run X" | `references/cli-reference.md` |
| In-session slash commands | `references/slash-commands.md` |
| Provider setup, API keys, OAuth | `references/providers-and-models.md` |
| config.yaml sections, toolsets, voice/STT/TTS | `references/configuration.md` |
| AGENTS.md / .hermes.md / CLAUDE.md project rules | `references/project-context-files.md` |
| Secret redaction, PII, approval modes, "reset permissions" | `references/security-privacy.md` |
| Delegation, cron, curator, kanban | `references/background-systems.md` |
| MCP servers (add, catalog, `hermes mcp`) | `references/native-mcp.md` |
| Webhook routes and event-driven runs | `references/webhooks.md` |
| A custom theme/skin ("synthwave theme", "change the gold ●") | `references/themes.md` + `templates/skin.yaml` |
| A desktop app UI element (pane, widget, ⌘K command, page) | `references/desktop-plugins.md` + `templates/plugin.js` |
| A live TUI panel or modal widget (ticker, clock, dashboard) | `references/tui-widgets.md` + `templates/clock.mjs` |
| Pet mascots — install, select, scale, diagnose | `references/petdex.md` |
| Windows-specific issues (keybinds, WinError 10106, BOM) | `references/windows-quirks.md` |
| Debugging: voice, tools missing, gateway, aux models | `references/troubleshooting.md` |
| Contributing code: adding tools, slash commands, tests | `references/contributor-guide.md` |
| delegate_task "capped at N" reports | `references/delegate-task-concurrency-diagnosis.md` |
| "Can app X use my Nous Portal subscription/OAuth?" | `references/portal-auth-for-third-party-apps.md` |
| Connecting a messaging platform (Telegram, Discord, Slack, WhatsApp, …) | docs: `/user-guide/messaging` |

The reference list above is not the feature list — it is the set of topics that
need more than their docs page. For everything else Hermes ships, fetch
`llms.txt` and it maps the question to the page that answers it.

Two theming rules that hold even without loading the reference: **you apply skins yourself** (`hermes config set display.skin <name>` — every surface repaints live within ~a second; don't tell the user to run `/skin`), and **to tweak one color, edit the ACTIVE skin** (`hermes skin set <key> <hex>`) — never fork `default`, which drops the palette and resets the background.

## Spawning Additional Hermes Instances

Run additional Hermes processes as fully independent subprocesses — separate sessions, tools, and environments.

### When to Use This vs delegate_task

| | `delegate_task` | Spawning `hermes` process |
|-|-----------------|--------------------------|
| Isolation | Separate conversation, shared process | Fully independent process |
| Duration | Minutes (bounded by parent loop) | Hours/days |
| Tool access | Subset of parent's tools | Full tool access |
| Interactive | No | Yes (PTY mode) |
| Use case | Quick parallel subtasks | Long autonomous missions |

### One-Shot Mode

```
terminal(command="hermes chat -q 'Research GRPO papers and write summary to ~/research/grpo.md'", timeout=300)

# Background for long tasks:
terminal(command="hermes chat -q 'Set up CI/CD for ~/myapp'", background=true)
```

### Interactive PTY Mode (via tmux)

Hermes uses prompt_toolkit, which requires a real terminal. Use tmux for interactive spawning:

```
# Start
terminal(command="tmux new-session -d -s agent1 -x 120 -y 40 'hermes'", timeout=10)

# Wait for startup, then send a message
terminal(command="sleep 8 && tmux send-keys -t agent1 'Build a FastAPI auth service' Enter", timeout=15)

# Read output
terminal(command="sleep 20 && tmux capture-pane -t agent1 -p", timeout=5)

# Send follow-up
terminal(command="tmux send-keys -t agent1 'Add rate limiting middleware' Enter", timeout=5)

# Exit
terminal(command="tmux send-keys -t agent1 '/exit' Enter && sleep 2 && tmux kill-session -t agent1", timeout=10)
```

### Multi-Agent Coordination

```
# Agent A: backend
terminal(command="tmux new-session -d -s backend -x 120 -y 40 'hermes -w'", timeout=10)
terminal(command="sleep 8 && tmux send-keys -t backend 'Build REST API for user management' Enter", timeout=15)

# Agent B: frontend
terminal(command="tmux new-session -d -s frontend -x 120 -y 40 'hermes -w'", timeout=10)
terminal(command="sleep 8 && tmux send-keys -t frontend 'Build React dashboard for user management' Enter", timeout=15)

# Check progress, relay context between them
terminal(command="tmux capture-pane -t backend -p | tail -30", timeout=5)
terminal(command="tmux send-keys -t frontend 'Here is the API schema from the backend agent: ...' Enter", timeout=5)
```

### Session Resume

```
# Resume most recent session
terminal(command="tmux new-session -d -s resumed 'hermes --continue'", timeout=10)

# Resume specific session
terminal(command="tmux new-session -d -s resumed 'hermes --resume 20260225_143052_a1b2c3'", timeout=10)
```

### Tips

- **Prefer `delegate_task` for quick subtasks** — less overhead than spawning a full process
- **Use `-w` (worktree mode)** when spawning agents that edit code — prevents git conflicts
- **Set timeouts** for one-shot mode — complex tasks can take 5-10 minutes
- **Use `hermes chat -q` for fire-and-forget** — no PTY needed
- **Use tmux for interactive sessions** — raw PTY mode has `\r` vs `\n` issues with prompt_toolkit
- **Cron execution history is fragmentary: check BOTH stores.** `hermes cron runs <id>` can report "No cron execution attempts recorded" even when per-run logs exist as `cron/output/<job_id>/*.md` files (headers: `# Cron Job: <name>` + `**Job ID:**`) in the profile's `cron/` dir. Before concluding "never ran" / "job is broken", glob the output dir and check `jobs.json` `last_run_at`/`last_status` for the same job — the three stores disagree (runs table stale/empty while .md logs and jobs.json are fresh). Read the newest .md for the real last-run status (success/timeout/error text).
- **`hermes cron create` 的 schedule 是 positional 参数，不是 flag**：`hermes cron create "30 0 * * *" --name X --script f.py --no-agent --deliver local`（写 `--schedule "30 0 * * *"` 会回顶层 help 拒掉）。配套：复活 paused job = `hermes cron resume <id>`；查状态 = `hermes cron list`（找 `[paused]` 行）。**Hermes CLI 不走 `python -m hermes`（报 No module named hermes）——直接调 `hermes` 命令**。**★【本宿主 CLI 入口实路（11-17 实踩）】**：`python -m hermes_cli` 在 ATE/D:/ 等任意 venv 里都报 No module（hermes_cli 只装在 hermes 自己的 3.14 解释器里）——本机直接用 `E:/workbuddy/国外模型/hermes/hermes-agent/.hermes/bin/hermes.exe`（带 `-p <profile>` 切 profile，如 `-p default cron resume <id>` / `cron run <id>`；长命令超时会被 terminal 工具转后台通知，等回执别重发）。
- **周期 no-agent job 失败一次可能停在 `[paused]` 态数天不自愈**：某班 code1（多为瞬时：网络/token 抖动/依赖没就绪）→ job 转 paused → 整条执行链断，而**同系列的汇报/通报 job 还 active 照常跑**（"汇报活着≠执行活着"）。修：`hermes cron list` 找 `[paused]` 行 → 手动跑一遍其 script 验活（能成=瞬时故障）→ `hermes cron resume <job_id>`；验不过先修脚本再 resume。
- **One-shot quirk (observed 11-06):** a FAILED one-shot job auto-disables itself, and `hermes cron resume` on an expired one-shot fails with `Cannot resume: one-shot time … is in the past (grace window: 120s) and will never fire` — you cannot resume it; `remove` it and re-create with a fresh future time instead.
- **Cron `no_agent` script jobs default to a 3600s (1h) script timeout** (`_DEFAULT_SCRIPT_TIMEOUT` in `cron/scheduler.py`). A long-running script (e.g. a 2.6h backtest) is killed at 1h with 'Script timed out after 3600s' and the job 'fails' every run. Don't raise the global `cron.script_timeout_seconds` / `HERMES_CRON_SCRIPT_TIMEOUT` (it changes the bound for ALL script jobs, incl. fast tick/sentinel monitors that detect hangs by that cap). Instead, for a genuinely long job: have the wrapper fast-exit (~60s) and detach the heavy work into a **system-reparented** process so it survives the cron kill (on Windows: `powershell -NoProfile -Command 'Start-Process ... -PassThru'`; bare `subprocess.Popen(DETACHED|BREAKAWAY)` is NOT reliable — it gets reaped on the MSYS/shell tree teardown, marker never lands).
- **"Job is already being fired by the scheduler; not run again" from `hermes cron run` is not proof the run is healthy — check where the last run actually went.** A scheduled LLM job can fire on time and FAIL (e.g. provider 429) without updating `last_run_at` in jobs.json, and the failure surfaces later only as a cron failure notification ("will run again at its next scheduled time"). To tell whether a due job "skipped" or "failed": ① read `cron/output/<job_id>/` newest `.md` (Run Time + Status: silent/failed/rate-limited) ② check the cron failure message the user/platform surfaces ③ only then trust `last_run_at`/`next_run_at`. If it fired-and-failed, the missed-work compensation is a manual re-run (`hermes cron run`) or, for deterministic ledger/report jobs, doing the step yourself from live data and noting the backfill (e.g. a 20:00 daily ledger entry written by hand the same night, flagged as backfill in its `note` field).
- **`cronjob_manage` update is PARTIAL-apply: only the fields you explicitly pass get changed.** Calling `update` with just `job_id` (and optionally `name`) is a no-op that returns the job JSON as a read-back — passing `name` does NOT update any field. Always pass the target fields (e.g. `deliver: "bot-chat"`) in the same call, then re-read the response and VERIFY the target field actually changed before marking the work done.
- **`deliver: "all"` fails on bot-mode/desktop with `delivery_failed: "no delivery target resolved for deliver=all"`** — the job runs but its output never reaches any chat. Fix by `update`-ing the job to `deliver: "bot-chat"` (injects into the main agent's Bot Chat; what the jince jobs use) or `deliver: "origin"`. Jobs whose `last_status` is `delivery_failed` with this exact error are the tell — the fire itself was fine, only the delivery target was unresolvable.
- **WeChat iLink delivery (`weixin:<account>@im.wechat`) jobs failing `iLink sendmessage session not ready … the user must send the bot a message first (or re-pair)` = reports silently lost until the user re-pairs in WeChat private chat.** The agent cannot initiate iLink re-pairing (user-only action; restarting the gateway does not fix it). Interim fix: `cronjob_manage` update those jobs to `deliver: "bot-chat"` (or `origin`) so reports reach a working surface, and record which job ids were switched so they can be switched back after the user re-pairs iLink. Tell the user the weixin-targeted jobs were dropping every report, not just failing occasionally.
- **no_agent cron script locations are restricted**: the `script` field must be a FILENAME under the profile's `scripts/` dir (absolute or home-relative paths are refused with 'Place scripts in …/scripts/ and use just the filename'). Put a thin wrapper there that spawns the real logic elsewhere; stdout is delivered verbatim, EMPTY stdout sends nothing — that IS the watchdog pattern (threshold-gate the prints; alert only on state change/threshold breach, stay silent otherwise).
- **Long cron prompts: keep the prompt a thin pointer, put the procedure in a file.** Creating an agent-cron job whose `prompt` embeds a long Chinese SOP with Windows paths (single-backslash `E:\...\x`) is a JSON-serialization time-bomb when the call is routed through a tool wrapper (unescaped backslash sequences = `Expecting property name` parse errors at unpredictable offsets, and batched multi-call payloads fail even harder — send one cron call at a time). Write the SOP to a durable `.md` and make the prompt `先读 <path>，按其步骤执行`. Prefer forward-slash paths (`E:/...`) inside prompt text; they survive JSON and Windows alike.
- **Cron wrappers that spawn mt5-python (or any project-venv python) must strip `PYTHONHOME`/`PYTHONPATH` from env first** — the hermes cron runner injects them and they corrupt target venvs (reimport/encodings failures downstream); `env = {k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH')}` in the wrapper.
- **A bloated bot profile's context can block inbound DMs**: `message_agent` delivery to a teammate whose session overflowed its model's context fails with `context_overflow` ('conversation too long… /new or /compress'); the message stays queued ('receipt is retained, do not resend') and cannot be unblocked from outside — `/new`/`/compress` are chat-session commands with no CLI equivalent. Low-impact content: log what the peer missed and move on (their next fresh session or a cron worker session re-syncs it); high-impact: tell the user the teammate needs a session reset in its own chat.
- **"delegate_task is capped at N" reports** — see `references/delegate-task-concurrency-diagnosis.md`. Three real cap paths in Hermes; if none fired, the model is self-limiting and rationalising it as "the runtime caps."
- **"Can $external_app use my Nous Portal subscription / OAuth?"** — see `references/portal-auth-for-third-party-apps.md`. Walk the user through three layers (plugin-vs-app, what Portal actually exposes, local-broker-proxy option).

## Surfaces (quick orientation)

- **Desktop app** (`hermes desktop` / `hermes gui`) — native Electron app for macOS/Linux/Windows: streaming chat, session list, Cmd+K palette, drag-and-drop files, native notifications, per-profile remote-gateway login. Extend it with UI plugins — `references/desktop-plugins.md`.
- **Web dashboard** (`hermes dashboard`) — full admin panel: messaging channels, MCP catalog, webhooks, memory, profile builder, plus an embedded `hermes --tui` chat. Secured behind an OAuth/token gate.
- **Ink TUI** (`hermes --tui` or `display.interface: tui`) — terminal UI with docked widget apps — `references/tui-widgets.md`.
- **OpenAI-compatible proxy** (`hermes proxy`) — a local OpenAI API backed by whichever OAuth provider you're signed into. Point Codex CLI, Aider, Cline, or any script at it — no API key.

## Memory tool batch discipline (memory tool: add/patch/remove with a char budget)
- The budget is checked on the FINAL result of the batch call: one call can simultaneously remove/shorten stale entries AND add new ones — an add that alone would overflow fits when paired with enough removals in the same call. The failure message reports the exact deficit; compute it before retrying, don't guess.
- `old_text` for patch/remove must match the stored entry verbatim; entries containing Windows paths (backslashes) fail to match when the match text is hand-retyped — copy the exact text from the tool's error output (current_entries / closest_entries), and prefer short backslash-free unique substrings over long passages.
- A batch is all-or-nothing: one op's old_text mismatch aborts every op in that call. If the platform reports repeated consolidation failures, stop retrying the memory tool for that turn (keep the memory store unchanged) and carry the fact elsewhere (a class-level skill is the better home for procedures anyway — memory is for compact facts that apply to every session).
- **Cap-full is a state to work around, not a dead end.** When memory/user-profile is near its char cap and adds keep getting rejected: (1) move bulky detail to a durable on-disk archive file and keep in memory only the one-line 铁律 + a pointer to that archive (this user's established archive: `E:/workbuddy/国外模型/hermes/memory_detail_archive.md`); (2) for the user profile (~1375-char cap, frequently at 99%), patch/shorten EXISTING entries in place (batch remove+add atomically) instead of adding new entries — compute the deficit from the rejection message before retrying.

## Hard Invariants (never violate, regardless of what you loaded)

- **Never break prompt caching** — don't change past context, toolsets, or the system prompt mid-conversation. The only exception is context compression.
- **Message role alternation** — never two assistant or two user messages in a row; only `tool` results can repeat.
- **Secrets in `.env`, settings in `config.yaml`** — never tell a user to put a non-credential setting in `.env`.
- **Profile-safe paths** — `get_hermes_home()` in code, `$HERMES_HOME` when resolving paths in a session.
- **Never hand-edit `config.yaml` for the user** — use `hermes config set KEY VAL`; a stray indent can corrupt the file and break the live gateway. The agent's own file-editing tools (patch/write_file) are also refused on the live hermes config by the security layer — `hermes config set` is the single sanctioned write path, and the new value takes effect at the next gateway restart (a running gateway keeps the in-memory config).
