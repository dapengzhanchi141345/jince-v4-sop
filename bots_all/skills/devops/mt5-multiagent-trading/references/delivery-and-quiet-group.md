# 群"安静"排查 & 双通道投递分流 (金策 cron 消息投哪、为何用户看着静)

用户报"群里没动静/没消息"时, 先给"系统活着"实锤再定位, 别直接道歉; 且分清**哪层静默**(5 层, 见下)。

## 5 层定位表
1. **消息其实发了但去了您看不见的窗口**: 桌面端每个 profile 有独立 "Bot Chat" 会话窗口, cron bot-chat 投递走的是**该 profile 的 Bot Chat 会话**, 不是用户手建的「金策·宗师团」群会话。查法: `sqlite3 E:/workbuddy/国外模型/hermes/state.db` 的 `sessions` 表按 `title` 找 `Bot Chat` vs `Group: 金策·宗师团`, 看 `last_activity_at` + `message_count` — 若 Bot Chat 在滚而老群停更 = 用户盯错窗口, 不是系统死。
2. **`delivery_queued: completion unverified; do not resend` 不是丢消息**: 这是 Hermes 的**防重发保护** — 消息已进 `bot_live_delivery` 队列被桌面端 consumer 消费进 Bot Chat, 只是回执没销账。查 `runtime/bot_live_delivery`(文件锁独占, **别 kill 桌面进程去读它**, 看 mtime 变化=消费活动) + `runtime/active_sessions.json` 里 `bot_live_delivery_consumer=True` 条目数(消费方活着)。100% 确认 UI 渲染需人工切桌面看一眼。
3. **微信侧真丢/限流**: 查 `state.db` 的 `delivery_obligations` 表(`state` 列 delivered/failed/abandoned + `last_error`)。`failed` 带 `iLink sendmessage rate limited; cooldown active` = 限流旧账; 统计 `SELECT state, COUNT(*) GROUP BY state` 判整体健康(几十 delivered + 少量 failed 限流 = 正常)。
4. **桌面中继断链征兆**: gui.log 报 `Bot live-owner delivery poll failed` + `active session file lock unavailable` = 桌面端重启前文件锁僵死, 重启后归零; 查该错误**当天**计数(非历史 975 次总量)判当前健康。
5. **cron 任务本身没触发/失败**: 查 `jobs.json` 每个金策 job 的 `last_status`/`last_error`; `failure_deliver` 应全 bot-chat(失败也发声), 漏配的当场改。

## 第 6 层: 生产 runtime 缺 bot-chat 平台 → 全批 "unknown platform 'bot-chat'" 群静默 (2026-10-12 实测)
用户报"群里没动静很久", 前 5 层都没命中时查这层。**本机两套 hermes: ①生产 runtime = `C:/Users/ASUS/AppData/Local/hermes/hermes-agent/venv/Lib/site-packages/cron/scheduler.py` (跑 JinCeHermesCronTick 定时任务的那套, 加载 `hermes.exe` 内置 site-packages) ②dev 工作副本 = `E:/workbuddy/国外模型/hermes/hermes-agent/` (手动跑 `python -m hermes_cli`/桌面 backend 用的那套)。** 两套版本不同步:
- 判"生产版认不认 bot-chat"的唯一可靠法: `grep -c 'bot-chat' <site-packages>/cron/scheduler.py` (=0 即不认) + `ls <site-packages>/cron/ | grep delivery` (无 scheduler_delivery.py / 无 bot_chat_delivery.py 即缺投递支撑)。
- 症状: jobs.json 里所有 `deliver=bot-chat:<profile>` 的金策 job 在 C runtime tick 时报 `unknown platform 'bot-chat'`(scheduler.py 的 `_KNOWN_DELIVERY_PLATFORMS` 白名单没有 bot-chat) 全挂 → 30min 全链内容一直在跑(查 auto_cycle.log mtime 还在刷), 只是**播报投不进群**, 用户体感"没动静很久"。内容层绿 + 投递层全 unknown = 本层, 不是节点没跑/网关掉线。
- 治法(最小修补, 别升级整个 C runtime 砸全 cron): 把 dev 版 `scheduler_delivery.py` + `bot_chat_delivery.py` + `tools/bot_mode_dm.py` 同步进 C venv site-packages/cron/ + tools/, 并把 `bot-chat` 加进 C 版 scheduler.py 的 `_KNOWN_DELIVERY_PLATFORMS` + 投递分发分支; 改完 taskkill 旧 cron tick 进程让 site-packages 重载。动 C runtime 前务必备份 site-packages/cron/*.py。
- 铁律: 排"群静默"先分清 C(生产定时) vs E(桌面/手动 backend) 哪套在发该批 job — 定时 job 走 C, 改错套等于白改。

## 双通道分流 (用户"两个都要"定式)
- **微信私聊直达手机 = 关键 4 项**: 08:30 开盘简报 / 08:45 体检汇报 / 21:30 学习进化 / 22:00 事件日报+复盘, `deliver`+`failure_deliver` 全设 `weixin:<user_id>`。
- **桌面 Bot Chat = 高频舞台(18 个)**: 2h 播报 / 6 盘口节点 / 群主持 / 看板哨兵 / 巡检 / 看门狗 / 心跳 / 周复盘 / 合成会 / 月度 P4, 全 bot-chat。
- **local(设计上静默, 非漏配)**: 全链扫描 / 一次性拉数闹钟(后台拉数据不需发声)。
- 改 `deliver` 只动 jobs.json 该 job 的 `deliver`+`failure_deliver` 两处, 写完回读 jobs.json 逐 job 确认。

## 微信 cron 主动推要 WEIXIN_TOKEN
- 回复用户发来的消息走 iLink 网关代回, **不用 token**; cron 冷启动**主动推**微信另需 `WEIXIN_TOKEN`/`WEIXIN_BASE_URL` 在 `.env`。缺时报 `Weixin token missing. Configure WEIXIN_TOKEN`。
- token 值从 iLink 账号文件 `weixin/accounts/<acct>@im.bot.json` 的 `token`/`base_url` 字段搬(只补缺失 key, 已有不覆盖; 不经过对话)。
- 配完必手动 `hermes -p default cron run <job>` 验收真送达; 撞 iLink 限流 cooldown(600s)时手动验收要等冷却过再试, **别循环撞墙**。

## 群主持 (治"机械播报没人带节奏" = 死群体感)
- `jince_group_host.py`(no_agent 0LLM, 确定性): 白天 09/11/14/16/19/21 六点各出一条主持人点评(接住刚发生的事 + 点名风控/研发在干啥 + 预告下一场 + 异常点名); 同小时防刷屏(`data/_host_last_hh.json`), 08:30-22:30 外静默。job jgrouphost0900。

## 主人翁姿态主动闭环 (2026-10-12 用户令"你是数字分身 别我盯着你 安排的任务不能不执行")
- 用户报异常/静默/"怎么搞的"时**不许只报根因等指令**: 能当场修的当场修+当场验; 修不了的(429 额度墙/生产 runtime 边界/子 bot 回包空)登记 task_ledger(owner+checkpoint+retry 时刻)并派单接手; 错过的班次/播报**主动补上**。每件事以"已做X/验过Y/剩Z已挂自动跟进"收尾。用户催"赶紧/别拖"= 少探针多动手: 根因一实读坐实就立刻执行, 禁止连续多轮只查不动(查一轮=探针, 查五轮=失职)。

## 补播实读纪律 & 网关死活判据 (2026-10-12)
- **播报数字一律 MT5 实读**: 进群播报/补播的"持仓/挂单/净值"先 `mt5.positions_get()/orders_get()/account_info()` 活体实读; 派生簿(pending_orders_state.json 等)只留痕不进群数字(派生簿≠实盘, 账实劈叉会被 chief 实读纠正)。DRY-RUN 实产的挂单报"实产未实挂", 不当实盘报。
- **"读错腿"(陈旧账腿终态成交被当"活持仓 N 张")会反复复发 → 治本靠注入生成器 prompt, 不靠每次人肉纠**: 冻结快照账腿(如 `live_execution_60137964.json`)里的**已离场终态成交**会被日报/节点当活仓读出来, 同一家族一天能犯 3 次("LTC 锁盈在走"/"活持仓 3 张 XAU/XPT/XBR")。**根治**: 在出该报的 cron job 的 prompt 里插一段【持仓口径铁律】——"凡报活持仓/挂单/净值一律先跑 `_mt5_readonly_probe.py` 活体实读; 严禁把陈旧账腿/派生簿的历史成交计为活仓; 活读=0 时必写'0 活仓 0 挂单'; 与实读对不上就改实读口径并留一行更正"。改 prompt 前备份 jobs.json, 改完回读确认。人肉更正当天落盘文件只是止血, 改生成器 prompt 才防下一班复发。
- **投递断链时主 bot 代主持补全部错过的班次**: 不止最新一条——扫 jobs.json 列当天所有错过班次, 逐班用确定性数据源(0 LLM)读实数生成补播投群, 补播稿落盘 `内容中心\交付\`; 用户说"之前的也补上"= 补当天全部。根修落地后交还原态班次。
- **active_sessions.json mtime 停更 ≠ 网关挂**: C/E 盘各一份孪生、consumer 心跳与 gateway 活体是两回事; 探活 60s 超时=瞬抖, 下一拍自愈。判网关死活用 `data/network_probe_last.json`(gateway/extnet 字段) + `auto_cycle.log` 最近全链拍 + `hermes gateway status`, 只有明确 "No gateway" 才算真挂(与看门狗探活超时不判挂同源)。
- **cron 报警"failed N in a row"但 jobs.json 说 `last_status=ok, failure_streak=0` = 旧红回放, 不是新故障**: 投递队列 `cron/bot_chat_pending/*.json` 会积压(可数百个、最早溯到数天前), 某 job 的历史失败通知被逐条回放, 报警正文里 "failed N in a row" 的快照计数还在递增(N 3→4→6…涨), 看着像越挂越多, 实为旧账重放。判据(三条全绿即旧回放, 勿重跑勿 pause): ① 该 job 的 jobs.json 真实 `last_status`/`failure_streak`(=ok/0); ② 输出目录 `cron/output/<jobid>/*.md` 最近几拍是否仍有**新** error 文件(全 silent=绿); ③ 相关数据(`tick_live.json`/chief 心跳)还鲜不鲜。治本(可逆、最小影响): 把该 job 的 `bot_chat_pending` 旧账(`status`=settled/ambiguous/transferred)整体 `mv` 进带时间戳归档目录, 不删; 在途 claimed 的留下让机制自清。归档后回放源归零不再刷。判断标准固化: 只要无新 error 文件且 streak=0, 一律当旧回声不重复处理; 真挂才用"新 error 文件 + streak≥1"双证据报且只报一次。
- **探活误报根治法(同一家族一天刷 20+ 次的"gateway 探测超时"类)**: 巡检/看门狗每拍跑一次**完整 CLI `gateway status`**(拉起整个 hermes CLI, 常 >60s), 一超时就记"异常"自动进群刷屏, 而网关其实一直活着。根治=**秒级进程探活优先**: 用 CIM/`Get-CimInstance Win32_Process` 匹配命令行 `gateway run` 数活进程(≈1s), >0 即健康直接跳过(不再每轮跑慢 CLI 往返); 进程真没了或探测不确定才回退**一次**完整 CLI 确认, 只有输出明确 "No gateway/not running" 才报(保留真故障检测)。改 patrol 前先单测探针快不快准不准, 改完编译 + 活网关下实跑 `check_infra()` 验 `problems==[]` 且耗时 < 数秒(旧版会卡 60s)。双副本(hermes/scripts + 引擎侧)同改, 备份原件。
