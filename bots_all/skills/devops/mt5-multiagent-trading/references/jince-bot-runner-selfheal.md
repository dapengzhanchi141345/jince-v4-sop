# jince_bot 独立 runner 韧性 + gh-api 多同步错峰

本参考记 jince_bot（引擎 AI 信号层的独立执行 bot）与多套 gh-api 同步的运维铁律。SKILL.md 主文件已超 100K 上限，故单列。
> **闪屏/糊屏（python.exe/gh.exe 黑框）排障另见** `references/no-flash-window-troubleshooting.md`（三层闪源 + pythonw/CREATE_NO_WINDOW 改法 + 批量 patch 右括号/验货血坑）。本参考的进程树诊断（`Get-CimInstance Win32_Process` 按 CommandLine/PPID 分类）就是那个方法论的第一步。

## jince_bot 是什么
- 独立执行 bot：`runner.py + side_brain/brain.py + side_hand/hand.py + signal_bridge`（ZMQ 脑手架构），15s 轮询 + 60s 信号刷新，`persist_on_release=True` 后台常驻。
- 代码目录 `E:\workbuddy\内容中心\交付\AI交易bot方案_20261019\jince_bot\`，独立 venv（pyzmq + MetaTrader5）。
- **它不是 30min 全链**：金策看门狗 / 30min 循环 / 03:00 体检**都不覆盖它**，它死了没人拉、持仓没人管。

## 死因 + 最小影响恢复（核心铁律）
- **根因：手侧 attach 的 MT5 终端断连/重启 → 主循环 fail-closed 优雅退出（不乱动单是对的），但独立 runner 一退整棵进程全没，持仓裸奔到下次有人重启。** 终端会自行重启（PID 常变，别按 PID 判生死），一抖就崩。
- 恢复顺序：
  1. 先 `initialize()` 探活确认终端真连上——终端重启后 1-3s 内可连，别因一次 `False` 就判死（带 `last_error()` 重试 2-3 次再下结论）。
  2. **最小影响 = 不清仓、不动已开点位、直接重拉 runner**（`--execute --poll 15 --signal-refresh 60` + 双钥匙）让它接管既有持仓。**绝不为「重启干净」而平掉现有仓**（用户要的是接管，不是重置）。
  3. 重启前清残留：`kill_residual.ps1` + 删 `jince_bot_runner.lock` / `jince_bot_hand_ready.json`，确认 5555/5556 端口真空再挂。
- **自愈已落地（非缺口）：`jince_bot/jince_selfheal_watchdog.py` + 计划任务 `JinCeBotSelfHeal`（5min 轮巡，`MultipleInstances=IgnoreNew`，探活 runner，absent/hung 时 `Popen` 复拉，单实例 msvcrt 锁，落审计 `data/jince_bot_selfheal_audit.jsonl`）。**
- **11-14 状态复核 + L5 收紧（覆盖上条的自动拉起假设）**：本机实测 `JinCeBotSelfHeal`=TASK MISSING + `jince_selfheal_watchdog.py` 无进程（即上条「任务可能被静默丢失」的缺失态=当前现实，勿按 recipe 盲目重建）；且旧版 boot_guardian 的 jince_bot DIRECT backstop 曾**无人自动拉起** equity runner（`boot_guardian.log` "jince_bot runner DIRECT backstop launched"）= 实盘进程自动启动越 L5 红线。现码已禁用该 backstop（runner 缺席只 log_once）。规则：不重建 JinCeBotSelfHeal 任务、不恢复自动拉起；**复活 runner = 李彦明 L5 拍板**，届时再按上文 recipe 重建 watchdog+双钥匙。 复拉参数 equity 初值读 daystate.start_equity（fallback 971.40），带 `JINCE_BOT_LIVE=1` + venv zmq PYTHONPATH。
- **「自愈脚本存在」≠「自愈在排程活着」——每轮先验任务态再下结论**：selfheal 任务会被静默丢失/未注册（实测 `Get-ScheduledTask JinCeBotSelfHeal` 可能 = TASK MISSING，导致 runner 死后 0 自动接管、双 runner 窗口恶化成全裸奔）。处置三步：① `Get-ScheduledTask JinCeBotSelfHeal` 验任务态，缺失就按下面 recipe 重建 + 首拍 `Start-ScheduledTask`；② 读 `data/jince_bot_selfheal_audit.jsonl` 尾行确认最近一次 `absent_relaunch` 真发生 + 复拉的 runner PID；③ 实拉进程表确认「1 runner + 1 shim + 1 活 hand」而非 0 或真双活（shim 链判定见「双进程同命令行」节）。别只信脚本存在就报「自愈在」。
- **重建 selfheal 计划任务 recipe（PowerShell）**：`New-ScheduledTaskAction -Execute <uv-cpython311-python> -Argument """<...>jince_selfheal_watchdog.py"""` + `New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)` + `New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit 0 -AllowStartIfOnBatteries`，`Register-ScheduledTask -TaskName JinCeBotSelfHeal -Force`，再 `Start-ScheduledTask` 首拍。注意 selfheal `relaunch()` **只 Popen runner.py，不单独拉 hand**——hand 由 runner 自 spawn，所以复拉后正常是「1 runner + 1 shim + 1 活 hand」（uv shim 链是正常形态，见下面「双进程同命令行」判定序；只有真双发才是竞态，且先验 PPID 再定罪）。
- **双 hand 表象 = shim 链，先验 PPID 再定罪**：runner.py 有两处 `subprocess.Popen(hand.py)`（顶层 bootstrap L~178 + 类方法 `start_hand` L~301，不在同一路径上不会双发），但**实拉看到的「1 runner + 2 hand（差 1 秒）」大概率是 uv venv shim 的 re-exec 进程链，不是双活 hand**：链形 `runner(uv cpython 3.11) → .venv\Scripts\python.exe（shim，CPU 仅 0.0x s / ~60KB 空壳）→ uv base cpython（唯一活手侧，hello/全部 query 都出在它名下）`。判定三连：① 读 PPID 链（父=shim、shim 父=runner 才是同链；两腿 parent 都是 runner 才是真双发）；② shim 腿 CPU≈0、内存几十 KB、0 审计事件；③ 脚本自述（hand.py L~115 注释自己写了 shim 坑）。**真双发**才走最小影响不 blind-kill（`daystate.breaker ON + 持仓 0 + 挂单 0` 时休眠态 0 double-send，不急着杀，去重排 rd_queue）；**shim 链**则验收标准改验「1 runner + 1 shim + 1 活 hand」，去重项标 closed_not_needed，0 kill 0 改码。

## 双钥匙真下单（fail-closed，demo 专用）
- runner 带 `--execute`（手侧才真 order_send）+ 环境变量 `JINCE_BOT_LIVE=1`（脑侧主闸），**缺任一把自动退回 DRY**。
- 这是 jince_bot 自己的钥匙，**≠ 金策引擎 `allow_live_trading` 总闸**（引擎仍 DRY-RUN 没动）；4 把金策专属 key 永不在 jince_bot 上动。
- 切回 DRY = 重启时去掉这两把。急停三钥匙：`一键急停.bat`（撤全挂单+平全持仓，只碰本系统 magic，绝不误伤手工仓）/ `kill_switch.py --execute`（独立进程，relay 死了也能清仓）/ 说「切回 DRY」。
- 日亏 10% 熔断 + 单品种日 3 单 + 单笔 0.5% 全在 `bot_risk.py` 单一源，UTC+8 时区写死，`daystate.json` 落盘重启不丢魂（重启不清零熔断/计数）。
- **daystate 真身路径 = `E:/GoldstrategyEngine/data/jince_bot_daystate.json`（引擎 data 目录，非 jince_bot 代码目录）**：查熔断态/日单计数认准这个，查代码目录会误报「absent」。字段 `breaker` / `start_equity` / `day_orders`（各品种当日开单数）。`stop_today.py` 写/清它控制当日开仓。重启 runner 读到这格 `breaker:true` 即今日 0 开新单（只风控巡检接仓），明早 new_day 自动翻篇。

## 双进程同命令行：先验 PPID 链再判「双实例」（hand/watchdog 通用）
- 同族坑不止 hand：`jince_watchdog.py` 带 msvcrt 文件排它锁（`LK_NBLCK`，第二腿抢锁失败静默退出，逻辑上恒 1 实例），但计划任务 + shim 叠加仍可能同秒冒出两个 watchdog 实例。与 hand 同判：父 svchost（计划任务）→ 子 ATE shim 同命令行差 1 秒 = re-exec 链，销账 0 kill；只有锁缺失 + 两腿都真跑逻辑才是双调度搅乱。
- **通用判定序**（报「双 X 竞态」前必走完，别把 shim 链当 bug 报）：
  1. `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object CommandLine -match '<脚本名>'` 列全部实例（全表无 -Filter 的 Where-Object 扫描会超时，必须 -Filter 预筛）；
  2. 逐个读 PPID + CreationDate：父是 shim/`.venv`/svchost 且同命令行、创建差 ≤2s = 单链；两腿 parent 都是同一调度源才是双实例；
  3. grep 脚本源码单实例锁（`LK_NBLCK|msvcrt|lock`）确认「后腿静默退出」逻辑；
  4. 核锁文件（如 `E:/GoldstrategyEngine/data/jince_watchdog.lock`）+ 审计 jsonl（活体事件全出在同一 PID 名下）。
- **Windows 进程实拉工具坑**：git-bash 里内联 PowerShell 脚本时 `$_` 会被 MSYS 路径展开搞坏（报 `/c/Users/ASUS.Name : 无法识别`）——写 .py 临时脚本用 `subprocess.run(['powershell','-NoProfile','-Command', ps])` 传整段，别走 shell 内插；`glob`/递归扫引擎目录会 RecursionError（深层目录环），用 PowerShell Get-ChildItem -Recurse -Filter 或按已知路径直查。

## gh-api 多同步错峰 + 无改动静默
- 机上不止金策一套走 `push_via_api`（gh api 绕 443 墙）的同步：金策 `jince_github_sync.py`（03:00）+ 技能仓 `skills_github_sync.py`（04:30）。
- **多套同打 gh-api 时 cron 时间戳错峰**（技能仓已错到 04:30 避金策 03:00 撞 443 墙余量），谁撞墙谁失败下一轮重试，别挤同一分钟。
- **no_agent 同步脚本必须「无改动就静默」watchdog 模式**：增量幂等（按内容 sha256 缓存去重，无新改动只建一笔空提交 / 0 blob 传输），stdout 只在有实质上传或失败时出声，全绿静默不刷屏。
- 复用而非自造：新同步直接 `import` 金策 `jince_github_sync.push_via_api`（gh api + blob 缓存 + 全量树一次 POST + 非 force 推 ref），不重写 443 绕行机制。上传前扫敏感数据（真 key/密码/私钥），占位符与代码变量是误报，真密钥才需脱敏。
