# Leak-token list for touring/client decks

Project the deck → the BODY must be jargon-free. Two leak families, both scrubbed from slide body + tables; the real identifiers may stay in speaker notes only.

## Family 1 — project internals
Internal filenames / module names / cron tokens / env-var names: `chief_pipeline.py`, `veto_log.json`, `meta_evolver`, `AGNES_KEY_*`, `daily_advisory.json` → plain role labels (全链流水线 / 留痕账本 / 元进化引擎 / 专属密钥（风控档）).

## Family 2 — the platform's own brand + CLI syntax (touring decks)
Clients don't care what engine the bot runs on; naming it exposes the stack and repels non-technical readers. Replace each with a plain Chinese role label:

| Body jargon | Replace with (body) | Notes may keep |
|---|---|---|
| `Hermes` / `Hermes 界面` | 系统 / 系统界面 / 后台 | Hermes |
| `hermes chat -q "..."` | 后台对话 / 「一句话只回结果」 | hermes chat |
| `hermes doctor` | 系统体检 | hermes doctor |
| `hermes profile create X` / `--clone` | 后台一键新建一个 bot / 照抄一套改个名 | hermes profile |
| `hermes skin use X` | 后台一键换整套外观，一秒生效 | hermes skin |
| `hermes config set` | 改配置走后台管理台（别手改文件） | hermes config set |
| `hermes setup / model` | 配置向导 / 图形化选脑子 | hermes setup |
| `curl -fsSL https://.../install.sh \| bash` | 一条命令搞定（自动配环境、装本体） | the real install line |
| `hermes --continue / --resume` | 「继续」两字接着聊 / 「回到上周那个」 | flags |
| `OAuth / token` | 身份验证 | OAuth / token |
| `.env` | 密钥箱 | .env |
| `config` (as a file concept) | 设置 | config |
| `/model` | 换脑子（顶部下拉） | /model |
| `/reset` | 新开会话（改完工具才生效） | /reset |
| `TUI / CLI` | 终端 / 命令行 | TUI / CLI |

Rules:
- Apply only when the deck is touring / client-projected. An internal ops manual for the owner may keep the real commands.
- Scrub the source build files, REBUILD the .pptx, then grep the SHIPPED .pptx (not just the source) for `Hermes|hermes` and the install URL — zero hits is the gate.
- When sweeping English tokens, keep the leak-scan on word boundaries: `sk-` inside `risk-sop` is NOT a credential; match credentials as `sk-[A-Za-z0-9]{6,}`. Same for short tokens (`cli`, `os`, `key`) that appear inside ordinary English — anchor to command/flag usage, not raw substring, or the scan chases false positives.
- After the scrub, re-render the changed pages (they sit mid-deck, usually in the how-to back half) and vision-QA that the shorter/longer replacement text didn't overflow a card — a two-word swap can push a dense line over the card edge.
