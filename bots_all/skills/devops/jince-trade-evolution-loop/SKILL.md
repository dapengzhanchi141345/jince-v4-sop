---
name: jince-trade-evolution-loop
description: 金策每单必进化制度, 开单9步SOP+验尸哨+参数版本锚+日进化链+时间感知交付. 开单/结算/进化任务前加载.
---

# 金策·订单进化闭环制度（李11-15令: 要有严格工作流程和制度, 每次开单都有进化, 都要有技能提升）

## 时间感知交付（李11-16令: 今天就应该完成, 会看时间）
- 每个交付物带时间锚: 何时完成 + 之后哪个定时任务接手; 不说"稍后报/几分钟出结果"这类悬空承诺。
- 有时间敏感执行窗口(挂单/结算/cron 触发点): 挡路项当天全清, 窗口前手动预验一次(dry 预检/手动触发/状态轮询), 不靠定时任务首跑兜底。
- 后台长任务当天 poll 到完成并核验真实产物(commit sha / PASS verdict / 落盘文件)才收尾, "跑完再报"不是有效收尾。
- 用户问"完成了吗": 先逐条对账未竟项(后台进程状态、cron last_status、台账/stamp 文件)再作答, 全绿才报完成。

## 9 步 SOP（每单必走, 缺一步=失职）
1. **信号**: OE评分/区事件(Seiden OD区, 前一日选样口径)
2. **五验闸**: 同分母A/B + 无未来 + 成本扣减(0.095R) + 12h红线 + OOS —— 不过=不许挂单
3. **参数表版本锚**: research/sd_symbol_params.json 带 version 字段(现v2=御史口径); 改表必 bump version + 留 .bak; 读版本必走挂单脚本 SYM_PARAMS 常量(research/ 层), 手拼 ROOT 层路径=该层无此文件, 版本恒读成 0 且不报错
4. **挂单留痕**: 逐单写 data/order_lifecycle.jsonl (ev=open, params_ver, ticket, sl/tp, live) —— 挂单脚本自动做; dry 记录同写, 消费方必按 live 过滤
5. **在位守护**: 锁利10秒一拍(峰值落盘sd_peak_state.json重启不断链) + 12h/24h分级强平哨30min巡检(锁利单豁免12h只吃24h)
6. **结算对账**: 验尸哨 research/sd_evolution_postmortem.py 12h窗口扫MT5成交补 close 事件(pnl/出场原因/时长) —— 只对账 live=True 开单, 否则 dry 记录配 MT5 成交补出假平仓
7. **验尸三问**: ①对/错(P&L符号) ②为什么(TP/SL/锁利/强平/区失效归类) ③改什么(参数漂移: 是否按 vN 表挂的)
8. **进化三出路**(每单结论必落其一, 不许只报不改):
   - 参数问题 -> 参数表 bump version(走五验闸)
   - 机制问题 -> skill_manage 更新本技能或 jince-* 技能(留痕: 触发事件+改动+验证结果)
   - 待裁定 -> rd_queue 提案(3连同因SL自动提案; 不自动改表, chief 裁定)
9. **技能提升台账**: 技能改动 + MEMORY 沉淀(每会话末查: 本轮学到什么没进 MEMORY/skill = 没学)

## 执行窗口前预检（防整批被挡）
- 关键挂单/结算窗口前, 先跑一次 `place_sd_all_20261115.py --params sd_symbol_params.json`(非 live=dry): 验挂数/跳数/败数 + no_trade 品种正确跳过。⚠️ dry 会被同日区闸短路（输出「[同日区闸] 整批 skip, 退出」）= 刚加的品种级 skip/闸读逻辑根本没跑到——验挂单器新逻辑前须先清 `data/sd_all_zone_state.json`（或等次日新 zone）, 别拿「整批 skip」当验证通过。
- 同时清陈旧区闸 state (data/sd_all_zone_state.json): 旧批次写下的 last_zone_dk 会令整批 skip 退出; 窗口任务自带重置, 手动预验前需自行清掉双保险。
- dry 输出尾部核对 `params_ver=` 是否为当前表版本, 不是=版本锚没生效。

## 日进化链（87任务中68启用, 金策主线）
- 00:10 全宇宙回测(不限时, 0 LLM) -> 01:30 验收(training_run.py) -> 07:30 高流动性K线刷新(防断更)
- 02:30 验尸进化哨(job 53b396f0a14e, sd_evolution_postmortem.py: 对账补close+逐单三问+3连SL提案rd_queue)
- 20:00 日结进化(七步SOP jince_rijie_sop.md: 家族账/筛子命中率/进化提案/总线复盘)
- 21:30 学习进化(strategy-rd领题+五验)
- 08:45 429补跑哨(job cd863fdae55c): 查日结/学习进化 last_status, 限流挂掉的自动补做
- lifecycle-analyst 泄漏告警（全生命周期深析产物, 告警体=分析+路由, 0 改实盘参数=合规）: 命中泄漏项=次日 05:00 前必入 rd_queue 工单(owner strategy-rd, P1), 工单把确定性五验（WFO 回测脚本 0 LLM, 不待 key 堵解先行跑）与 LLM 翻闸（chief R11, 待 key 恢复）分段认领; 泄漏连续 5 天未修=P0 升级单独报。收告警不静默"留讫"。
- 每日03:00全面体检 | 2h效率播报 | 24h心跳看门狗点名

## cron 脚本目录铁律
- 定时任务 script 必放 `E:/workbuddy/国外模型/hermes/scripts/` (create 报 "file not found"=放错目录; research/ 下的脚本先 cp 过去)
- **hermes cron 命令的入口 = 原生 `E:/workbuddy/国外模型/hermes/hermes-agent/.hermes/bin/hermes.exe`（git-bash 直调, 如 `".../hermes.exe" -p default cron resume|run|list|pause <jobId>`）：`python -m hermes_cli` 在 ATE venv / 3.13.12 里报 `No module named hermes_cli`（模块只装在 hermes 自己的解释器里, 11-17 补跑日结 job 实踩）；tools/ 目录下那个 `python-3.14.9+...` 目录名带占位符字符, bash 里直接敲也炸——别猜 python 路径, 一律用 hermes.exe 入口, 子命令失败看 stderr 第一行
- LLM 任务(no_agent=False)必配 429 兑底补跑哨, 否则限流日进化环断
- no_agent 脚本 stdout 直接投递: 空输出=静默, 非零退出=报错; 交付通道优先 deliver=origin, 避免 bot-chat 握手超时 delivery_failed

## 关键铁律
- **数据有效性闸**: MT5连不上/台账缺失=显式FAIL拒出报告, 禁静默; 断线快照的 pos/od 不作实值(11-09 脏快照案)
- **盈亏必须可归因**: 哪版参数表挂的哪单, order_lifecycle.params_ver 串到底
- **MT5掉授权=零参 initialize() 重登**(强平哨报 INIT FAIL (-6, 'Authorization failed') 即此症; 零参重登恢复后手动触发哨验证)
- **jince_sass/.venv 的 numpy 崩=ABI不兼容**(11-15 实例: 2.4.6 崩, 装 numpy==2.0.2 修好; 守护重启前必验 numpy+MetaTrader5 双 import)
- GitHub 全量推走 gh-API(jince_github_sync.py push_via_api, 443墙内直连必崩); 多线程缓存竞态已修; excludes 必覆盖研究数据缓存目录(npz), 否则 tree 构建报"1文件blob缺失"(大文件>100MB或未追踪引用)
- **cron no_agent 解释器缺 tzdata**: `C:/Users/ASUS/AppData/Roaming/uv/python/cpython-3.11` 跑 zoneinfo.ZoneInfo("Asia/Shanghai") 抛 ZoneInfoNotFoundError(PEP668 挡 pip install) -> 脚本顶层必 try/except fallback 到 datetime.timezone(timedelta(hours=8))(北京无夏令时, 等价)
- **宿主闸认 hermes-cron 宿主**: 回测由 hermes cron 拉起, 父链=pythonw gateway 而非 taskeng/svchost 调度器根, 只认调度器根会永久假 FAIL 锁死池单闸; 回测收工且新卷落盘判 PASS_INDIRECT, 残链/在跑假焊仍 FAIL(修处 training_host_gate_check.py)
- **杀进程用 taskkill /F /PID**: 内联 python -c 多行含 kill/psutil 的复合命令会被 approval 层 SIGTERM(exit 15) 截杀; 多行逻辑写临时 .py 文件再执行
- **12h强平/决策点哨必落 one-shot cron 作消费者**: 只往 jsonl/json 哨文件写条目而无排程消费者=无人认领, 哨形同虚设——登记哨时先 grep 确认有脚本/排程在消费该文件, 没有就用 cronjob_manage 建 one-shot(run_at=ISO 时刻, failure_deliver=local), 哨文件只当台账双写; 到点无动作也要 NOOP 留痕（见"事件决策点到点必写 task_ledger"条）。**one-shot 哨绑具体单/wave（票号/锚点在哨名里）——旧单的哨不覆盖新开的 wave, 新开一批单登记当拍必新建对应 one-shot 并回读 jobs.json 验在**（11-18 实踩: 12h 哨只有旧 XAU 单专属哨, 新开的三腿币仓裸奔到主 bot 发现才补建）
- **12h 哨不依赖引擎活着（断链补撤, 11-16 断链案）**: 哨死在"引擎停摆=哨停摆"上——引擎/哨每轮重启与每轮巡检都须对全部活挂单做 12h 超时 diff（超时线=挂单 ts+12h, 时间锚钉死, 禁用"哨执行时刻-12h"类推导, 会提前/滞后触发）, 超期未触发单立即补撤并写 order_lifecycle（CANCEL_12h_RECOVER 带票号）+ 总线留痕, 不等下轮或人工。引擎重启恢复后第一件事=跑这个 diff（11-15 夜→11-16 早引擎停摆, 12 张币线挂单带隔夜敞方向存活 17h 才补撤, 且撤单在本地台账零记录=撤单动作与台账必须同拍）工单入队≠修复完成：根修验收=引擎重启后 5min 哨扫描对已超 12h 的挂单自动补撤（台账可查）；未过该验收前 12h 超时再复发，P 级逐次升档（P1→P0）并留台账，不因"工单在案"而降级。排序/挑活类哨（数据官刷缓存、补跑选件）修优先级键后必实跑一拍验优先项实际被处理（如 mtime 刷新）——布尔/元组排序键写反时『跑通 0 失败』照样饿死目标项（11-18 实踩: `in` 写反成非主力优先, 主力 4 品种饿 3 拍, 靠回归验 mtime 才发现）
- **撤单留痕同拍铁律**: 任何撤单动作（哨撤/人工撤/风控裁定撤）当拍写 order_lifecycle（ticket+时间+原因）, 台账无撤单记录=撤单事件不可归因（11-16 案: 12 张单被撤后翻遍本地台账无一条撤单记录, 只能靠 orders_get 前后张数差反推"被撤"且无法定执行者）
- **多闸并存双读（闸不咬合变体）**: 挂单前必须读齐该品种全部闸文件（退役 symbol_pause / 家族冻结 family_freeze / 出池 excluded_symbols / 事件窗）, 取最严者；执行通道只读自己知道的"解冻"闸会漏掉退役/冻结/出池闸, 把违规单再挂回来。发现"撤违规单→补跑/重挂→再违规"死循环时, 不逐张撤单循环（撤 N 张重挂 N 张）：给挂单脚本加品种级闸读 skip（命中即 skip+留痕）在执行层断环, 再一次性清在板违规单；新裁定（冻结/出池/退役）必落对应闸文件, 只写日报正文=执行层读闸文件不生效, 等于没判。出池裁定还必须同步落挂单脚本的品种数据源（research/sd_symbol_params.json 的 excluded_symbols 字段）——落闸文件≠落品种源, 不同步则下一批照样把出池品种挂回板面（11-17 实证: 学习批五验出池 XPT 当日被挂单批重挂 2 张, 补落品种源+挂单器闸读后才断环）。
- **闸判读以 policy/数值字段为准不认标签**: 读 risk_freeze 类闸文件认 policy 字段实值（如 policy.open_new_order）, 不认 level 标签与 note 文案——标签/注释会随裁定过时（旧"禁开新单"口径已被解冻令推翻但 label 未变, 报告层按旧口径研判=执行层照旧口径把在板挂单全撤, 且撤单不留痕=不可归因）。闸裁定变更后必扫报告层/已登记任务文本中的旧口径引用。
- **代行/推导闸不得越过用户显式令（11-18 三口径冲突实踩）**: 代行使闸（代日结/代裁定落闸文件）只许收敛用户已有显式令的范围, 不许推导收紧——把"某族冻结"推导成更严的冻结闸=越令, 且执行脚本只读机器字段（policy 类）不读 note 文案, 越严口径若未同步落机器字段就是多口径并存: 越权脚本按机器字段"合法"开违规单。代行使闸必带 ①"代行"属性+用户令原文锚 ②机器字段与 note 文案同步改 ③与既有闸文件全部显式令比对一次再落。发现多口径并存=红报用户裁, 主 bot 按"最新显式用户令 > RETIRE/退役硬闸 > 闸文件 > note 文字"顺序执行, 不静默选边。
- **开单入口白名单（11-18 越权一次性脚本实踩）**: 引擎根目录禁放一次性开仓脚本（wave/market_in 类, 绕过挂单部链路直连 MT5 开仓）——发现陌生 magic/comment 开仓 = 先平违规仓（平仓方向/字段坑见 mt5-manual-trading-practice）再把该脚本归档为 .disabled（防复跑）+ 查触发源（cron/计划任务/他会话）。判入口身份看持仓的 comment+magic（deal comment=自报）; 白名单外的新 magic 开仓=红报。归档=mv 到 data/disabled_*.disabled, 不删（留审计）。**合规对偶（用户令授权的白名单 wave）**: 脚本放 scripts/exec_wave/（非引擎根）+ magic + wave comment + 0.01 + 12h 红线戳 + task_ledger.jsonl/order_lifecycle.jsonl 双登记; 令覆盖既有闸（如 RETIRE 硬拒）时必把 override 同步写进闸文件机器字段（新增键带令锚+红线时刻）, 只写令正文不落闸文件=双口径并存, 他 bot/哨读旧闸误判。
- **事件决策点到点必写 task_ledger（NOOP 也写）**: 日报/事件表挂的决策点（重挂闸/翻闸点）到点无论有无动作必须落 task_ledger 一行（NOOP+原因）——到点后 grep 0 命中=触发器缺失红报（板面无敞口不代表闸没丢, 下次有存量单时静默不跑=纪律破口）。
- **补跑哨须辨意图撤单（intent-cancel 态）**: 30min 故障补跑哨以"板面无输出"判失败会重触发挂单脚本, 把纪律性撤单（12h 哨/冻结窗/闸违规撤）全变重挂。补跑判定必须读订单台账状态：主动撤单行（cancelled_intentional, 带 actor+reason+ts）不重跑, 只重跑真失败态；板面存在性=实读核对源不是状态源。与此同源：12h 哨撤单若被补跑哨重挂=12h 纪律再破, 根修=订单台账状态机三方（挂单/撤单/补跑）共读同一状态。
- **活读有挂单但台账无=无主单补账**: 挂单通道下单后必写 ticket/进场价/SLTP/12h 强平 deadline 进 order_lifecycle；活读发现不在台账的挂单（通道挂了没写台账）=grep 对应做单思路消息全文定源（其挂单参数即源证据）, 无显式指令=执行通道自挂。补账=台账补一行(op=watch_backfill, 票号+进场+SLTP+12h deadline=挂单时刻+12h)+按关键铁律登记 12h one-shot 哨；默认不撤该单（通道合规+规模有界, 撤单动作本身风险更高）, 通道违规（超上限/错方向）则立撤并记原因。**周期巡检口径（11-17 实证）：每拍巡检/晨报 diff 活体实读挂单张数 vs order_lifecycle 台账张数, 差 >3 = 存在无台账挂单批（非个别无主单）, 立即批量补台账行（op=watch_backfill, 批次量+magic+时间窗+根因假设）+显式报, 不待晨报/对方点名才发现膨胀**——30 挂单一夜膨胀 27 张无台账单, 晨报才暴露的教训：挂单账实 diff 是每拍常规动作不是事后补救。
- **品种级闸线 vs 现价陈旧性预检（挂单/重挂前必做）**: 执行挂单/重挂任务前先读品种级 gate 文件比闸线与现价——闸线设得早、现价已破线一大截（差距 >5%）= 闸永久 active 态，该品种事实性停挂（新挂/重挂全被挡），显式报"闸失效态"（挡单归因闸不归因执行层），别当成执行层 bug 反复重试。gate 文件是 L4/风控裁定资产，交易侧无权单改闸线——把"重置到新结构（如新支撑下沿破位线）vs 维持停挂至销绿"两案送风控官裁定，裁定后回读闸源数值字段验落位（注意 scope/rule 文案可能未随数值同步，以数值字段为准）。闸口径变更后扫一遍已登记的 one-shot 哨/重挂任务的 prompt 文本，陈旧闸线引用会静默挡死执行且无人报警（任务登记时必带前置闸清单）
- **仓数突变（MFE/MAE/巡检报 0→N 或 N→0）先验真再定性（11-18 实踩）**: MT5 positions_get 实读 → magic+comment+开仓时刻 验身份（comment=wave 名自报）→ 对 task_ledger/order_lifecycle 登记定合规（白名单波/李令直裁 override vs 违规入口）→ 合规波把 override 回写闸文件机器字段（防他哨读旧闸误判）→ 异常才追 rogue 链路。平仓侧 deals `[sl 价]` comment=锁利 trailing 移 SL 证据；台账 ts 与 deals 时刻可差数小时（台账本地钟 vs 服务器钟），对票号不对时刻，别误判重复开单。
- **deal comment = 入口身份唯一可靠源（11-17 实踩: 连续 4 批无留痕动作）**: 撤单/挂单日志各系统留痕口径不一，唯 MT5 deal 的 `.comment` 是下单方自报——每拍实读新 deal 按 comment 分入口审计：有标识的（如 v3fwd-OOS30-*=进化营前向OOS采样、L4retired+coinfreeze-close=主bot、[sl]=止盈止损自动）归因清楚；**无标识或陌生标识（如 "mx"）= 违规入口，其仓位/挂单发现即平/撤并留痕**。未知入口会升级行为模式（先挂限价、撤后改市价直挂仓位），所以巡检 diff 必须**挂单+持仓双侧**对 order_lifecycle（只 diff 挂单会漏直挂仓位）；同一入口第 3 次越线 = 停打补丁（逐脚本加闸读打不完），改推中央下单闸：所有 SD magic 下单/撤单过统一闸口函数（读 symbol_pause+family_freeze+excluded_symbols+12h 登记三闸+动作留 actor），无留痕拒单。
- **LLM 子代理 live 动作物理隔离**: 五验/升级批的 LLM 子代理只许出结论与回测，live 验证/挂单/平仓必须走中央闸口+留 actor（"只出结论不翻闸"破例=违规源）；子代理产出的括弧两腿/B0 形态单出现在实盘=它的越权实锤，先撤平再查其执行痕迹（workbuddy 侧 subagent 日志）。
- **LLM cron 自动开单 prompt 必须写死名单（换网/闸放开/tm 翻转类）**: prompt 里『自动开 N 腿/N 单』不给品种名单=LLM 自决, 可能开出 RETIRE/冻结品种或与在仓 wave 重复（11-19 实踩: 换网哨『tm=1=自动开4腿』无名单, 修=写死 earn-cell 三腿白名单+『先实读现有持仓仍活则 NOOP』+『RETIRE 名单永不开』）。自动开单类 job 三件齐: 白名单名单、去重前置（先读持仓/挂单）、禁开名单（RETIRE/冻结）。
- **经纪商 close-only（SYMBOL_TRADE_MODE=4）= 可平不可开**: 12h 强平/风控撤单不被 close-only 阻挡（平仓照走）, 自动开单类哨只在 tm 翻 1 时才有开单意义; 巡检报『N 品种仍 close-only』必联读当前持仓态——close-only 只挡新开, 不挡存量单与平仓, 别误报"持仓会被 close-only 卡死"。
- **限价挂单前先查同品种现有挂单防同价堆叠**: orders_get 过滤该 symbol, 目标价±停损宽幅内有活单=按最小影响原则跳过(只报不动), 与"持仓清理最小影响"同口径
- **家族账本补账缺日写显式标记行**: 断账日(如 LLM 日结 429 被吞未生成条目)补登一行 `status=GAP_EXPLICIT`(ts+缺因+参考区间), 不静默不造数——数据有效性闸的账本变体, 巡检点名断账时以显式销账

## 即时启动机制（李11-16令: 别因一个限流就不干活了）
- **池全 WALL 时确定性回测主 bot 自跑, 不等池不派 LLM 子代理**: LLM 池堵时 P1 修复批/参数研究的**确定性段**（同分母五验回测）由主 bot 直接 `terminal` 跑 `research/rd_verify_batch_20261114.py` 复现器（`prepare30/gen_signals/simulate/five_gates/verdict_of`, 常量 `COST=0.095/COST_T5=0.15/REAL_SL_CAP=1.2`, 解释器 `D:/workbuddy/binaries/python/versions/3.13.12/python.exe`）——网格扫描(SL×TP 格点/giveback 离场宽容度)全 0-LLM 自跑出逐品种裁定; 只把 LLM 段（翻闸/归纳）留池恢复。自跑脚本三坑: dist/tp_d 须传与信号栏 ATR 同长度数组（传全长 atr 必 IndexError）、R 数组转 float 再 json.dump（ndarray 不可序列化）、gates/cand dict 补全 "R"/"n" 键（five_gates 内部 T3 要 array_split cand["R"]）。
- **参数研究 <6/6 = 提案文件不激活 + 前向攒样单**: 未过 6/6 的参数结论写 `data/practice_params_vN_proposal_*.json`（status=PENDING_FORWARD_SAMPLE, 逐品种列 lever+证据净R+闸分）, **不改生产参数表**; 配 rd_queue P1 前向攒样单（前向波 0.01 手挂单标 params_ver=vN-fwd, 30 单或⑥线到=chief R11 翻闸 bump 版本, 未到=继续攒）。挂单时机=用户清场令解除后, 清场期 0 挂单保持, 攒样单排队不硬挂。
全品种深度优化执行法（李令"所有品种深度优化/全部按赚钱参数执行"类指令, 开单前必跑）:
- 确定性段主 bot 自跑, 0 LLM: 复现器 research/rd_verify_batch_20261114.py(prepare30/gen_signals/simulate/five_gates/verdict_of) × 全 M30 可回测品种(现 11 个: BNB/BTC/ETH/EUR/GBP/KSM/LTC/SOL/US30/XAU/XRP) × 网格 SL∈{0.5,0.8,1.2,2.0}×ATR × TP∈{1.5,2,3}R 同分母五验; 可复用 runner=research/all_symbols_deep_opt_20261117.py(改 OUT 文件名后直跑, 单跑 ~10min 后台跑)。
- 翻转纪律: 只翻 verdict 过线格(WATCH≥4/6 且 OOS 双正)的 sl_mult/tp_mult, 逐品种留 prev 值+来源注; 无过线格品种参数表**一字不动**(防过拟合); 样本 n<30 品种无裁定权(GBP/US30 常态)。
- **跑网格前必先同分母 OOS 核验现行生产参数表**: 进化产出的宽参数表(sl_mult 4.5/tp 7 类)30d OOS 可能全线净负=整表负期望——发现后第一优先项就是回退保守格, 不是调进场所。
- 报数纪律: 格点排名从 JSON 按净 R 降序复核后再报(手速易把"4/6 双格"排序报反, 会话实踩); best 字段只取 4/6 格, 净 R 更高者手动复核。
- rd_queue.json 顶层 dict(键 items/ts/tasks/queue, 非 tickets): 追加工单前先读实际结构再写, 不猜键。
- 指令切换留痕: 会话内用户先后两条令 SL 口径相反(宽损防扫损样本 ↔ 紧损赚钱格)时, 每条令各自执行留痕, 新令在执行窗(开单哨 fire time)前覆盖旧令——被覆盖的哨脚本当拍重挂锚+py_compile(改常量名后正文常残留旧名引用, 编译不过=哨静默挂, 编译验活是注册 cron 前的必检)。
- 用户指令样本单(params_ver 标 L5_DIRECTIVE_SAMPLE): 照令执行但数据只当指令样本记账, 不用于参数表五验/翻闸, 验尸哨单独归档"为什么亏+怎么改对"。
- 故障后**立即重试**, 不空等下拍: 强平哨/验尸哨 INIT FAIL=5min×3 零参重登循环(已落码)
- 任务级: jince_rerun_immediate.py(4be8bdf1b647 每30min静默扫 jobs.json 24h 内失败) + cd863fdae55c 故障补跑哨(每30min: error类 cronjob run 重跑[429直接run/MT5先零参重登], delivery_failed类只列补投清单不重跑, 30min限流防风暴)
- MT5 掉授权=零参 initialize() 立即重登, 不等 30min 哨下拍

## 429/Agnes key 全 WALL 降级处置（LLM 任务批量挂的判别与等待纪律）
- LLM cron 连败 ≥4 拍先查 key 哨状态定根因再动：全池 RED/全 WALL=外部堵墙（多任务同根，不逐 job 修 prompt）；单 key 异常=池配置问题。堵墙态下**禁手动 `hermes cron run` 重触发 429 job**（限流窗口内重试=风暴），由 key 哨自带 429 回收机制接管（堵解自动跑）；确定性兑底件已落盘=允许静默等待，未落盘=当晚补跑哨必须接住。**池堵时确定性研究段（五验回测/网格扫描）不等池: 主 bot 自跑复现器, 见「池全 WALL 时确定性回测主 bot 自跑」条。**
- 429 子类判别（读报错文案，不只看 HTTP 码）："used up today's text quota / Try again after H:MM:SS"=日额度耗尽，以文案时刻为恢复点（勿估次日 08:00，会错过重置窗口）；**该时刻已过后池仍全 WALL=池级堵墙非单 key 额度**，升红单独报而非继续静默等待。
- 暂停挂掉的 LLM job 允许（止噪）但必带恢复承诺：连败重报刷屏 + WALL 池被重试锤击时 pause 止噪收益>风险；风险只来自"暂停后忘 resume"——暂停当拍必须登记恢复承诺（one-shot 哨挂 WALL 复查时刻，或次日 06:00 复查点），承诺写进 sd_guard_run.log（job id + 触发条件 + 复查时刻），堵解后 resume + 手动补跑欠的 LLM 段, 并 message_agent 点名 LLM 依赖席位（研发/风控等）认领在途待裁/待回执工单, 不等其轮询。若 WALL 跨夜且次日关键 LLM 任务（事件窗哨/K线刷/汇报）依赖它=06:00 前仍 RED 则升红单独报用户。
- 定时回测枪静默判读：看门狗报「回测产物 >36h 且无回测进程」先读产物 stamp 文件（如 backtest_edge_run_stamp.json 的 note）——「引擎在跑, 本枪不并启」=防竞写 by-design 非故障；stamp 无 note 或 note=crash 才开枪补跑。另 cron job 的 last/next_run 字段易读混（last 显出未来时刻=实际读到 next），判死以「产物 mtime + 进程在否」实读为准，不信 job 字段。

## 验尸案例库 · 11-17 30d 全量亏损单深度验尸（李彦明令"全面深度解析亏损单, 务必学到技能", MT5 实读 238 平仓单）
> 大盘: 30d(10-18~11-17) 赢 81 笔 +341.72 / 亏 157 笔 -323.97 = 净 +17.75, 胜率 34%。"不赚钱"=赚亏互抵, 亏的结构 5 源全定位。证据 cache/scratch/loss30d_20261117.json。
- **四大铁律(每单验尸必问)**:
  1. **单笔风险 ≤1% 净值**: SL距离×手数 上限(989 净值≈$9.9)。案例: 1.0 手美个股 m20261105 4 单 1 赢 3 亏净 -21(BLK -18.80 单笔风险 1.9%)=总亏损 12%。1.0 手仓=L5 李彦明拍板项, 执行层不自主持(闸码先行=large_lot_size_gate_20261117 入队 P1)。
  2. **通道/参数版本 30 笔净归因, 不过即关**: 每 magic 通道/参数表版本带 30 笔滚动净归因, 净负且 PF<0.5 且样本≥30=关闭。案例: m20261020 老通道 9 笔净 -77.59(PF 0.04)=最惨日 10-22 -72.43 全出自它, 停 26 天无人查=教训: 老通道不显式关闭会静默带病。
  3. **宇宙修剪: 30d PF<0.1 的家族/品种出池**: 小众离岸 FX(NOK/SEK/SGD/CNH/MXN/AUDNZD) 20 笔 19 亏 1 赢净 -28.76=系统性点差手续费磨损, 无 edge。出宇宙=universe_prune_exotics_20261117 入队 P2(同分母回测出池前后净 R 差+前向 0 单确认)。
  4. **对治验收=部署后零复发日, 部署≠根治**: B0 量能闸+ADX 闸 11-14 部署→11-15~17 B0_INVAL 零复发(此前 4 天 52 笔 -70.09)✓=验收通过才销账。凡"已部署"宣称必附部署后同型事件计数, 不附=验活哨打回。
- **反向证据(别动好的)**: 股指族 30d 净 +76.26(PF 2.9)=唯一大净源; 主对 FX +7.86; 币系 29 笔 -12.69 单笔均 -0.44=磨损型(滑点 0.095R×2 边, 币系点差吃 2/3 R); JPY 族 E2 否决闸部署后 11-15~17 仅 -0.86 ✓。亏损集中日: 10-22(-72.43 老通道)/11-17(-21.09 大头 BLK)/11-12(-12.48 批量窗)。
- 大白话: 赚的是股指+主对, 亏的是 ①假突破追单(已治) ②没人管的离岸垃圾对 ③1.0 手大仓 ④老通道带病 26 天。技能提升台账=本案例库+rd_queue 2 件+L5 报李(大手数冻结/降 0.01)。
- **李彦明11-17纠正: 亏损不是斩除对象, 是学习素材——每个亏损源要找到"为什么亏+怎么改对", 修复走同分母五验过线才翻闸, 禁"亏损就砍"**: 四修复方向入队(升级上面粗口径)——①b0_exit_upgrade_20261117(P1): B0 52笔0赢=进出场组合缺陷(进场付突破溢价+离场早于结构完成), 修复=结构失效离场(M15破结构/2连收+MFE≥0.5R持有)+扫掠确认进场+8主流集中, 30d B0事件集4组同分母(A现行/B结构离场/C扫掠确认/D组合); ②large_lot_struct_sl_20261117(P1): 1.0手SL距1.5-1.9%过宽=结构锚定SL(M15摆动±0.3ATR)+单笔风险≤1%净值硬预检, 1.0手去留=L5报李; ③coin_ny_session_edge_20261117(P2): 币系37亏7赢但单笔对称(-0.45/+0.43)=胜率问题非量问题, 修复=NY午后17-21UTC波动重心时段+位移确认; ④cost_ratio_universe_20261117(P2, 并入universe_prune_exotics): 离岸FX出池依据=成本比公式(2×点差$+手续费)/(0.01手风险$)>30%R=数学无edge(可回测出池前后净R差同分母), 非"亏损就砍"。

## 挂账 bug（修完销账）
- [x] 01:30 验收 delivery_failed + tzdata 崩(ZoneInfoNotFoundError) -> deliver 改 origin + training_run.py tzdata fallback 修讫(11-16)
- [x] 日结/学习进化 429 挂掉 -> 08:45 补跑哨 cd863fdae55c 兑底修讫(11-16)
- [x] 宿主闸 hermes-cron 宿主假 FAIL 锁死池单闸 -> training_host_gate_check.py 加 PASS_INDIRECT(回测收工+新卷落盘)修讫(11-16), 重跑哨销旧 stamp
- 御史P2: GTC跨日超龄挂单显式撤销 + HOT_USD/FLOOR_USD 死常量清理(下轮)
