# 未签开单层清扫 (ghost position + unsigned process 全停退役)

Use when: 风控裁定/用户授权认定簿外第三开单层（循环工具/老 bot/影子层）开了仓，需要"平仓＋停进程＋0 残留＋交接复验"。去留裁定归 L4，不可逆动作授权归用户，0 残留复验归运营，magic 完整性格重 grep 归风控官——执行者只做执行，不代签任何一格。

## 0. 进程普查与复活源分类（先做，否则杀了白杀）
1. `Get-CimInstance Win32_Process` 全表拿目标命令行＋ParentProcessId 父子树。
2. 复活源按类分、按序处置：
   - **Windows 计划任务**（JinCe*/cron/gateway 系）：先 Disable，以 `schtasks /Query /FO TABLE` 人读"已禁用/就绪"确认（PS `.State` 枚举整型输出有过误读史，人读表为准）；
   - **看门狗进程**：杀（不可逆，需授权）；
   - **外部 agent 的 shell 会话**（兄弟 agent 的 codebuddy-shell-payload 等）：只登记不代杀，交接给该 agent 侧；一次性启动 shell 通常自行退出；
   - **venv/pythonw detached 子进程**：随链杀。
3. 目标若是 runner→hand 类父子链，杀根即全树死（子级报"无此实例"= 已随树死，不是错误）。
4. 查目标脚本全路径归属（哪个 agent 的目录、E/D 哪侧），再核安装区有无同名脚本副本＋同款定时任务——查无副本才算"杀掉＝杀净"。

## 1. 平仓（先平后杀，平的过程里进程还在开新仓就白平）
- **动手前先用 `mt5.positions_get()` 实读真实 open ticket 清单，别信该层自记 CSV 的 OPEN 行数（2026-11-03 幽灵仓实例）：** fail-open 层自记 `live24_trades.csv` 的 OPEN 行 `rc=10009 'Request executed'` 只代表请求被受理，**不代表实盘真成仓**——本实例 CSV 报 3 仓（XAU/BTC/ETH 全 rc=10009），`positions_get()` 实读只有 XAU 1 仓，BTC/ETH 在 4h deal 流里无开无平＝假阳性。只平实盘在的票；CSV 里实盘没有的 OPEN 行在台账打 `实盘无此仓 rc10009假阳性` 注、**0 编 exit 价**（编 exit＝造账实劈叉）。consec/halt/连亏计数一律按 MT5 实读成交对账、**不按 CSV 行数**——halt 裁定若基于假阳性行数会错挂 24h 冷却。
- 解释器选装有 MetaTrader5 包的那把（如 jince_bot 独立 venv；裸系统/D 侧 python 缺包就换解释器，不临时 pip install）。
- 账号闸：attach 后先验 `account_info().login == 目标账号`，不符 fail-closed 中止（账号铁律 fail-closed，与闸源读不到同款处理）。
- 平仓 = `TRADE_ACTION_DEAL`＋反向 type＋BUY 仓 @bid / SELL 仓 @ask＋deviation；filling mode 按 quirks §13 读 bitmask，币系 IOC 可过；成功 retcode ∈ {10008,10009,10010}（quirks §15）。
- 平完验证三件套：`positions_get()` 空＋`orders_get()` 空＋balance/equity 实读；单仓 P&L 按手数估（XAUUSD 0.01 手≈1oz、ETHUSD 0.01 手≈0.01 币），与余额差对账，差以余额为准（quirks §19）；`history_deals_get` 空手＝同步延迟，几何估不编数（quirks §14）。
- 台账：当日 CSV/ledger OPEN 行→CLOSE 补 exit/pnl/deal/时间戳/注释；结果 JSON（retcode/deal/平仓价）落引擎 `data/`。

## 2. 杀进程（授权后执行）
- `taskkill /F /PID` 逐目标；父侧捕获输出一律 `subprocess.run(..., capture_output=True, text=True, encoding="gbk", errors="replace")`，否则 taskkill/tasklist 中文输出直接 UnicodeDecodeError（quirks §9 镜像）。

## 3. 0 残留验证（证据标准，过了才叫"杀净"）
- WMI 全表按**命令行/脚本名** grep（`Where-Object { $_.CommandLine -match 'a|b|c' }`），**不按 PID 验**：PID 复用会让死号变成无关进程。
- 剔除自己搜索的 grep/powershell 残影（命令行含关键字的搜索进程是假阳性）。
- 稳定双采样：隔 ~30s 同表再打一遍，两次都 0 活体；起壳源（外部 agent shell）已 gone 或已显式交接。

## 4. 交接与重启
- 0 残留证据（WMI grep 0 行＋双采样＋任务"已禁用"表）报运营独立复验；过闸后才交风控官重 grep magic 完整性格销账。
- 清扫期 Disable 的基建类任务（30min 循环/看门狗）在裁定窗（如 08:30 开评）重启，重启权归运营主管；事件快通道保持 Disabled 归 L4 点头——执行者不擅动任何一方。
