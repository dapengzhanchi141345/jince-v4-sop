---
id: jince-profitlock-speedup
name: jince-profitlock-speedup
description: "Use when 金策实盘浮盈没锁住/SL没动。速查四层静默点、L0热仓1s高速通道、R口径、10016预检。"
version: 1.0.0
---

# 锁利提速与失明防护（L0 热仓高速通道）

## 触发场景
- 『大浮盈没锁住/SL没动/平仓追不上插针』→ 先按四层静默点逐层排查, 别直接猜。
- 要加速锁利（行情快、插针多）→ 上 L0 高速通道（已落码 jince_live24.py 主循环前）。

## 一、四层静默失明点（11-11 TW88/CHFZAR 事故实锤, 全部已修）
1. select 态丢失（终端重登后冷门/自定义品种）→ 主循环整品种 continue。**修**: 先查仓后 select, 有仓+tick 可用=降级管理+LOUD。
2. per-symbol `positions_get` 返回 None → 静默 continue。**修**: 全局仓列表兜底+告警。
3. per-symbol 返回 []（终端未订该符号不可映射）→ 误判无仓走开仓流。**修**: 每轮一次全局 `_ROUND_POS` 缓存兜底+告警。
4. `manage_position` 内 `symbol_info_tick` None → 静默 return（CHFZAR 型）。**修 P1④**: 强制重 select 一次再取, 仍 None=每轮 LOUD 告警。
5. **SL 丢失（外部动作·EURHKD 型）**: 服务器端 SL 被清（手工持仓面板改单/平台重置）→ 持仓变裸仓, 且所有自动化方都无日志（引擎棘轮只推不清、L5 EA 可能停摆、L1 未挂）。**修**: manage_position 入口 SL 丢失哨兵——`p.sl==0` → 🔴 红警 + 自动恢复 SL（买单=现价下 gap / 卖单=现价上 gap, 只护裸仓不推位, 棘轮后续再收紧）+ `log_trade` SL_LOST_RESTORE 留痕；L0 与主循环都走此路径 = 秒级发现。**排查顺序（用户问"SL 谁清的"）**: ①棘轮日志 grep 该品种（有无清 SL 动作, 棘轮推位全留痕）→ ②L5 EA 活性（jince_status.json/jince_mfe_track.jsonl 的 mtime）→ ③L1 心跳 CSV（挂了没？在跑没？）→ 剩余=手工面板或平台重置（终端 GUI 无审计日志, 只能证明"自动化全部排除"不能证明具体是谁）→ 恢复 SL + 哨兵常备。
**铁律: 有仓必管理、必留痕、必报警; 状态未知=fail-LOUD, 禁止静默 continue。**

## 二、L0 热仓高速通道（11-11 上线, 实例 pid 常轮换, 以 lock 文件当前 pid 为准）
- 主循环 246 品种池 ≈85s/轮 → 热仓锁利追不上秒级插针。
- 独立 daemon 线程 1s 轮询: 只处理 |浮盈R|≥0.5 的热仓（浮盈该锁/浮亏该斩）, 复用 `manage_position`（棘轮只往紧推 + last_trail 去重 + 拒单 60s 冷却 = 与主循环并存安全, 重复推同值 SLTP=no-op）。
- 关键认知: **锁利最终落在服务器端**（SL/TP 服务器零延迟触发, 引擎死了也兜底）; 高速通道=把 SL 更快推到利润侧, 不是自己平仓。
- 全网调研结论（MQL5 官方）: OnTick 只为图表品种生成; 真 tick 级另有订单簿事件 OnBookEvent（比 OnTick 更频繁）但 **OnTimer 粒度是 1 秒（毫秒定时器不存在）**; MT5 内置 Trailing Stop=平台侧非服务器侧（平台死则失效, 10s/单节流）, 不如自管棘轮强但可做最后防线。
- **升级路线**: L0=1s 轮询（现役）→ L1=MQL5 热锁 EA（HotLockEA.ex5, OnTick tick 级+OnTimer 1s 兜底, OnBookEvent 在 TMGM build 被拒, 见技能 mt5-indicator-authoring）→ L2=broker 条件单/服务器端（零延迟）。
- **L2 代理+regime 门跑批坑（11-14 夜双雷实锤, 已修）**: ① cron no_agent wrapper 用 Hermes 自带 python(3.13/3.14) 跑 jince_regime_zone_runner.py, **该解释器无 MetaTrader5 模块** → regime 全 UNKNOWN(err='No module named MetaTrader5')。修法: regime 计算体拆到 `E:/GoldstrategyEngine/data/_regime_calc.py`, runner 用 ATE 专用解释器(`C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe`, spawn 时剥 PYTHONHOME/PYTHONPATH) 跑子脚本, 结果 merge 回原结构, ATE 不可用回退本地 import；**凡 cron 脚本要读 MT5 K线/账户, 一律 ATE spawn, 别指望 wrapper 解释器**。② `datetime.strptime(..., "%F %T")` 是 shell 变量不是 strptime 指令 → ValueError 崩拍(exit 1)；坑点: 本机 `time.strftime("%F %T")` 竟然能正常输出 `YYYY-MM-DD HH:MM:SS`(Windows CRT 宽容, C 层 strftime 与纯 Python strptime 不对称), 所以采集器写的 ts 看着正常, runner 一 parse 才炸——且 last_ts 空时走 else 分支永远不炸, 首次写时间戳才引爆(潜伏雷)。已改 `"%Y-%m-%d %H:%M:%S"`+try/except 防呆(畸形 ts fail-safe 判死不崩)。验活: runner 实跑 exit 0 + regime_state.json 8 品种真 regime 无 UNKNOWN。**【11-12 L1 已清退（李拍板弃用）】**: ex5 挂 2 天反复闪退未根治（Trade Rights+通道拥挤挤挂, MetaEditor 编译链损坏无修复工具）, 成本>收益, L0(1s)+L2(挂单)已兜底 → 不再重挂/不再挂图指引；**清退 SOP**: ①看门狗 hotlock 探针撤点名（jince_watchdog.py 保留探针状态记录、删 ⚠️告警行, 防已弃组件每 15min 刷警扰李）②台账对应任务 CANCELLED（注明弃用理由+重启须李令）③状态卡+memory 各一行④ex5/mq5 文件保留不删（重启资产, 删=归零）②⑤ 重启 L1 只有李新令才做, 且先修编译链（23:00-06:00 调试窗排 MetaEditor 修复）；弃用前 L1 挂图排障经验（『loaded 后数秒被 removed』取证段、活目录铁律）仍有效, 重启时直接用。
- **L1 实装要点（HotLockEA, 源文件 E:\workbuddy\金策宗师团\strategy-rd\HotLockEA.mq5）**: ① 只管 InpMagic=30261103, 只改 SL/TP（PositionModify）绝不做主动平仓; ② 只紧不松棘轮+giveback 地板 0.6R, 与 L0 双通道并存安全（同向推, 重复写同值=no-op）; ③ 每 30s 写 `MQL5\\Files\\Common\\HotLock_heartbeat.csv`，看门狗（jince_watchdog.py hotlock 探针, 15min 拍）查 `Common\Files\` 心跳：文件不存在=not-mounted（info 面不误报）, mtime>10min=hb stale 点名报（带重挂指引）; ④ 挂载是 GUI 用户动作: 开 XAUUSD M1 图→导航器拖 HotLockEA 上图→允许算法交易→笑脸=活（headless 侧只编译+放 ex5+加哨, 给李 3 步指引）。**『挂载后仍不 tick』判读（心跳只有 1 行 init 且 ticks=0/moves=0）**: 按优先级三连查——①**活目录里 ex5 在不在**（只有 .mq5=导航器里根本挂不上, 从兄弟目录拷回同 build ex5, 见技能 mt5-indicator-authoring 最高发根因条）②挂进的是哪个终端数据目录（挂进停摆老终端/非 60137964 账户的终端 = 该终端无 30261103 热仓, EA 空转不写后续心跳）③终端『算法交易』总闸未开蓝（OnInit 跑完事件循环不生成, 经典 MT5 坑, 程序打不开只能用户手点）; 缺 deinit 行=异常移除非正常关图。判活=心跳文件 30s 一行在刷 + 看门狗 hotlock=ok。**『loaded 后数秒被 removed』取证（EA 反复挂上即消失时）**: 先活目录 `logs/<当日>.log` 找 `expert HotLockEA (sym,period) loaded successfully / removed` 时间对——该日志是 UTF-16LE+ASCII 混合编码, `grep -a`/`iconv -f UTF-16LE` 都不稳, 用 Python `open(log,'rb').read().decode('utf-16-le',errors='ignore')` 再 grep `expert.*loaded|removed|failed`；判读: 'loaded successfully'+2-5s 内 'removed'+日志无任何 error/failed 行+心跳无 deinit 行 = 异常卸载（图表被重置/终端强卸/用户手动移除, 先向用户问三件: 图上 EA 名什么状态/算法交易按钮颜色/挂后动过什么）, 不是加载失败; 日志有 'initializing ... failed with code 0 (symbol synchronization timeout)' = 该品种行情未同步（品种不在 watchlist/休市）, 换 24h 有行情品种重挂。**心跳行格式（11-12 升级版）**: init 行 8 列 `ts;init;ticks;moves;lastaction;login;chart;terminal`（直接看出挂哪个终端/账号/图表）, 常规行尾列 `tickstarve_s`（0=tick 活, -1=从未有 tick）, deinit 行 `deinit:<reason码>`; 行内 ts 是服务器时（本地 -6h）, mtime 才是本地时。当前部署态: 7643C0 的 ex5=有效旧版（兄弟目录救援拷入）, mq5=新版（含诊断字段, 待 GUI F7 重编生效）, 1FF8F897 亦已备 ex5; 重编前必备份 ex5（MetaEditor 失败会删旧不生成新）。
- **L1 数据目录铁律（『没看到这个EA』实锤）**: ex5 必须放进**李当前在用的 TMGM 终端数据目录 = `7643C0...`**（活目录判定 = 该目录 `bases/TradeMaxGlobal-Demo/ticks/*/` 与 `config/terminal.ini` 有分钟级 mtime 写入；`A3B1DF...` 是停摆的 JinceSentinel 老终端, 放那导航器里永远看不到）。**引擎 L1 死人开关查的心跳路径必须与 EA 实际挂载目录一致**（EA 在 7643C0 运行→心跳写在 7643C0 的 Files\\Common；哨兵路径指向 A3B1DF 会整段误报红）, 换挂载目录后先对一次哨兵路径再验活。
- **引擎拉起路径与 OOM 防复发（11-11 76076 死因复盘, 永久）**：机器上 python 进程多（19+10）时, 引擎会死于 OpenBLAS 内存分配失败（numpy 多线程膨胀, stderr `OpenBLAS error: Memory allocation ... giving up` 是取证锚点）。预防=看门狗拉起段 Popen env 带 `OPENBLAS/OMP/MKL/NUMEXPR_NUM_THREADS=1`（已 patch 进 jince_watchdog.py；引擎单线程逻辑, 小数组 np 运算零行为变化, 纯省内存）。拉起纪律: **生产唯一拉起路径=看门狗自愈**；chief 临时拉起必用 PowerShell-detached（**agent 的 bash 后台会话会被 harness 清理杀进程**, 11-11 19284 教训, 别把常驻 daemon 挂自己会话上）；拉完读 `live24_magic_30261103.lock` ts 在刷 + stderr 零新增 OpenBLAS 错才算验活离场。

## 二附、李的美元口径锁利死线（11-12 令, L0 已 LIVE @ $5）
- **规则（双口径取更紧, 自动补位）**: 触发 = 浮盈 >$10(美元绝对值) 或 ≥0.5R, 先到先触发（小仓 0.01 腿 $10≈大 R, R 口径会漏、$ 口径接住；大仓 0.5R>$10, R 更紧）；触发瞬间 SL 立即推「开仓价±$5」（半阈值保底, 绝不让浮盈吐回 0）；之后 SL = 更紧的 max(现SL, 峰值-0.6R, 峰值-$10) 双地板。
- **落地层**: L0 已 LIVE（jince_live24 热仓通道 $ 口径双阈值, dollar P&L=(tick-open)×volume×合约规模）；L1（HotLockEA InpHotUSD）未接线；L2（服务器 SL 天然锁死, 不动）。
- **灵魂指标**: 「浮盈峰值后回吐超 $X 的笔数」新旧口径同分母对拍必须显著下降（进五验⑥净期望线 1.0R 扣 0.095R）。
- **WFO 裁定（11-12 第3~5轮, 永久规则）**: 早锁家族（EPF 早期正地板 / HARD_BE 硬保本）**全部 REJECT**——早锁把需存活至回踩的大赢单提前砍掉, 净R恶化（HBE0.05→-0.0344R, HBE0.30→-0.0179R, 亏损率只降1~3pp 不值）；**只有『利润地板』型（SL 推保本/半阈值保底）与『吃大趋势』两全**, 任何新锁利提案先跑净R同分母对拍再谈翻闸；逐品种六参数微调（ΔR+0.0032 量级）五验不过一律维持冻结（R1）, 别因单点偏置翻闸。
- **状态纪律（现状 11-12 更新）**: 阈值随李口谕演进过两轮（$10 → **$5.0**『小单子只要有利润就不能再亏损出场』）。**汇报一律大白话:『浮盈超 $5 绝不回吐, 大趋势照样吃（L0 1s 通道+服务器 SL 双保险）』**, 别说未上线/参数黑话；改阈值=L5 翻闸动作（引擎重载+台账留痕+总线回执）, 李一句话即可下调/上调, 不用重新提案。
- **引擎重载坑族（MAGIC_DUP_EXIT, 11-12 实锤）**: ① taskkill 后**必须 wmic 确认 jince_live24 实例数为 0 再拉起**（旧实例拖尾 3~10min, 新进程见旧实例即自退）；② **PID 复用假阳性**: OpenProcess(pid) 成功≠锁主还活, 锁验活须 wmic get commandline 核该 PID 命令行含 jince_live24（已 patch）；③ 锁龄阈值 600s 收紧 180s（引擎 30s 刷锁=6 个周期, 覆盖 kill 拖尾窗）；④ OpenProcess 成功也要 CloseHandle 防句柄泄漏；⑤ 拉起=PowerShell Start-Process detached（单线程 BLAS env 照旧）, 拉完 25~30s 存活+锁 ts 在刷才算验活离场。

## 三、浮盈 R 口径（防 CHFZAR 型误判）
- `浮盈R = (cur - open) * sgn / dist`, sgn=买单+1/卖单-1, **dist=开仓初始SL距离**（open_meta/load_init_sl, 非当前 |open-sl|——SL 推过保本后 |open-sl| 塌缩, 见 P2 dist 修复）。
- p.profit 是**美元**不是点数/R, 别把 $1.42 当 15R（CHFZAR 事故: 实际 0.37R, 未到 0.5R 锁利触发线, 0 推位=正确行为）。

## 四、10016 Invalid stops 预检（推 SL 前必过）
- 空单 SL 必须在当前价上方、多单 SL 在下方（SL 绝不能放到当前价的利润侧, 否则立即触发被拒 10016）。
- 推位前读 `symbol_info.trade_stops_level`（CHFZAR=0, 多数品种>0）: 新 SL 与当前价距离 < stops_level 会被拒; 价格放 tick 网格（SYMBOL_TRADE_TICK_SIZE 取整）。
- 引擎已有 SL_RETRY_COOLDOWN=60s 拒单冷却（只 10009 成功才入 10min 去重窗）, 拒单=不卡死可重试。

## 五、验证清单（重启后 3 分钟）
1. `cat data/live24_magic_30261103.lock` 新 pid + ts_unix 在刷（锁龄自愈心跳）。
2. 日志有 `[L0热仓高速通道] 1s线程已启动` 行。
3. `data/mgmt_heartbeat.json` ts 每轮在刷 + managed 全仓带 SL。
4. 热仓（|R|≥0.5）出现 `强化锁/锁半利/斩亏` 新行 = 高速通道在推（1s 级）。
5. 台账 t_tw88_unmanaged_p1_1111 / t_init_timeout_p2_1111 / t_giveback_floor_promote_1111（giveback-floor 翻闸 11-11 已即时执行闭环；五步 SOP 全文见技能 jince-bus-and-heartbeat-ops 的 references/gateflip-sop.md）。
6. ~~L1 层验活~~（11-12 L1 清退, 不再例行；仅李令重启 L1 后恢复: 心跳 csv 30s 在刷+看门狗 hotlock=ok）。

## 六、fail-open 铁律（治 jince_tick_push 三拍 exit 1 型）
- 任何包了重试/退避的辅助函数（_retry 型）, **必须 try/except 包住 fn() 本身**: subprocess.TimeoutExpired/FileNotFoundError 一类异常不捕获就穿透到 __main__ catch → exit 1, 把设计好的 fail-open 闸（静默拍/2h 重申）整个绕掉。捕获后折成 rc=999 失败拍继续退避重试, 交还给发声闸。
- 推 GitHub/外部 API 的辅助步失败 = 本地数据照写 + exit 0（或约定的 fail-open 码）, 只有连续卡滞才按防刷屏闸发声; 单拍同步失败绝不拖垮整条链的退出码。

## 七、锁利克隆到独立 magic 批（不动生产引擎的部署模式, 20261104 SD 批首例）
- **新 magic 批（模拟/练习/进化批）要锁利时: 不改 jince_live24（生产单 magic、OOM 敏感、重载坑族全在重载上）**——单独起一个克隆守护进程（范式 = `E:/GoldstrategyEngine/research/sd_profitlock_guard.py`）, L0 规则集原样搬, 只换 MAGIC 与触发/地板参数。
- **克隆配方（照抄 L0 已验口径）**: ①热仓=|浮盈R|≥0.5, R 基准=**开仓初始 SL 距离**（从本批 prac log 的 open 行按 sym+ticket 反查, 防 SL 推后 |open-sl| 塌缩误判, 同 P2 dist 修复）②棘轮目标 = 开仓价 + max(峰值R − giveback, 0)×risk（trig/giveback 为分品种变量：两段网格优化出分品种表，见 institutional-order-flow §八「分品种参数表」；表读「分品种+全局 fallback」，缺品种落全局默认，giveback 下限 0.2R 防过触发）。**触发口径=峰值R≥trig（绝不用当前浮盈R做触发）：峰值一旦到过 trig，此后任何时刻（含回吐期浮盈跌破 trig）都推 峰值−giveback 地板——用当前浮盈做触发会在回吐期棘轮停推，峰值利润没锁住=「浮盈 $10 → 反转止损离场」型亏损的根因，11-15 终审实踩**。②附 **R 基准匹配按 品种+开仓价**（prac log open 行的 price≈position.price_open）：pending 挂单的 res.order=订单票号，成交后 position.ticket=持仓票号，两者不同——按 ticket 反查=查不到=risk None=锁利守护静默全失效（11-15 终审实踩）. **波次重开场景失配变体**: 同品种多波开仓使 prac log 残留旧 open 行, 最近行匹配挑错行（开仓价对不上）→ 守护打 "open_risk 价格失配回退最近open" warn 并静默用歪 R 基准续跑.**修法（已落地, 两道）**: ①**开仓方登记**: 波脚本/挂单器开仓成功后必向该批 prac log 追加 open 行（kind=open, ts/sym/price/sl/tp/ticket/magic/wave）——不登记=守护只能匹配旧腿基准, 锁利地板全歪（新波开仓后守护日志必查有无该票号 open 行, 缺=执行岗补账）②**守护侧防呆**: open_risk 加时间门（只认持仓开仓时间前 6h 内的 open 行, 旧腿行作废）+ 失配价差>15%价格=LOUD 拒用（risk=None 跳过该仓推位, 安全侧, 绝不静默回退错基准）. 再见到失配 warn 且带新波票号=登记链断了, 重查①; 再见到 loud 拒用行=检查开仓方是否漏登记或价格异常（插针成交/数据脏）. ③只紧不松: 仅当目标>现 SL 才推, 同值去重 ④推前过 10016 预检（SL 在现价正确侧 + stops_level + tick 网格）⑤拒单 60s 冷却（**峰值状态 last_trail 只在推单成功 10009 时更新；拒单/no-op 去重保留旧值供下拍重试——无条件写会把去重 no-op 也记成已推，棘轮从此停推，锁利永久失效**）⑥SLTP 落服务器端=守护死了最后一推仍零延迟触发。**SL 方向铁律（11-15 三方审查重写；旧式「卖仓 SL 只能上提/统一 target=open+lock_r×risk」已证伪——克隆照抄=空单永不锁或越锁越宽）**: ① 锁盈方向随持仓: 买仓锁盈=SL 上提 target=open+lock_r×risk；**卖仓锁盈=SL 下移 target=open−lock_r×risk**（sgn=buy+1/sell−1）；锁位落开仓价另一侧=利润锁死，0R 地板（SL=开仓价）双向合法且算已锁。② 10016 服务端规则与盈亏无关（固定侧）: 卖仓 SL 必须>现价(ask)、买仓 SL 必须<现价(bid)——卖仓把 SL 下移到开仓价下方是合法的（只要仍高于 ask）；非法=SL 放当前价利润侧（卖 SL<ask/买 SL>bid 立即触发）。③ 推前预检价别用反: buy 用 bid、sell 用 ask（用反=点差内边界误拒进 60s 冷却）。④ 只紧不松 skip 方向感知: buy 现SL≥target 才跳；sell 现SL≤target 才跳。⑤ 棘轮/结算代码单测必须双方向各喂确定性 K 线断言 R 值——手写公式验对、代码符号反照样 PASS（11-15 settle/guard 双实踩）。
- **部署=Windows 计划任务（常驻守护别挂 agent 会话, 同引擎拉起纪律）**: ①必须 `-User Administrator`（"仅登录时运行"）——SYSTEM/交互模式跑 MT5 桥 LastTaskResult=**267009**（用户会话终端连不上）②Settings 带 RestartInterval=1min + RestartCount 大=死机自愈 ③进程侧再加实例唯一锁（lock 文件 pid + ctypes `OpenProcess(0x0400)` 判活, 同 MAGIC_DUP_EXIT 族, 但**克隆守护侧判活用 OpenProcess 快路径、不核命令行**——PID 复用假阳性窗口极小: 任务 1min 心跳 + 进程刚起, 加命令行核验收益负成本正: 嵌套 CIM/wmic subprocess 判活 = 30s 级冷启动, 超时被 except 静默吞掉 = 锁静默失效双实例, 11-15 实踩; **锁异常分支必须 LOUD 打印, 禁 `except: pass`**）④tick 间隔按账户体量定: 0.01 手模拟批 10s 够（与生产 L0 1s 共终端, tick 越小 IPC 压力越大）, 实盘放量再降 3s。⑤**常驻守护不热加载新参数表（11-15 实踩）**：守护进程启动时把参数读进内存——改了分品种表/代码后旧进程仍按旧参数跑，计划任务 RestartInterval 只在进程死时自愈，不替改参拉起→改参/改码后必须主动重启（kill 旧 pid→任务自动拉新代码→核 pid/锁文件换新）；汇报守护状态时注明当前进程载的是哪版参数。**每次终审/审计后若修了守护代码，重启=审计的最后一环，不重启=修了白修（进程内存还是旧 bug）**。
- **守护/强平脚本修改后两道验收闸（11-15 SD 批 P0 两雷，上计划任务前各验一次）**：①**分级分支可达性**——分级处置脚本（12h/24h、锁利单/未锁单分级强平）的每个动作分支必须有合成用例实跑一次（构造合成持仓+时间戳喂给分级函数），验动作真执行；「代码读起来像对的」≠可达，动作分支排在 continue 之后/条件永假=死代码 0 生效（终审实踩：分级强平一整段死代码，靠审计 AST 通读才查出，不是靠跑）。②**DRY-RUN 是必须验证的属性不是命名**——dry 模式入口硬 assert（order_send 调用点 0 执行或 mode 闸在 send 内），且「dry-run 通过」后回读账户 positions/orders 确认 0 副作用；只改日志不改发送路径的「dry」=假 dry 直发实盘。两闸都是审计 P0 级，克隆守护/强平哨改码后不过=不上线。
- - **"仓没了/秒平"分诊先对锁利线再立项**: 持仓消失且窄窗 deal 查询看不到平仓记录（服务器钟偏移+同步延迟）时, 先读 `data/sd_profitlock_log.jsonl` 该品种末行——平仓价==守护推的 new_sl 且有"锁利"行 = 浮盈峰值后回踩触发服务器端 SL, 设计内落袋（deal reason 面常显示 VPS/By client 型, 不是 rogue 进程）; 无对应行才走 jince-v4-trading-loop 的 P1 取证链。
- **用户常设偏好: 锁利优先于净R**（"直接锁利 不能让利润没了"）: 锁利层回测若显示牺牲净R（首例: 峰值-0.6R 保本层=净R 的 68%）, 照样上——先报两个数（原结构 vs 锁利结构的净R/胜率/五验）让用户拍板, **默认保留锁利层, 禁止为净R 好看自动跳过锁利**。与 §二附 WFO 裁定（早锁家族 REJECT）不冲突: 拒的是"早期正地板砍大赢单", 不拒"利润地板型"。
- **锁利 vs 不锁利裁定（11-15 同分母对拍实锤）**: 棘轮锁利（峰值−0.2~0.3R 地板）净R **高于**不锁（+2~3%）且消灭「浮盈回吐成亏」型亏损单；**别用硬保本/早锁**（2R 硬 BE=净R 掉 32%，早锁家族 REJECT 同族）。锁利层的价值向用户汇报=「浮盈不会变亏损」，不是净R 数字。

## 执行节奏（11-11 用户令「好的技能不能拖」定调）
- 已验证的组件/技能/翻闸（五验/守卫/回测全过 + 低风险行为如棘轮只紧不松）= **立即按最优方案执行，不等 23:00 调试窗**；23:00 窗只留给未验证的活、高风险结构性改动、L5 权限项（实盘手数/资金/魔号/对外发送）与排程类活。同批捎带已验证小补丁，一次重启全生效。

## 事故时间线（11-11 实证）
- 09:18 重平仓抑制窗 bug（10009 才入窗）→ 10:15 MT5 IPC 冻死（零参重登）→ 12:21 第一波定稿（PROFIT_SECURE lh1.2/bb0.2, 捕获 72.6% 基线）→ 14:15 TW88 三层静默失明（浮盈 5.62R 但 SL 停 0.24R 位 3h, 手动推 1.2R=3740.26）→ 17:37 SL 触发 @3740.26 落袋 +$9.36 → 17:27 全链 auto_cycle 挂死 30min（手动补拍, 改进=脚本每步心跳+阻塞 15s 超时保护）→ 18:5x 实盘深度优化派单卡 OPT-1~4 → 19:4x CHFZAR 型 P1④ + L0 高速通道上线（78972）。
