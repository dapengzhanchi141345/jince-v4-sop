---
name: mt4-ea-replication
description: Use when 从 MT4 观摩账号成交数据逆向复刻/重写一个能跑的 MQL4 EA 并交付。
---

# MT4 EA 逆向复刻（从成交数据重建 .mq4）

Class of task: 用户给一个 MT4 观摩账号(或 F2 导出的 `Statement.htm` 全量成交文件)要"深度分析并复刻/写一个更完美的 EA"。目标不是改终端, 是把**该账号在某个日期窗口内的操作行为反推成一套可回测的 MQL4 EA**, 编译 0 错后交付。姊妹技能: `mt4-terminal-data-export`(怎么拿到数据) + `mt5-indicator-authoring`(编译/验收套路通用)。

## 铁律（每次必守）
- **只按用户指定的日期窗口算指标**。全量 `Statement.htm` 常混着"旧策略"和"新策略"两段(策略换过), 用户会明说"只分析 8 月后/某日之后的"。**动手前先问清窗口**, 用 `odt>=datetime(Y,M,D)` 过滤后再算, 绝不拿全量套。
- **复刻要落到行为指纹, 不是抄信号**。观摩账号里跑的是别人家/另一台电脑的 EA(用户会强调"不是本地的"), 本地 MQL4 目录里的旧 EA 是残留、别当依据。依据 = 成交记录本身反推: 手数/并发/节奏/时段/方向/盈亏比。
## 交付边界
- **只有编译体没有源码**: 客户/观摩方只给 `.ex4`/`.ex5`, 拿不到源码——**不要在反编译工具上纠缠**(ex4decomp 等工具公开下载链接全 404, 见 `ea-restriction-crack` 的"只有编译体"节), 直接走**行为指纹复刻**: 从 `Statement.htm` 成交数据反推参数(手数/并发/时段/节奏), 占位信号留可替换口, 交付时在说明里写清"占位信号=MA交叉, 真实入场逻辑待源码后替换"。
- **交付边界**: 只读观摩账号, 产出的 EA 是"复刻原型", 默认 0.01 手 demo 级; 实盘前必回测对拍原窗口指标(PF/胜率/净利)。挂单/实盘走 `mt5-multiagent-trading` 五验闸, 本技能不管实盘。
- **汇报大白话**: 黑话/缩写翻成人话, 数字给结论。用户提的"先知源/时差套利"这类原理, 先确认"接不接真源": 不接就留成**可填入口**(默认关), 不瞎接。

## 工作顺序
1. **解析 `Statement.htm` 全量成交**（复用 `scripts/parse_statement.py` 的思路）：`re.findall(r'<tr[^>]*>(.*?)</tr>', raw, re.S)` 逐行 → 每行 `<td...>` 取列, 按 colspan 展开对齐；`Buy/Sell` 行才有效(过滤 Balance/Deposit/Comment 行)。提取每笔: 类型/手数/品种/开价/SL/TP/净利/开仓时刻/平仓时刻。持仓秒=`cdt-odt`。**时间列可能空, 容错**(空 close 记 0, 别崩)。
2. **按用户窗口过滤后算"操作指纹"**（这是复刻依据, 一次算全）：
   - 总量/净利/盈亏比 PF/胜率; 每笔净=净利/笔数。
   - 手数分布(通常 99% 单一小手数)、品种分布。
   - **峰值并发**: 把每笔 (odt,+1)(cdt,-1) 事件排序扫描, 记 `cur/peak` 和分日 `daypeak`——定 EA 的最大并发闸门。
   - **开单间隔** 与 **持仓** 的分位(P10/P50/P90)——定剥头皮节奏(中位持仓是秒级还是分钟级)。
   - **时段门**: 按服务器时 hour 分桶算净利+胜率, 排最好/最差几小时(注意区分"服务器时"和"UTC", 汇报时说清)。
   - **进出场模式**: 开仓时 SL/TP 是否预设(裸单 vs 挂止损)、赢单 vs 亏单持仓时长对比(判断"错得快砍对的多跑"与否)。
   把这套指纹存 `spec_*.json` 备查, 汇报成一张表。
3. **写 `.mq4` 镜像指纹**（build 14xx 兼容, 见 `mt4-terminal-data-export` 步骤2/3）：用经典 MQL4 API(`OrderSend/OrdersTotal/OrderSelect(...,SELECT_BY_POS,MODE_TRADES)/iMA/iATR/iTime/AccountEquity`), 指纹逐条映射成 input 参数(手数→基准手数, 峰值并发→`InpMaxPositions`, 时段→好/坏时段门, 节奏→ATR 虚拟 SL/TP+最大持仓)。"先知源/快报价"原理留成 `InpUseFastSource`+`InpFastSourceFile` 可填入口, 默认关。加原版没有的风控(日亏熔断/连亏冷却/点差闸) = "更完美"。
4. **探针→编译→验收**(复用 `mt5-indicator-authoring` 套路)：先拿最小 .mq4 探针编译一遍, 确认本机 build 哪些函数名可用(`OrderClose` 返回、动态数组 `int arr[]` 要 `ArrayResize` 或定长、`InList` 签名), 再写正式版。`metaeditor.exe /compile:<abs> /log:<abs>` 出 0 错且 `.ex4` 在源旁真实存在才算成(日志 UTF-16LE, 无空格路径不套引号)。
5. **交付**：`.mq4`(源码)+`.ex4`(编译体)+大白话 `说明.txt`, 拷进 `E:\\workbuddy\\内容中心\\交付\\<名>\\`(铁律: 内容归内容中心), 附**回测对拍指引**(挂 XAUUSD M1、Every tick、回测同窗口, 目标贴近原 PF/净利)。

## 交付记录
- **客户青岛账户 EA 复刻**(纯客户行为指纹, 不掺金策策略): `E:\workbuddy\内容中心\交付\青岛客户EA复刻\`(Qingdao_GoldScalp_Clone.mq5/.ex5, MT5 版, 已升级 v2)。账户 88803002 是**客户的**, 非李彦明自己; 李彦明演练账户是 60137964, 别混。指纹: 0.30手/并发2/日≤3单/TP=SL=360价格点(1:1)/最小间隔2h/拉黑 01,04,17,19,23 时(服务器时)/72h超时强平; 占位信号=MA9 EMA vs MA50 SMA(客户真实信号未提供, 留替换口)。
- **v2 多账户融合**(客户要"所有优点全吸收"): 新增三账户指纹徐总905015(7777笔+\$35k,0.01手超高频,峰值并发22,88.5%利润来自2.3%大单)/新建20011176(49025笔,8月起41614笔+\$12.6k,回撤仅0.7%,盈亏比1.31,14-16点赚,12/22/0点亏)。共性优点做成默认关可选 input: 防裸单(默认开)/三账户合并时段拉黑/连亏冷却(含历史回看)/高置信时段放大手数(徐总88.5%利润依据)/放宽并发。全部默认关、原版零改动, 用户逐条开。
- **提炼成金策自有纪律**(客户要求"做成我们自己的"): 客户共性优点不止进客户 EA, 还要落到我们系统——trader_brain.py 开单大脑加 ④.5 盈亏比闸(TP/SL≥1.3, 源自新建号1.31), 默认生效; 演练号 60137964 挂"人工操盘演练纪律卡"(4道闸: 黄金时段14/15/16点+盈亏比≥1.3+0.01~0.02手+错就快砍, 复现新建号0.7%回撤/1.3盈亏比)。提炼结论 + 待同分母回测项写进 `strategy-rd/研究台账.md`, 交 @strategy-rd 五验。
- **本机 build 探针先行铁律(2026-10-07 v2.2 一轮编译 3 次 0 错铁证落地)**: 给本机 TMGM build 写 EA 前, 任何"照老书抄"的 API 签名都先拿 3-5 行探针验: 探针里 `iTime(sym,PERIOD_M1,0)` 3 参标量返回 datetime 可用(不用 CopyTime 句柄)、`iATR`/`iMA` 返回 int 句柄(不是 double, 用 `CopyBuffer` 取值)、`iTime` 连续性判断 `iTime(M1,0)==iTime(M1,1)+60` 在新 build 0 错、`SymbolInfoInteger(SYMBOL_TRADE_STOPS_LEVEL)` 不是 `SymbolInfoDouble`、deinit 枚举没有 `REASON_CHART_CHANGED` 只有 `REASON_PARAMETERS`(=4)、`input int arr[]` 在部分 build 报 285 用定长标量 `InpBlockH1..H5`+`ArrayResize` 替代。一次编译 5 错全在探针 30s 内可预判的签名上, 不预判就一次烧 5 轮编译循环。**深度优化多轮叠加(5项→12项→5项共 22 处)时, 每一轮都先 3 行探针验新用的 API, 别假设上一轮编译过的用法在本轮还能用**(build 升级 / 多账号 / 多品种都可能让签名变)。本轮 22 处深度优化最终 `Result: 0 errors, 0 warnings, 2172 ms elapsed, cpu='X64 Regular'`, .ex5 46KB 同步到 MT5 Experts + 交付目录。
- **`MathMax`/`MathMin` 本机 build 只收 2 参, 3 值取最大要嵌套**: `MathMax(a,b,c)` 报 error 199 满屏级联(同一位置重复 10+ 行)。写 `MathMax(MathMax(a,b),(double)c)`; int×double 比较给 int 侧强转 `(double)` 防 warning 94。写 SL 距离/手数归一化前拿 1 行探针确认 `MathMax` 参数量, 别照多参老书抄。

## MT5 版复刻的 build 坑(本机 TMGM MetaEditor64, 2026-10)
- 本机只有 MT5 编译器(`C:\Program Files\TMGM MT5 Terminal\MetaEditor64.exe`), 编不出 .ex4; 客户行为指纹与平台无关, 出 .mq5 即可, 说明里写清平台差异。
- 该 build 的签名与老书不同, 一律探针先行: `iMA` 是 **6 参** `(symbol,period,ma_period,ma_shift,ma_method,applied_price)`(带/不带 shift 都试过, 就 6 参 0 错); `DoubleToString`(不是 DoubleToStr); 历史订单时间枚举是 `ORDER_TIME_SETUP`(不是 ORDER_TIME_OPEN/ORDER_TIME_TRADE); `CTrade::PositionClose(ticket)` 单参; 订单开仓时间用 `HistoryOrderGetInteger(t,ORDER_TIME_SETUP)`。编译: `MetaEditor64.exe /compile:<mq5绝对路径> /log:<log绝对路径>`, 日志 UTF-16, 0 错且 .ex5 生成才算成。
- **`SYMBOL_TRADE_STOPS_LEVEL` 用 `SymbolInfoInteger` 不用 `SymbolInfoDouble`**: `SymbolInfoDouble(g_sym,SYMBOL_TRADE_STOPS_LEVEL)` 在本机 build 报 `error 262 cannot convert enum` + `error 199 wrong parameter count`。正确写法: `int slLvl=(int)SymbolInfoInteger(g_sym,SYMBOL_TRADE_STOPS_LEVEL);` 再 `double stoplevel=slLvl*pt;`。同理 `SYMBOL_TRADE_FREEZE_LEVEL` 也走 Integer 版。写 EA 前拿 3 行探针验证 `SymbolInfoInteger/Double` 哪个不报 262。
- **CTrade Limit 家族要传满 8 参才能带 comment**: `trade.BuyLimit(lots, price, _Symbol, 0, tp, "x")` 6 参调用报 `error 262 cannot convert enum`(第 6 参是 ENUM_ORDER_TYPE_TIME, 跳不过去), 正确 = `trade.BuyLimit(lots, price, _Symbol, 0, tp, ORDER_TIME_GTC, 0, "x")` 全传。市价族 Buy/Sell 是 6 参 `(lots, symbol, price, sl, tp, comment)`(symbol 在第 2 参, 与 Limit 族顺序不同)。别用三目 `? Buy(...) : BuyLimit(...)` 混两种重载——类型推导撞 enum 报 262, 拆 if/else。
- **源文件放不可写目录时改用 /inc 指向 datafolder**: `C:\Program Files\...\MQL5\Experts` 无写权限时, 源放用户目录编: `MetaEditor64.exe /compile:<用户目录abs.mq5> /log:<abs.log> /inc:<datafolder>\MQL5`。`/inc` 必须指 **MQL5 根**(含 Include\ 的目录), 指到 `Include` 会拼成 `Include\Include` 报 file not found; datafolder 用 `C:\Users\ASUS\AppData\Roaming\MetaQuotes\Terminal\<hash>\MQL5`(含 `Include\Trade\Trade.mqh` 的那个 hash, 本机 7643C0B9/A3B1DF 两个都是活 MT5 安装)。
- **`REASON_CHART_CHANGED` 不存在于本机 build 的 deinit 枚举**: `OnDeinit` 里写 `reason!=REASON_CHART_CHANGED` 报 `error 256 undeclared identifier`。本机可用的是 `REASON_PARAMETERS`(参数变更=4)、`REASON_REMOVE`、`REASON_PROGRAM`、`REASON_CHART`(=8, 注意没有 `_CHANGED` 后缀)。写 deinit 逻辑前用 3 行探针验哪个枚举名能编译过, 别照老书抄。
- **`input group` / `input` 数组多值参数在本 build 会报 error 285**: 时段门等用**定长标量 input**(`InpBlockH1..H5`)+`OnInit` 里 `ArrayResize` 进定长 `int arr[5]`, 不写数组 input。
- 探测 build 可用符号时别递归扫 `C:\Program Files`(WindowsApps 会 PermissionError), 只扫已知 MT 安装目录一级。
- **高频剥头皮 EA 深度优化 12 处(2026-10-07 v2.2 落地)**: 指标句柄 CopyBuffer / 已收盘 bar / iTime 连续性 / PositionClose / 历史扫描 2s 节流 / 手数归一化 / StopLevel 合规 / 数据就绪闸 / 浮亏强砍(价格距离比例) / deal 去重 / 净浮亏开单闸 / ResultRetcode 验活。详见 `mt5-indicator-authoring` 技能 §6。
- **本机 build 的 1 参 Position*/History* 属性读法 + 未声明枚举清单(2026-10 王金光复刻实测, 与 GoldScalpClone 同 build)**: ①持仓属性读法用 **1 参形式** `PositionGetTicket(i)` 取 ticket 后直接 `PositionGetString(POSITION_SYMBOL)` / `PositionGetInteger(POSITION_MAGIC|POSITION_TYPE|POSITION_TIME)` / `PositionGetDouble(POSITION_PRICE_OPEN|POSITION_PROFIT|POSITION_SWAP|POSITION_SL|POSITION_TP|POSITION_VOLUME)` —— **不是 2 参 `PositionGetInteger(ticket, POSITION_MAGIC)` 形式**(2 参形式在本 build 报 error 199/262 满屏级联, 但 1 参形式 0 错); ②`POSITION_TIME_SETUP` / `DEAL_TYPE_ENTRY_IN` / `DEAL_ORDER_TYPE` / `DEAL_TYPE` 都**不存在**(报 256 undeclared); 成交类型判进出场用 `HistoryDealGetInteger(deal,DEAL_ENTRY)` 配 `DEAL_ENTRY_IN` / `DEAL_ENTRY_OUT` / `DEAL_ENTRY_OUT_BY`; ③订单方向(买/卖)无法从 deal 直接取(DEAL_ORDER_TYPE 缺), 单方向日开单计数改**内存计数器**(OpenLeg 成功时 `g_dayBuyOpen++/g_daySellOpen++`, 日切归零, 重启清零), 比扫 deal 更稳也不依赖缺失枚举; ④`DEAL_MAGIC`/`DEAL_SYMBOL`/`DEAL_PROFIT`/`DEAL_SWAP`/`DEAL_COMMISSION`/`DEAL_ENTRY` 都可用, 配 1 参 read 即可。写 MQL5 EA 前拿 3-5 行探针验这些签名, 别照网上 2 参老书抄。

## EA “不运行”根因定位 SOP（2026-10-07 GoldScalpClone 20011176 落地, 永久）
用户报“EA 不运行”时, 按这个顺序定位, 别改逻辑改到崩：
0. **先确认 EA 真加载了(读 UTF-16 终端日志, 别只看 .ex5 在不在)**: `.ex5` 拷进 `MQL5\Experts\` ≠ 已挂载。终端日志 `C:\Users\ASUS\AppData\Roaming\MetaQuotes\Terminal\<hash>\logs\2026*.log` 是 **UTF-16LE**(直接读会满屏 `\u0000` 乱码, `read_file` 按 UTF-8 解也读不出——必须 `iconv -f UTF-16LE` 或 python `open(f,'rb').read().decode('utf-16-le')` 才读得见内容)。grep 两行: ① `expert <EA名> ... loaded successfully` ② 你 OnInit 里那句自定义 `Print("<前缀> attached: ...")`。**两行都没有 = 终端根本没重新加载(EA 没挂上/没 Ctrl+F5/算法交易被禁), 客户那句“挂了不动”多半是这层, 不是逻辑 bug**。本机有多个终端 datafolder(7643C0…/A3B1DF… 等), 拷错目录就永远加载不到——先确认客户挂的是哪个终端再往那个 Experts 里放。用户会说“客户ea没在我的电脑运行 你自己系统检查”——够不到客户机时, 本地同类终端日志 + 代码静默分支审计就是你的检查面。
1. **先分语言平台**: 看 `.ex4`(MQL4)/`.ex5`(MQL5) 还是 `.mq4`/`.mq5` 源码。若给的是 **MQL4 源码(.mq4)** 但本机**只有 MT5 编译器(MetaEditor64.exe, 无 MT4 终端/编译器)**, 那它在本机**永远跑不起来** —— 拿 MetaEditor64 编 .mq4 第一行就报 `error 208: unsupported file extension`(被当 MQL5 强行解析, Bid/Ask/OrderSend/OrdersTotal/OrderSelect(MODE_TRADES) 全未声明)。这是“不运行”的头号真凶。
2. **铁证=实测编译, 不靠猜**: `powershell -NoProfile -Command "& 'C:\Program Files\TMGM MT5 Terminal\MetaEditor64.exe' /compile:'<mq5绝对路径>' /log:'<log绝对路径>'"`, 等 2-3s 后 `iconv -f UTF-16LE -t UTF-8 <log>` 读日志, 看 `Result: N errors`。`0 errors` 且同目录生成 `.ex5` 才算成。**交付前必留一次干净重编译铁证**(可复现 0错0警告)。
3. **修复法**: 把 MQL4 源码**重写为 MQL5**(见上节签名坑), 用本机 MetaEditor64 编到 0 错, 生成 `.ex5`, 拷进 `MQL5\Experts\`(本机 datafolder `C:\Users\ASUS\AppData\Roaming\MetaQuotes\Terminal\7643C0B96C7AD5841307C9E1EB0B9252\MQL5`), 终端 Ctrl+F5 刷新后挂 XAUUSD M1。挂上后日志应打印 `GoldScalpClone MQL5 attached: ...` 这句=真的活起来(MQL4 版不会)。
4. **另一类“不运行”=能编译但逻辑永不开单**: 头号根因是**零可观测性**——每个 gate 静默 `return`, 客户除了 OnInit 那句 attached 啥都看不到, 只能报“挂了不动”。两个放大器: ①**时段门太窄**(好时段只占 24h 的一小段, 客户挂几个小时正好全落在坏时段=当然没单) ②**时区硬编码**(服务器时→北京时 `+5h` 写死, 客户终端服务器不是 GMT+3 时段门整体错位)。根治=交付时就做**可观测版**: 每个开单闸的 return 分支都打**限频诊断日志**(60s 节流 + 换原因才打, 防刷)并写进 `g_blockReason` 字符串; 面板 `Comment()` 最后一行永远显示 **“当前未开单: <原因>”**(非开单时段/点差超闸/无信号/连亏冷却/并发达顶…), 客户把面板截图发回来即可秒定位; 再给 2-3 个“逃生 input”(`InpAllHours`=好时段放宽到全天、`InpLooseSignal`=信号放宽、`InpServerOffsetH`=时区偏移可配) 让客户/你自己能临时验证“信号本身能开单吗”。排这步: 看面板最后那行 + 限频诊断日志, 或临时开 AllHours/关 UseSession/放宽点差验证, 别只靠猜。本 EA 默认好时段 15/14/16/03, 非该时段+周五不开, 属正常设计不是 bug——但**必须让客户看得见这个原因**, 否则“正常设计”在客户眼里就是“坏了”。
5. **绝不 spawn/kill terminal64**(金策铁律): 验证终端健康只读探测(`tasklist | grep terminal64` + 读账户), 引擎终端自行重启, 别按 PID 判被误杀。MetaTrader5 Python 包仅 32 位 Windows 可装, 本机 64 位 Python 装不上 `MetaTrader5` import, 别耗在这条路上, 改走“编译 0 错 + ex5 就位”铁证。
**“挂上不开单”可观测性根治(限频诊断日志 + 面板“当前未开单:<原因>” + 逃生 input AllHours/LooseSignal/ServerOffsetH)详见 `references/not-opening-observability.md`。**
本次产出: `GoldScalpClone_20011176_复刻EA/GoldScalpClone_EA_m5.mq5/.ex5`(0错0警告), 交付 `E:\workbuddy\内容中心\交付\GoldScalpClone_20011176_复刻EA\`, 已拷 MT5 Experts。

## 客户 Statement.htm 解析(本机实测, 2026-10)
- 列结构: Ticket/Open Time/Type/Size/Item/Price/S L/T P/Close Time/Price/Commission/Taxes/Swap/Profit。只保留 Type=buy/sell 行; balance/deposit 行 Size 列是金额非手数, 必须滤掉。净盈亏=Profit+Swap+Commission(先 replace 千分位空格逗号; 负数可能括号 `(123.45)` → 负号)。时间列可能空, 容错(空 close 记 0)。
- **空 cell 剥标签后残留 `&nbsp;`**: HTML 模板把空值写成 `&nbsp;`, 剥 `<td>` 标签后字符串还在 —— float()/strptime 前必须 `x.replace('&nbsp;','').strip()`, 空/`-` 记 None, 否则一批缺 close 时间的行让整次解析崩掉。解析记录落 JSON 前先 datetime→ISO 字符串(`default=str` 或 strftime), 否则 `json.dump` 报 `Object of type datetime is not JSON serializable`。
- **"高频剥头皮 + 无SL + 加仓"类账户的指纹判读(大亨 1014343 型)**: 0 SL/全 TP/持仓中位 2min/手数档呈斐波那契级(0.01×9→0.02→…→1.79)/同日同 TP 同平仓时刻可聚成"篮子"(用 `(round(tp,2), close_time)` 分组, 篮子≥2笔才算)——这是 TP-only 篮子马丁指纹。利润真相必按手数分档累计: 小单档(≤0.07)常合计净亏, 利润 100% 来自大单收割档(1%笔数); 汇报时给"该档净盈亏+累计占比"表, 点破"91%笔数是燃料"。回撤用 10 分钟粒度事件扫描算, 并标清是小单亏损造成的假象; 尾险按瞬时最大敞口(gross lots)算反向 $100/$300/$500 的亏损额。

## MT5 交易历史报告 ReportHistory-*.html 解析 (本机实测, 2026-10, 与 Statement.htm 不同格式)
给的是 **MT5 导出的 `ReportHistory-<账号>.html` 全量交易历史** (不是 MT4 F2 的 Statement.htm), 解析完全不同:
- **文件是 UTF-16, 不是 UTF-8/GBK**: 直接 `open(...).read()` 会满屏 `\u0000` 交错乱码。先 `raw=open(path,'rb').read()`, 按 `('utf-16','utf-8','gb18030')` 顺序 try decode, 成功的用哪个 (本机 MT5 报告实测 utf-16)。存一份 utf-8 副本到工作目录再处理。
- **整份报告只有一个 `<table>`**, 段标题是**单 cell 的行** (`持仓`/`订单`/`成交`/`结果`), 数据行是**多 cell 行**。定位段: `re.findall(r'<tr.*?</tr>', table, re.S)` 逐行取 cell (`<t[dh]>` 内剥标签 + `&nbsp;`→空格), cell 数==1 的就是段标题, 按标题切段。
- **持仓段 14 列** (开仓时间/持仓ticket/品种/类型/交易量/开仓价/SL/TP/注释... 平仓时间/平仓价/手续费/库存费/盈利); **订单段 11 列** (开价时间/订单/品种/类型/交易量/价位/SL/TP/时间/状态/注释); **成交段 15 列** (时间/成交/品种/类型/趋势/交易量/价位/订单/成本/手续费/费用/库存费/盈利/**结余**/注释)。有效交易行判据 = 第 2 列 (ticket) 是纯数字且 len>8。ticket 列常带三段式手数 `888/408/558354782`, 取第一段或整段存都行。
- **资金流水 (出入金) 藏在成交段的非 buy/sell 行**: `type` 列出现 `balance`/`correction` 的才是存/取款/余额调整 (金额在 盈利/结余 列), `buy`/`sell` 行才是交易。算纯交易净利/账户余额曲线时**先剔 balance 行**, 否则入金会把净利曲线打爆。
- **千分位数字坑**: 数字带**空格千分位** (`2 667.80`), `float()` 直接炸 `ValueError`。先 `x.replace(' ','').replace(',','')` 再 `float`。结余/净利/手续费列全要过这道。
- **结果段自带官方统计** (总净盈利/毛利/毛损/盈利因子/采收率/夏普/最大结余亏损/最大连亏): 直接抓来对拍, 不要自己算口径对不上 — 但注意它给的是**含出入金结余口径**, 纯交易口径要自己从持仓段 499 笔 profit 加总。两口径并列报, 别混。
- 指纹集一次算全: 净利/胜率; 手数 Counter(常 99% 单一); 方向分列 net; **峰值并发**(open+1/close-1 事件排序扫, 定 InpMaxPositions); 开单间隔 P50/P90; 持仓 P10/P50/P90 分钟; 赢单 vs 亏单持仓时长对比(判错快砍对多跑); 时段净盈亏按开仓服务器时 hour 桶排 best/worst; 最大连亏; **大单(≥主力手数3倍)笔数占比 vs 净利占比**(徐总号 2.3% 大单扛 88.5% 净利, 即"高置信放大手数"依据)。

## 多账户提炼融合(客户要求"所有优点全吸收"时)
- 逐账户出指纹后, 找**共性优点**(如全号 100% 预设 SL=无裸单; 亏时段并集)与**独有优点**(大单占比/高并发/单月最佳): 共性→默认开的安全闸(防裸单), 独有→全部**默认关**的可选 input, 原版行为零改动、用户逐条开。提炼完还要落到"我们自有纪律": 写 chief 纪律卡 + 研究台账待回测项(同分母铁律), 别只停在客户 EA 里。

## 深度吸收进金策系统(客户/观摩方 EA 优化完要"做成我们自己的"时, 2026-10-07 GoldScalpClone 17项优化落地)
复刻/复刻优化完一个外部 EA 后, 用户常再下一道"深度吸收进我们的系统"的令——意思是把这次 EA 学到的风控/纪律**内化成金策自有资产**, 不是停在客户 EA 文件里。固定套路 = **5 道高频风控闸 + 3 落点 + 1 派单**, 一次全做完:

**第 0 步 · 先提炼成 5 道高频风控闸(通用模板, 高频剥头皮型 EA 直接套; 趋势/波段型把 ⑤ 换成"动量衰减砍仓"、把 ⑦ 点差闸换成"滑点成本比 1.5% 净利阈")**:
| 闸 | 通用参数 | 来源实证 |
|---|---|---|
| ⑤ 浮亏强砍 | 价格走完 0.5×SL 距离 立即市价砍(不等 SL 滑点) | 新建号 P50 持仓 0min 的"错快砍"行为 |
| ⑥ 净浮亏开单闸 | 当日已实现净亏(含 swap/commission)超 1.5% 账户 当天停开新单 | 高频防追单放大 |
| ⑦ 点差闸 | 点差 > 35 点 不开(可填 input) | 高频剥头皮对点差最敏感, 费用占毛利 3.3% |
| ⑧ 日亏熔断 | 单日亏 1% 熔断停手 + 连亏 5 笔冷却 300s | 金策纪律铁律 |
| ⑨ 下单验活 | 开单后读 retcode=TRADE_RETCODE_DONE 才算成功, 防假开单/幽灵仓 | MQL5 g_trade.Buy 返回 true ≠ 服务器接受 |
参数值先照客户指纹定(如新建号 1.31 盈亏比→TP/SL≥1.3 闸), 别套默认。

**第 1 落点 · trader_brain.py 开单大脑(机器线)**: 在 `multi_agent/trading/trader_brain.py` 加 5 个闸方法(命名 `_hard_cut_check`/`_net_float_block`/`_spread_block`/`_lot_normalize`/`_verify_retcode`), 常量类属性集中管理(HARD_CUT_MULT=0.5 / NET_FLOAT_MAX_PCT=1.5 / MAX_SPREAD_PTS=35 / DAILY_LOSS_PCT=1.0 / CONSEC_LOSS_COOLDOWN=5 / COOLDOWN_SEC=300); **提案 dict 新增 `high_freq_gates` 字段(把 5 道闸参数打包传给执行端)**, 执行端按此守纪律。改完必跑 `python multi_agent/trading/trader_brain.py` 实测: 提案 3 条不崩 + 提案里 `high_freq_gates` 字段带出 = 才算吸收成功, 别只信 patch success。

**第 2 落点 · chief 演练纪律卡(人工线)**: `E:\\workbuddy\\金策宗师团\\chief\\三账户思路_人工操盘演练纪律卡.md` 在原 4 道闸(时段/盈亏比/仓位/快砍)后加 5 道高频风控闸(参数照上表, 演练号 60137964 人工下单 + 机器开单两线通用), 让"机器开单 + 人工演练"都吃到同一套纪律。patch 后**重读一次整个纪律卡**验有没有重复追加(上条教训: patch 把标题+来源行重复追加了两次)。

**第 3 落点 · strategy-rd 研究台账(待同分母回测)**: `E:\\workbuddy\\金策宗师团\\strategy-rd\\研究台账.md` 加"高频剥头皮 5 道风控闸 · 吸收进金策系统"一节, 每道闸一行同分母回放待验项(重点 ⑤ 浮亏强砍 0.5×SL 距离立砍 扣 0.2R 滑点后净期望差 vs 等 SL 扫损), 未过五验只作纪律不放大仓位。加完同步进 `rd_queue.json` + `task_ledger.json`(交 strategy-rd 同分母回放定 WATCH/APPROVE), 并更新 `金策宗师团_当前状态卡.md` 单一事实源加吸收落点记录。

**第 4 步 · 派单回流自动闭环**: 吸收完必派 rd_queue + task_ledger 两条同分母回放单给 strategy-rd(不靠 LLM 回话, 30min 循环自动跑), 结果进研究台账 WATCH/APPROVE 定去留, 放大仓位/进 live 仍须走五验(同分母+DSR+PBO+品种稳健+WF3)。

**铁律**: 这 5 道闸是**纪律/风控参数, 不是新策略腿**——要"放大仓位/进 live"仍须走五验; 未过五验时它们只作开单前硬闸 + 演练号纪律, 绝不放大仓位。吸收完在交付 `说明.txt` 里写清"这套纪律已吸收进金策 3 个落点", 客户才知道价值不止在客户 EA 里。

**吸收前先判"策略族"再落参(2026-10 王金光扛单腿实测)**: 吸收的外部打法若与已吸收的**不同族**(剥头皮族 vs 波段扛单/马丁族 vs 金字塔族), **绝不把它的参数塞进已有族的常量块**(会跟剥头皮 ⑤⑥⑦ 打架)——新起一个**独立编号常量块(如 ⑫), 默认 WATCH 模式**, 通用风控(浮亏强砍/净浮亏/日亏)那部分只标"再次验证"不重复造, 高风险打法(扛单+加仓=马丁近亲)登记 rd_queue 走五验默认 WATCH, 原样极端打法(如 0.65 手战役加仓)**不吸收**只按风险比例研究。trader_brain 里给该族加 `_xxx_check` 标注方法 + 提案 dict 挂一个同构的 `xxx_gate` 字段(state 带出), 实测三场景(小单标注/大单拒放大/非适用族 N/A)全对、主程序不崩才算落好。判别口诀: 不同族=独立块, 同族=合并入已有块。


## Gotchas
- **复刻交付后用户要"深度解析成报告"**: 交付不止 `.mq5/.ex5/说明.txt`, 还要出精美 Word(.docx): 封面+目录+彩色表格(Light Grid Accent 1)+净值/逐日盈亏 2 张图+页码, 微软雅黑, 存 `E:\\workbuddy\\内容中心\\交付\\<名>\\`(李老师铁律: 所有分析报告一律精美 Word)。图表 matplotlib: 中文字体 `fm.fontManager.addfont(r'C:/Windows/Fonts/msyh.ttc')`+`rcParams['axes.unicode_minus']=False`; 日盈亏柱状图 x 轴用 `range(len(daily))` 别用跨度天数(交易日不连续会 shape mismatch); 净值曲线标事件点用 `bisect` 吸附最近交易日(某日无平仓直接 `list.index` 报 ValueError)。Word 用 docx 技能 `docx_create.py spec.json`(blocks: heading/paragraph/table/image width_mm/page_break + footer_page_numbers), 生成后 `docx_read.py --text` 验关键数字串在 + `docx_validate.py` 0 错才交付。generate docx 必须用**系统 `python3`(3.14, 已带 python-docx)** 经 terminal 跑脚本; execute_code 沙箱内核没有 numpy/docx, 写 `import docx` 会 ModuleNotFoundError(换解释器一枪即可, 别装包重试)。
- **旧数据混旧策略**: 全量文件不滤日期会把废弃策略算进来, 数字全错。窗口没确认就别算。
- **`input int arr[]` 数组在部分 build 报 `error 285 objects/arrays not allowed as inputs`**: 时段门这种多值参数, 用**定长标量 input**(`InpGoodH1..H5`)代替数组 input, 或在 `OnInit` 里 `ArrayResize` 动态数组。写第二版前先探针确认哪种过。
- **动态数组传参/访问报错**(`error 241/120/253`): MQL4 全局动态数组 `int g_h[];` 不能按 C 式 `int g_h[6];` 定长; 传参签名要 `int &arr[]`, 索引前必须先 `ArrayResize`。探针阶段就会撞。
- **`TimeToSec`/`OrderClose` 返回值等函数名随 build 变**: build 14xx 有的没有, 一律探针先行, 别照 MT4 老书抄。
- **持仓中位≠平均**: 被少量长单拉高的"平均持仓"会骗人, 用 P50/P90 分位定节奏, 汇报别报平均。
- **服务器时 vs UTC**: 时段门要按成交时刻所属时区, 汇报时写清是服务器时还是 UTC, 用户才能对上盘口。
