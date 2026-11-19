# 金策运维排障沉淀（2026-10-06/07 反复验证，速查）

> 本文件是 mt5-multiagent-trading 技能的支撑文件。SKILL.md 正文已 >100k 无法再追加，故排障细节集中在此。

## 1. GitHub 443 间歇墙 = SNI/IP 级，TCP 通 ≠ git 能推
- 现象：socket 探活 7 个 Anycast IP 有 5-6 个通，但写死 IP 的 `git push` / gh-token 全 21s 超时；同一时刻 `git push origin`（走系统 DNS）反而成功、`curl --resolve` 也回 200。根因 = 墙掐 TLS 握手（放行 TCP），且瞬时（几分钟恢复）。看板同步哨兵 / sync_to_github.py 会因此反复报"N 条路全挂"。
- 处置铁律：
  ① 手动 `git push origin` 裸推常能成，成功后把 `C:\Users\ASUS\jince-dashboard\.last_synced` 刷成源 `daily_dashboard.html` 的 mtime（下轮哨兵静默）。
  ② 选路顺序 = 裸 origin 优先（系统 DNS 最稳）→ 探活 resolve IP 逐试 → gh-token 兜底；IP 候选 7 个 = 140.82.114.4 / 20.205.243.166 / 140.82.113.4 / 185.199.108.153-156。
  ③ resolve 必须配 `http.<IP>.resolve=github.com:443:<IP>`（IP 键、保留 Host 头）；配在 `http.https://github.com/.resolve` 会把字面 URL 当键 → 永远不命中 → 误报全挂（jince_dashboard_sync_guard.py 2026-10-07 01:06 踩过，已修）。
  ④ `E:\GoldstrategyEngine` 下有一份旧脚本副本，cron 工作目录漂移会找错文件（"Script not found" 同病），改脚本后两份都要同步。

### 1a. 路径 D：GitHub REST API（gh api）直推 = 绕过 SNI 级 443 墙（2026-10-07 根治）
上面 ①②③ 的裸推/IP 探活/gh-token 全走 `git` 协议端点（github.com 的 smart-HTTP / upload-pack），会被 SNI 级墙掐 TLS。还有一条独立通道：**走 REST API（api.github.com 域）重组远端** —— 不经 git 协议、不经被掐的 SNI 指纹，443 墙抖时是唯一还能成的一路。已内建进 `jince_dashboard_sync_guard.py` 的「路径 D」。
- 流程：取 main HEAD → 把本地 `index.html` 内容上传为 blob → 建 tree（只替换 index.html 那一项，父 tree 不变）→ 建 commit → `gh api` 更新 ref `main` 指向新 commit。全链走 api.github.com。
- **坑（踩过）**：`GH_USER_REPO` 若写成 `owner/repo.git`，REST API 的 path 会 404（API 不认 `.git` 后缀，那是 git 协议专属）。走路径 D 前必须去 `.git` 后缀；git 裸推那条才保留 `.git`。两路 repo 串别共用同一个变量。
- **坑（f-string 调试残留）**：手动 patch 调试把 f-string 改坏（字面 `{...}` 语法错 / `NameError`），外层 `except: pass` 会静默吞掉 → 路径 D 整段从未真跑过却查不出报错。验证法：把路径 D 各步单独实跑、打印每步返回码（如 blob_rc），别只信「脚本没崩」。
- 验证：推成功后 `gh api .../contents/index.html` 的 size/content 与本地对得上、`.last_synced` stamp 追到源 mtime，即消告警。

### 1b. 看板「行情价不动」= 30min 批量快照，非故障；根治 = 独立 5min 实时喂线
用户问「行情时间怎么没变 / 没有同步更新」，根因**不是**同步链路没推上去，而是看板价格本来就是 **30min 全链跑完才换一拍的快照**（全链循环抓那一秒 tick 写死进 HTML），两次全链之间价「冻着」看着像没同步；443 墙抖还会让上一份快照的推送也卡一拍，放大「冻结」错觉。
- **诊断先实读不猜**：① 读看板 HTML 里 tick 时间戳（`ts=` 那串）看停在哪一秒；② ATE python 活体 `mt5.symbol_info_tick()` 读 3 个代表品种（黄金/币/股指）的 bid/ask/time——终端价若活着（刚那一秒）而看板旧，即「价活着 + 快照节奏慢」，非数据坏；③ 终端价也冻在某秒 = IPC 又卡死，走 engine-terminal-ipc-recovery.md。
- **根治（最优=不碰 30min 全链批量=不碰交易链，已落地）**：① 独立确定性小脚本 `jince_tick_push.py`（no_agent 0 LLM 0 429）：每 5min ATE 活体实读 15 品种 tick(bid/ask/ts) → 写 `tick_live.json` → 走 §1a 路径 D 推上 GitHub；终端断/全品种无 tick = fail-open 沿用上份 + 点名报不崩。② 看板 `dashboard_gen.py` 模板在 `</body>` 前注入自包含 JS（30min 全链重生成自动带上）：页面顶栏每 60s 拉同目录 `tick_live.json` 显示 15 品种现价 +「最后 tick N 秒前」，拉不到降级「显示 30min 快照价」。③ Hermes cron 每 5min 调 `jince_tick_push.py`（no_agent，deliver/failure_deliver=bot-chat，失败发声不静默、成功空 stdout 不投群）。
- 铁律：**加准实时价用独立喂线（小 JSON + 页内轮询），绝不改 30min 全链批量节奏**——改批量=碰交易研判链，风险大且无必要；两线并行（快照供研判、实时条供看盘）最稳。改 dashboard_gen.py 注入 JS 后必须 py_compile + 重生成 + 推上 + grep 新 JS 关键词确认带上（验货法见「Dashboard 加新卡 踩坑」）。

## 2. 节点评"老时间"bug（jince_node.py latest_advisory）
- 节点评印的"研判基准"停在早上（如 09:31）：根因 = `daily_advisory_YYYYMMDD.json` 日内被重写（mtime 新）但 `sections[0].beijing` 没刷新，latest_advisory 旧写法只取 mtime 最新文件的 sections[0]。
- 修法：latest_advisory 在文件内取 beijing 基准最新的 section（15:02 > 09:31）再读动量；top_movers 相应改读该 section，不再写死 `ad['sections'][0]`。已修（2026-10-06）。

## 3. 心跳假点名（jince_heartbeat_watch.py 认三本账）
- 研发心跳看门狗旧版只读 `rd_ledger_24h.json`（停在 20:00），但 strategy-rd 出件实际写 `rd_ledger.json` + `rd_verify_batch_*.json`（00:26 更新）+ `discussion_log` 里 `actor=strategy-rd & evt=heartbeat`，两边对不上 → 每 5min 假点名 @strategy-rd（2026-10-07 00:25 实例）。
- 修法：`read_ts_rd()` 取三本账最新时间戳 = rd_ledger_24h.json + rd_ledger.json / rd_verify_batch_*.json 的 mtime + discussion_log 里 actor=strategy-rd&evt=heartbeat。已修。

## 4. 子 bot 专属 key 429 = 配额限速（非挂死，凌晨窗口过即恢复）
- 现象：chief / strategy-rd 派单后 "No reply: every provider in the fallback chain kept failing"。根因 = 它们的 .cn 专属 key（AGNES_KEY_RD / AGNES_KEY_CHIEF）当日文本额度用完 → 限速"1 请求/分钟"，fallback 链（.com）也限速 → turn 停。
- 诊断：`curl -s -m 25 https://api.agnes-ai.cn/v1/chat/completions -H "Authorization: Bearer <key>" -d '{"model":"agnes-3.0-flash","messages":[{"role":"user","content":"ping"}],"max_tokens":5}'` —— 200=活、429=限速中（报错给恢复时刻）。
- 处置：凌晨配额窗口过了自动恢复，重发派单即可；不紧急活改走落盘队列（`金策宗师团\chief_主持任务队列.jsonl` + 巡检 `check_chief_queue` 点名）不靠 LLM 回话；P4/回测类确定性活由总调度直接跑 `E:\GoldstrategyEngine\backtest_engine.py` 兜底（不烧 LLM）。

## 5. 看门狗 gateway 探活误报（jince_watchdog.py / jince_auto_patrol.py）
- 现象：报 `gateway=was down -> restart` / `probe-fail`，但 gateway 实际一直活着（PID 不变，如 30112）。根因 = 探活 `gateway status` 偶尔卡 25-30s 超旧 timeout → 误判挂。
- 修法：探活 timeout 改 60s，且 `except subprocess.TimeoutExpired` 只记 "probe-timeout60s(未判挂, 下轮再探)" 不报异常；只有明确 `No gateway`/`not running` 才算真挂。已修两脚本。

## 6. 任务续跑双轨隐患
- P4 出徒线若新旧两批并存（如 p4_path_close 旧 V5 线 + p4_new_angle 新角度批），旧线的 3 个卡点被新批覆盖后，务必把旧 task_ledger 条目标 `superseded_closed`（next_retry_at=None），否则 02:15 到点空续空烧。唯一出徒路径只留一条。

## 7. cron/体检 spawn ATE 子进程必须剥 PYTHONPATH/PYTHONHOME（治 numpy 假红）
- 现象：每日体检/巡检 spawn ATE(3.13) 跑节点入口报 `numpy._core.multiarray failed to import`、节点被误判红——但节点在 30min 循环里实际正常。根因 = cron 父进程（Hermes gateway 3.11 venv）的 PYTHONPATH 注入子进程，3.13 ATE 加载了 3.11 的 numpy C 扩展即崩（同 mt5-python-quirks 的「PATH 污染」病）。
- 修法：凡自 spawn ATE 子进程的脚本（jince_daily_healthcheck.py / jince_auto_patrol.py / jince_node.py 及任何 L0 流水线）在 `subprocess.run` 里传净化 env：`env = {k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')}` + `subprocess.run([ATE, script], env=env, ...)`。验证手法：手工模拟污染环境（显式 `export PYTHONPATH=<hermes venv site-packages>` 后跑修好的脚本）仍全绿才算根治，别只在干净 shell 里验。

## 9. 过闸/销账汇报前实读卷体（防空卷 PASS_INDIRECT 假象）
- 现象：回测闸 verdict=PASS_INDIRECT 被当"双闸销账/过闸"报给用户, 实读卷体发现 per_symbol 只覆盖 3 品种、各腿 n=0 笔、0 正 edge 腿 = **空卷过闸**(INDIRECT 是间接通过不是真验证), 被纠正"别当出徒进展报"。
- 规则：凡要向用户报"过闸/销账/验收通过", 先实读卷体(backtest_edge.json/universe 卷)三项: per_symbol 覆盖全 universe 品种 + 腿级 n>0 + 有正 edge 腿。缺一即空卷, 改报"销账属实但卷空、live 不动、出徒不动", 并登记"空卷转真卷"任务给 strategy-rd。闸 verdict ≠ OOS 样本量, 出徒 OOS floor 不随过闸移动。

## 8. 节点/循环撞上 MT5 重启窗口 = 时间点竞态，非故障
- 现象：重启引擎终端后的首个开评节点报「② MT5 实读降级 + 实时 tick 0 品种」，看门狗同窗点名 chief 超窗。
- 判定：读 `data/auto_cycle.log` 最新「全链自动运行完成」行——若完成时间落在重启后 1-2 个循环、点名与补完成同分钟，即节点撞上重启窗口拖住循环 5min 超容差，警自消，不算事故、不处置。区分真故障 = 循环日志无补完成行 + 实读持续 10005。
- 铁律：**重启引擎终端前必须先实读确认 0 挂单 0 持仓**（有单走最小影响：撤单归 0 或先报后动，别硬重启），见 mt5-engine-terminal-wedged-recovery.md §1/§2。
