# Cron bot-chat 播报投递断链分诊（"群里没动静"专用）

**适用症状**：群/频道长期没收到自动播报，但底层内容引擎还在正常跑（30min 全链、看板、回测都在出新数据）。这是**投递层断链**，不是内容层没跑——先分清这两层，别去重跑内容。

## 第一步：先读投递错误，不猜
读目标 cron job 的 `last_delivery_error`（在 jobs.json 里）。两种错误、两种根因、两种处置，**别混**：

| last_delivery_error / 回执 reason | 根因 | 层 | 处置 |
|---|---|---|---|
| `unknown platform 'bot-chat'` | 实际跑 tick 的那套 runtime 的调度器**不支持 bot-chat 投递**（bot-chat 投递模块在源码/dev 树里有，但跑 tick 的 production runtime 的 site-packages 里没有） | 结构/能力缺口 | **别擅动 production runtime**（最小影响边界），登记根修 + 用 host 代主持补播兜底，等用户点头 |
| `delivery to profile 'X' failed` / `timed out` | 目标 profile 的 gateway 死了，bot-chat spawn 连不到活会话 | 运行态 | **安全操作：拉活该 profile gateway**，可主动做 |
| 回执 `{"reason":"target_busy"}` / stderr `hermes-refusal-reason: SESSION_NOT_OWNED` / "already has a live owner" | 目标 profile 的**那个 named 会话（"Bot Chat"）正被活体持有**：一个卡住/超时的 `hermes_cli.main chat` 进程攥着会话锁不放手，或一批 job 全 resume 同一个**已膨胀的胖会话**（几十 k token），每个回合 60~170s、锁串行 → 并发的其余播报全排队 → 排到超时就拒 target_busy → delivered=0。与 gateway 死活、429、防刷屏都无关 | 会话锁 | 见下面「第三类根因」小节：先只读定位活体持有者，隔离残留 live.json，清掉卡死的 chat 进程（**非 gateway、非交易、且最好是本进程刚 spawn 出的僵尸**才清；活的/用户正持有的不碰），结构根治=会话轮换（见末节，未验先做前先核） |

## 第二步：判活 gateway（bot-chat 投递的前提）
bot-chat 投递要 spawn 子进程把消息送进目标 profile 的会话，前提是那个 profile 的 gateway 活着。判活信号 = `profiles/<p>/runtime/active_sessions.json` 的 mtime：
- 几分钟内刷新 = 活
- 几小时前停 = 该 profile gateway 死了 → bot-chat 投递必失败
- 桌面各 profile 的 active_sessions.json 可以很旧（各自独立刷新），别拿一个 profile 的旧时间戳判定全局。

## 坑
- **两套 runtime 会漂移**：tick 任务（如 JinCeHermesCronTick）指向某个具体 hermes.exe。先查它到底跑哪套、那套支不支持 bot-chat，别拿你手边在看的 dev 源码树下结论——dev 有模块 ≠ 跑的 runtime 有模块。
- **`unknown platform` 时别急着把 tick 切到 dev runtime**：dev 树自己的 cron 依赖（如 hermes_yaml）可能也 import 不过，切了可能两头都断。结构性切换属运维域，走最小影响 + 用户点头。
- **补播兜底**：链接断着期间，host（主 bot）可以直接代目标岗（如 @chief）把漏掉的一班播报发到群，让群立刻有声音，再把根修登记进 task_ledger。别让它静默空转。

## 第二层根因：目标 profile 的 gateway 反复自退（startup 被跨平台凭证毒化）
「delivery to profile X failed / gateway 死」时，拉活前先判它为什么起不来。一个 per-profile gateway 可能被**继承来的跨平台凭证**拖死：
HERMES 级 `.env` 有某平台变量对（如 `WEIXIN_ACCOUNT_ID`），但该 profile 被剥离了对应 token → gateway 启动自动连该平台 → 报「<platform> startup failed: <TOKEN> is required」→ **non-retryable 启动冲突 → 整个 gateway 干净退出**（`gateway_state.json: startup_failed, exit_reason: <platform>: ... is required, platforms.<p>.state=fatal`）。
诊断签名（看该 profile `logs/gateway.log` 尾部）：
`Gateway hit a non-retryable startup conflict: <platform>: ...` 紧跟 `Gateway exiting cleanly`。
**修复（最小影响，不碰 HERMES 级 .env / 不碰 root）**：给**该 profile 的 config.yaml** 加 `platforms.<平台>.enabled: false`（该 profile 顶层块照 matrix/telegram 格式）。机制：config_env.py 里「用户显式禁用的平台永不因 env 凭证复活」，显式 disabled 压过继承的 env。改完备份 config，再拉活。

## 第三类根因：`target_busy` / 会话锁——**别再去拉活 gateway，方向就错了**
`target_busy` 时 gateway 往往是**好的**（active_sessions.json 活着、log 无 poll error）。真因是**会话锁被活体攥着**：
1. **先只读定位持有者，别乱拉活 gateway**：`agent.log` 搜 `Refused active session <sid>: already held by pid=<N>` → 那个 pid 就是活体锁持有者；`API call #N: in=<tokens>` 看会话多大（`in=86037` = 胖会话，每回合 60~170s）；`turn ended reason=text_response` = 其实有过一条出结果（群没全死，是"迟到挤着出"）。
2. **残留 live.json 意图锁**：`Temp\hermes-dm\*.txt.live.json`（`*.live.json` 持久）的 `owner.session_id` 是几十小时前的旧会话 → 是 stale 残留，可**隔离**（rename `.bak`，别删）。**但删 stale live.json 常常没用**——若 `target_busy` 仍在，说明锁是**活进程**持有（下面），文件残留只是表象。
3. **清掉卡死的 chat 进程（最小影响、守住被叫停过 taskkill 的边界）**：`Get-CimInstance Win32_Process` 找 `Name -match python` 且 `CommandLine -match 'hermes_cli\.main chat'` 且**存活 >120s 的**才清（卡住=僵尸锁持有者）；**非 gateway、非交易、最好是本进程这轮刚 spawn 出的探针才清**，活的/用户正持有的 chat 不碰。
4. **结构根治 = 会话轮换**（本条未独立验通，先做前先核）：一批 job 全 `deliver=bot-chat:<p>` 且全 resume **同一个 named 会话**，该会话会越滚越大（几十 k token）→ 每回合重喂全量历史、锁串行。治法=让高频哨兵 job 开**新会话**而非 resume 那个胖会话，或定期 compact/rotate 该会话。不碰交易实盘、不碰 gateway。

## 坑（本类专属，血泪）
- **别在拥堵的投递路上反复手动 spawn 探针**：每条探针都去 resume 同一个胖会话、各占 60~170s 锁 → 你亲手给队列加塞，越杀一个冒一个（本会话就 436→4652→31268→35972 一串）。**诊断用只读**（agent.log / executions.db / 进程清单），**停止 spawn**，让下一班 cron 自然跑，再用 executions 表实读 `delivered` 数验收。
- **`status=completed` + `error=None` + `delivery_outcome=failed` 的读法**：任务体脚本**跑成功了**（completed、无 error），断的是**最后一步投递**（被拒 target_busy / unknown platform / 超时），不是 gateway 死、不是任务崩、不是 429。先读 `delivery_outcome` 的 reason 分流，别往任务/gateway 方向瞎猜。
- 判断"该清哪个 chat 进程"的**唯一安全依据 = 存活时长 + 是不是自己刚 spawn 的探针**；拿不准就**只读不杀**，把清进程作为"需用户点头的破坏性动作"上报（SKILL.md 铁律：破坏性动作先经用户点头）。

## 拉活姿势（Windows 本机）
- `hermes gateway run/restart` 的 CLI 直接 spawn 是**子进程，随你的 terminal 返回而退**；要持久得走 **detached**：profile 级启动器 `profiles/<p>/gateway-service/Hermes_Gateway_<p>.vbs`（内部设 `HERMES_GATEWAY_DETACHED=1` + 独立 spawn），或 Windows 登录项。
- 拉活前先看该 vbs 用的解释器 + `HERMES_HOME` 是否指到**该 profile home**、且那套 runtime 能 import 到 config（否则改了 config 也没读进去）。
- **解释器漂移会让 config 改动静默失效**：改了 `platforms.<p>.enabled:false` 却仍死在同一平台 → 十有八九是该 vbs 指向了**旧 runtime / 旧解释器**（如 uv-cpython 配 C: site-packages），那套代码根本没你改的 config 特性。症状="config 明明改了、拉活还是原样死"。修法：把 vbs 的解释器 + `HERMES_HOME` 对齐到**有该 config 代码的那套 runtime**（本机金策 = E 盘 `hermes-agent/venv/Scripts/pythonw.exe` + root `HERMES_HOME`，不是 uv-cpython 也不是 C: site-packages）。拉活前 `grep` 该 vbs 的 pythonw 路径确认指向，别假设它指对。
- **拉 gateway 不烧 LLM key**：gateway 存活与 429 额度墙无关，别把「429 额度烧光」误判成 gateway 死因；gateway 死因看 `gateway.log` 的启动冲突行。

## 收口口径
修好 = ① 目标 profile active_sessions.json 刷新到当前 ② 该 profile gateway.log 尾部有新"Press Ctrl+C/running"标志 ③ 手动触发一次该 cron 的 bot-chat 投递、回执 unverified 但进队列（非 unknown platform/非 failed）。再口头复核。

## 旧账回放（stale failure-alert replay）：收到"某 cron 连挂 N 次"先别当新故障
一条「⚠️ Cron X failed… This job has failed N runs in a row」通知 **可能只是投递队列在逐条回放一批旧失败**，不是此刻真挂：通知正文里的 "failed N in a row" 是**排队时快照的历史计数**（队列排得越久 N 越大：3→4→5→6 递增），不代表 jobs.json 的实时 `failure_streak`。本会话踩过：同一 job 连递 4 条 failed 报警，实时全绿。
**先验地面真相再决定动不动**（三读，快查即可）：
1. 读 `cron/jobs.json` 该 job 的 **实时** `last_status` / `failure_streak` / `last_run_at`——`streak=0` + `last_status=ok` + last_run 近期 = 此刻健康。
2. 看该 job 输出目录（`cron/output/<jobid>/*.md`，`ls -t`）里**声称失败时刻之后**有没有**新的** error 文件 + `**Status:** error`；连续 `silent (empty output)` = 在正常跑。
3. 若两者全绿却还反复收到该报警 = 投递队列积压的回放。去 `cron/bot_chat_pending/` 数该 job 的待投递文件（`grep -l <jobid>`）；旧账（status=settled/ambiguous）可**可逆归档**到带时间戳目录止住刷屏（别删，`transferred`/在途文件留待机制自己收尾）。
铁律：**streak=0 且无新 error 文件的 failed 通知 = 旧回放，不 pause 不重跑不重复处理**；真故障用「新 error 文件 + streak≥1」双证据报一次。反例：盲目 `hermes cron pause` 会把健康的每 5min 行情喂断掉。