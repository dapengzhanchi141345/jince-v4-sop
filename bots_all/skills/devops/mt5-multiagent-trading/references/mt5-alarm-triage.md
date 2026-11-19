# MT5『读 0 品种 / 握手降级』报警三分法（收报警先验货，别信节点自报）

收到 巡检/喂/看门狗 报「MT5 实读 0 品种 / 终端 IPC 断 / initialize 握手 15s 封顶降级」时，先跑
`E:/GoldstrategyEngine/_mt5_readonly_probe.py` 活体实读（唯一 source of truth），再按 `connect` 结果三分：

- **connect:false + terminal64 窗口活 + RAM 高(≥90%)** = **IPC 冻死族**（内存压力根因）。
  fail-open 沿用上份 tick、没丢数据；通常几分钟自愈，**不重启**。RAM 破 93% 且连续 2 拍冻死 → 升级报用户拍板
  （重启 terminal64 或指认内存大户），**不擅动终端**（spawn/kill terminal64 铁律见主 SKILL.md）。
- **connect:false + terminal64 窗口活 + RAM 低(≈82%)** = **broker 掉线窗口**（TradeMax 侧断线/重连）。
  终端自己会重连，等下一拍 `connect:true` 即静默销账，**不重启**。
- **显示层假警**（如看门狗 extnet 报『余量=4』而实为 4989 满血）= 查 `jince_watchdog.py` 里
  `probe['extnet'][:30]` 截断把 "余量=4989" 切成 "余量=4"。改按前缀取干净状态词（ok/down/probe-fail），
  完整值看 `data/network_probe_last.json`。探活逻辑本身没坏，纯显示层丑。

## 第四种模式：Python 侧 initialize() 报 `(-6, 'Terminal: Authorization failed')`（＝终端拒外部连接，**不是账号没登录**）
- 症状：终端窗口里账号登录态正常（用户侧一直登着），但各 Python 层 `mt5.initialize()` 全报 Authorization failed、活读全降级。用户报「账号我一直登着 为什么显示登不上」时答「登录没问题，是程序连终端的线被拒」，别答成掉线重登。
- 根因链：终端进程重启（Win32_Process CreationDate 变新）→ 重启前起的常驻层握的 IPC 句柄全作废且不会自动重连 → 期间持续报降级；主链 30min 拍是每拍新进程，下一拍天然重连自愈。
- 判据实读：终端进程启动时间 > 各常驻层启动时间 = 旧句柄坐实；主链新拍 0 授权失败 + 数据文件 mtime 续动 = 已自愈。
- 处置：① 降级窗样本打 STALE 标（窗 = 最后一拍失败→恢复拍，OOS/五验分母不入池）② 常驻层恢复 = 重启那几个进程（用户授权域），0 代码改动 ③ 与终端日志里 broker 侧 `authorization ... failed (Invalid account)`（模式 2，掉券商线要手动重登）严格区分，别混报。

## 数值铁律（反复踩，务必守）
**净值/持仓/挂单一律以 `_mt5_readonly_probe.py` 活体实读为准**，严禁拿 `data/dept_hub.json`、
`data/_chief_mt5_readonly_*.json`（带时间戳的旧快照）等缓存当当前值。
实例：
- 08:30 简报报 $965.40 = 10-12 旧快照 `_chief_mt5_readonly_1145.json`（活体实读实为 $893.95）。
- 22:00 日报报「活持仓 3 张」= 读派生簿假账（活体实读 0 持仓）。
根治：job `ac80590fc779`(08:30 简报)、22:00 日报 的 prompt 已加「活体实读铁律」。

## 判断口诀
收到 MT5 类报警 → 先 `_mt5_readonly_probe.py` 活读 → 看 connect 值 + RAM + 窗口 三件定三分 →
fail-open 已保数据不断就不慌 → 只有 RAM 破红线/连续 2 拍冻死才升级拍板 → 数值永远以活读覆盖缓存。
