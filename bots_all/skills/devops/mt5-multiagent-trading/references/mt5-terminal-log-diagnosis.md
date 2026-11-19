# MT5 终端日志 = IPC 挂时的持仓真值源

## 路径（账户 60137964）
C:/Users/Administrator/AppData/Roaming/MetaQuotes/Terminal/7643C0B96C7AD5841307C9E1EB0B9252/logs/YYYYMMDD.log
（其它终端是别的 hash，如 A3B1DF...；7643C0 对应 60137964 主账户。日志按当天 UTC+8 日期命名。）

## 编码 / 读法
- 日志是 UTF-16LE（行间 \x00），`grep` 直接匹配会失败。
- Python 读法：
  ```python
  import re
  raw=open(LOG,"rb").read()
  txt=re.sub(r"\x00+","",raw.decode("utf-16-le","replace"))
  for l in txt.splitlines(): ...
  ```

## "IPC 断" 两种失败模式（必须区分，处置不同）
1. 本地 IPC 通道抖：initialize() 间歇 False、positions_get 0 品种。
   - 通常 5-10min 自愈。盯着即可，不用惊动李彦明。
2. 终端掉券商线（更重，本次 11-03 12:47 就是这种）：
   - 日志出现 `disconnected from TradeMaxGlobal-Demo` + `authorization ... failed (Invalid account)`。
   - terminal64.exe 进程还活着（wmic 能看到），但跟券商断了线。
   - 此时 positions_get / account_info 数据**不可信**（读到的是旧快照或空）。
   - **必须李彦明手动重启 MT5 终端 / 重登 60137964**。铁律：agent 禁 spawn/杀 terminal64、禁自动登录，只读 attach。

## IPC 挂时的持仓真值读法（看日志行）
- `deal #X sell/buy N <SYM> @price done (based on order #Y)` = 成交。
- `cancel order #Y`（无后续 deal 行、无 expired 行）= 撤单（非成、非失效）。
- `market sell/buy ... close #Y ... deal ... done` = 平仓。
- `failed ... [Request rejected due to absence of network connection]` = 断网执行不了。
- 撤/成/失效 判定只有终端日志是权威；派生簿/御史快照可能过期，冲突以日志为准。

## 坑
- 泄漏腿（live24/L5 绕闸）开的单，终端断线后**仓还在服务器端**（SL/TP 在服务器），进程/终端挂也不消失 → 终端恢复后必须实读确认再处理。
- 本次实例：live24 泄漏 SELL #663837800 XAUUSD 0.01@3927.57（12:15 开，12:47 终端断线后无法平），日志至断线无平单 → 服务器端仍开。
