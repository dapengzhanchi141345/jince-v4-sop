# 活体执行层 vs dry-run 全链、回测线分认（报持仓/判开单来源/回测重跑用）

## 活体执行层 JINCE_LIVE24 独立于 dry-run 全链
- 新 demo 持仓多来自活体执行层 **JINCE_LIVE24（magic 20261103, comment "JINCE_LIVE24"）**，它独立于 dry-run 全链扫描——扫描简报写「0 开仓/0 平仓」时账户里也可能新冒 JINCE_LIVE24 持仓（本会话 23:05 实锤：扫描全绿但活仓 1 张）。
- 位置永远以 `positions_get()`/`orders_get()` 直读为准，**别按「扫描说 0」归因**；也**别**把活体层冒的新仓当成「违约」深挖——先认层再判断。
- magic 认层速查：`20260902`=USDJPY 系统单（全链残留）、`20260903`=币系 L4 例外腿、`20261103`=JINCE_LIVE24 活体实盘循环。
- 认不准新仓是否在授权范围（尤其 `LIVE_TRADING_ENABLED` 名义关着时）：按「报后动」——报最小影响方案（只动这一张、不动点位/RR）给李彦明拍板，绝不擅自平/改。

## 回测线（00:10 全宇宙 / SMOKE 枪）
- 00:10 每日 job 跑 `E:/GoldstrategyEngine/training_full_universe.py`（默认 SMOKE 3 主品种，约 14min+）；**收口才写** `data/backtest_edge.json`——判活看：①对应日志有「开跑」行**且**有收口行；②backtest_engine 的 pythonw 进程 CPU 在涨。只有开跑行=中途死（常见诱因：期间终端掉过）。
- 日志命名约定：首枪 `_smoke_YYYYMMDD.log`；重开第二发 `_smoke2_…log`（同日前缀）。补长空窗时趁终端在位重开一枪，**主 bot 不重复开首枪**（引擎锁防双跑）；收口后双方实读同一份 backtest_edge.json 交叉核 n/胜率。
- runner 内部已做 child_env 剥 PYTHONPATH/PYTHONHOME + 预检：依赖缺失=硬 fail（rc=1）；MT5 终端挂=**rc=4 干净跳过**留痕不刷屏 → 终端挂时 00:10 自动跳过、恢复后自动补跑，无需人工干预。rc 判活/陈旧 flag 细则见技能 `jince-watchdog-noise`。
