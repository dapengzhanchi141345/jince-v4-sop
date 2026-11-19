jince-silent-pipeline-diagnosis.md — JinCe 循环/群「突然安静了」的根因诊断手册。用户报"循环停摆"/"群里没动静"时按本表定位, 别在 429/gateway/看门狗层空转十几枪。

# JinCe 静默管线诊断手册

用户报"循环停摆 / 群里没动静 / delivered 了却看不到"时, 先判是哪一层断的, 再动手。三条常见根因, 从上到下逐层验, 命中即修, 命中一层就停, 别全查一遍。

## 层 1: 计划任务被冻死僵尸挂住 (循环停摆 · 实盘监控失明)
**症状:** `auto_run_cycle.py` 整条 30min 全链静默停摆 N 分钟, `auto_cycle.log` mtime 卡在某一拍, 实盘监控失明, 但没报错、没 429、没看门狗报警。

**根因模式 (区别于 2026-10-06 的"多实例堆积叠死"):** 单个冻死实例把 JinCeAutoCycle 任务状态挂成"运行中", 从此吞掉所有后续 30min tick。任务 Settings 里 `MultipleInstancesPolicy=IgnoreNew` 让它不会叠新实例, 但那个卡住的旧实例也永远不退出 → 任务永远"运行中" → 下次 30min 触发被 IgnoreNew 静默丢弃。

**诊断三件套 (纯只读, 先做):**
1. `auto_run_cycle.py` 的 python 进程存活 > 100min + 工作集小 (~1580KB 是冻死征兆, 正常跑动时工作集会涨) → 冻死坐实。
2. `auto_cycle.log` 最后 mtime 卡在某拍, 之后无新"全链自动运行完成"戳。
3. `schtasks /Query /TN JinCeAutoCycle /FO LIST` 任务状态=运行中 且 next_run 时间已过期 (中间 30min 触发全被吞)。

**清法 (最小影响, 杀前必验明 PID 身份):**
1. **杀前必验明** — `Get-CimInstance Win32_Process` 读目标 PID 的 CommandLine, 确凿指向 `auto_run_cycle.py`/`backtest_engine.py SMOKE` 才杀。防 PID 被 OS 回收成别的进程误杀。
2. `taskkill /F /T /PID <父>` — /T 递归一次清掉父子树 (等价于先杀子再杀父, 但一条命令更干净)。
3. 验 0B `backtest_engine.lock` 占位文件无害 — msvcrt 锁随持锁进程死自动释放, **不需要额外清文件**, 占位空文件留着不霸锁。
4. `taskkill /F` 在 MSYS bash 下会过智能审批 (kill 不可逆类), 直接跑、抓真输出; **`Stop-Process -Force` 在非 admin 权限下可能静默失败被 `SilentlyContinue` 吞掉错误, 别用它替代 taskkill 还当它成功**。taskkill 报"成功终止"后 `tasklist /FI "PID eq X"` 验 0 匹配才算真清。
5. 杀完立即 `schtasks /Run /TN JinCeAutoCycle` 手动触发加速 (事故级停摆不能让用户等下一个 30min 窗口), 9-10s 内验新父+子 python 进程拉起即绿。
6. 杀完当场验: ①两 PID 清没 ②JinCeAutoCycle 任务状态回"就绪"还是已手动 Running ③auto_cycle.log 出现新拍 ④`backtest_engine.lock` 释放。

**治本 (进 22:00 日报故障行):** 给 `auto_run_cycle.py` 外层加看门狗 — 每轮结束前显式释放 msvcrt 锁 + 把任务状态改回"就绪" + 独立 30min 触发器跟循环本体解耦, 防单轮卡死挂死整个任务状态。

## 层 2: C/E HERMES_HOME surface 劈叉 (cron 说 delivered、用户桌面群却静默)
**症状:** 33 个金策 cron bot-chat 播报日志显示 `delivered`, 但用户桌面「金策·宗师团」群窗口 6 小时没进一条 → 用户报"delivered 了群里没动静"。

**根因 (跟 429 网关毒化无关, 纯 storage split):** 本机两套 Hermes home, 各自独立 `profiles/*` 目录 + 独立 `state.db`, 互不共享消息库:
- C 盘 `C:\Users\ASUS\AppData\Local\hermes` — 桌面「金策·宗师团」Bot Chat 窗口连的这套。
- E 盘 `E:\workbuddy\国外模型\hermes` — 金策 33 个 cron bot-chat 播报全投的这套。

两套各有一份 `profiles/chief` → 投进 E 盘的 bot-chat 内容**永远不渲染到 C 盘那个群窗口**。这就是"delivered 了却群里没动静"的终极真相。

**诊断 (纯只读):** 读两侧 `state.db` mtime + 各自 `profiles/chief/state.db` 里最后一条群消息时间戳对比。C 盘 state.db 数小时前才动 + E 盘 state.db 分钟级活跃 = 劈叉坐实。`AppData\Roaming\Hermes\backend-ownership.json` 也能看桌面 app 认哪套 (可能 `{backends:[]}` 即懒启动未连)。

**铁律: 永远不拿"delivered"当"用户看到了"。** 必须先确认用户桌面 Bot Chat 连的那套 home 就是 cron 投递目标那套 home; 两侧 state.db 最后消息时间戳对得上才算投递真到用户眼睛。在错的那套上修 10 枪 = 全白修。

**最小修 (不擅自动正在跑的引擎那套):** 把 33 个 cron 的 `deliver=bot-chat:<profile>` 改指到用户桌面连的那套 profile-home (只改投递目标, 不碰引擎本体 + 10 个定时任务), 做完验目标那套 `profiles/chief/state.db` 最后一条群消息刷新到新时间戳才算绿。动两套 HOME 影响面大, 默认选"只改投递目标"这条最小路, 不反向合并整套 home。

## 层 3: gateway 429 / weixin 跨平台毒化 (真投不进, 前面两层都排除了才查这)
已在本 skill 主文记录: 前半夜静默多为 chief 独立 gateway 被 weixin 毒化拖死, 今早已恢复 + 高频哨兵防刷屏 94% suppressed。本层不重复, 前两层未命中再回主文查。

## 诊断顺序速记 (一张表)
用户报"金策某循环/群静默" → 1) 先只读查目标 python 进程是否冻死挂任务状态 (层1) 2) 再查两侧 state.db mtime 劈叉没 (层2) 3) 最后才查 gateway 429/毒化 (层3, 回主文)。命中一层即修, 修完验对应那层的时间戳/任务状态刷绿, 不跨层空转。
