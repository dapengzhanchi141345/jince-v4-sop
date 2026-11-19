# 金策群主持与节点准点监测 SOP

## 触发场景
用户报"节点都是老时间" / "很久没在群里回复" / "没按时开会" / 要求总调度当群主持 / 报"好几天没进展" / "主持务必做好"。

## 零层: 主持岗主动进群纪律 (2026-10-07, 用户令"主持务必做好, 不能好几天没进展"; 2026-10-05 用户报"没动静"实锤)
用户报"没动静/没进展"的根因 ≠ 系统没跑(6 节点全留痕), 而是**主持活没主动投群** — 节点内容在 bot-chat 投递队列排队插不进活跃群 + 我的汇报/对账/进展播报没主动发。三条纪律:
1. **每 4 小时至少进群一条主动进展**(系统心跳实锤 gateway/mt5/extnet + 在办事项销格 + 待办), 不等用户催; 长操作(拉网页/回测/学习)卡住 10 分钟没结果就群报一行进展, 不闷。
2. **节点生成≠进群, 投递层有看门狗兜底**: `jobs.json` 该节点 `last_status=delivery_queued` 且群没收到 = 投递卡队列。检测已自动化: `jince_watchdog.py` 每 15min 读 jobs.json, 凡"今日已生成但卡队列 >2h 未投达"自动投群点名, 主持人(我)只需手动补投(直接跑 `jince_node.py <key>` 出新数据版重投, 不重放 log 防重复); 补投后 jobs.json 该 job 更新 last_status, 自动脱离 stuck。不在活跃群反复硬塞(越塞越堵), 漏投的 22:00 日报统一补发。
3. **用户报"没进展"第一动作**: 先给系统心跳实锤(auto_cycle.log 最新戳 / discussion_log 最新条 / `hermes gateway status` / 看门狗 `network_probe_last.json`), 再定位哪层静默(生成层/投递层/主持这条线), 不空道歉。
判"该主动发还是该静默"反悔成本: 主动进群一条进展反悔成本≈0(最多嫌吵), 静默等催反悔成本=用户流失感 — 一律选主动。

## 主持岗"缺席"=被动救火不是主持 (用户令"主持人全面主持 怎么缺席了 出来制定方案")
主持(default 总调度)的失职形态 = 用户点哪修哪的**被动救火**——用户报节点漏投就查投递层、报没动静就发心跳, 永远在"响应", 从不在"推进"。这是"缺席"的真底: **主持的价值是主动制定方案+推进, 不是应答**。两条纠正:
1. **用户说"主持/制定方案"= 要求以主持身份主动出方案(定规则/定时刻表/定派单), 不是再汇报一次已有机制**。先认账"我之前在被动救火", 再当场出方案+落地动作(改脚本/建台账/改cron), 不空谈"下次注意"。
2. **机制要"发现即补"不要"最后补"(用户令"不是最后补 是 及时发现及时补")**: 任何兜底/补发机制, 首道永远是**当下自动补**(生成层当场补 / 投递层卡 30min 即时重投), 定时批量(22:00 日报)**只做兜底销账漏网项, 绝不是首道**。设计成"攒到晚上统一补"= 把漏投当常态, 用户会再报"耽误了"。判定: 机制里若有"等 XX:XX 批量补"当第一道防线, 就是设计错, 要改成"发现即补 + 批量兜底"两层。

## 看门狗"节点全齐"静默是正确行为, 不是故障 (2026-10-05)
手动 `cronjob run` 补发节点脚本后, 若该节点今日已有讨论日志记录, 看门狗判"全齐"会输出空 (silent, 不重发任何消息), 结果块显示 `Status: silent (empty output)` + `Result: ok` — 这是防重复投递的 watchdog 模式, **内容没丢**。诊断"补发失败"时先读 discussion_log 确认节点当日是否已生成过: 已生成 + silent = 正常静默; 未生成 + 非空输出 = 真在补发。**判定看门狗健康一律看探针文件 mtime + 网关/外网字段, 不看手动触发的输出内容** (静默=好, 有异常=点名投群)。

## 节点静默/投递排查的四层定位法 (2026-10-05 三层, 2026-10-08 增投递层)
用户报"没动静"时**按层排查, 别跳到重启**:
1. **生成层**: 读 discussion_log 当日该节点 key 有记录没 (有→生成层 OK)。
2. **投递层**: `jobs.json` 该 job `last_status=delivery_queued` + 群没收到 = 活跃群排队。现由看门狗 `regen_body` 每 15min 即时重投(见 `midday-nodes-and-delivery-backstop` §4), 手动补投只在群空闲时跑一次, 不反复硬塞。
3. **网关层**: `hermes gateway status` 掉线 → `gateway start` (看门狗已自动拉, 一般到这层是历史残留)。
4. **外网层**: 外网断只影响数据降级不影响本地节点/投递。
**哪层卡就修哪层, 不跨层乱动** (例: 节点投递卡 ≠ 网关挂了, 重启网关治不了投递排队)。

## 三层根因（先定位是哪层哑了，不凭感觉）

### 1. 节点评"数据基准老时间"bug
- 现象：节点评显示"研判 2026-10-06 09:31"，但文件 15:07 已重写——晚上节点还印早上基准。
- 根因：`jince_node.py` 的 `latest_advisory()` 只取 mtime 最新文件，但日内该文件的 `sections[0].beijing` 停在早上（如 09:31），节点评读 sections[0] 就印旧基准。
- **根治**：`latest_advisory()` 在该文件内遍历 sections，取 `beijing` 字符串最大的 section（日内 15:02 比 09:31 新）作节点评动量源 + 展示基准，返回 3 元组 `(文件名, section, beijing)`。不硬读 `sections[0]`。
- 改后手动补一个节点（`jince_node.py us_open`）验基准是否刷到当日最新 section 才算写完。

### 2. 节点迟发无人管
- 现象：东京开评迟 2-13 分且 1h 内连发 4 条（数据源抖动重试），无迟发检测就静默带过。
- **根治**：`jince_watchdog.py`（每 15min no_agent）除查"应发未发"外，必查"已落但迟 >15min"的节点：读 discussion_log 该节点当日 ts，与 SCHEDULE 计划时刻比，迟 >15min 也投群点名 + 要求主持收口（点名→归纳→拍板→派单→落盘）。全齐无迟发=空 stdout 静默。

### 3. 群里讨论不落盘（观感=没开会）
- 根因：节点评只发评不主持；总调度（default）不在金策群实时消息流里（chief/risk/strategy 互聊不经过 default）；群讨论 16:07 后没落盘到金策目录。
- **治本**：
  ① 建 `E:\workbuddy\金策宗师团\群讨论落盘.jsonl`（JSONL，含 ts/发言bot/结论/派单对象），总调度订阅此文件才能及时主持（不等 cron 推摘要）。
  ② 立 `金策群主持制度_v1.md`（单一事实源）：节点开评后 10min 内主持人必做五件事——点名 1 条必推进动作 / 归纳成大白话 / 拍板做不做 / 派单给对应岗 / 落群讨论落盘.jsonl。不许"批次满就散会"。
  ③ 节点准点监测：计划时刻+15min 未落盘自动点名 chief 补开。

## 看门狗必管"生成后投没进群"(三层全兜底, 2026-10-08 用户令"彻底解决")
旧看门狗只管生成层(应发未发)+迟发层(超 15min), **生成成功但卡投递队列的节点能静默数小时无人报**——用户报"开了会我没在群里看到"时, 根因常在这第三层而非生成层。**根治**: 看门狗必含投递层检测: 读 `cron/jobs.json`, 凡今日 `last_status=delivery_queued|delivery_failed` 且卡 >30min 的节点, 看门狗 `regen_body(key)` 当场重生成最新正文注入自身 stdout, 靠 15min tick + 群空闲 bot-chat 即时落进(非攒到 22:00, 见 `midday-nodes-and-delivery-backstop` §4)。**三层(漏跑/迟发/卡投递)缺一层 = 静默失败有机会复发。**
**补投法**: 重跑 `jince_node.py <node_key>` 生成新数据版重投(内容新鲜), 不重放 discussion_log 旧版防重复投递。

## jince 脚本 BJT 时区 naive/aware 混减 + 宽 except 吞异常两大坑
- `datetime.datetime.now(BJT)` 是 aware; `fromisoformat(...).astimezone(BJT)` 再 `.replace(tzinfo=None)` 变 naive。两口径相减必 TypeError。**jince 脚本内统一 naive 北京时间**。坑: 这种 TypeError 被外层宽 `except Exception` 吞掉 → 脚本报"正常"但兜底函数静默返回空列表, 兜底形同虚设。
- 改完看门狗类脚本: py_compile 通过 ≠ 兜底有效, 必须**实跑一次 + 单独 import 调兜底函数看真实返回**, 防宽 except 静默吞掉新逻辑的异常。

## 巡检误报"gateway 探测异常"先验实况
- 巡检报"gateway 探测异常"≠ gateway 真挂，可能是探活命令 30s 超时卡住（`hermes gateway status` 偶尔卡 30s+）。
- **第一动作**：手动 60s 跑 `hermes gateway status` 看实况。活（PID 在跑）= 误报，根因=探活 timeout 太短，修脚本不重启 gateway；真挂（输出 `No gateway`/`not running`）才 `hermes gateway start`。
- **根治**：巡检/看门狗探活 timeout 30→60；`except TimeoutExpired` 单独捕获 → 只记"探测超时(未判挂，下轮再探)"**不进 problems 当异常**（真挂时 gateway status 会明确输出 No gateway，只有那条才算挂；探测卡住 ≠ gateway 挂）。改后实跑确认活 gateway 不误报才算写完。

## 子 bot 专属 key 撞 429 限速（当日文本额度用完）
- 现象：chief/strategy-rd 没回复，agent.log 撞 429，fallback 链全限速，turn 停"No reply: every provider kept failing"。
- **诊断**：① 查子 bot `logs/agent.log` 的 429 行（`grep 429`），看 `provider=` + "Try again after HH:MM:SS"恢复时刻；② curl 实测该 key 补全（`/v1/chat/completions` ping）确认仍在限速窗口 vs 已恢复；③ 专属 key 限速是临时的（分钟级配额恢复），**不用改配置/换 key**——等恢复时刻过了 `message_agent` 重发即可。
- **铁律**：非紧急派单（host-support 类）等配额窗口过了再重发不阻塞；真紧急错开恢复时刻发。4 把金策专属 key 池被多 bot 共用耗尽是已知风险，治本=key 池隔离（每岗独立 key 不互耗），跑完一轮后验各 key 池独立性。