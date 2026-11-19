# 盘口中间深析节点×3 + 看门狗投递层兜底 (2026-10-08, 永久)

> 本文件是 SKILL.md 因超 100k 上限被拒后的落点, 承载以下四块。SKILL.md 正文已超限, 新制度一律写本文件, 不再塞 SKILL.md。
> 443/DNS 闪断、回测"静默 vs 连崩"、去重指纹稳定——先诊断后动手的判据在 `references/flapping-shared-resource-diagnosis.md`(同目录), 本文只写投达兜底制度。

## 1. 盘口中间深度解析节点 ×3 (用户令"加大例会密度/开盘收盘中间加一次深度解析 全员参与 进化升级 助力尽快出徒")
- **3 个中间节点 (no_agent 0 LLM, 429-proof)**: 脚本 `E:/workbuddy/国外模型/hermes/scripts/jince_midday_deep.py`, 比 6 开/关评节点多两段 —
  - ② **半日对账**: 开评研判方向 vs 当前实价, 逐品种判 命中/做反/未动 (读 daily_advisory + live tick, 降级用基准价)
  - ⑤ **进化点**: 确定性挑 1 条"系统方向 vs 24h 动量矛盾"(|动量|≥3% 反向) 信号进五验, 0 LLM, 矛盾就点名 @strategy-rd 同分母复验方向闸
  - 5 段结构: ①动量top ②半日对账 ③我方open挂单/持仓 ④引擎健康(swing胜率/回撤/净方向/事件面) ⑤进化点
- **cron 三 job (全 no_agent=true deliver=bot-chat)**: `jince-midday-asia-1005`(10:05亚)/`jince-midday-europe-1635`(16:35欧)/`jince-midday-us-2335`(23:35美), 落在对应开/关评节点之间的盘口中段。脚本不带参按钟点 fallback 到正确中间节点 (9-12→asia / 15-19→europe / else→us)。
- **全员参与铁律**: 中间节点投群后各岗 30min 内接力 — @chief 归纳 / @risk-officer 复核 / @strategy-rd 认领进化点, 漏接的 22:00 日报点名。助力出徒 = 每 3 段盘口多一次"半日对账+进化点", 把 1 天 6 节点的进化密度提到 9。
- **冬夏令时也吃 DST**: 16:35 欧中/23:35 美中是夏钟点, 冬夏令切换日 (美 11月第1个周日/欧 10月最后周日) 前后各移 1h (欧中 17:35/美中 00:35), 切换日总调度手动挪 cron + 群里标一句, 与 6 开/关评节点同规则。

## 2. 看门狗"投递层兜底" (治 10-07 21:05 卡12h / 10-08 02:05 卡7h 没进群的静默失败根因)
- 旧看门狗 `jince_watchdog.py` 只管"节点生成没生成"(缺节点/迟发), 不管"生成后投没进群" — 这是 12h/7h 漏投没被兜住的根因。
- 新增 `check_delivery_stuck(today)`: 读 cron `jobs.json`, 凡今天已触发(last_run_at 是今天)但 `last_status=delivery_queued/delivery_failed` 且卡 **>30min** 的节点 → 判为'生成了没进群'。SCHEDULE 已扩到 9 节点(含 3 中间), NAME2KEY 加了 jince-midday-* 映射。
- **发现即补(非 22:00 批量)**: 卡投递的节点由看门狗 `regen_body(key)` 当场重生成最新正文(`--noreceipt` 不重复写 log), 塞进看门狗自己的 stdout → 看门狗本身是 no_agent cron, 每 15min 一 tick, bot-chat 把这段正文当消息投群, **群一空闲就落进去**(SESSION_NOT_OWNED 只在群活跃时拒, 空闲即通)。所以投递层是'卡 30min 就动手、每 15min 重试到落进', 不是攒到晚上。
- **防刷屏 vs 及时补 要拆开**: `alerted`(落盘 state)只去重'告警文案'避免每 15min 重喊, 但**不挡正文重新注入**——正文每轮都重新塞, 才能'群一空就落进'。若把正文注入也按 alerted 去重, 就退回'卡一天没人补'的老毛病。
- **正文注入本身也要防刷屏 (2026-10-08 实撞, 永久)**: 节点卡在 `delivery_failed` 且通道降级(如外网探活误报)时, "每轮全篇正文重塞" 会反向刷群(同节点全篇正文连刷 3 次+)。治法: 给重投加**每节点冷却** (同 key 45min 内只重投一次, 冷却内只报一行"冷却中"、不再重发正文; 冷却到后只发**一行摘要**(实读:账户$/0挂单0持仓), 不再全篇 6 段)。冷却戳落 `node_backfill_queue.json` 该条目 `ts_last_regen`。判据: 冷却内 = `now - ts_last_regen < 45min`。**三层压频**: 全篇→摘要→冷却中静默, 内容全程落 discussion_log + 22:00 兜底销账, 零丢失。坑: 冷却/摘要逻辑要放在 `check_delivery_stuck` 循环里按 key 判, 别把 cooled 节点也 append 进 `backfilled_bodies`(那就还是全篇刷)。
- **实现坑 (会炸)**: `datetime.now(BJT)` 是 aware, 减 naive 的 lr_naive 会 `can't subtract offset-naive and offset-aware`。修法: `datetime.datetime.now(BJT).replace(tzinfo=None)` 归一 naive 再减。
- 三层兜底闭环: 生成层(漏跑→当场自动补生成) + 迟发层(超15min→报) + **投递层(卡>30min→当场重生成+每15min即时重投)**。静默失败机制上没机会。

## 3. 投递卡队列真根因 SESSION_NOT_OWNED (jobs.json last_delivery_error 实读)
- bot-chat 注入群消息时, 若该群会话被别的 owner (cli/桌面会话某 pid) 持有活跃 lease, 报 `hermes-refusal-reason: SESSION_NOT_OWNED ... already has a live owner (cli, pid 16352)` 拒绝投递 → 内容留在 delivery_queued。这是活跃群里节点"生成了没进群"的真底。
- 区别于另外两层静默根因: 网关进程掉线 (bot-chat 600s 超时) / 外网断 (fail-open 用快照) — 三层症状都"没进群", 根因不同, 排查要分: 生成层看 discussion_log, 投递层看 jobs.json last_status/last_delivery_error, 网关层看 gateway status + network_probe_last.json。
- **extnet 探活单端点误报 (2026-10-08 实撞, 永久)**: 看门狗 `extnet` 探活若只探 `api.ipify.org` 单端点, 那台抖了就把**整个外网判 down**(挂过 129min), 反向把投递层压成 fail-open 降级态, 节点卡队列。实读判据: 外网通不通看 `gh api rate_limit --jq .resources.core.remaining` — 余量满(5000)= 非账号级限流 + 外网通, ipify 只是抖了不该判 down。治法: 探活加 **gh-api 余量兜底**(ipify 探不到再验 gh token 余量, 余量>0 判 `ok(gh-api兜底)`, 余量见底才真 down); 且 `extnet=ok/down` 判据要与投递层"群能否落进"解耦, 别让探活误报卡死投递。
- 治法: ①看门狗投递层**即时补**(卡>30min 当场 `regen_body` 重生成正文, 每 15min tick 重投, 群空闲即落) ②避免在群活跃时反复手动 `cronjob run` 补发(同样撞 SESSION_NOT_OWNED, 更插不进; 交给看门狗的 15min 重试) ③**22:00 日报只做兜底销账**(扫 node_backfill_queue 里还 `retrying_now`/`awaiting_2200_batch` 的, 强制补投销账), 不是首道。不删 live owner 的 lease 强夺。
- **卡队列"卡很久"≠ 内容丢了 (实读判据)**: `delivery_failed` + `last_delivery_error=SESSION_NOT_OWNED` 的节点会一直卡(几百分钟), 但正文**早已落 discussion_log**(生成层那刻就写了), 台账 `rule_no_silent_drop` + 22:00 兜底批量销账双保险 → 全程零丢失。判"卡队列"时先实读该 key 在 discussion_log 有没有正文, 有 = 安全, 交给 22:00 销账, 不必手动重发(手动重发同样撞 SESSION_NOT_OWNED, 反而刷屏)。
- **别强改 jobs.json 的 last_status 去销账 (改产物被冲回)**: 手工把 `last_status` 从 `delivery_failed` 改 `ok/delivered` 只活一轮, 下一班投达/看门狗重算会冲回(同 risk_freeze_state.json 那族"改被循环重算的 state")。销账只能走 22:00 兜底批量那条合法路径, 或等该节点下轮投达自然翻 ok。强行改 = 治标不治本还留脏读。
- **合法销账点 = node_backfill_queue.json 台账条目(非 jobs.json)**: `delivered_nodes(today)` 读台账 `layer=delivery + status=delivered + ts_created_day=当日` 来抑制重投, 手写这个条目不被循环冲回。某节点反复刷屏且实读确认正文已进群(用户端逐班收到摘要/巡检 6 节点已发含该 key)时, 直接把该 key 台账条目置 `status=delivered`+`ts_delivered`+note 留痕 = 当场止血, 是 22:00 兜底销账之外的人为提前销账合法路径。与 jobs.json last_status 的区别: jobs.json 是投达循环重算的产物(改了冲回), 台账销账是看门狗自己读的状态源(写了即生效)。验货: 写后复跑 `delivered_nodes(today)` 确认该 key 在名单里 + 下一班看门狗不再列该 key。
- **治本: 投达目标切到干净 profile(切 `bot-chat`→`bot-chat:<干净profile>`)**: 上面全是止血。结构性根子 = `deliver='bot-chat'`(own/默认桌面会话) 的投达走 CLI 旁路, 用户全程在桌面对话时该会话被 desktop owner 长期持有 lease → 每条 cron 投达撞 SESSION_NOT_OWNED 被拒(修网络/加超时都治不了)。治本 = 把金策任务的 `deliver`+`failure_deliver` 改成 `bot-chat:<某干净profile>`(该 profile 的 Bot Chat 无桌面 owner 占租约, CLI 旁路能正常 claim+投递)。改前三件硬要求: ①备份 jobs.json ②**精筛**哪些任务要切(同文件里常混着非交易任务如各学科网站/教学线, 别 bulk 全切, 逐条按 name/script 筛) ③改完用 `parse_bot_chat_deliver_token`+`_resolve_bot_chat_target(job, tok)` 实读 target **非 None** —— 若投递进程的 profile 根里 `profile_exists` 看不到该 profile, 解析返回 None = 任务**静默 skip、内容进不了任何群**(比 SESSION_NOT_OWNED 噪声更难发现)。config.yaml 的 `cron.bot_chat_delivery_timeout` 是保护文件 agent 改不了(需用户手动), 不影响主修复, 跳过。

## 4b. 正期望腿放大候选的实数口径 (用户令"务必出赚钱的策略")
- 放大候选只从 edge_tracker 里"有样本 + 正期望 + 未退役"的腿出, 不凭空造腿。判据: n>=5 + pf>1.0 + gate_flags.retired!=True。`n*(pf-1)` 越大越优先。
- **异常 pf 铁律 (踩过实数坑)**: pf 异常高(如 99.0 = 单笔超大赢单顶上去的)不是"稳期望", 是**单笔 outlier**——判据 pf>=10 或 max_win >> avg_win*3 的腿一律只观察不放大。放大候选只取"样本多 + pf 中等(1.5~5) + WR 健康"的腿。实例(2026-10-08): 全系统唯一正期望腿 7 条, 其中 GBPAUD(pf99)/RIVN(pf18) 是 outlier 不放大; 真正放大候选 = EURJPY(n20 pf2.2 WR70%) / EURNZD(n19 pf1.6) / GBPCAD(n22 pf1.05) / CADJPY(n10 pf5.0)。
- **放大 = 走五验攒样本逐级升, 不是当天拉满仓位**: 0.01 观察仓起, 五验过了才升手数; 负期望腿(如 21 条 RETIRE) 0 开 0 放大是赚钱的另一半(砍失血点)。丑话必带: 历史回测≠未来收益, "赚钱"= 正期望+风控+时间, 不承诺收益。
- **剥头皮类(赢单均值小、靠胜率>70%)的腿**别套 swing 腿的 RR≥2 质检**, RR 口径单独定(高胜率+RR<1 也能正期望), @risk-officer 复核时按腿型分开核。

## 3.5 后台训练机制(完善版, 2026-10-08 用户令"不进场后台模拟训练/训练机制进一步完善", 永久)
**"不进场≠不训练"闭环**: 30min 全链天天攒样本(edge_tracker 164 腿) + 回测台每日验收考正edge + 五验 WATCH 交叉 → 哪条腿样本≥30+胜率/盈亏比达标才放大实盘=出徒路径, 全程后台模拟零实盘风险。
- **确定性脚本 `~/.hermes/scripts/training_run.py` (no_agent 0 LLM 429-proof)**: 三步全 fail-open ① 跑 `backtest_engine.py`(全宇宙, 超时900s 退 SMOKE冒烟 3品种) ② 交叉五验 WATCH/PENDING 卡对照回测正edge候选(进=攒够可升级/没进=继续观察) ③ 写 `data/training_daily_report_YYYYMMDD.md` + 投群正文。坑: 该脚本在 GoldstrategyEngine 下另有一份同名副本, cron 只认 ~/.hermes/scripts/ 下相对文件名, 改要改对那份+同步。
- **[2026-10-09 修根·两枪拆分] 旧版把 6.7h 全宇宙回测塞进 01:30 验收枪的 900s 超时 subprocess → 每日必超时降级=空报告("有闹钟没内容", 用户问"制度怎么没运行"的根因)**. 现拆: ① `0878a08d2a92` 金策·后台训练·全宇宙回测(00:10 不限时, no_agent, script=training_full_universe.py) ② `475d7361ad9a` 01:30 验收枪 training_run.py **只验收上一轮产物**(读 backtest_edge.json + backtest_edge_run_stamp.json 判新鲜度≤36h + engine_selfcheck_pass), 读不到→fail-loud 抬头报不静默降级, 看门狗抓 delivery_queued/failed 补投。坑: 00:10 job 若创建时点已过当日 00:10, 首次调度落次日, 当天需手动 `cronjob run` 开第一枪。
- **回测 cron 子进程 numpy 崩根子 (10-09 实锤, 治 3 个月没刷新)**: cron no_agent 运行器把父进程 PYTHONPATH/PYTHONHOME 带进回测子进程 → `No module named 'numpy._core._multiarray_umath'` 0.2s 崩(手动终端干净环境能跑, cron 链路崩)。修: training_full_universe.py 子进程 `env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')}`。验: 污染场景下子进程 `import numpy` 应出 ATE venv 的 2.5.3 而非父 2.4.3。
- **回测模式定死**: 全宇宙 164 品种按 2.2h/品种 要 ~15 天排不进窗口 → 每日 00:10 只 SMOKE 3 主品种含黄金(~6.7h), FULL 仅 env(JINCE_BT_MODE) 手动/引擎提速后再排。金策关注的黄金在 SMOKE 3 品种里。
- **引擎自检哨兵 (新闸, 治"回测口径虚高")**: training_full_universe.py 落 run_stamp 时扫 backtest_edge.json, 凡 n>500 且 wr>0.9 的腿数>0 即 engine_selfcheck_pass=False(实例: TREND XAUUSD n=8901 wr=0.996 = 引擎触价判定有偏, 非真有 99.6% 胜率腿)。验收枪读到哨兵不过→本轮回测作废, 点名 @strategy-rd 修触价判定, 修好前 3 条正 edge 候选全挂起不得作五验依据。
- **回测台已有防过拟合闸(别重复造)**: `backtest_engine.py` 带 DSR(Shap>0概率)+PBO(概率加权bootstrap过拟合概率)+walk-forward train/test 切分+真实点差/隔夜swap+防前视(信号bar i→下根开盘入场)+同根K内SL/TP皆触取距entry近者。正edge判定 n≥20 且 pf≥1.0。
- **训练行口径**: 全链每 30min 出的 `[训练] 净值=...曲线已落盘` 是净值曲线, 不是回测验收; 真正的"训练→验收→出徒"= 00:10 回测 + 01:30 验收交叉那两枪。两者别混。
- **通用铁律(制度验收)**: 建任何 cron/自动化后必实数验 last_status + 进程活 + 产物刷新戳, 禁止"建了=在跑"。判回测真在拉数据: 找 16:5x 起的回测子进程(高内存 80→400MB 在涨), 不是看脚本日志(收口才 print, 在跑=0 字节正常)。

## 4. 节点补发机制 (no-gap 铁律, 2026-10-08 用户令"耽误了要补上、不能就算了、下一步要有个补发机制不能空缺")
主持岗失职根因 = 机制停在"点名"(旧看门狗只报不补)。现已做全, 与 strategy-rd 的研发侧 `research_backfill_queue` 镜像成两条补发线:
- **节点侧台账** `E:/GoldstrategyEngine/data/node_backfill_queue.json` (镜像研发侧结构), `rule_no_silent_drop=true`, 跨日自动翻篇(按 ts_created_day 过滤, 只留当日 items)。
- **生成层自动补生成** (jince_watchdog.py 每15min): 某节点到点没生成(log 缺) → 看门狗当场跑对应脚本补出正文 (`jince_node.py <key>` / `jince_midday_deep.py <key>`, MIDDAY_KEYS 判哪个走哪个, 显式身份会写 discussion_log 回执), 并把节点正文带进 stdout → no_agent 投递时当场进群(用户立刻看到), 进台账 status=backfilled。
- **投递层发现即补(非 22:00 批量, 用户 2026-10-08 明确令"不是最后补 是 及时发现及时补")**: 节点已生成(log 有)但 cron last_status=delivery_queued/failed 卡>30min → 看门狗 `regen_body(key)` 当场重生成最新正文(--noreceipt 不重复写 log), 正文注入看门狗 stdout, 靠 15min tick + 群空闲 bot-chat 投达, 台账 status=retrying_now; 重生成失败才落 status=awaiting_2200_batch 升级兜底。铁律: 22:00 只兜底销账, 绝不把漏投攒到晚上当首道。
- **22:00 日报兜底销账** (job 44cf5a303c9e 加 5b 步): 读 node_backfill_queue + research_backfill_queue 两份台账, 对还 `retrying_now`/`awaiting_2200_batch` 的逐条: 节点侧重生成正文投群+销账; 研发侧 @strategy-rd 认领格 BACKFILL 补做或 DROP 显式放弃(需 risk-officer L4 签核); 日报末加一行"补发销账: 节点X条/研发Y条, 全销/剩Z条升级"。
- **两脚本互不冲突**: jince_auto_patrol.py(30min) 只报不补(缺失进 problems), 看门狗补完后它看到的 got 集合已有该节点 → 不重报; 巡检 6 节点范围比看门狗 9 节点窄, 更保守。
- **验证三枪**: ①三脚本 py_compile 全过 ②单测 backfill_generation('asia_open') 真补出带⑥教学层全 26 行正文 ③台账 round-trip no_silent_drop=True 落盘。坑: 单测会真写一条 asia_open 进 discussion_log(等价补发该节点), 下次看门狗会判它"迟发"(落盘时刻 vs 计划 08:05 差>15min)——测试副产物, 非真迟发, 可忽略。
- 铁律: no_silent_drop = 没有"就算了"选项, 耽误的**当下就补**(生成层当场自动补 / 投递层卡 30min 即时重投), 22:00 只兜底销账漏网项, 全程留痕在两份台账。用户原话钉死: 首道永远是"及时发现及时补", 不是"最后补"。

## 3.6 防复发三道闸 (2026-10-09 用户连令"怎么还没执行/看看怎么回事/下一步如何避免再次发生", 永久)
事故链: 01:30 验收枪把 6.7h 全宇宙回测塞进 900s 超时→每日超时降级空报告, 空转 3 个月无人发现; 拆分(00:10 回测+01:30 验收)后第一枪 0.2s 崩(numpy), 重开的那枪又因宿主选错静默死——**根子不是单点, 是"建了≠跑了"没人盯**.
- **闸① 开跑前快检** (`training_full_universe.py`): 干净环境(剥父进程 PYTHONPATH/PYTHONHOME)先 10s 验 `import numpy,pandas,MetaTrader5+initialize`, 坏 fail-fast 秒报不烧 6.7h。环境坑根因: cron 运行器 PYTHONPATH 指向基础 3.13 site-packages(numpy 2.4.3), 继承给 ATE venv 子进程→`No module named 'numpy._core._multiarray_umath'`(numpy C 扩展与解释器错配), 终端直接跑没事、cron 链路必崩。
- **闸② 训练枪自监控** (`jince_watchdog.py` main 尾部 `_bt_warn`): 每 15min 自动报 三种 fail-loud: (a) 回测产物>36h 且无 backtest_engine 进程=静默没跑 (b) run_stamp engine_selfcheck_pass=False=引擎哨兵打回(TREND腿 n=8901 wr=0.996 这种虚高) (c) 上一枪 rc≠0 且无新进程=崩了。哨兵判据已收紧: 任何 n>500 且 wr>0.9 的腿即虚高实锤, bad==0 才 pass。
- **闸③ 宿主选错死循环** (2026-10-09 17:47 实锤): 从自己的 terminal 后台会话拉起的长跑进程, 会话一断整棵进程树被连锅端(31712→45448→34416→20084→35308 全没, 0 字节日志静默死, 非崩是杀)。规则: **超过会话生命周期的长跑(回测/训练/全链)一律挂 cronjob_manage run 或独立 Windows task(宿主=调度器), 不挂自己 terminal 后台**; 挂完必须 wmic 实核子进程起跑才算"开打了", 不能只看回执 success。
- **回测节奏定死**: 每日 SMOKE 3 主品种含黄金(~6.7h, 00:10 起 06:50 收); 全宇宙 164 品种按 2.2h/品种 要 15 天排不进窗口, FULL 仅 env JINCE_BT_MODE=FULL 手动触发, 等引擎提速后再排。strategy-rd 加过"防竞写"段, 其 reuse 判定("")有 bug 已由 @hermes 修成 reused 标志——改这段脚本前先读全文, 别覆盖掉竞写防。
- **防竞写 reuse 防"并启双枪"也防"误报没有枪" (2026-10-10 实修)**: 探活 wmic 的 `child_env` 若把 PYTHONPATH/PYTHONHOME 剥太干净, wmic(C:\Windows) 会"不是有效的 WIN32 应用程序" → 探活抛异常 → 走"降级直跑" → 已有枪在跑时又并启第二枪写同一真源(脏写)。治: wmic 探活必须用**原始 os.environ**, 只有启动 ATE 引擎子进程才用 child_env, 探活异常不得 fail-open 降级直跑。
- **引擎 rc=1 真因家族 (2026-10-10 实锤)**: `if syms == ['SMOKE']` 判的是**逗号分隔列表**, 而 argv 传单元素 'SMOKE' → 匹配失败 → 实跑 164 全宇宙(数小时)被超时 SIGKILL → 收工写 rc=1。治: argv 传 `'EURUSD,XAUUSD,BTCUSD'`(逗号分隔) 才进 3 品种 SMOKE 支路; 直跑诊断要重定向到 UTF-8 文件再读, 前台 pipe 读 ATE 输出会 GBK 解码崩。
- **引擎自检哨兵判据 (收紧 2026-10-09)**: backtest_edge.json 里 任何 n>500 且 wr>0.9 的腿都算引擎虚高实锤, 计数 bad, `engine_selfcheck_pass = (bad==0)`; 哨兵不过 → 本轮回测整份作废, 全部正 edge 候选挂起不得作五验依据, 点名修触价判定。
- 销账规则硬化(同日): 看门狗冷却只防全篇刷屏不定销账; 正文已落 discussion_log 且卡>4h→强制 delivered; 卡>2h→强制摘要重投(不再拖 183min)。
- **[2026-10-09 第三枪 814s 挂, 暴露 3 个非 numpy 新坑(逐个修, 防再犯)]**: ① 调度器 reader 按 UTF-8 读 no_agent 脚本 stdout, 而 cron 环境 locale=GBK → 脚本中文 print 出 0xd3(GBK 字节)崩 reader 线程(UnicodeDecodeError); 治=脚本头 `sys.stdout.reconfigure(encoding='utf-8',errors='replace')`(已焊 `training_full_universe.py`)。② strategy-rd 防竞写段 `reused=getattr(r,...)` 在 pids 空时 r 未定义→UnboundLocalError 降级; 治=`("r" in dir()) and ...` 守卫(已焊)。③ 引擎本体 rc=1(814s 早挂, 上轮 SMOKE 6.7h 才正常收工)= 真因未定, 待引擎直跑日志; 快检闸① 只验 import 不验引擎能否跑通 → 回测 rc≠0 时看门狗闸② 会 fail-loud 报"上一枪崩"。
- **no_agent 脚本铁律(防再犯总纲)**: stdout 可能进调度器 reader → 必 reconfigure UTF-8; 子进程用 clean env(剥 PYTHONPATH/PYTHONHOME); 长跑挂调度器不挂自己会话; 改前读全文别覆盖 strategy-rd 防竞写段; 每道闸上完实跑验证(不是嘴上说"加好了")。

- **全正口径闸失效判据 (2026-10-10 实撞)**: 池单筛选格修"读错字段"(`exp_R` 回落读 `exp_R_scan/exp_R_tick`)后若 dry_run 实测放行腿数 = 池内全部腿数(如 184/184), 说明闸没在筛——n_fill 门槛对 800+ 腿形同虚设 + exp_R 没扣成本。此时**整条池单闸挂起**, 不得按最小缝放行任何一条(闸失效时放行=放水); 修到"过闸腿 < 全池数"才谈出单。放行依据只认 edge_tracker 逐笔实盘双正腿(n/wr/pf), 不认池内 exp_R 口径。
- **研判≠下单依据 (铁律, 反复纠正点)**: 用户会把"分析很给力"推到"按分析做单就能赚钱"——主持必须拆穿: 91 笔实盘里方向对但扣成本仍亏的腿(金/币多数负) 就是反例; 研判只沉淀成 ①否决门 ②可回测触发位, 不当单独开仓依据。高胜率≠正期望。放大只走出 P6 出徒四件齐那条链, 不出"每天分析→跟着做单"的口子。历史回测≠未来收益必带。

## 3.8 进化加速 + 全面规章制度 + 巡检制度 (2026-10-10 集体讨论定稿, 立即执行)
用户令: 集体讨论加快进化步伐、建详细规章制度、所有有利进化路径全面落地、建巡检制度立即执行。
详细制度文档: `references/evolution-acceleration-and-inspection_20261010.md` (进化路径 P1-P6 全链 + 加速三招 + 规章制度 + 巡检 10 条 + 立即执行清单)。
本节只留**主持岗放行的 always-on 规则**:
- **放行前置 = 数据源健康**: 回测引擎 rc=1 连挂 N 晚且 backtest_edge.json 未刷新 = 进化链数据源头断了。此时 **P4 回测验收 / P6 出徒放大 全挂起**, 不得凭旧产物放大; 主持先报"引擎断了两晚", 再谈出单。治法 = 引擎 rc=1 真因家族(见 §3.6) + 引擎提速 @strategy-rd 认领。
- **加速三招 (不等引擎, 可并行)**: ① 5 条正期望腿 0.01 验证仓按三铁律并行攒 OOS 同号(学费单不是印钞机, 不加品种不加手数) ② 出徒台账每日 01:30 自动刷 OOS x/30, 到 30 笔自动提请 L4 二次 APPROVE ③ 研判→规则: 方向判断只沉淀成可回测触发位/否决门, 不单独开仓。
- **巡检制度 10 条 (全 no_agent 0 LLM 429-proof)**: 节点看门狗15min / 24h心跳5min / 看板10min / 行情喂5min / 全链30min / 每日体检03:00 / 2h效率播报 / 训练枪自监控(闸②) / 出徒巡检(新) / 引擎rc=1专项(新: 连挂2晚升级 @strategy-rd 必修, 第3晚未修 fail-loud 报群)。任何巡检 fail-loud 不是静默。
- **主持纪律 (用户反复纠正点)**: 用户问"怎么没开仓/怎么没按时例会/怎么还没执行"时, 主持**先实数核台账+cron+进程**, 不辩解不检讨话术; 核到"建了≠跑了"的真断点(投递卡/引擎挂/宿主选错), 当场销账或 fail-loud, 不留到下一轮。铁律: 耽误的当下就补, 首道是"及时发现及时补"非"最后补"。

## 3.9 研判→做单 方向反馈环 (2026-10-10 用户令"学会根据分析优化做单方向, 不能只分析不会做单", 永久)
实数底座: daily_advisory 每日出 ~150 项方向研判(方向+置信+形态+EMA/HH/LL 结构位), 但 30min 出单候选**不读它**(全链 grep advisory/方向闸 0 命中) = 分析与做单两条断线; 半日对账 66 条 recon 已记 命中30/做反32(总准头 0.48≈抛硬币), 证据在攒、反馈环没闭。
- **落地脚本 `~/.hermes/scripts/direction_feedback.py` (no_agent 0 LLM 429-proof)** 三件: ① 准头表 — 从 discussion_log.jsonl 抽 recon 行按品种聚合 {hit,rev,n,acc,action}, 落 data/direction_feedback.json ② 方向闸 — 品种样本>=5 且 准头>=0.60 → 候选方向==研判方向时 WATCH→PROMOTE(**提权不提仓**, 放大仍走出徒四件齐); 准头<0.40 → 只做否决门不正向提权; 样本<5 不表态 ③ 巡检 — 准头表>48h 未刷新 / recon 0 条 → fail-loud。已接进 auto_run_cycle.py(step2f_advisory 之后), 每日 21:30 cron job 09a5de108a20 自动巡检投群。
- **准头表是品种分层的, 别笼统全接**: 总准头 0.48 是噪音, 但币系品种(UNIUSD 0.75/ADAUSD 0.67)准、部分(RIOT.NAS 0.12/XRPUSD 0.00)做反 — 按品种×方向提权/否决, 下一步 @strategy-rd 做品种×时段二层分层 + 把 PROMOTE 真正接进出候选提权分支(反馈环判据已落表, 匹配那格在引擎侧)。
- **铁律不变**: 研判只做否决门+提权、不单独开仓(与 §3.8 "研判≠下单依据" 同口径); 历史回测≠未来收益。

## 3.7 "务必开仓/天天开仓"放行三格实读 (2026-10-09, 治"报开仓但没开成"+"天天开仓"节奏决策)
用户拍"务必开仓"且子bot报"下轮 30min 循环自动出单"时, 主持先实读三格全齐才放行, 缺一格就改口不画饼:
- **格1 rd_decisions 有 L5 APPROVE**: 认数字对得上 edge_tracker(n/wr/pf 实读, 非子bot印象)。
- **格2 veto_log 有该品种 APPROVE 同判条目**: 挂单段真正读的是 veto_log(非 rd_decisions)。缺失 = 按 L4 同判格式**手动补一条**再放行(照 veto_log 现样例 {ticket,sym,decision,reason,ts}, decision=APPROVE, reason 写清"最小缝口径+edge 实数+三铁律不变+非手动插单走 30min 循环挂单段"), 补完数条数验写入。
- **格3 CIO regime 闸实读**: `grep <sym> data/auto_cycle.log | tail` — 若出 `regime=trending ADX=.. 大级别无挂单(等触发)`, 则大级别方向闸在拦, APPROVE 也**不出市价单**, 只能挂触发单且不一定立刻成交 → 子bot"自动出单"承诺在此口径下不成立, 必须改口"挂单等触发"。
- **"天天开仓"= 放大节奏决策, 主持不自己定**: 给用户两选 — (A)守纪律: 哪腿 30 笔同号过五验才放大(主持强烈建议, 这是"有 edge 才做"); (B)临时降门槛: 3 条样本最够的正期望腿各 1 笔 0.01 观察仓(为有单而做, 风险用户担, 按最小影响: 不加品种不加手数/币腿 0/强制 SL/三铁律不变)。选 B 也逐笔加不跳档。历史回测≠未来收益必带。

## 5. 群"静默"投递侧定论法 + per-profile gateway weixin 毒化 (治"群没动静"反复 churn)
用户报"群没动静/很久没声音"且生成层(节点脚本/discussion_log)已坐实在跑时, 根因常不在"拉活 gateway"而在投递最后一百米 — **别再在 gateway 死活上反复 churn(多轮喊早/盲 kill 进程会被用户叫停)。** 先读证据再定性, 最小影响修:
- **投递层真值 = executions.db 的 `delivery_outcome`, 按 bot-chat job_id 统计当天并分四桶: `delivered`(真进群) / `queued`(入队等桌面 consumer drain) / `failed`(整点 600s 超时或撞 429) / `suppressed`(同群 N 个高频 job 同小时防刷屏、只放行 1 条其余被静默吞)。** 判据: `queued`≠进群(是入队未消费), `suppressed`≠漏发(防刷屏正常静默高频哨兵、放行有意义班次), 只有 `delivered` 才是真进群。误把 queued 算进 delivered=高估群活性; 误把 suppressed 当漏发=瞎改本不坏的 schedule。
- **改 schedule/降频前先分"该静默的高频哨兵" vs "该发的有意义班次": 高频哨兵(5/10/15min no_agent 心跳/看板/行情喂)一律不降频=监控密度铁律(降了变稀); 整点重要播报(08:30/08:45/22:00)若撞 failed, 用错峰(错开 30-60s)治, 不动节点时刻。**
- **per-profile gateway weixin 跨平台毒化 (群静默真根因之一):** 症状=某子 bot 独立 gateway 起不来/反复死→群播报无活接收方。根因=HERMES 级 `.env` 带 `WEIXIN_ACCOUNT_ID` 但子 profile 没给 weixin token→gateway 一起来就试连 weixin→报 `WEIXIN_TOKEN is required`(non-retryable)→整条 gateway 干净退出。最小影响修(改配置不碰进程): 给该子 profile `config.yaml` 加 `weixin: enabled: false`(子 bot 本就该后台 worker 不接消息通道, 见"微信通道撞车隐患"节)+ 确认其 gateway 启动器(vbs)指向能认禁用标记的新 runtime(旧 runtime 不读该标记仍会连 weixin)。修完读 gateway 日志坐实"将不启 weixin 适配器"+ 收敛到 1 个活进程。
- **动手纪律: 诊断群静默先读证据(executions.db delivery_outcome + gateway 日志 + config)再定性, 不盲拉/不盲 kill; 同一"拉活 gateway"手法连试 2 轮未收敛=停手换结构性不同路线, 第 3 轮裸重试即失职(同"同一失败手法不许重试第 3 次"铁律)。**
