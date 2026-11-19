# 独立引擎 live24 & 回测孤儿（拓扑事实 + 处置铁律）

SKILL.md 超容未能内联，本文件承载这两条；判症状时与 jince-watchdog-noise 的「MT5 共享终端 IPC 争抢」条对照。

## live24 独立实盘引擎（jince_live24.py）
- 位置 `E:\GoldstrategyEngine\tools\jince_live24.py`，用户授权的独立 24h DEMO 实盘引擎，与主链 `LIVE_TRADING_ENABLED=False` 无关；PID 会变，别按 PID 认亲。
- 品种限 XAUUSD/BTCUSD/ETHUSD；0.01 手；随单 SL/TP；持仓 comment=`JINCE_LIVE24`；台账 `E:\GoldstrategyEngine\data\live24_trades.csv`（OPEN/CLOSE 行，rc=10009 成功）。
- 它的开仓/平仓/持仓循环是**正常引擎行为，不是主链漏单**：不入主链 16 部门统计、不计连亏冷却；但 MT5 实读持仓**总是含它**——报持仓明细前先按 comment 分清是谁的仓，节点报告余额/净值差额可能是它落袋。
- **停引擎、平它的仓 = 大动作先报后动**（李彦明点头前默认继续盯）。
- 节点报告"平仓后余额差几分"且持仓=0：差额 = 刚结那笔已实现盈亏，直读为准别当故障。
- **live24 可处 L5 RETIRE 闸源态（看门狗不重拉，翻活需三件）：** 看门狗每拍打 `🔒 [L5 RETIRE] jince_live24 处于退役闸源态 (rd_decisions RETIRE), 看门狗不重拉; 翻活需 L5 根因关闭+挂全闸源+OOS 三件后翻 active=false`。此时 jince_live24 进程已不在、watchdog 不会自动拉活——是**安全态**（漏单引擎不会再复活漏单）。**判 RETIRE 别只信看门狗一面之词，实读三处**：① `wmic/powershell` 查 jince_live24 进程在不在；② `E:\GoldstrategyEngine\data\rd_decisions.json` 搜 live24/RETIRE 条目；③ `data\risk_state.json` 的 `excluded_mags`（漏单/借壳单登记，L4 追溯 VETO + P&L 口径 + 0 喂 consec）。**"live24 层停/留 = @user 一字域"**（risk_state 明文 0 耦合）：停/留是用户一个字定的，翻活则必须 L5 三件齐（根因关闭+挂全闸源+OOS 解冻），非用户一字能开。默认维持停（0 仓 0 单+冷却中时留着无价值且有漏单史）。

## 回测孤儿进程铁律
- 手动起每日 00:10/全宇宙回测编排器时，进程必须活得过启动 shell：用前台 shell `&` 后台化会让编排器随 shell 死，留下 **backtest_engine 孤儿**（`wmic process where "commandline like '%backtest_engine%'"` 查 PID）。
- 孤儿占着 `data/training_full_universe.lock`，并跟实盘 OOS runner 抢 MT5 共享终端（8736）→ MT5 IPC 间歇饿死，一串症状同源：
  - 回测全品种 TIMECAP（单品种 3060s 未完成）→ `backtest_edge.json` 空件（n=0、aborted_by_timecap）；
  - 风控闸"刷新受阻(IPC冻死?) / 价源断 LEVEL=2 全冻结"；
  - tick 喂"MT5 实读 0 品种（终端 IPC 断?）沿用上份 tick"；
  - chief 全链某拍没跑完、心跳卡死。定性先直 attach 实读（login+品种数通 = 瞬态已自愈），再查孤儿。
- 发回测后先验编排器存活；发死/超时先查残留 PID + 锁文件。**杀孤儿"重起"= 先报后动的用户点头动作**（李彦明令最小影响原则），不擅杀。
- 根治方向（策略研发定）：回测走本地缓存 K 线、不走 live IPC；不动实盘终端/runner。

## JinCe 计划任务被反复 Disabled（静默死亡的常见根因）
- JinCeAutoCycle（30min 全链）/ JinCeEventGuard（5min 快通道）/ JinCeWatchdog（巡检）会整任务变 `State=Disabled`（LastTaskResult=267014），看门狗"轻踢"对 Disabled 无效。
- 全链心跳冻结/事件快通道静默，**第一步查这三个任务的 State**；Disabled 直接 `Enable-ScheduledTask` + `Start-ScheduledTask` + 看 log 出新拍即恢复，不必重注册；启回后逐拍盯是否再被停用（再停才深挖停用机制）。
