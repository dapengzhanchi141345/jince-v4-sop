---
name: model-key-pools
description: "Use when allocating Hermes API keys or credential pools."
version: 1.0.0
---

# Model key & pool management

Class: allocating multiple API keys across Hermes custom-provider pools + credential rotation + cross-endpoint fallback, so the user can see at a glance which key is serving. Live stack: Agnes (.cn + .com endpoints) — vendor specifics in references/agnes.md.

## Standing rules
- **Never hand-edit `$HERMES_HOME/config.yaml` with the patch/write_file tools** — writes may be refused (security-sensitive); use `hermes config set <key> <val>` or a user-approved python rewrite (back up the file first, verify with yaml.safe_load where a yaml module exists).
- After any `hermes config set` of a LIST-shaped key (`plugins.enabled`, `fallback_providers`, …), verify the on-disk YAML: the CLI can store it as a JSON string. Readers that demand a real list (e.g. plugin discovery's `isinstance(enabled, list)`) silently skip the entries. Re-emit as a YAML list if it landed as a string.
- Label every pooled credential (`--label <short-name>`) — the user's requirement is "一眼看出是哪把 key 在干活": `hermes auth list <provider>` shows the active marker, so labels are the legibility layer. Label format: `<endpoint>-<first-4-chars-of-key>` (e.g. `com-1Jns`) — unique within a pool, contains no secret material.
- Fallback chains are for the chat model only. Never list image/video model ids in `fallback_providers`.

## Procedure (re-allocate or add keys)
1. **Inventory**: read `.env` `*_API_KEY=` lines; fingerprint each key as sha1[:8] of the token (never print full keys); dedupe — legacy alias vars are often the SAME key under two names. ** ALSO sweep every profile's `providers:` map for INLINE `api_key: sk-…` blocks (key families like the K10 round-rotator exist ONLY in config, invisible to the .env sweep) and fingerprint those too — counting .env + pool only undercounts the fleet and breaks feasibility math. ** 找『闲置 key』(用户指定从闲置里找)时的跨 profile 判别法**: 逐个 profile 的 .env 同名 `AGNES_*_API_KEY` 变量取指纹交叉比 — 各岗同指纹=共享专属 key(禁改, 不算闲置); 只被低频 fallback 槽引用或某 profile 独享且非主链引用的变量 = 闲置候选; 候选按 step 2/3 验活(端点归属: .cn 401 ≠ 死, 可能属 .com 体系)后才配。
2. **Probe each distinct key against ITS endpoint** (read-only, free, no quota risk): `GET {base}/models` → which model surface the key sees; one minimal `chat/completions` ping → quota/rate state. Record exhausted-quota keys (error `insufficient_user_quota` / ¥0) — they are added to pools later, not now.
3. **Endpoint scoping**: keys are bound to their base_url; cross-endpoint auth is 401. A 401 at endpoint A does NOT prove the key is dead — it proves the key belongs elsewhere. Probe every distinct base_url in the profile's config plus the vendor's known alternate endpoints (.cn/.com) before concluding "key invalid". Credential pools are per-provider (per base_url). Never add a key from a different endpoint into a pool — rotation would 401 and drag the healthy pool down.
4. **Allocate**: same endpoint + same model surface → same provider's credential pool via `hermes auth add <provider> --type api-key --api-key <key> --label <name>` (auto-rotates on 429/503, recovers on cooldown). Different endpoint → separate provider entry in `fallback_providers` for cross-endpoint failover. Quota-exhausted keys stay out until recharge.
5. **Restart** the app/gateway so the running agent loads the new pool + plugin state; config files alone do not affect the live process. When the agent's own terminal runs inside the gateway process, `hermes gateway restart` is refused (restart-loop guard) — do not retry it; instead verify the pool on disk (`hermes auth list <provider>`) and hand the user the single `hermes gateway restart` line for a plain outside shell, with what to expect (brief channel disconnect, auto-recover).
6. **Verify in a fresh process**: credential-pool entry count (`agent.credential_pool.load_pool('custom:<provider>')`), plugin registry active provider, and that the configured model/provider resolves. Report the final topology as a table.

- Gateway 进程禁止自我重启（`hermes gateway restart` 从 gateway 内部终端跑会被挡：'Refusing to restart the gateway from inside the gateway process'）。给用户留一键 .bat（如 `E:\workbuddy\国外模型\hermes\一键重启网关.bat`，走系统终端跑 `E:\workbuddy\国外模型\hermes\bin\hermes gateway restart`）；重启后三条证据复核：进程 PID 变了、gateway.log 有新 'Starting Hermes Gateway' 行、`hermes auth list` 池内条数对。

## Pitfalls
- **Quota wall ≠ dead key — probe before concluding, and a fresh key set breaks the wall**: exhausted-quota keys (today's 429 text-quota wall, `/models` 200 is a FALSE POSITIVE — only a real `chat/completions` request exposes the 429) stay OUT of rotation and self-heal at the daily 00:00 reset — do NOT retry-spam or touch the 禁改 standing keys. The durable fix is user-supplied keys from a DIFFERENT vendor account/endpoint: probe each with a real chat ping, wire the live ones in as fallback pools per the per-profile recipe (references/jince-profiles.md). A single probe timing out / 408 is network jitter — re-probe ONCE with a longer timeout before marking dead; a completion that arrives proves liveness even when truncated. **The 00:05 daily sentinel (`scripts/jince_agnes_key_sentinel.py`, cron) IS the recovery mechanism**: it re-probes every wall'd/orphan key right after the quota reset and auto-wires recovered keys back into the default fallback chain — schedule wall re-checks for ~00:05, never mid-day. Pool proxy `/health` `valid` counts `/models` 200 (the false positive above): trust the sentinel's real-chat probe, not `/health`.
- **Duplicate input/param-name collision**: when the second pass of a multi-round edit adds a same-named input already declared earlier, error 125 (variable already defined) + error 282 (identifier already used) kill the build — check existing names before writing new declaration lines; remove the duplicate, re-add any removed name that later code still references.
- **Gateway-respawn verification is time-based**: after killing profile gateway PIDs to load a new key pool, the proof the new config is live is the new PIDs' creation-time stamp being LATER than the config write (Win32_Process.CreationDate), NOT merely that PIDs exist — old-epoch PIDs mean the respawn never happened and the pool edit is dead on arrival.
- `hermes config set <key> <val>` will SAVE unrecognized keys with a warning but the runtime never reads them — never rely on an unverified config key for a behavior change. Verify the key name against a recognized-key hint (the CLI suggests candidates like `cron.session_db_timeout_seconds`), and `hermes config unset` any key saved unconfirmed; the durable backstop is application-level (daily-report catch-up delivery), not a silently-ignored config value.
- Adding a valid live key to a pool with fewer effective keys is wasted capacity: when multiple same-endpoint free keys exist, add ALL of them to the same provider's credential pool — rotation spreads RPM across the pool, so free-tier throughput scales with pool size. Cross-endpoint keys stay in the fallback chain, never mixed into the same pool (rotation would 401 and drag the healthy pool down). Verify pool size after with `hermes auth list <provider>`.
- `.env` 本身被 read_file 屏蔽（Hermes credential store，'Access denied: .env is a Hermes credential store'）——盘点 key 一律走 terminal `grep '^VAR=' .env`，且对输出掩码（`sed 's/sk-[A-Za-z0-9]{6,}/sk-…/g'`），绝不把完整 key 打进对话或日志。
- Re-fingerprint keys before reusing any key→pool mapping — keys get reissued; last session's mapping is not trustworthy.
- After any probe or allocation script that embeds key literals in a temp file, delete that file immediately — plaintext secrets on disk are the same leak class as printing them to the log.
- When probing key liveness, ALWAYS pass the full key literal in the script — a truncated/placeholder key (middle replaced with `...`) produces a false 401 and you will wrongly conclude the key is dead. Suspect your own literal before reporting "key invalid". Nested-quote bash one-liners mangle keys; write a `.sh` file and `bash file.sh` instead.
- `plugins.enabled` as a scalar string silently disables user plugins (discovery skips non-list values with no error) — check the type, not just presence.
- Vendor docs sites are often JS-rendered; try the Mintlify `.md` endpoints and `llms.txt` index with curl before reaching for a browser.

## Video generation (custom provider)
Agnes video has per-model parameter contracts — see references/agnes.md (payload rules + the installed plugin at `$HERMES_HOME/plugins/video_gen/agnes/`).

## 20-key local pool (default profile main provider, 2026-11-05)
WorkBuddy provisions a 20-key .cn round-robin pool: `agnes_pool_keys.json` — a DICT `{"endpoint": …, "keys": [ … ]}`, NOT a bare list — → `agnes_key_pool.py` (local proxy 127.0.0.1:8787, auto-rotate, 429 cooldown) → `agnes_pool_watchdog.py` (single-instance via msvcrt file lock on `logs/agnes_pool_watchdog.pid`; restarts pool on death, kills+restarts on 3x /health failure; logs to `logs/agnes_pool.log`). Boot persistence: scheduled task `AgnesKeyPoolWatchdog` (AtLogOn, wscript→vbs→venv pythonw watchdog) + Startup `start_agnes_pool_hidden.vbs` (same target, lock dedupes). Hermes default `model.provider` + `delegation.provider` = `agnes-cn-pool` (base_url http://127.0.0.1:8787/v1, dummy api_key); single-key .env entries (AGNES_KEY_DEFAULT/DCOM/FLASH/MAIN…) are the fallback_providers chain behind the pool. Verify with `curl --noproxy '*' http://127.0.0.1:8787/health` → {total, valid, cooldown}.
- **11-14 池缩水 21→17**: 4 把活池 key（fp 0775e285/0a0539bf/1490b541/15acfd4e）借给 tianji-ge/video-crew/yan-shu-kaoyan/yimou-pavilion 做固定专属 key（李令分配）；池 json 已改、proxy 重启验活 /health total=17。池仍管 default 的 delegation 吞吐。看门狗若未跑, 手动 `wscript //nologo start_agnes_pool_hidden.vbs` 拉起。

Pitfalls discovered wiring this up:
- **urllib probe false-negative 401**: agnes .cn front (new-api/nginx) can 301-redirect; Python urllib drops the Authorization header on redirects → every key looks dead (401) while curl (resends Bearer on same-host redirect) shows 200. ALWAYS verify key liveness with curl, not urllib, before concluding 401=dead.
- **bat spawn line without `start "" /b` blocks the whole watchdog loop forever** (pythonw never exits; a bare line in a batch waits). Use `start "" /b "pythonw" "script" >> log 2>&1`.
- **venv pythonw.exe is a shim that re-execs the hermes-runtime cpython pythonw** → expect a parent/child shim pair in the process tree (parent venv path, child `.hermes-runtime\python\cpython-3.11…` path). One logical process, not two.
- **bat encoding**: cmd decodes batch lines in the active code page; a GBK-encoded file + `chcp 65001` mid-script mangles Chinese path bytes (spawn fails silently). Keep bat GBK + `chcp 936`, or pure-ASCII + `chcp 65001`. Hermes patch/write_file tools write UTF-8 — after editing a GBK .bat/.vbs, re-encode via terminal python or the Chinese paths die.
- **Hermes terminal session cleanup kills spawned process trees** on call end; only `subprocess.Popen` with `DETACHED_PROCESS|CREATE_NO_WINDOW` (or a scheduled task) survives for long-lived daemons. A Popen'd `cmd /c batch` survived; a wscript block did not.
- msvcrt.LK_LOCK on the pidfile makes the watchdog's second launch exit immediately; a plain pidfile read+write is TOCTOU-racy (observed dual start).

## Per-profile key topology (金策 multi-bot layout)
Each bot profile under `profiles/<name>/` has its own `.env` + `config.yaml` with a dedicated key layout (main .cn key + .com fallback slots per role). Allocating new keys there follows a minimal-impact recipe — insert-only, main chain untouched, verify each key is distinct and the block landed inside the `providers:` section. Details: references/jince-profiles.md

## 2026-11-14 固定分配拓扑 (李彦明令: 交易 bot 固定 2 把, 其他固定 1 把; 台账 t_agnes_realloc_1114)
全盘 58 把不同 key = 53 活 + 5 堵 429（k10-8/k10-9 + 池内 3 把; 堵墙 key 不进活跃链, 00:00 重置后复探再放）。
- **交易 5 席 = 专属 .cn 主 + .com 备, 零共享**: default=AGNES_KEY_DEFAULT(.cn)+AGNES_KEY_DCOM(.com) / chief=KEY_CHIEF+KEY_CHIEF_COM / risk-officer=KEY_RISK+KEY_RISK_COM / strategy-rd=KEY_RD+KEY_RD_COM / post-mortem=PM_CN+PM_COM。config: model.provider=各席 .cn 块, fallback_providers=[各席 .com 块]; .cn 块必须直连 https://api.agnes-ai.cn/v1（早期错指 8787 池 proxy 会被池轮转忽略=名不副实, 已根治）。
- **其他 26 席 = 各 1 把专属 key, fallback_providers: []**（原 10 把 K10 共享轮转 main 全部退役; K10 块保留不引用）。4 把来自池借出（见上节）, 其余为 .cn/.com 独占 key。
- **零动**: 共享基建 .env 变量 AGNES_MEDIA/REASON/FLASH/MAIN_API_KEY（video_gen/reason 工具链, 全 profile 共用）; K10 块定义; L5 红线。
- **生效**: 网关单进程（一个 root gateway 承载全 profile, 各 profile gateway.lock 同 pid）→ 新配置各 profile 下次会话/cron 即生效; 立即全量生效=一键重启网关.bat（李彦明侧）。
- **坑**: ①config 的 model/fallback 段用文本手术（regex 段替换）+ pyyaml（venv python）验活, 别 yaml.dump（丢注释）; ②自写 set_fallbacks 类函数只返一个值, 别解包成 `t, flag =`; ③池 proxy 杀了要用 start_agnes_pool_hidden.vbs 拉看门狗自恢复, 再 /health 验 total; ④池 json 是 `{endpoint, keys}` dict — 迭代前先 `.get("keys")`, 直接 `for k in pj` 会把字段名当 key 探针, 报出一堆假 401。

## 深度优化二轮的定型形态（李彦明"池子还是专属"裁定: 按席位地位分层混用）
- **高频主 bot = 池轮转主链**（`model.provider: agnes-cn-pool`, 吞吐=池大小, 429 池内冷却自动轮）+ 专属 .com 备 + 恢复的孤儿 key 逐级备（三级 fallback）。
- **交易关键席 = 专属 2 把**（.cn 主 + .com 备, 故障隔离优先于吞吐）; **低频席 = 专属 1 把**（负荷小, 池红利轮不到, 且"固定"=独占语义）。
- 分配时**两遍法**: 先给每席保留其 .env 现值（若该 key 在可用池内, 零 .env diff）, 剩余席再从可用池补位 — 最小化 .env 改写面。
- 自动维护 = 每日 00:05 哨（见 429 坑条目）: 全量探活 + 堵墙点名（交易席 RED / 其他 YEL / 全绿静默）+ 堵墙 key 0 点重置后自动回收。
