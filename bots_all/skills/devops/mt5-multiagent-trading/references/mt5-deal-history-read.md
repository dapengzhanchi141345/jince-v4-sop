# MT5 只读拉数 & 平仓流(consec)重算 —— 本 build 坑 + 配方

只读拉 MT5 成交/持仓/净值，或做连亏(consec)/24h 冷却重算时走这里；全程 0 下单 0 撤单 0 挂单，拉完 `mt5.shutdown()`。客户账户(friend observer)额外红线：只读，绝不 order_send/position_close/modify。

## 可用解释器（路径因机而异，先验后用）
- MetaTrader5 只在 `ate` env（Python 3.13）能 import；Hermes 默认 `python`（常是 3.14）报 `No module named 'MetaTrader5._core'`（该 pyd 无 3.14 构建）。
- SKILL.md 里写死的 `C:\Users\ASUS\.workbuddy\binaries\python\envs\ate\Scripts\python.exe` 只在原机有效。**本机若 workbuddy 已迁到 `E:\`**，可用入口＝`E:\GoldstrategyEngine\python\envs\ate\Scripts\python.exe`，前缀 `export PYTHONPATH=E:\GoldstrategyEngine\pylibs`。
- 验证后再用（别盲信路径）：`"<ate-python>" -c "import MetaTrader5 as m; print(m.initialize())"` → 必须 `True`；再 `account_info()` 核对 `.login`＝目标账户。
- 若该 pylibs 只含 MT5 单包，`export PYTHONPATH` 直接指向它即可，不必 `env -u PYTHONPATH` 剥净（`env -u` 那套是「多包 + numpy 被 hermes venv 遮蔽」的机器才需要，见 SKILL 的 PATH 污染节）。
- 跑模块：`"<ate-python>" E:/GoldstrategyEngine/multi_agent/trading/<module>.py`（工作目录或绝对路径皆可）。

## 本 build 字段坑（写死数值，别裸用 build 常量）
- `mt5.DEAL_ENTRY_BY` 等入口常量**缺失**（AttributeError）：deal 入口类型一律用数值 —— **`IN=1 / OUT=3 / INOUT=2 / OUT_BY=4`**（官方 C++ 枚举值；0 不是 IN——早期文档曾写 `IN=0/OUT=1` 已证错，按错表 filter 会把开仓行读成平仓行，凑出假「零盈利离场」批次；判平仓批次先取 entry==3/4 行求和并与余额跳变对账，分毫不差才算读对行，见 SKILL 报账口径节 11-11 补强）。
- `mt5.terminal_info()` **无 `.login`**；账号/净值走 `mt5.account_info()`（`.login/.equity/.balance/.server`）。`terminal_info()` 只有 connected 与 `trade_allowed`（本 build 字段名 `trade_allowed`，非 `trading_allowed`）。
- deal 的位置字段名随 build 变：`pid = getattr(d,"position_id",None) or getattr(d,"position",None)`。
- stdout 出 ASCII-only JSON（GBK 管道禁 emoji/汉字 tag），末行单行 JSON 供父进程解析；失败 fail-open 报 ok=False。

## consec 连亏重算配方（magic 白名单滤退役腿）
目的：把账户级 `consec_losses` 按「活 magic」重算，剔掉退役/演练腿与假阳性，判 24h 冷却是否真触发。
1. **白名单读表不背号**：`E:\GoldstrategyEngine\data\magic_registry.json` 的 `existing_map_verified`（系统腿）＋ `assignments` 里 `status` 非「已撤销/收回」的腿＝active；`status` 含「已撤销/收回」（如 workbuddy 程序腿）＝retired。magic 号会变，一律现读。
2. `mt5.history_deals_get(now-45d, now)`，按 position 归组：`pnl`＝该 position 所有 OUT/OUT_BY/INOUT 的 `profit+swap+commission` 之和；`close_time`＝这些 deal 的最大 time；**position 的 magic 取 IN deal 的 magic**（手动平掉的 OUT deal magic 常为 0，别用它判腿）。
3. 有 close_time 的才算「已实现平仓仓」；按 close_time 倒序。
4. 尾部连亏＝从最新往回数，`pnl<0` 连续累加、遇 `pnl>=0` 断。分别算 ALL 口径 与 ACTIVE-only 口径。
5. 口径铁律：**冷却闸该认的是 ACTIVE-only 连亏数**；`data/risk_state.json` 的 `consec_losses` 常是过期值或 D 侧未滤 magic（混入退役腿/假阳性），**以 MT5 实读 deal 流为准**，别信文件那个数。重算后要提醒 L4/risk 按 MT5 底把 consec 与冷却行改判。
6. 冷却触发时点＝最后一笔连亏平仓的 `close_time + 24h`（转北京时间报）。

## 平仓配对 & MFE 归因配方（2026-11-11 深析沉淀）
目的：把一段历史成交配对成「开→平」逐笔 P&L，并按「峰值浮盈(MFE)→反转即出场」量化出场优化空间。
1. **配对**：`history_deals_get(t0,t1)` → IN 行(entry==1) 按 `position_id` 找同 position 的 OUT/OUT_BY 行(entry∈{3,4}) 配对；INOUT(entry==2) 自成一对（常见于 broker 预注册开仓的到期成交，其平仓侧 profit 常记 0.00，真实盈亏看余额跳变或平仓行，别把 0.00 读成「零盈利」）。position_id 缺失用 `getattr(d,"position",None)` 兜底（字段随 build 变）。
2. **MFE 实算**：拉该品种 M5（`copy_rates_range`，注意 tick time 与本地时区 2h 偏移坑）；SELL 单 MFE=`max(open-low)`，BUY 单 `max(high-open)`；MFE<0 = 「开仓即错」（从未浮盈，出场策略救不了，要砍腿/查方向/事件窗）；MFE>0 且峰值后大幅回吐 = 「真反转吞浮盈」，可用「浮盈回吐至峰值×(1-k) 砍回」量化吃到第一波的空间。
3. **同分母分层**：砍回参数（如 k=0.6）对大点差族（股指/金银）与小点差族（币/小货币对）效果相反——一族赚一族亏是常态；出场优化必须按族分层，别推全品种统一规则（统一规则=选择效应，假 edge）。
4. **新闸假设先数据否决**：想建 kill zone/时段冻结等新闸，先把该时段全部历史单跑同分母 P&L 试算——净为正的时段建闸=误伤正期望（11-11 实例：凌晨 02-07 组 10 笔净赚 +$26.6，杀区假设当场否决）。

## 假阳性坑（务必宽窗复核）
- 断「某仓 0 成仓 / rc10009 假阳性」前，用**宽窗（≥45 天）history_deals** 复核，别只看 4h 窄窗：委托被受理(rc10009)后可能在你检查时刻**之后**才成交/入账，窄窗判「无 deal」＝假阴性。上一轮报「X 仓 0 成仓」、下一轮宽窗一读它已开已平＝典型翻车，改口要当众认。
- `rc=10009`（Request executed）只表「请求被受理」，不表实盘已开仓；以 deal 流里真出现该 position 的开/平 deal 为准。
