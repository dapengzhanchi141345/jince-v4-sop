---
name: jince-bus-and-heartbeat-ops
description: "Use when 金策总线回执消失/点名/翻闸, 速查双写/口径/SOP。"
---

# 金策总线双写 + 心跳口径 + 翻闸 SOP（11-11 实锤版）

## When to Use
- 发往 workbuddy 的回执/裁定件疑似“对方没收到”（催办风暴、反复“未见回执”）
- 看门狗对 chief 点名/全链断拍，要判口径或手动补拍
- 执行 giveback-floor 第7组件翻闸（23:00-06:00 调试窗）

## 1. Bus 发件必须双写（11-11 实锤）
- **发往子bot判断岗（strategy-rd 等）也用 inbox 双写**: `E:/AgentCommons/bus/inbox/<agent>/<ts>-<rand>.json`（目录不存在先 mkdir -p）, 正文带 X-Jince-To 等 header 风格, 15min 取件哨保证消费——这是 message_agent 通道不可靠时的**主动送达通道**（区别: 深督拍停摆条款是被兜底, 双写是主动）。
- **总线 inbox 件标准字段集(照 yushi/workbuddy 实件照抄): {id, ts, from, to, subject, body, priority, status:'pending', refs}**——refs 指来源件 id(转件必带, 供销账核链); status 收方消费后置 done。
- **御史晨报告「留个判断给风控」= 转件不代裁**: 李的 L4 风控权威与交易链物理隔离, hermes 不代裁——把判断原文+数据点转发 `inbox/risk_officer/`(目录常不存在, mkdir -p 先行, 15min 取件哨保证消费), subject 标『hermes转·御史判断』, refs 挂来源件 id; 台账记一行「已转风控」即可, 等风控官出批复再转御史。
- **`message_agent` 返回 `admission_conflict`（「delivery unconfirmed; do not resend」）= 该通道本次不可重试, 立即 bus 双写兜底, 别再等下拍重投 message_agent**：同文写进 `inbox/<目标>/<ts>-<rand>.json`, note 字段带 message_agent 证据句（"admission_conflict, 总线双写代发"）。strategy-rd 等子bot收件箱目录常不存在, mkdir -p 先行；15min 取件哨保证消费。
- **「X 给我发的信息你看了吗」= 全通道五处扫描, 不是只瞄一眼自己的 inbox**: ①`inbox/hermes/` 顶层(pending 未消费) ②`inbox/hermes/processed/` 按 `<x>` 名件过滤(已消费) ③`outbox/<x>/`+`archive/<x>/`——**两者都不存在 = 该 agent 从没发过件, 立即停搜别处, 如实答「没收到」**(dsh 11-13 实证: 无 outbox/无 archive, 手动会话形态本就不发消息, 属正常不催) ④`shared/live_state.json`+`memory/decisions.md`(共享数据面, 对方结论可能落这里不落总线) ⑤`memory/agents/<x>.md`(对方画像, 看 mtime 判活跃度)。答完「没收到」后**必点出同时段 pending 的高优先件**(用户口头的「X 发的信息」常指抄送了 X 的那件, 真实待办在自己 inbox, 如 yushi 早报同时投 hermes+dsh 两箱)并当场消化+回执。
- **已取件原件去 `processed/` 子目录找**: 15min 取件哨会把已消费件从 `inbox/<agent>/` 移进 `inbox/<agent>/processed/`（还在 inbox 顶层 = 未消费）；哨报的名字（如「20261113T064509-yushi」）≠ 实际文件名（实际 `20261113-064509__yushi__<随机词>.json`, T→- 且带随机后缀）——按 `ls -t processed/ | grep <日期>` + 时间前缀捞, 别硬编码全名。
- **周期性重发风暴诊断（对方小时级重发同一件 N 天不止）**: 先判链路不是判循环——`ls outbox/hermes/` 我方回执件还在 + `ls archive/<对方代号>/` 无我方件 = 对方 drain 没消费我方 outbox，对方判定"未回执"而持续重发（重发是它的超时机制非 bug，催它"停循环"前它先要看到回执）。处置双保险: ①发一张高优先级停止指令件，**要点全文直接写进新件正文**（别让对方查我方 outbox——它查不到才重发），同时点名"请跑一次你们侧 drain 或停小时级 cron"；②我方取件哨加主题级去重（同主题去尾部时刻戳归一 + 同日已报=静默，**时刻戳 HH:MM 含冒号，判"纯数字"必误判，用 `re.sub(r"\\s+\\d{1,2}:\\d{2}$")` 剥尾**），对方继续重发也不刷群。对方 drain 恢复（archive/<对方>/ 出现我方件 + 对方回 ACK 件入我方 processed/）即闭环，风暴自停。
- **表现**: CR 催办反复（“未见回执”N 轮）+ 看门狗“投递卡>30min”虚警（台账“强制销账/实际已进群”行）= 同根因，**不是投递通道堵**。
- **处置**: 每个发件件同时 `cp` 进 `inbox/workbuddy/<同名.json>`（留痕 outbox/hermes + 投递 inbox/workbuddy）。判断“对方收没收到”：`ls outbox/hermes/` 文件还在且 `archive/` 无 = 未消费，别再重发内容，发链路诊断件（ALERT kind）点名挂消费侧。
- **投递层全线降级面（网关半死 + iLink 会话掉）**: 脸 = 所有 weixin 目标 cron job 的 last_delivery_error 含 `iLink sendmessage session not ready (ret=-2, the user must send the bot a message first (or re-pair))` + bot-chat job storage_unavailable/delivery_queued + 看门狗心跳 `gateway=ok (探活超时, fail-open不判挂)` + 节点卡「卡投递队列 Nmin」逐拍递增。处置: 队列卡是账面态不挖（内容每拍摘要重投零丢失, 见 jince-watchdog-noise 投递卡条）；根治 = 李彦明两件套动作——①双击 `E:\workbuddy\国外模型\hermes\一键重启网关.bat` ②微信里给 iLink 机器人随便发一条消息 re-pair 会话（机器人不能先开口铁律, agent 代不了）。两步都做完下一拍自动验活销账；期间 weixin 目标 job 的 delivery_failed 全归「等两件套」一行，不逐 job 重新诊断。提醒用户前必实读 last_delivery_error 确认含 `session not ready`，别凭「投递卡队列」猜（可能只是 job 目标地址配错）。

## 2. chief 心跳点名口径（auto_cycle）
- 看门狗点名认 `E:/GoldstrategyEngine/data/auto_cycle.log` 里 `全链自动运行完成` 行（30min 窗），**不是** `live24_stdout.log` 的“金策全链”行（那是 live24 内嵌 15min 巡检，另一条链，别拿来销点名）。
- 触发链: Windows 计划任务 `JinCeAutoCycle`（30min）→ `ate` 环境 python 跑 `E:/GoldstrategyEngine/auto_run_cycle.py`（单跑正常 ~90s）。
- 挂死模式: 撞 MT5 IPC 冻窗 → 任务 30min 超时 ERROR_TIMEOUT（-2147020576）强杀 → 断拍连报点名。
- **处置**: 手动跑一遍 `auto_run_cycle.py`，78s 内出 `全链自动运行完成` 新拍 = 偶发挂死，闭环销名；又挂 = 系统性，给脚本加"每步心跳行"；11-11 已落地：auto_run_cycle.py 全部 22 步经 `_step_run` 包「步骤心跳 开始/完成」留痕，挂死可直接定位步（配合计划任务 30min 强杀自愈）。

## 3. 组件晋升/翻闸 SOP（五步，11-11 已执行 giveback-floor 闭环；详见 references/gateflip-sop.md）
- 晋升议案 EVO-PROP-20261111-GIVEBACK-FLOOR（WFO 五验 PASS: n=1500/BAND=0.6R/三时段 delta +0.138~0.141R/毛刺 0% 误出/p<1e-5）。
- 五步: ①我侧重跑 `research/giveback_floor_wfo.py` 验 PASS 可复现（对方沙盒=重建版，不复现=自动回退 research 存档不翻闸）→ ②`profit_secure_guard.py` 16/16 + py_compile → ③翻闸 `GIVEBACK_FLOOR_ENABLE=True`（开关默认关=零改变现役，`GIVEBACK_BAND_R=0.6` 已并入 max() 棘轮只往紧推）→ ④重启引擎（每魔一号 + 锁龄自愈在位；taskkill /F 有 3-10min 拖尾，僵尸判活则 rm `live24_magic_*.lock`；**重启必须 wmic 确认实例数为 0 再拉起**——旧拖尾+PID 复用会让新实例误判"锁主还活"→ MAGIC_DUP_EXIT 自退（验活逻辑须 wmic get commandline 核 PID 命令行含 jince_live24 + 锁龄 180s + CloseHandle, 11-12 已 patch 进 jince_live24）。**flag 文件类参数（如 l24_feature_flags.json）在进程 import 时读取: 写完 flag/补丁后必验 锁/桥 启动 ts 晚于写 ts, 看门狗自动重拉若早于写入=旧码仍在效, 须再杀一次等新实例, 否则「写盘完成」≠「生效」**; git-bash 杀进程 `taskkill //F //PID` 因 MSYS 斜杠转换静默失败, 用 `powershell -NoProfile -Command "Stop-Process -Id N -Force"`→ ⑤首轮观察 8+ 仓 SL/TP 零误伤 + 台账留痕，执行完向李彦明汇报。
- 台账锚: `t_giveback_floor_promote_1111`。完整五步+时序判定见 references/gateflip-sop.md。

## 3.5 陈旧闸误判判别 + fail-closed 旗龄化（11-19 实锤）
- **报「闸 vs 新执行标准冲突」前先读闸源文件全文（rule 文本 + reset/supersede 历史字段）**: 闸线常已被风控重置到新标准（破位撤单闸 4190→3800，reset_reason 记裁定依据）——读出来多是「互补」不是「冲突」（闸休眠时刻=执行标准放行时刻）。不读源就判冲突 = 虚惊误判 + 白开工单。判序: 读闸 json → 核 rule 语义与新标准时序是否互斥 → 真互斥才登冲突工单，互补则一行闭环。
- **一次性验活旗类闸 fail-closed 会永久堵通道: 哨检规则「flag=True 且龄>7d 即报」**: 「验一次就把某 flag 置 False」型闸（会话钟时区待验类）读不到/True 时 fail-closed，没人做验证就无限期阻断整个挂单通道（17 天无人做实证）。确定性验活主 bot 当场做（0 LLM），不等 LLM 岗被 key WALL 卡住。钟时区类验法: `symbol_info_tick(sym).time - int(time.time())` 两品种交叉核（冬 EET=恰 +7200s）判 PASS → 翻 flag；**翻后必实跑下游 probe 函数验返 False（probe 每拍读源文件, 改文件即生效, 但「改盘完成」≠「生效」, 必须跑一次留返回值）**。销账依据=原冻结令期限条款 + 用户解冻令（销账=执行原期限非新决策）, 留痕 sd_guard_run.log 一行带 probe 返回值。

## 4. CR 回执与外报缺陷裁定纪律（11-11 催办风暴复盘, 永久）
- **变更单回执必须逐项编号（对/补/驳 + CR 号）**：通用『已核对/认同』式 ACK **不计入**对方『登记已 N 分钟未见回执』判定——workbuddy 侧催办按 CR 号等逐项回执, 泛 ACK 不销账（11-11 两件催办挂 542/428 分钟, 直到逐项编号回执+双写才一次销掉两件）。回执格式: 『已收到 CR-XXXX, 逐条: ①对 ②补（补充内容） ③驳（理由+出处） ④已做留痕:…』, 发件双写 §1。**『补』型条目若对方要求验证的常量/参数不在我侧（如 scorer 类参数归对方代码）, 就写『补: 该常量在我侧不可代验, 请补充实证(如该值写入哪个决策 json)』——明确标"本侧无法代验+请对方补实证"同样算逐项回执(每项有结论即可), 不是未销账; 别因一条验不了就整单搁置, 也别猜一个值冒充验证过。
- **外部『代码缺陷报告』先逐行核源码再采纳, 逐条裁定（对/补/驳）, 不批量照单全收**：11-11 进化营报 6 项代码缺陷 = 5 误报（设计行为/用户已决参数/已有兜底/有意留白/双口径各自有意）+ 1 真缺陷。误报判别器: ① by-design（如 DEMO 宽范围 v4 授权）② 用户已决（如冷却=0 是李的指令）③ 已有兜底（glob 全目录覆盖）④ 注释写明理由的留白分支 ⑤ 表面矛盾实为两个不同口径各自有意。**真缺陷也不直接改生产**: 涉及闸口径=候选→WFO 五验→翻闸（见 §3）, 登记成 candidate 与对方放宽批次同批验。
- **催办重列『已回执 CR』: 重发既有逐项回执（标『重发』+ 双写）, 不新造回执, 不写催办回应件**——对方催办是按 CR 号台账生成的, 让它销账的是「该 CR 号有一条最新带时间戳的回执」, 不是回应动作本身; 新造回执 = 重复劳动 + 新台账条目越堆越多。已逐项回执过的 CR 被催办重列时, 原回执按双写规则再投递一次即可闭环。
- **派多轮优化指令时回执节奏必须写进指令**: 「仅收口时裁定（同分母+五验+裁定/搁置）, 不逐轮回执」——逐轮回执 = 回执乒乓 + 台账重列（§4 聚合件风暴的源头之一）；对方领受确认节奏后, 中间轮不再跟, 只在收口件到件时按五验裁定。
- **周期性『待办聚合』件重复列已闭环项 → 一次核销提醒件打住，别当新活重做**: workbuddy 侧每 15min 聚合件（『共 N 项未闭环』）常把我方已执行/已回执的条目（翻闸/裁定/双写讫）继续列着（对方台账未追平）。到件先对我侧台账逐条核销：已完成 = 发**一次**核销提醒件（逐项编号 + 完成证据：bus 双写讫/台账 id），让对方销账停止再列；未完成才进正常处置流。同一批已发过核销提醒又原样重列 = 对方消费侧缺陷，发链路诊断件点名（§1 口径），不逐轮陪跑。
- **「请回执 ①②③…」逐条应答纪律（对件带编号回执请求时）**: ①先查我方 outbox 该请求是否已答过——答过就重发原逐项回执（标「重发」+双写）销账，不新造回执（重复回执=乒乓+台账膨胀）②「疑似截断」条目先读我方发出的原文找截断点（生成侧写 bus 截断 vs 接收侧丢失），回「截断在生成侧，请补发全文」，别盲目重发；**对方生成层同样丢全文、补发不出时 → 裁定「生成层截断不可恢复」直接结案: 实质内容以手边最完整件为准, 新意见须以新函（带 MsgId）重提, 旧件不追, 条目不再挂 open（防幽灵件在对方周期性聚合件里无限重列）** ③「事实声称」条目（工具已就绪/已重建/已完成）不代认——我方台账实查（grep/任务表/实读）核对，不符则「产出先行 bus 通报再采信」+ 我方台账记验收点 ④「定义/口径」条目（magic 归属表、状态定义、权威源清单）直接给权威表答复，让对方可引用。
- **自动生成内容里的数值样本必过脏数据闸**：比率/RR 类样本构造按『距离<0.1%现价→弃样本, 比率>10→弃』（11-11 edu 教学 L1 曾出『止损=现价→RR123x』误导样本教训）；给李看的数字不出现黑话、不出现脏数据。
- **对方侧『固定模板自动重生成请求』与『人工催办重列』是两个方向, 处置相反, 别混**：人工催办（§4 首条『催办重列已回执 CR』）= 重发既有逐项回执销账；但**生成器模板**（如 V4.1 开单建议件的『请回执回执①②③④⑤』固定段, 对方脚本每拍原样再生成、非人工盯催）= 逐项回执**只发一次**（标『已答, 此段为模板固定文本, 按已答处理不再逐拍重复, 仅 X 项待你补发』）, 后续同面拍一行归『模板固定段, ACK 已在位(给 id), 按已答处理』, **不重发回执**（重发=回执乒乓+台账膨胀, 且对方消费侧未必读）；销账条件=对方模板更新/新请求项出现/被点名项（如『疑似截断』段）补发全文——只有补发件到才动。判别器：同请求段在多拍里**逐字不变**=模板自动面（走一次 ACK）；请求段内容在变化或带 CR 号/催办措辞=人工面（走重发销账）。

- **跨 bot 数据索取必给权威批次锚点（文件名+字段口径），不给近似数；对方拒编造时做数字溯源**：索取逐单明细（如「N 笔止损明细」）只报命题里的近似数时，对方权威台账对不上（三份源实数均≠命题数）必拒编造凑数=正确纪律——此时主 bot 做两步：①**数字溯源**（grep 我方数据目录找该近似数出处：多为用户命题/旧报里的概数，非台账实数）②按对方给的多选口径裁定并总线回复（选字段最全者全量导出 + 文件内注明「实际 N 笔与命题数的差异及缺项原因」，别为凑命题数裁剪数据）。对方共享数据落盘必走 CR 双向验证（先登记变更单+逐项回执，获回执才落盘，未获回执不单方写 shared/），我侧发件带 refs 指来源 MsgId 供核链。
- **旧崩溃/故障票销账先验代码 mtime（closed_selfheal 口径）**: 处理「某日崩溃/exit=1」类积压票时先核涉事代码文件 mtime——自崩溃窗口起代码未动过 = 数据依赖型瞬发（当时数据缺/坏），实跑两连 rc=0 + py_compile 过即按 `closed_selfheal` 销账，**销账文案必写重开条件（再现 rc=1 即重开定位）+ 不标「已修」（没修，是数据恢复自愈）**；自 heal 票不留痕 = 复发时无证据链。判数据依赖 vs 代码缺陷的分母: 代码 mtime 早于崩溃日 = 数据依赖嫌疑, 晚于 = 真代码改过要正常验收。
## 5. 心跳/巡检拍的状态行数据源铁律（11-12 主持拍币系误报根治, 永久）
- **所有定时拍的状态行（主持拍/巡检/看门狗/22:00日报）必须读『实读侧落盘的实时结论文件』, 不读静态闸文件**: 静态闸 json（crypto_freeze_gate.json 类）值常停在旧事件日, 当现状报 = 误报连刷（主持拍『币系已放』×42 连报实证, 实盘 tm=4 close-only 两天）。
- **修复模式（三方分工, 已落地可复用）**: ①实读侧（巡检拍, 每 30min 跑 mt5 读值的脚本）在判读分支前把结论落盘 `data/coin_tm_state.json`（ts/数值/口径/src 四字段, 异常不影响主流程）②报方（主持拍等）读落盘文件 + **30min 新鲜度闸**, 过期/缺文件 fallback 文案=『未证实(巡检数据缺)』——**绝不猜现状（猜错方向比『未证实』糟, 李会按假信息决策）** ③文案标口径来源（『币系(broker实读): close-only(tm=4, 时间戳)』）, 李一眼看出数据从哪来。
- **判别器（报方新加状态行时先问）**: 这行的值是『会随实盘变的状态』还是『我方闸的意向』？状态→必须实读侧落盘源；意向（我方闸开/关）→可保留静态, 但文案必须标明是我方闸不是实盘。
- **live_state.json 实读必带 mtime 新鲜度闸（11-18 节点假读旧快照实踩）**: 节点/日报读 live_state 报『实读』时先验文件 mtime（写方=验尸官, >15min 判 stale）——stale 必须改走 MT5 positions_get/orders_get 直读并标注数据戳, 禁止拿旧快照报『实读持仓 N 张』（平仓后节点照旧快照报 3 张=新形态假交付, 误导风控研判）；报方文案一律带数据戳（『实读@HH:MM』）。**写侧盲通道变体（11-18 实踩: live_state 新鲜却报 0 持仓）**: 写方终端是 attach/只读且读不到持仓浮动盈亏时, 文件 mtime 新鲜但数值错——tell = positions=0 且 equity==balance==margin_free 三者全等而 MT5 实读有活仓。持仓口径报数出现分歧时以 MT5 positions_get 直读为准（活体>快照）, 并把写侧单客户端化登记 P2 根修工单, 报方文案标注『live_state 写侧盲, 以 MT5 实读 N 笔为准』。
- **JSONL 台账写读双向纪律（11-17 日结补行长行截断崩汇总 job 实踩）**: 台账追加长行（日结/补账类）落盘后立即 json.loads 回读验活（截断/缺括号当场重写, 备份 .bak 留档）；读方脚本一律坏行容错——skip + stderr 显式报（数据有效性闸铁律: 坏行禁静默吞、也不许崩整个 job）, 汇总类脚本聚合出『?』/0 行先疑台账行 schema 变更（新行长文叙事体无机读字段）再疑桥。

## 8. 确定性拍 no_agent 化（LLM 中断簇隔离，11-14 全链扫描根治版）
- **凡是"跑确定性脚本+读日志出简报"的定时拍（全链扫描类），LLM 驱动版在 provider 中断簇下会连续 interrupted 丢拍**（11-13 起 3 连挂实证）。根治 = cron 改 `no_agent: true` + `script: <纯脚本>`（0 LLM，永不被 provider 链路波及；非 0 退出/超时才发 error alert，正常拍 stdout 简报照投）。
- **脚本定型**（jince_fullchain_scan.py 范式）: ①ATE python 跑引擎主循环（`auto_run_cycle.py`，timeout 600s，CREATE_NO_WINDOW）②读引擎日志尾 N 行 + 派生简报文件 ③组大白话简报 print（stdout=投群内容；空 stdout=零发送，静默拍照 watchdog 模式）。**剥掉子进程 env 的 PYTHONPATH/PYTHONHOME/PYTHONNOUSERSITE 再调 ATE**（3.13.12 实读路径同 mt5-live-read 黄金法）。
- **配套去重静默**（防 LLM 拍消失后脚本拍刷屏）: 例行全绿/稳态拍一律本地 .jsonl 留痕不 print（空 stdout）；仅异常/状态变化 print（jince_watchdog/patrol/eff_report 三脚本 11-13 已落此模式，新拍照抄）。
- **判据**: 拍的逻辑=固定命令+固定文案=该 no_agent；拍的逻辑=要读多方状态裁断/出策略=留 LLM 但加 fail-open 与降级文案。拿不准先 no_agent 跑一周看简报缺什么再补 LLM 拍。

- 李说『不用了/不修了』= 当日清退, 不留尾巴: 撤该组件的全部定时点名/告警（看门狗探针只留状态记录不发声）+ 台账 CANCELLED（注明弃用理由+重启须李令）+ 状态卡/memory 各一行 + 文件资产保留不删（删=重启归零）；**别留着弃组件的 15min 报警刷李**（清退不彻底=每拍骚扰, 李下次问『怎么还在报』）。

## 6.5 总线投递补充（11-17）
- **outbox 无自动拾取**：relay 只清收件箱、无发件分支。回执/裁定件写 `bus/outbox/hermes/` 后若当日必须对方读到=同拍 mv 到 `bus/inbox/<目标>/` 直投（文件名带迁移标记防对方误当新件重复处理）；积压死件=逐件读 to 字段分类迁移（目标目录先 makedirs，常不存在），迁完 ls 验余 0。outbox 只当留痕，不当投递通道。
- **message_agent 回执被 key WALL 卡死时主链不阻塞等**：目标 bot 的 LLM 全堵（key 哨 RED/全 WALL 态）时，已 queued 的回执件可能永远不来——需对方裁定的事项按「待裁」显式标注继续推进主链，不挂起等回执；key WALL 跨夜（次日关键 LLM 任务前仍 RED）=升红单独报用户。等回执超 2h 且 key 哨 RED=按「对方 LLM 不可用」定性而非「对方没看到」（前者查 key 哨/池状态，后者查总线收件箱）。
- **gateway 探活超时连续≥3拍=建 P3 工单**：「gateway=ok(探活超时,fail-open不判挂)」单拍=瞬态不报；连 3 拍同现=CIM/WMI 查询慢响应（gateway 本体 CLI 探活仍 ok 则无功能损失），建 P3 工单（修向：CIM 加退避 / 改读 gateway 自写心跳文件免 WMI / 连续 N 拍才进群止噪），不逐拍报警刷屏。

## 7. 群聊身份铁律：宗师团群在 bot 界面上, 不在微信（11-13 实踩定稿）
- **金策·宗师团 = Hermes bot 界面（state.db `hosted_rooms`）里的房间, 不是微信群**: 微信 iLink 只有私聊, 无群聊——『把你的 bot 拉进微信群』/『在微信群发消息』类指令不可行, 11-13 被李彦明当面纠正（"bot 群聊不在微信, 在你的 bot 界面; 微信没有群聊"）。金策全部 cron 投递走 bot-chat 投宗师团房间; iLink 私聊仅私聊投递, 且有"机器人不能先开口"约束。
- **改群名/判"两个同名群" SOP**: 界面出现两个同名群 = 通常**同一房间两种显示名（DB 名 vs UI 陈旧缓存）, 不是两个实体**——先读 state.db `hosted_rooms`（name/room_id/relation）确认单房间再动手。改名五步: ①UPDATE hosted_rooms SET name=新名 且 revision+1 ②**updated_at 必须保持 epoch 数值**（写 ISO 字符串会让 gateway 解析失败, 实踩后回退） ③重启 gateway 清 UI 陈旧缓存 ④回读 DB 验 name/revision ⑤确认投递零影响（bot-chat 按 room_id 映射, 与显示名无关; 读投递队列/日志验证无丢失）。改名后旧名群在界面上残留=纯缓存面, 重启即消, 别再建第二个"群"。
- **iLink『session not ready / the user must send the bot a message first』= 用户先发首条消息建会话, 非 bug**: 通道重连（含 gateway 重启后）iLink 会话需李彦明在微信私聊随便发一条任意消息后才建立, 之后 bot 才能发; 此是通道设计（机器人不能先开口）, agent 代不了——见 §1 投递降级面"两件套"。报用户时给精确动作（"微信私聊给 iLink 机器人发一条任意消息"）, 不写"重配对"等黑话。
