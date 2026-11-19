# MQL5 指标 / EA 编写与编译 — 深度参考

配套 `mt5-indicator-authoring` 技能。只写"踩过的坑 + 正确写法", 不复述 MQL5 官方教程。

## §0 括号配平验证脚本 (大文件多段 patch 后必跑, 防 unbalanced 反复横跳)
600+ 行的指标手数 `{}` 极易错。改完用这个一次性脚本验收 (写进工作目录跑):
```python
import re
path = r"...\JCEquityRecon.mq5"          # 改成目标文件
lines = open(path, encoding="utf-8").read().splitlines()
depth, decls = 0, []
for i, raw in enumerate(lines, 1):
    s = raw.strip()
    if s.startswith("//"): continue
    pre = depth
    depth += s.count("{") - s.count("}")
    if re.match(r"\s*(int|void|bool|double)\s+\w+\(", raw):
        decls.append((i, pre, raw.strip()[:45]))
print("final depth:", depth, "(应=0)")
for num, pre, name in decls:
    print(f"  L{num:4d} pre-depth={pre}{'  <-- 异常' if pre!=0 else ''}  {name}")
```
两条验收: ① final depth==0; ② 每个函数声明行 pre-depth==0(任一≠0 = 上一函数体没收干净, 编译器报 `expressions not allowed on global scope` + 吞掉后续函数 `OnCalculate not found`)。改前先跑基线, 改后对照。本会话在净值还原指标(600+行)上用此脚本定位出 L555/L606 pre-depth≠0 的根因, 比 MetaEditor 猜行省 6+ 轮。

## §1 编译器判定: 用对编译器, MT5 的 MetaEditor64.exe 能真正编出 .ex5
- 本机有两类 compiler, **务必分清**: ① MT4 终端自带的 `metaeditor.exe` (如 `D:\tmgmmt4\metaeditor.exe`) — 只能对 `.mq5` 做语法检查, 日志 0,0 打 `error 208: MQL5 files compilation is not supported, syntax checking only`, 不出 `.ex5`; ② MT5 终端的 `MetaEditor64.exe` (如 `C:\Program Files\TMGM MT5 Terminal\MetaEditor64.exe`) — **能真正编译 `.mq5` → `.ex5`** (跨品种分位指标实测 0 errors 出 .ex5)。
- 命令行编译: `"<mt5_dir>\MetaEditor64.exe" /compile:"<abs>\Name.mq5" /log:"<abs>\Name.log"`, 等 1-2s 后读 `.log` (UTF-16LE, 用 `iconv -f UTF-16LE` 转可读), **验收铁律 = `.ex5` 在磁盘上**, 永不拿"0 errors / 语法通过"当交付。
- 探针顺序: 先探编译器能否出 .ex5, 出不了先看是不是拿错了 compiler (把 MT4 的 `metaeditor.exe` 当 MQL5 用是最常见坑), 再怀疑代码。只有当 `MetaEditor64.exe` 也编不出时, 才退回让用户在桌面 MetaEditor 按 F7。
- 编译目录: MT5 的 indicator 源要放进对应终端数据目录的 `MQL5\Indicators\`。本机有多个终端数据目录 (`C:\Users\ASUS\AppData\Roaming\MetaQuotes\Terminal\{7643C0...,A3B1DF...,...}\MQL5\Indicators\`), 选**目标终端实际使用的那份**; 拷错终端目录也会不出 .ex5 或装了不显示。编完把 `.ex5` 备份到策略源目录 (如 `E:\workbuddy\金策宗师团\strategy-rd\`) 留底。

## §2 MQL5 指标只用内置 API — MQL4 风格伪 API 全不可用
写 MQL5 indicator 时**禁止**照搬 MQL4 / 网上旧例的这些, 它们在本机 MQL5 compiler 下整串报错 (256 undefined identifier / 199 wrong parameter count / 166 no overload applied):

| 错误写法 (MQL4 风格) | MQL5 正确写法 |
|---|---|
| `IndicatorSetInteger(INDPLOT_DRAW_TYPE,0,DRAW_LINE)` | `PlotIndexSetInteger(0, PLOT_DRAW_TYPE, DRAW_LINE)` |
| `IndicatorSetInteger(INDPLOT_COLOR,0,clrX)` / `INDPLOT_WIDTH` | `PlotIndexSetInteger(0, PLOT_LINE_COLOR, clrX)` + `PlotIndexSetInteger(0, PLOT_LINE_WIDTH, 2)` |
| `SetIndexDrawType(0, DRAW_LINE)` / `SetIndexStyle(0, STYLE_SOLID, clrGold, 2)` | **这两个 MQL5 里不存在!** 用 `PlotIndexSetInteger(0, PLOT_DRAW_TYPE, DRAW_LINE)` + `PlotIndexSetInteger(0, PLOT_LINE_STYLE, STYLE_SOLID)` + `PlotIndexSetInteger(0, PLOT_LINE_COLOR, clrGold)` + `PlotIndexSetInteger(0, PLOT_LINE_WIDTH, 2)` |
| `SetIndexLabel(0, "净值")` | **不存在!** 用 `PlotIndexSetString(0, PLOT_LABEL, "净值")` |
| `SetIndexEmptyValue(0, EMPTY_VALUE)` | **不存在!** 用 `PlotIndexSetDouble(0, PLOT_EMPTY_VALUE, EMPTY_VALUE)` |
| `iOpen(sym, 0, "EURUSD")` 建句柄 + `IndicatorRelease(handle)` | 跨品种直接 `iClose("EURUSD", PERIOD_CURRENT, shift)`; **不需要 iOpen** |
| `iClose(sym, PERIOD_CURRENT, shift, PRICE_CLOSE)` (4 参) | `iClose(sym, PERIOD_CURRENT, shift)` (3 参; 返回 close 价) |
| 副图不声明 `#property indicator_*` 直接绑 buffer | 必须 `#property indicator_type1 TOGGLE` + `indicator_buffers N` + `indicator_applied_price PRICE_CLOSE` 才认副图 |
| `PlotIndexSetInteger(0, PLOT_SHOW_DATA, true)` | 不需要; 主图数据标签默认显示 |
| `LongToString(x)` (long 转字符串) | **不存在!** 用 `IntegerToString(x)` (MQL5 的 IntegerToString 同时收 int/long/ulong) |

**指标缓冲 API 唯一稳定路径 (2026-10 净值还原指标踩坑, 永久):**
- 设可见性/线型/颜色/宽度/标签/空值 **全部** 走 `PlotIndexSet*` 家族:
  - `PlotIndexSetInteger(idx, PLOT_DRAW_TYPE, DRAW_LINE|DRAW_NONE)`
  - `PlotIndexSetInteger(idx, PLOT_LINE_COLOR, clr)` / `PLOT_LINE_WIDTH` / `PLOT_LINE_STYLE`
  - `PlotIndexSetString(idx, PLOT_LABEL, "text")`
  - `PlotIndexSetDouble(idx, PLOT_EMPTY_VALUE, EMPTY_VALUE)`
- **禁用** `SetIndexDrawType` / `SetIndexStyle` / `SetIndexLabel` / `SetIndexEmptyValue` / `PlotIndexSetInteger(INDPLOT_*, ...)` — 前四个 MQL5 里根本不存在 (error 256 undeclared + 级联 149), 后一个 IND PLOT 宏是 MQL4 时代残留。`SetIndexBuffer` 是**唯一**存在的 Set* 函数 (把数组绑到 buffer), 别混淆。
- 颜色/宽度/线型既可用 `#property indicator_color1/width1/style1` 静态设, 也可 `PlotIndexSetInteger` 运行时切; 二者可混用 (property 给默认, 运行时覆盖)。

副图指标最稳骨架 = `#property strict` + `indicator_type1 TOGGLE` + `indicator_buffers N` + `indicator_applied_price PRICE_CLOSE` + 每个 buffer 一个 `SetIndexBuffer(idx, buf, INDICATOR_DATA)` + `PlotIndexSet*` 设样式 + `OnCalculate` 里写 `buf[i]`。模板见 `templates/mql5-quantile-indicator.mq5`。
EA (非指标) 不同: EA 用 `OnTick`, 不需要 `#property indicator_*`; 挂单/平仓走 `CTrade`(见下 §2a), 跨品种读价同样用 `iClose` 三参, 不用 iOpen。

### §2a EA 专用: CTrade + 三个 MQL4→MQL5 迁移硬伤
写 EA 交易逻辑用标准类 `CTrade`(头 `#include <Trade\Trade.mqh>`), 不要手写 MQL4 的 `OrderSend` 11 参/`OrderClose`——它们在 MQL5 里都不存在, 照搬必挂整串 256/199:
- `#include <Trade\Trade.mqh>` → `CTrade g_trade;` 全局; 开仓 `g_trade.Buy(lots,sym,price,sl,tp,comment)` / `g_trade.Sell(...)`; 平仓 `g_trade.PositionClose(ticket)`。**先 `g_trade.SetTypeFilling(ORDER_FILLING_IOC)`**——demo 账户 filling 类型常和 broker 默认不符, 不设会 `ORDER_RETCODE_INVALID_FILL` 拒单。
- **周期参数必须 `ENUM_TIMEFRAMES`, 不能 `int`:** `input ENUM_TIMEFRAMES InpPeriod = PERIOD_H1;`。写成 `input int InpPeriod = PERIOD_H1;` 再喂给 `iMA/iTime/iBars/CopyBuffer` 会报 `error 262: cannot convert enum`。
- **`TimeToStruct` 是两参返回 bool, 不是 MQL4 的取 `.date`:** `MqlDateTime dt; TimeToStruct(TimeCurrent(), dt);` 再 `dt.year/dt.mon/dt.day` 自己拼日期(`IntegerToString` 拼 `"y.m.d"` 再 `StringToTime`)。写成 `TimeToStruct(TimeCurrent()).date` 会 199/232/256 三连错。
- **`TimeToCurrent` 在 MQL5 里不存在**(MQL4 有, 照搬直接 error 256 undefined): 算"当日0点"用截断式 `datetime dayStart=(datetime)((long)TimeCurrent()-((long)TimeCurrent()%(86400)));`, 别造 MqlDateTime 中转。日切判断同样用 `(long)TimeCurrent()/86400` 比较。
- **MQL5 脚本(.mq5, 非指标/EA) 必须用 `void OnStart()`, 不能用 `void main()`:** 写 `void main()` 报 `error 356: event handling function not found`; 也别加 `#property script_show_results` (unknown property, 报 error 288, 直接删掉即可)。
- **MQL5 脚本里 `new double[n]` / `new datetime[n]` 是类指针, 不能直接 `arr[i]` 索引:** 会 `error 241: '[' - array required` + `error 237: object pointer expected`。改用动态数组 `ArrayResize(arr, n)` + `arr[i]`, 或边读边折叠不存数组 (净值还原脚本就是后者, 最省内存)。
- **SAR 函数名是 `iSAR` 不是 `iParabolicSAR`:** MT4 叫 `iParabolicSar`, MQL5 内置叫 `iSAR(sym, tf, step, period)` — 注意参数序 **step(最大步长)在前、period(最小)在后**, 别颠倒; 写成 `iParabolicSAR` 直接 error 256 undefined + 级联 149。
- **MQL5 没有 C 风格指针形参:** `void f(double *p)` 报 error 253 pointer cannot be used; 一律改引用形参 `void f(double &p)`, 调用时传 `f(x)` 不是 `&x`。
- **ticket 类型坑:** `PositionGetTicket` 返回 **ulong**, `HistoryDealGetTicket` 返回 ulong; 局部 `long tk=PositionGetTicket(i)` 会 warning 43(ulong→long), 统一写 `long tk=(long)PositionGetTicket(i);` 显式强转, deal 侧同理 `ulong tk=HistoryDealGetTicket(i);` 直接用。
- **数组 series 警告**: 函数内 `double f[3],s[3];` 局部数组 OK; 放 `static` 里再 `ArraySetAsSeries` 会 warning 63。要 series 就用函数内局部数组。
- 成交回报用 `OnTrade()` + `HistorySelect(0,TimeCurrent())` 遍历 `DEAL_ENTRY_OUT` 判平仓盈亏(累 `DEAL_PROFIT+DEAL_SWAP+DEAL_COMMISSION`), 更新连亏/冷却; 别在 `OnTick` 里用 tick 价近似判。
- **自定义指标(iCustom)缺失要降级不崩:** 依赖的自定义指标(如 ZZI 之类第三方/自有结构指标)做 input 文件名传入, OnInit 里 `iCustom(sym, tf, InpZZIName, ...)` 判 `INVALID_HANDLE` 时**不 `INIT_FAILED` 整挂**, 打一条"指标缺失, 降级单腿运行"的 Print 继续跑(趋势指标仍可单腿开单), 让用户在日志里看见缺什么; 关键逻辑分支里判句柄再决定要不要要求该指标同向。指标本体要先编译进 `MQL5\\Indicators` 同名 .ex5, 缺指标=缺腿, 不能静默当 0 值算。
- 交付话术(§5)同适用: EA 未跑回测就交付, 必说"只验了编译, 没回测, 历史≠未来"; 客户高风险打法(金字塔摊均价/不挂SL扛单)另配书面风控警示 + 隔离小账户。**盈利加仓(同向 pyramiding)属高风险子类:** 加仓单+首单同向浮亏会同时放大, 日总止盈只保"赚够了离场"不保"单日先亏多少" — 交付时点明建议先小账户试跑看最大单日回撤再放大手数。
- **property 读取器用 1 参隐式票, 不是 2 参票 (本机 TMGM build, 永久铁证):** `PositionGetString(POSITION_SYMBOL)` / `PositionGetInteger(POSITION_MAGIC)` / `PositionGetDouble(POSITION_PRICE_OPEN)` 等**只传 property 枚举, 不传 ticket** — 它们读"上一个 `PositionGetTicket(i)` 已选中的持仓"。写成 2 参 `PositionGetString(tk,POSITION_SYMBOL)` / `PositionGetInteger(tk,POSITION_MAGIC)` 在本机 build 报成串 `error 199 wrong parameters count` + `error 262 cannot convert enum` (官方 MQL5 其实支持 2 参, 但此 build 只认 1 参)。**这是最贵的一类坑: 报在正确代码行上, 看着像别的 bug, 会浪费一整轮编译循环。铁律: 写 EA 前先 grep 一个**本机已 0 错编过的 .mq5**(如交付目录里的 `GoldScalpClone_EA_m5.mq5`)看它怎么访问 position/deal property, 原样抄它的 1 参写法, 别信官网。**
- **本机 build 的 deal/position 枚举名与官网不同名, 一律以已 0 错 EA 的 grep 结果为准 (别再照官网抄):** ① 成交 entry 判断用 `DEAL_ENTRY` + `DEAL_ENTRY_OUT`/`DEAL_ENTRY_OUT_BY`, **不是** `DEAL_TYPE`/`DEAL_TYPE_ENTRY_IN`/`DEAL_TYPE_OUT` (后者本机 error 256 undeclared); ② 成交方向用 `DEAL_ORDER_TYPE` 读到的 `ORDER_TYPE_BUY/SELL` — 但 `DEAL_ORDER_TYPE` 本机同样 undeclared (error 256), 所以**当日方向开单数改用内存计数器** (开单成功 `g_dayBuyOpen++/g_daySellOpen++`, 日切清零), 别去扫 deal 重建; ③ 持仓开仓时间用 `POSITION_TIME` (long), **不是** `POSITION_TIME_SETUP` (后者本机 undeclared); ④ `HistoryDealGetInteger(deal, DEAL_MAGIC/DEAL_ENTRY)` 与 `HistoryDealGetString(deal, DEAL_SYMBOL)` / `HistoryDealGetDouble(deal, DEAL_PROFIT/SWAP/COMMISSION)` 都是 **1 参 ticket + property** 形式 (与 position 侧一致), 写成 2 参才报 199。写前拿 3 行探针逐个验 property 名, 或直接抄 §2a 上面 GoldScalpClone 的现成 grep 表。

## §3 单指标画不了 8 条跨品种线 — 架构决定
一个 MQL5 indicator 只属于"它挂的那个品种"的图, 副图数据 buffer 按该图品种的 K 线列展开。所以:
- **"8 个货币对同屏各一条强弱线" 单个 indicator 做不到。** 正确落法: indicator 挂在某一个品种图上, 它的 buffer 值 = **该品种在 8 篮子中的分位 (0-100)**; 想看 8 个就把 indicator 在 8 个品种各挂一个 (8 张副图), 或用 EA/面板 `iCustom(..., quantile)` 一次读 8 个分位画在一张图上。
- 先跟用户确认他要"单品种相对分位"还是"8 线同屏" — 前者一个 indicator 就够 (模板), 后者要 EA 面板或 8 份 indicator。
- 跨品种读价本身没问题: `iClose("USDJPY", PERIOD_CURRENT, shift)` 在挂 EURUSD 的图上完全合法。

## §4 shift 索引与回看窗口
- `iClose(sym, PERIOD_CURRENT, shift)` 的 `shift` 是从**当前(最新)K线=0**往回数。回看窗口锚点 `lookback = i - InpAnchorBars` (i 是 buffer 行号, 0=最旧) 时, 注意 buffer 行号 0 是历史端: 前 `InpAnchorBars` 行没有更早的锚点, 必须 `if(lookback<0) { buf[i]=EMPTY_VALUE; continue; }` 否则最早几根会算错/越界。
- `OnCalculate` 增量: `start = (prev_calculated>0)? begin : MathMin(InpAnchorBars, rates_total-1)`, 首次从 `InpAnchorBars` 起算, 后续只算新 bar。
- 跨品种 `iClose` 在某 shift 拿不到 (品种刚添加/数据未加载) 返回 0 或 -EMPTY_VALUE, 做 `if(c<=0) continue` 保护, 别让 0 进分位算错。

## §5 交付话术 (给李老师, 大白话 + 丑话)
- 一句人话说清数字含义: "挂在某个品种上, 副图那条线是它今天比另外 7 个强的程度, 0=最弱 100=最强"。
- **必说丑话 (同族"高胜率≠正期望"):** "这个强弱图帮你把 8 个缩到最强/最弱 2 个做候选, 但不保证拿最强打最弱就赚 — 惯性会不会断、断在哪、止损放哪、拿多少仓, 还得走系统五验闸; 这只是筛选不是稳赚。" 别把 indicator 吹成印钞机, 用户朋友测试时别丢脸。

## §7 净值还原 / deal 历史指标 (2026-10 净值还原指标落地, 永久)
**铁律0: 净值 equity ≠ 余额 balance — 客户交付前必核对口径 (官方 775369 博客)。**
- **净值 = 余额 + 当前持仓浮动盈亏**。余额只在平仓/存取款时变, 所以"余额回撤"只量已实现亏损的连续段; **净值回撤才量账户真正掉到过的最深处 (含后来回本的浮亏)**。对扛单/网格/马丁, 余额回撤看着温和、净值回撤可能差 3 倍——**触发强平看净值不看余额**。客户问"回撤/净值"默认给净值口径, 别只报余额。
- 但 deal 历史**只能重建"已实现净值路径"** (官方 23175 明说: 要还原浮动净值得喂净值快照序列, deal 里没有)。所以指标里历史段拿不到盘中/多日持仓浮亏——只能"已实现路径逐笔折叠 + 末根K线叠加当前实时浮动"。**做这类指标务必在面板/交付话术标清口径: "历史曲线=已实现净值(不含盘中浮亏), 仅末端叠加实时浮动; 扛单/网格/马丁的真实净值回撤可能更深"** —— 不标=误导客户 (卖家常犯的错就是只给较小的那个数字)。

**铁律1: MQL5 deal 属性里没有 `DEAL_EQUITY` / `DEAL_BALANCE` 快照** — 这是最大的坑。deal 只提供 `DEAL_PROFIT`/`DEAL_SWAP`/`DEAL_COMMISSION`/`DEAL_TIME`/`DEAL_TYPE`/`DEAL_ENTRY`/`DEAL_VOLUME`/`DEAL_PRICE` 等,**没有逐笔的 equity/balance 数值**。所以"逐笔重建净值曲线"唯一正确做法 = **从起始资金逐笔累加已实现净影响 (profit+swap+commission)**, 这不是抄 MQL4, 是 MQL5 官方 23831 文章的标准做法。

**净值还原指标架构 (三轨线 + 回撤DNA + 统计面板):**
- **历史段净值 = 逐笔折叠余额**: 每笔 deal `run += profit+swap+commission` (存取款/利息/调整/佣金单都是 deal, 全被折叠进去, 密度远高于 MT5 自带小时级快照)。
- **末根K线叠加实时浮动**: 历史 deal 只有已实现部分, 当前未平仓头寸的浮动盈亏不在 deal 历史里 — 用 `PositionsTotal()` + `PositionGetDouble(POSITION_PROFIT/POSITION_SWAP)` 现算, **只加到最后一根 K 线** (前向填充法: 双指针 O(n+m) 扫 deal→bar)。
- **三轨**: ① 净值线(余额+实时浮动, 金) ② 余额线(逐笔已实现, 蓝) ③ 峰值线(高水位, 灰虚)。净值线 vs 余额线 缝=浮动盈亏; 净值线 vs 峰值线 缝=回撤(水下区)。
- **回撤DNA (官方 23175)**: 峰值→谷底→恢复, 算 Ulcer Index(回撤平方根均值)、Pain Index(回撤绝对值均值)、水下时间占比 (bar 数低于高水位的占比)。最大回撤的峰/谷用 `OBJ_ARROW` (箭头码 233=↑峰值绿, 234=↓谷底红) + `OBJ_TEXT` 标注。锚点锚用 `ANCHOR_BOTTOM`(峰值箭头) / `ANCHOR_TOP`(谷底箭头) — **MQL5 没有 `ANCHOR_LOW`/`ANCHOR_HIGH`** (error 256), 只有 LEFT/RIGHT/TOP/BOTTOM/CENTER。
- **客户交付级必做: 回撤区间表(episodes) + Recovery Factor, 别只报"最大回撤 X%"一个数** (两个策略最大回撤都 18% 可以是完全不同的风险形状)。官方 23175 `DetectEpisodes` 把水下曲线切成离散区间, 每区间记 峰值时间/谷底时间/恢复时间(末段未创新高要诚实标 ongoing, 别假装已恢复)/深度%/水下 bar 数, 面板按深度列前 N 条。再加 **Recovery Factor = 净盈利 ÷ 最大回撤货币值** (策略测试器同口径, <1=没赚回最惨那次亏损)。整套=次数/平均深度/最长水下/水下占比/Ulcer/Pain/Recovery, 客户和风控看的是这一组不是单点。
- **CSV 导出(客户留档)**: `InpExportCurveCSV`/`InpExportDealsCSV` 两个 input 开关, 净值曲线(时间/已实现净值/峰值/回撤%)和逐笔成交明细写 `MQL5\Files\JCEquityCurve_<login>.csv` (FILE_WRITE|FILE_CSV|FILE_ANSI 逗号分隔), 客户下载留档。**导出只跑一次** (`g_exported` 标志), 别每 tick 刷文件。客户要"务必功能完善"= 曲线 + 回撤DNA区间表 + Recovery Factor + 账户信息(币种/杠杆/保证金/余额/净值, 实读 `AccountInfoDouble`/`AccountInfoInteger(ACCOUNT_LEVERAGE)`) + 今日盈亏(对齐日亏熔断) + CSV 导出 + 口径诚实标注, 一套齐活。
- **统计面板** (Comment 多行, 大白话): 总收益/年化CAGR/最大回撤/Ulcer/Pain/水下占比/Sharpe(日收益√365)/Sortino/胜率/盈利因子/最大连亏/今日盈亏(对齐日亏熔断纪律, 阈值可改 input)。
- **MQL5 存取款 deal 类型是 `DEAL_TYPE_BALANCE`/`DEAL_TYPE_CHARGE`/`DEAL_TYPE_CREDIT`/`DEAL_TYPE_BONUS`, 不是 `DEAL_TYPE_DEPOSIT`/`DEAL_TYPE_WITHDRAW` (后者不存在, error 256)。** 判存/取款方向用 `DEAL_PROFIT` 正负 (正=存款, 负=取款)。
- **`TimeToString(t, flags)` 的 flags 用命名常量** `TIME_DATE|TIME_SECONDS` / `TIME_DATE|TIME_MINUTES`, 别用裸数字 `0`/`2` (裸 0 不是合法组合)。
- **对拍验证 (Python 直连 MT5)**: 金策引擎的 `ate` venv 有 mt5 包 (`C:\Users\ASUS\.workbuddy\binaries\python\envs\ate\Scripts\python.exe`, 5.0.5735)。写个一次性脚本 `mt5.initialize(r"...terminal64.exe", timeout=60000)` attach 引擎终端 → `history_select(0, now+3600)` → `history_deals_get()` → 折叠对比 `ACCOUNT_BALANCE` (差值≈初始本金=证明无遗漏无重复)。指标算完后务必跑这个对拍, 别只靠编译 0 错。

## §6 高频剥头皮 EA 深度优化 16 处 (2026-10 掘金EA 系列落地, 永久)
从"能编译"升级到"实盘不卡不假开单"的 5 个必做项, 按优先级排:
1. **指标句柄 + CopyBuffer 取值守值**: `OnInit` 里 `g_hAtr=iATR(sym,PERIOD_M1,period)` / `g_hFma=iMA(sym,PERIOD_M1,fast,0,MODE_EMA,PRICE_CLOSE)` 建一次, 每 tick 用 `CopyBuffer(h,0,bar,2,buf)` 取 2 个值, **取 buf[1](上一个已收盘 bar), 不取 buf[0](当前未收盘, 会抖)**。禁止每 tick 直接调 `iATR/iMA` 函数(会新建 indicator, 句柄泄漏 + 卡死)。
2. **信号只用已收盘 bar1/bar2 比较, 不碰 bar0**: `EMA5 vs EMA12` 信号取 bar1/bar2 两根已收盘 K 线的值, 避免 bar0 未收盘时 EMA 反复翻转 → 假开单。`if(f1>s1 && f2>s2) return BUY` 这种结构。
3. **新 bar 判定加时间轴连续性检查**: `if(iTime(sym,PERIOD_M1,0)!=iTime(sym,PERIOD_M1,1)+60) return;` 周末/节假日跳 bar 时 bar0 和 bar1 时间差>60s, 不满足条件就误判成新 bar 触发, 加这条能防误判。
4. **持仓超时强平用 `CTrade::PositionClose(ticket)`**: 内部自动按持仓方向选 Bid/Ask 平仓, 不用手算 `closePt=(type==BUY)?Bid:Ask`。手算价在高频下容易因滑点/点差扩开导致平仓单被拒(10008/10018), 反而卡住强平逻辑。
5. **已平仓扫描加 2s 节流**: `HistorySelect(0,TimeCurrent())` + 全量 deal 扫描是高频 EA 卡终端的头号隐患(每 tick 重选历史 O(N) 扫 2000 条), 加 `if(TimeCurrent()-g_lastHistLoad<2) return;` 降到 2s 一次, 对连亏/日亏熔断统计无影响(平仓成交间隔本就>2s)。
6. **手数归一化到品种步长**: 直接传 `InpBaseLot` 进 `g_trade.Buy(lot,...)` 在 `SYMBOL_VOLUME_STEP>0.01` 的 broker 上会拒单。开单前 `lot=MathFloor(lot/vstep+0.5)*vstep`, 再 clamp 到 `[vmin,vmax]`。XAUUSD 在多数 broker 上 vstep=0.01 无影响, 但在 EC 类 broker 上可能 0.001 步长。
7. **Stop Level 合规**: `SL/TP 距入场价 < 品种最小止损距离` 时 `g_trade.Buy` 返回 `TRADE_RETCODE_INVALID_STOP`。开单前 clamp: `int slLvl=(int)SymbolInfoInteger(g_sym,SYMBOL_TRADE_STOPS_LEVEL); double stoplevel=slLvl*pt;` 注意 **`SYMBOL_TRADE_STOPS_LEVEL` 用 `SymbolInfoInteger` 不用 `SymbolInfoDouble`**, 本机 build 走 Double 版报 error 262 cannot convert enum。若 `sl` 距入场 < stoplevel 就向外推 stoplevel。
8. **数据就绪闸**: 终端刚连上或报价缺失时 `Bid/Ask/Point` 可能全 0, 垃圾价开单是最常见的假开单来源。OnTick 开头 `if(bid<=0||ask<=0||pt<=0) return;` 三值全非零才继续, 同时验证 `ask>=bid`(正常点差为正则 ask>bid, 若异常反转也 return)。
9. **浮亏强砍(错快砍)**: 不等 SL 被扫, 价格向不利方向走完 `InpHardCutMult × SL距离` 就立即 `PositionClose`。计算公式: `adverse=(type==BUY)?(openPx-cur):(cur-openPx); if(slDist>0 && adverse>=g_hardCutMult*slDist) PositionClose();` **不用绝对 PnL 金额**(PnL 与手数/点值挂钩, 不同账户不可比), 用价格距离比例。默认 0.5(砍到 SL 距离的一半就出)。
10. **deal ticket 去重**: `HistoryDealsTotal()` 返回的 deal 列表里同一笔平仓可能对应多个 deal(买入 deal + 卖出 deal + 手续费 deal), 直接累加会重复计连亏。用 `static uint seenDeals[2000]; static int seenN=0;` 定长去重数组, 换日时 `seenN=0` 清零。注意 `HistoryDealGetTicket` 返回 `uint`, 与 `ulong` 比较要 `(uint)` 强转否则 warning 43。
11. **净浮亏开单闸**: 开单前检查当日 net realized PnL(含 swap+commission)是否超过 `InpNetFloatMaxPct% × 账户余额`, 超过则停开新单。比 equity 快照更精确(equity 含浮动盈亏, 高频剥头皮浮动小但已实现累计大时 equity 没跌但已亏不少)。
12. **`g_trade.ResultRetcode()` 验证开单**: `g_trade.Buy()` 返回 `true` 只代表本地发送成功, 服务器端可能拒单(retcode≠0)。开单后读 `g_trade.ResultRetcode()` 确认 `==TRADE_RETCODE_DONE` 才算真开成; 拒单时 Print 出 retcode + 当时 sl/tp + stoplevel 供排障。
13. **加仓去重(同向+同间距档位, 防重复触发)**: 盈利加仓判断 2s 跑一次, 浮盈和间距都达标就加——但若不记档, 同价位可能被连续触发两次。记 `g_lastAddDir`(方向) + `g_lastAddTier`(间距档位 = int)(dpts/InpAddSpacingPoints)`, 同档位已加过就不重复加; 开新首单时档位清零。同向金字塔策略标配。
14. **当日盈亏按魔术号全品种统计(不只当前图)**: EA 可能同时挂多品种, 当日已实现/浮动盈亏必须跨品种按 `InpMagic` 统计(`HistoryDealsTotal` 遍历全 deal 按 `DEAL_MAGIC==InpMagic` 过滤, 不平 `DEAL_SYMBOL`), 总止盈/净亏闸判得才准。只统计当前图品种会漏掉其他图上的持仓/已平仓, 总止盈失准。
15. **图表面板(OBJ_LABEL 实时状态, 面板挂了不影响交易)**: `OBJ_LABEL` 创建用 `ObjectCreate(0,name,OBJ_LABEL,0,0)`(5 参, 无 x/y——x/y 走 `OBJPROP_XDISTANCE/YDISTANCE`), 配 `OBJPROP_CORNER/CORNER_LEFT_UPPER`。面板纯展示, 崩了不影响交易(面板和交易逻辑分开)。盈利绿/亏损红自动变色, 挂上就能看见它在干嘛, 不用翻日志。
16. **面板/日志双留痕(展示层与交易层解耦)**: 面板 `OnTimer` 2s 节流刷新, 交易逻辑(开仓/加仓/强砍/总止盈)独立跑, 面板崩了不影响交易。面板显示: SAR 方向/ZZI 方向/浮盈点数/加仓次数/当日盈亏美金/持仓张数/净亏闸状态, 共 8 行。

## §8 MetaEditor64 命令行编译器静默罢工排查 (2026-10 掘金EA 踩坑, 永久)
编译器偶尔对某些文件静默不编译: 前台 `bash` 直调 `MetaEditor64.exe /compile` 后 8-15s 既无 log 也不出 ex5 (exit=0 也白搭), 但同一台机刚编过的小文件能过。这不是代码问题, 是编译器进程状态卡了。排查顺序:
1. **先确认编译器本身还活着:** 重编一个已知能过的文件 (CRR 指标/之前成功的 EA 的 ex5 不删, 对照时间戳), 它也编不动 = 编译器卡, 不是新文件的问题; 能过 = 新文件本身有错, 看 log。
2. **杀进程重启:** `taskkill //F //IM MetaEditor64.exe` 后重新编译, 有时活过来。
3. **PowerShell 同步调用 (最稳):** 写独立 `.ps1` 文件 `& $ED /compile:"..." /log:"..."` + `Start-Sleep 8` + `Get-Content -Encoding Unicode` 读 log, 再 `Test-Path ex5` 验收。比 bash 直调可靠, 比 `Start-Process -Wait` 更稳。bash 直调经常静默失败, PowerShell 同步调能正常出 log+ex5。
4. **仍编不出 = 源码有真错:** log 会有 `Result: N errors` 行, 按 error 行修代码再编。别拿"编译器卡"当借口掩盖真错——先按 (1) 对照判别。
5. **对照判别铁律:** 同一台机 5 分钟前刚编过 A 能过, 现在编 B 不出 ex5 且 log 空, 但编 CRR 也不出 → 编译器卡, 修 (2)(3); CRR 能出但 B 不出 → B 有错, 看 B 的 log error 行。

## §8a EA 图表面板 OBJ_LABEL 创建 (2026-10 掘金EA v3 落地)
面板 = 左上角 `OBJ_LABEL` 控件, 交易逻辑与面板解耦(面板崩不影响交易)。关键 API:
- **`ObjectCreate(0,name,OBJ_LABEL,0,0)` 是 5 参**(0 图表句柄 + name + type + 主窗口 subwindow + x + y, 但 OBJ_LABEL 的 x/y 走 `OBJPROP_XDISTANCE/YDISTANCE`, 创建时 x/y 位置参数填 0 即可)。**写 6 参 `ObjectCreate(0,nm,OBJ_LABEL,0,0,0,0)` 报 error 199 wrong parameters count。**
- 定位: `ObjectSetInteger(0,nm,OBJPROP_CORNER,CORNER_LEFT_UPPER)` + `OBJPROP_XDISTANCE` + `OBJPROP_YDISTANCE`。
- 颜色: `ObjectSetInteger(0,nm,OBJPROP_COLOR,color)` — 类型名是 `color` 不是 `clr` (MQL5 里 `clr` 不是合法类型名, 报 error 256; `color c1=...` 才是对的; 常量仍叫 `clrLime`/`clrTomato`/`clrDimGray`)。
- 字体: `ObjectSetString(0,nm,OBJPROP_FONT,"Consolas")` + `OBJPROP_FONTSIZE`。
- 背景: `ObjectSetInteger(0,nm,OBJPROP_BGCOLOR,C'30,30,45')` (C'r,g,b' 字面量)。
- 销毁: `OnDeinit` 里 `ObjectDelete(0,nm)` 全删。
- 面板刷新在 `OnTimer` 2s 节流里做, 每 2s 刷 8 行状态 (SAR/ZZI/浮盈点数/加仓次数/当日盈亏/持仓张数/净亏闸), 面板纯展示不影响交易。

## §8c MQL5 纯 Python 回放脚本的常见语法坑 (2026-10 掘金EA 同分母回测, 永久)
写"独立 Python 回放脚本"(如 `juejin_backtest.py` 这类不进引擎的 scratch 回测) 时, 本机踩过三个高频错:
1. **`np.genfromtxt(path, names=True)` 读不到列名**: 若 CSV 首行被识别为数据行(非 header), `names=True` 会报 `no field of name 'high'`。最稳的是**不带 names**, 按列下标取 `d[:,2]/d[:,3]/...`, 自己定义列顺序(open/high/low/close/...)。带 `skip_header=1` 且不加 names 最可靠。
2. **函数返回元组与调用侧解包不匹配**: 一个函数写成 `return sar` 但调用侧 `sar,_ = f(...)` 报 `too many values to unpack (expected 2)`; 或声明返回多值实际只 return 一个。改前先在函数签名注释写清返回结构, 调用侧对齐。
3. **字符串字面量尾挂多余字符**: `out["k"]="..."]` 结尾多一个 `]` 造成 `SyntaxError: unmatched ']'`。写大 dict 赋值后立刻 py_compile, 别攒到最后。
通则: 回测脚本写完 `python -m py_compile X.py` 第一道 + 实跑看 `data/*.json` 落盘(读回 verdict 字段), 别只信脚本 exit=0。

## §8b MQL5 指标趋势线用 SMA 不用 EMA (2026-10 ZZI v2 数学 bug)
做"趋势过滤"判断斜率时, **趋势参考线必须用 SMA, 不能用 EMA**。EMA 永远跟着最新价走, 斜率几乎恒正 (价格每动一下 EMA 就拉一下), 趋势过滤等于没开。SMA 斜率: 本根 SMA 值 >= 前一根 SMA 值 = 向上; <= = 向下; 平 = 0 不交易。MA 句柄 `iMA(sym,tf,period,0,MODE_SMA,PRICE_CLOSE)`。
