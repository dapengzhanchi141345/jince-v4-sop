---
name: hermes-gateway-triage
description: "Use when Hermes 消息不通、会话锁或微信通道断，速查 5 步分诊修复。"
---

# Hermes 消息流分诊（本机 Windows）

用户报「不能发消息了」时的分诊类任务。核心判断：多数时候根因是**本地会话锁/通道轮询断掉**，不是网络，更不是模型。

## 永远遵守
- 先定位断在哪一层：桌面会话（当前对话能否收发）、网关、平台通道（微信），逐层切分，别一次全猜。
- `gateway_state.json` 里 platform.state 可能是几天前的僵尸值，**以 `logs/gateway.log` 尾部的 poll error 流为唯一事实源**。
- 破坏性动作（重启网关、杀进程）必须先经用户点头再执行；会话租约是数据库行，安全可清。
- 全程大白话中文汇报（本机约定），术语后跟一句人话。
- 「微信没收到内容/定时汇报一条没来」(全程未发, 非"消息发不出") ≠ 通道断: 先疑 **cron 投递目标**。iLink bot 账号重登后 DM chat_id 会变, 钉死旧 chat_id 的投递目标静默停发, 金策的汇报任务常常 `deliver=bot-chat`、微信端什么都没到。诊断: grep `E:\workbuddy\国外模型\hermes\cron\jobs.json` 里的 weixin chat_id——`origin` 字段只是创建时元数据与路由无关, `deliver`/`failure_deliver` 才是路由字段; 修法 = cronjob_manage update 把各汇报 job 的 deliver+failure_deliver 指到 `weixin:<当前会话的 DM chat_id>`(从当前会话上下文取, 不猜旧值), 改完回读 job 字段验在。别按旧 chat_id 假设"通道没通"去拉网关。另一变体: chat_id 正确但 job `last_delivery_error` 含 `iLink sendmessage session not ready (the user must send the bot a message first)` = **iLink 会话未就绪（非通道断、非配置错）**: 用户给 bot 发一条私聊即 re-pair（机器人不能先开口, 代不了）, 窗口期所有 weixin 投递 job 全 delivery_failed, 用户发消息后下拍自愈; 用户报「没收到」时先读 cron job 的 last_delivery_error 分「没跑」vs「跑了没投到」, 别把已生成未投递的报成「任务没跑」。
- 「群里没动静」先分**层**：内容层（引擎还在出新数据）vs 投递层（bot-chat 没进群）。投递层再分**三类根因别混**：`unknown platform`=runtime 能力缺口；`delivery failed/timeout`=目标 gateway 死；`target_busy`=会话锁被活体/胖会话攥着（gateway 是好的，**别去拉活 gateway**）。先读 `delivery_outcome` 的 reason + `agent.log` 的 `Refused active session ... held by pid`，别凭假设去 kill/spawn。

## 分诊步骤（按序）
1. **确认入口**：桌面 = 当前对话能收能发即通；微信 = 直接查日志，别信 state.json。
2. **查会话锁**：`state.db` 的 `session_turn_leases` 表（列是 `conversation_id, holder, acquired_at, expires_at`，**没有 session_id 列**，先 PRAGMA 再写 SQL）。
   - `SELECT conversation_id, holder FROM session_turn_leases`；holder 形如 `pid=NNNN:turn=...:platform=...`，取出 pid。
   - 判活：Windows 上用 `ctypes.windll.kernel32.OpenProcess(0x400, False, pid)`（0=存活；tasklist 单条查太慢）。
   - **holder pid 已死 + 租约过期 → 删除该行并 commit**（安全）。pid 活着（如桌面 app 已接管旧会话）→ 那是活租约，不删；等 expires_at 自动过期，或让用户在拥有该会话的界面关掉它。
3. **查通道轮询**：`tail logs/gateway.log | grep -i "poll error\|getaddrinfo"`。日志持续报连接错而本机直连测试正常（`python -c` 里 `gethostbyname` + `create_connection(host,443)`）→ 网关内该通道轮询循环断了没自愈（换网后常见）→ 需要重启网关。
4. **重启网关（需用户确认）**：本机有 `E:\workbuddy\国外模型\hermes\一键重启网关.bat`（= `hermes gateway restart` + status）。执行时直接调 bat 里那条命令帮用户做完，微信瞬断约 10 秒，桌面对话不受影响（网关是独立进程）。**安全机制：有在途会话时 stop 会被拒（"N live session(s) would be interrupted"）——这是防自毁设计不是故障；等待 2 分钟会话空闲再重试，或改用 stop→start→status 三步 bat（`一键重启网关` 形态）交给用户在空闲窗口双击。
5. **复核**：`gateway_state.json` 的 pid 变了、日志尾部不再新增 poll error、state.json 的 updated_at 刷新到当前，才算修好；再向用户口头复核。
6. **微信（iLink）通道专项**：用户报「开通微信 / 微信收不到 / 很久没用要重连」时，走 iLink 三步判别（通道轮询→凭证直探→bot 能否先开口）；bot 主动 sendmessage 回 `ret=-2 "prepare failed"` 是 iLink session-not-ready（不是限流），唤醒靠用户先给 bot 发一条消息，终局手段是 QR 重登。详见 `references/ilink-weixin-reconnect.md`。

## 坑（本机实测）
- **桌面"Hermes ended this turn without a reply"(no_reply)卡 ≠ 模型没回**：先查 `agent.log` 对应时刻的 `tui_gateway.ws: ws closed ... reason=client_disconnect(code=1009,reason=frame exceeds limit of 1048576 bytes)`——这是 11-09 实测根因：胖会话（24万+ tokens）状态下，`tui_gateway/owner_forward.py` 与 `tools/bot_live_delivery.py` 的 owner 转发连接用 websockets 默认 1 MiB 帧上限，session.resume 的 state 回放帧超限即 1009 断线→桌面误画 no_reply（原 turn 其实常已跑完、响应已进 local chat，内容没丢）。已于 11-09 给这两处 connect 加 `max_size=None`（仿 `tui_gateway/event_publisher.py` 先例），**下次网关重启生效**；若再犯先确认补丁仍在（升级后可能被覆盖，`grep -n max_size tui_gateway/owner_forward.py`）。同类放大因素：`credential pool: no available entries` + 503 "request queue is full"（池拥塞，turn 拖 25min+）、GIL stall（"event loop stalled Ns"）、网关 unclean exit（lifecycle_ledger 记录 SIGKILL/OOM）。
- **别把「进程刚 spawn / CLI 回 started」当「拉活成功」**：gateway 起来 1-2s 后可能就因启动冲突干净退出。判活 = `gateway_state.json` 刷新到**新 pid** 且 `gateway_state` 非 `startup_failed`/`fatal` 且 `exit_reason` 为 null，三者齐了才算活。拿「process appeared」喊早连着几次会让用户失去信任。
- **`gateway_state.json` 停在旧死 pid ≠ 新 spawn 一定没活**：该文件只在注册/清理事件写盘，一个刚 detached 起来、正 `active_agents:0` 空转的 gateway 可能长期不刷新它。state 文件读旧 pid 时**不能据此判"没拉起来"**，须交叉两个共权威正信号：① 进程层 `<runtime>pythonw -m hermes_cli.main --profile <p> gateway run` 命令行存活 >2min ② 该 profile `logs/gateway.log` 尾部有新启动段且**没有**再报「non-retryable startup conflict」。本轮只信 state 文件，连误 2 次"没起来"。
- **同一 gateway 拉活失败 2 次就停手**：每次盲 spawn 一个"起来即死"的 gateway 只加深用户对反复喊早的不信任（"别让我盯/主动闭环"≠反复乱拉）。第 3 次起改走**只读诊断 + 登记 task_ledger 让 00:00 额度重置/开机自启项自动重试**，别再手拉。churn 本身是用户明令纠正的行为，不是"主动"。
- **网关更新/draining 瞬态中断 agent 型 cron（批量 error 时先分这类）**：一批 job 同时 `last_error=interrupted` 或 `GatewayUnavailableError: Gateway draining: update_paused` = 网关正处更新/重启 drain 窗口，agent 型 job 中途被打断，`no_agent` 脚本型 job 不受影响照常跑。这类**无需任何修复、下拍自愈**（禁 KILL/RESTART 网关，本机铁律）；诊断=cron 群 last_status 扫一遍按「drain/interrupted」vs「逻辑错」分堆，只重跑真正漏拍的动作。连锁危害要单独警惕：自愈型哨（补跑哨/巡检哨）本身若躺在这批红里，前面崩掉的一次性动作会整天无人补=用户看到"停了一天"——全面检修时先手动补跑漏掉的动作，再谈哨群恢复。
- **churn 背后的慢性根因要先查 errors.log 堆叠，别一律当瞬态**：LLM 型 cron 反复失败 + 多个 Hermes 进程 StartTime 相近（分钟级一批）= 网关 churn；查 `gateway-starts.log`（epoch 列表）重启频次 + `logs/errors.log` 尾部异常堆。本机一实锤根因 = `hermes-agent/cron/scheduler_delivery.py` 的 `_home_env_lookup` 在无 profile secret scope 的投递上下文调 `get_secret()` 抛 `UnscopedSecretError`（可堆几十上百条），拖垮 cron 投递链 → 修 = read() 包 try/except 回退 `os.getenv`（与 scope 模块缺失语义一致），**下次 gateway 重启才生效**；hermes 升级后 grep 验补丁仍在（与 max_size=None 补丁同类，会被覆盖）。
- **cron 执行行 `status=completed` ≠ 投递成功**：completed 只代表 job 脚本跑完，不代表 bot-chat payload 真进群。验收必须单独确认投递回执（进队列 / unverified，但非 `failed`、非 `unknown platform`）。
- MSYS 下 `tasklist //FI "PID eq N"` 必须双斜杠，单斜杠会被当路径静默失败。
- 租约行可能**错位**（A 会话的行里挂着 B 会话的 turn 引用）——清理时按 holder 的 pid 判死活，别按 conversation_id 想当然。
- `gateway_heartbeats` 表会有几十条死 backend 历史行，属正常残留，不用清。
- 报错里写「live owner (cli, pid X)」时 X 可能早已死亡；先验活再决定清不清，不要照报错字面去关界面。
- 被系统拦截（destructive 确认门）时不要换马甲重试，停手向用户要点头。
- **自动化 restart 重试循环别用 gateway_state.json 的 pid 判活（11-10 实测）**：脚本连发 `hermes gateway restart` 时每次 stop 都 "Killed 1 gateway process" 再 spawn 新实例；state.json 只在注册/清理事件写盘，间隙会读到 "stopped+旧 pid" 的瞬时值 → 误判"没活"继续 kill/spawn，1 分钟内 churn 了 4 轮。判活改两步：① tasklist 查 spawn 返回的 pid 是否存活（>2min 才算活）② gateway.log 尾部有新启动段 + 平台 Connected 行。churn 后最后一轮 spawn 的实例往往其实活着——先验活再决定补不补 start，别盲目再发 restart。
- 微信"收不到回复"分诊（11-13 实例）：消息都进了（日志有 Flushing text batch）但没有 response ready → 会话被 unknown_execution 挡停（常见诱因=网关重启撞上进中的 weixin turn）。修：`bin\hermes.exe sessions discard <session_id> --yes`（官方围栏控制，非裸改 DB），队列消息随后按序排空；session_id 从 state.db session_turn_leases 或 agent.log 的 "Session X paused: unknown_execution" 取。重启网关前先确认无进中的 weixin/cron turn。
- **会话内重启网关在结构上做不到——别试，给用户 .bat。** `gateway stop` 在有 live session 时必被拒，而驱动分诊的会话本身就是一个 live session（它的 turn 算在途）→ 从会话内发起的 stop/start 永远失败。正解：造一个用户双击的 .bat（stop[安全拒] → 等 → start → status，~15-30s，账户 0 仓 0 挂单时零交易影响），安排在空闲窗口 + 用户调试窗口（本机规矩：服务调整 23:00-06:00）执行；别在同一会话里反复发起。
- **投递层挂起态（探活超时 / bot-chat unverified）会自消化——重启升级条件 ≠ 任何一次卡**。升级时加一条证据 = 查 Hermes/gateway 进程 StartTime（`Get-Process Hermes | Select Id,StartTime`）：数小时未重启的旧进程 = 投递子系统锁/状态积压（卡队列反复 40→100→258min 递增即此面），重启根治；向用户报时给两选项（"您回一句'重启网关'我执行" 或 "自己双击 一键重启网关.bat"），敏感闸会拦会话内自行 restart（live session + destructive 门），被拦后不重试同命令，只等用户点头；等待期间零丢失（22:00 兜底销账），后续同根因拍静默不重报。补发机制（15min 重投 + 22:00 兜底销账）零丢失，一天内多波挂起全自愈是正常波动：看门狗投递卡"两连卡"先再观察一拍是否自清；只有"仍卡且积压件增加"或"22:00 销账也失败（兜底闭环破）"才升级重启。因主 bot 会话跑在 gateway 进程里，重启动作不能由本会话发起（在途会话必拒）——预置 .bat 或借看门狗独立进程执行，挂台账 WATCH 项带升级条件即可，别每波挂起就动手。
- **bot-chat 投递成批失败/全 unverified + 网关探活全绿 = 先疑 deliver_target 坏值，别查网关链路**：grep `E:/workbuddy/国外模型/hermes/cron/jobs.json` 的 `bot-chat:` 带后缀值——`bot-chat:(own)`/`bot-chat:chief` 这类后缀会被调度器当「platform:profile」解析，profile 不存在 → 全体 unverified/failed（单日 297 败同源）。修四步：①坏值全改裸 `bot-chat`（先 cp .bak）②清被坏值污染的 `last_delivery_error`/`last_delivery_unverified` 记录（历史污染残留会让复验误读）③`last_delivery_queued` 里以坏目标为键的队列记录并入正确键（保 delivery_id 不丢）④复扫 0 残留 + JSON round-trip 验合法。运行中调度器缓存 jobs.json——下次 gateway 重启才生效，窗口期仍可能见到旧坏值产生的新一波卡队列标记（别在窗口期再修一遍，等重启验活=新执行记录的投递回执正常）。
- **`hermes cron` 命令挂起/报错「finishing an interrupted source update」「Preparing Node dependencies failed」= hermes 自更新收尾卡住（draining: update_paused 的源头），cron CLI 全挂**：cron 操作改直写 jobs.json——照同类 job 复制骨架（一次性哨=once schedule 模板），新 id（12 位随机）、状态字段（last_run_at/last_status/last_error/last_dispatch/last_delivery_*）全置 null、enabled=true，round-trip 验 JSON；gateway 下次重启加载，验活=到点看 executions.db/cron/output/<id>/ 出新执行记录。期间别手动跑 `hermes update`（重启网关属破坏性动作，需用户点头）；更新收尾自然完成后 CLI 恢复，新 job 无需重建。
- **网关挂死（进程活着但日志停写 + cron 全停摆）的两个本机实根因（11-06 实例）：** ① 胖主会话（20万+ tokens）的上下文压缩反复撞输出 token 上限拖死主循环（errors.log 特征："Context compression summary was truncated (finish_reason=length)" 每 15-30min 一条）；② 日志锁降级（concurrent-log-handler 缺 pywin32 → ImportError fallback，装 pywin32 进 tools python，下次 gateway 启动才生效）。持久修 = 主会话瘦身（`hermes sessions stats` 看 store 体积/会话数；prune 旧会话不可逆，属用户确认项；`sessions optimize --force` 在 live writer 下会让全部 agent 拒轮，必须排专属窗口，别白天做）。
- **网关重启后"全绿"的看门狗/cron 消息可能是挂死前的积压旧投递在泄洪，不是新心跳——别据此宣布恢复。** 验收恢复 = 消息内嵌时间戳晚于重启时刻 + executions.db/调度有新执行记录；旧积压（11-05 时间戳的"看门狗 03:00"）看着像新心跳，实为队列泄洪。

## 参考
- 症状→怀疑→动作对照表：`references/diagnosis-table.md`
- iLink 微信通道重连/开通/验证（凭证直探、session-not-ready 唤醒、QR 重登流程）：`references/ilink-weixin-reconnect.md`
- cron bot-chat 群播报投递断链（"群里没动静"、unknown platform / delivery failed 两错误分诊 + gateway 判活）：`references/cron-botchat-delivery-break.md`
