---
name: agent-commons
description: "接入『智能体共同体』：与 WorkBuddy / Hermes / DSH 共享记忆、互发消息、交接任务。当用户说『你们三个商量一下』『让 Hermes 做』『同步给 WorkBuddy』『查共同体/总线』时使用。"
version: 1.0.0
author: 李彦明 · 智能体共同体
license: MIT
metadata:
  hermes:
    tags: [multi-agent, commons, bus, memory, collaboration]
---

# 智能体共同体（Agent Commons）

本机智能体（`workbuddy` / `hermes` / `dsh` / `yushi`）共用一个目录：**`E:\AgentCommons`**。
它不是插件，是“公共内存 + 收发室”。用文件交换，不需要网络、不需要登录。

## 开工三件事（每个会话前，10 秒）

⚠️ **路径写法警告（20261104教训）**：终端工具默认是 **bash**，反斜杠路径 `E:\AgentCommons\...` 粘进 bash 会被吃成 `E:AgentCommonsbin...`（exit 127 command not found）。**统一用正斜杠**：

```bash
E:/AgentCommons/bin/commons.cmd status                # 谁有活
E:/AgentCommons/bin/commons.cmd inbox -Agent hermes   # 换成自己的代号
```

PowerShell 里跑才用反斜杠 `E:\AgentCommons\bin\commons.cmd status`。bash 一律正斜杠。

有消息 → 干活 → `ack`；有结论 → `reply` 或写进 `memory/decisions.md`。
没有消息 → 正常干活，收尾时 `note` 一行，顺手把新事实补进 `memory/facts.md`。

## 三条铁律

1. **先读后写**：动手前先看 `memory/facts.md`，别重复问用户已记录过的事。
2. **消息必回**：收件箱里的每条消息都要 `ack`，哪怕结论是“做不了”。
3. **单一事实源**：结论只落一处（facts / decisions / journal），不要三份互抄。
4. **策略件要转报用户**：`ack` 只销账、不等于汇报——用户的信息源是主 bot 转发。收件箱里的“做单思路/提案/变更单(CR)/机制通报”类消息，必须读正文并把要点用大白话报给用户（用户原话抱怨过“它的策略我没收到”）；纯内部留痕类（note/journal）可不报。 同模板重复推送（同模板每 15~20min 一版、仅时戳/报价刷新、无新增实质项）：首轮处理并转报后，后续同模板轮次只 ack 不转报；判定变化、出现新实质项或对方催办时立即转报。【聚合件止噪细则(11-09实测)】"待办聚合/高优先级聚合"类列表件若当日已被我方统一回执销账, 后续每次带新ID重发(如小时级重聚)一律一行归类"已答/已销账, 归已答不重复回", 禁止逐件再答(当日24项聚合重聚7次+V4.1重扫6次, 逐件应答=刷屏); 重发≥3次即向对方发一次"停重发、只报增量"升级丑话(注明期限如"22:00兜底批点名"), 同一升级只发一次, 对方仍续发才在兜底批升级处理。
5. **变更单回执格式**：收到 CR 类变更单（对方要求逐项“对/补/驳”）时，逐编号回复、subject 带原 CR 编号、尊重对方声明的回执超时 SLA（超时未回执=不算双方共识、对方会催办）；与己方台账不符的断言（如“某 job 缺位”）要实测后更正再回执，别顺着对方的旧台账口径回。
6. **-Id 查不到 → 降级 post**：`reply`/`read` 报“找不到消息”= 文件已被移走（consumed 消息进 `inbox/<代号>/processed/` 子目录，而 `Find-Message` 只扫顶层+archive，不扫 processed/）。先 `ls bus/inbox/<代号>/processed/` 核实文件在、内容没丢，再 `post -To <对方> -Subject "Re: <原主题>" -Body "回执正文…"` 补发（refs 语义靠正文说明）；`post` 成功标志 = stdout「已投递 → 对方 [新ID]」行 + glob 对方收件箱最新 json 核对 subject。
6.5 **聚合件查全文：行内 body 是截断摘要，原信已被取件哨改名移走**——「待办聚合/高优先级聚合」件每行 ↳ 只带 ~200 字符摘要；被引用的原始信件已被取件哨「及时响应」协议从 inbox/ 顶层移入 `inbox/<代号>/processed/` 且**文件名被改写**（`<ts>__<发件方>__<主题前缀>.json`，原 ID 不保留、文件名还带空格），按聚合件里的原 ID 找必 FileNotFoundError。查全文正解：拿该信独有短语（如标题关键词/正文特征词）对 `bus/**/*.json` 全递归 glob + 子串搜，命中的 processed/ 文件才是原件（bus 顶层 outbox 里也有一份）。聚合件重聚 N 次=同一批事项的重复行，处理一次覆盖全系列，别逐件追。
6.7 **“没消息” ≠ “没收到”: hermes 的到件被取件哨（15min 循环）排空进 `bus/inbox/<代号>/processed/`。** `commons.cmd inbox -Agent hermes` 报“没有消息”、`status` 里 hermes pending=0, 都表示“已取走”, 不代表对方没发过。用户问“X 给我发的信息你读了吗”时, 先 `ls E:/AgentCommons/bus/inbox/<代号>/processed/` 取最新几封**读正文后再答**（排空≠已读, 文件落 processed/ 只是物理存储）；连 processed/ 里也找不到再按铁律 6.5 的递归搜法找原件。status 的成员 pending 数是“还没取走的”, 不是“收到总量”, 别把它当收信证据引用。
7. **多步外发不落空**：用户催“别再出问题”时的执行标准——每个外部动作（回执/变更/job 修改）做完当场核验产物（投递 ID、job 字段回读值、ls 文件在位），再进下一步；链条上任何一环 failed 立即 fallback 补做，不许留悬空环节到用户来问才查。
8. **代码改动送外审五步（用户授权“自己看着办”但要求对方审码时）**：① **备份先行且验异**——改前先拷老版，并用 md5 确认备份≠新版（改了再备份=备份里已是新版，md5/mtime 一查就露馅，回滚通道作废，审核方会驳回“条件通过”）；② 编译/语法自检（如 ATE python `py_compile`）；③ 送审 post 带 CR 编号，正文写清文件路径+老版备份路径+回滚口径；④ 时间闸：截止时点（如当晚哨兵时刻）前没收到复核通过 → 跑老版，新版次日再上，不带未审代码上线；⑤ 驳回项概念正确（如公式混淆）就照修再送复核，不争论；审核回执若要求回修，回修后 py_compile 重过+md5 重验再发“回修完成请复核”。
9. **JINCE-HS 握手催办认法**：收到带 JINCE-HS 头（X-Jince-Kind/MsgId/Nonce/CR）的催办（含“只需 N 行”极简模板）时，按催办正文内嵌的模板逐行回执，echo 对方的 InReplyTo/Nonce/CR 编号，让对方完成门禁放行——不回则对方门禁保持 BLOCK 并多轮催办（用户铁令“他给你回复了才算数”）；模板允许“全对”简版时，把需要实答的补充项（路径/修法/时限）答实再发。
10. **方案执行铁律（用户点名“不能再看不见它的方案”）**：方案/CR/求援类到件，ack 只销账≠接住——必须把方案逐条拆成动作项：**立即能执行的当下执行**（或写明不执行的理由）并回执对方，禁止把“现在就能做”的项随大流压到次日/低打扰窗（11-08 实例：收到 A/B/C 三案只选了最保守的 C 顺延周一，把立即可执行的 A 也一起押后，被用户点名“要深度提升”）。巡更时顺手查对方标记待我响应的件（如 workbuddy 的 `hermes_action_todo.jsonl`）+ 我方方案响应台账：未执行的自动报群点名，不等用户来问；同模板重复推送按铁律4首轮处理、后续只 ack。

## 常用命令

```powershell
commons.cmd post -From hermes -To dsh -Subject "标题" -Body "正文"
commons.cmd post -From hermes -To all -Subject "同步" -Body "……"
commons.cmd inbox -Agent hermes
commons.cmd read -Id <id>
commons.cmd ack  -Id <id> -Body "结论"
commons.cmd reply -Id <id> -Body "给发起方的回复"
commons.cmd note -From hermes -Body "今天做了X"
commons.cmd digest -Days 7
```

⚠️ **【多行正文禁走 cmd（D8 铁律）】**：`commons.cmd post/reply -Body` 多行内容在 Win 批处理→PowerShell 参数层被按行拆掉，存总线只剩首行（实锤：一封 800+ 字的信存盘 body 仅 13 字符，对方连续多封报"又截断"同源于此，非对方 drain 问题）。发信前用 `ls bus/inbox/<对方>/` 回读存盘文件核对 body 长度，短于正文即截断。多行正文一律 Python 直写总线 JSON：`E:\AgentCommons\bus\inbox\<对方>\<ts>__hermes__<subject>.json`，字段 {id, ts, from:"hermes", to, subject, body(完整多行), priority:"normal", status:"pending", refs:"[]"}；单行短 Body 才可走 cmd。 直写总线 JSON 的字段名一律用既定集合（id/ts/from/to/subject/body/priority/status/refs），别自造别名（如 frm）——取件方按固定字段解析，别名字段会被忽略。截断信发出后向对方补发完整正文 + 注明根因。
**bot 直连（message_agent）卡死时的总线兜底**：`message_agent` 发 Hermes 侧 bot（如金策子 bot）回 `ambiguous`/`admission_conflict`（delivery 未确认）时，服从其 "Do not resend"——改走总线直写 `bus/inbox/<目标>/`（JINCE 风格字段，不再写 outbox——outbox 是死件箱无拾取者，见上条投递模式），触达靠取件哨下一拍（~15min），回执以对方 ack 或下一拍取件为准。**目标 inbox 目录可能不存在**（该 bot 从未被总线写过）——先 `os.makedirs(exist_ok=True)` 再写，直接 `json.dump` 会 FileNotFoundError。

**投递模式（11-16实锤修版）**：① **直写对方 inbox**（`bus/inbox/<对方>/<ts>__hermes__<subject>.json`）= 唯一可靠路数，取件哨下一拍（~15min）即达，回执/裁定件/当日必须对方读到的全走这条；② ~~写自己 outbox 由 relay 拾取~~ = **死件箱（11-16实证作废）：relay.ps1 全文只有 $Inbox 收件箱清空逻辑、0 行 outbox 分支，outbox/hermes 里 24 件积压 1.5 天无人拾取——禁止再用 outbox 投递，发现死件手工清**。死件清理配方 = 逐件读 JSON 的 to 字段分类（to 可能是总线 4 成员也可能是 Hermes bot 岗名）→ mv 到 `bus/inbox/<to>/`（先 makedirs，目录常不存在）且文件名加迁移标记（如 `__hermes_outbox_migrated__` 前缀）防对方误当新件重复处理 → 清完 `ls` 验 outbox 余 0、留痕。bot 直连（message_agent）走 Hermes 侧 bot 通道，与总线并行。
**回执 ACK 只写 `bus/outbox/hermes/`（自己名下的 outbox 目录），别写 `outbox/<对方>/`——对方目录不存在，io.open 会中途 FileNotFoundError 把后续销账步一起炸掉**（实踩：御史红项 ACK 先误写 outbox/yushi 报错，改 outbox/hermes 后对方取件哨才拾取）。写 ACK 前先 `ls bus/outbox/` 看有哪些收件方目录，ACK 永远落在自己目录。
**总线 JSON 文件名格式别猜**：inbox 顶层件 = `YYYYMMDD-HHMMSS__<发件方>__<主题含空格>.json`（横线时间戳 + 双下划线分隔 + 主题带原始空格），**不是** T 分隔（T 格式只在 `id` 字段里）；processed/ 里同格式。按主题关键词 ls/grep 找实际文件名再 cat，`cat 20261115T*` 必空。

## 坑（发信/销账高频踩点）
- **`post -To` 只收总线 4 成员（workbuddy/hermes/dsh/yushi）**：`commons.cmd post -To risk-officer`（或任何 Hermes bot 岗名）报「未知收件人（可用：workbuddy, hermes, dsh, yushi）」——post 校验只认成员表。bot 岗（risk-officer/strategy-rd/evolution/post-mortem/chief 等）发件主路=message_agent（Bot Chat 通道），总线兜底=直写 `bus/inbox/<岗>/` JSON（先 makedirs，该目录常不存在）等取件哨拾取，绝不用 commons.cmd post（会被校验拒）。bus/inbox/<岗>/ 目录存在≠post 可用（目录是直写产物，校验名单不含岗名）。
- **子代理件的回执/ACK 投 relay 侧不是 actor 侧**：JINCE-HS 件头 `X-Jince-Actor` 可能是没有独立总线收件箱的子代理（lifecycle-analyst 等），件物理上经 `X-Jince-From-Mailbox`（relay 方成员，如 workbuddy）到达。回复/ACK 必写 relay 方收件箱（`bus/inbox/workbuddy/`）并在 subject/正文注明转给哪个 actor——自造 `bus/inbox/<actor>/` 目录无人拾取（取件哨只扫既定成员箱），ACK 发那等于没发（11-17 B0 泄漏重报 ACK 实踩：lifecycle-analyst 无箱，改写 workbuddy 侧才闭环）。
- **inbox 销账用 glob 全量移 processed/，销完 `ls` 验证剩 0**：逐件按猜的文件名 mv 必踩（空格主题/T 格式猜错），一次脚本 glob 该目录所有顶层 *.json 全移 + 回读，比逐件稳；同批多件（含新到的周期做单思路）一锅端，别只销当报提到的那件。

## 从 Hermes（git-bash/Python）发中文消息的配方
- **命令行里直接带中文必碎**（cmd 的 ANSI/GBK 层或 PS 5.1 参数解码）——正文一律走 **UTF-8 文件**，命令行只留 ASCII 参数。
- **姿势 A（推荐，无 .ps1 文件）：inline -Command + Get-Content 读正文**——`powershell -NoProfile -ExecutionPolicy Bypass -Command "& 'E:/AgentCommons/bin/commons.ps1' reply -Id <id> -Agent hermes -Body (Get-Content -Raw -Encoding UTF8 'C:/.../body.txt')"`。**Bypass 必须带**（不带会被执行策略挡：无法加载 commons.ps1）；`-Id`/`-Agent` 是**命名参数**（位置传 id 报 "缺少 -Id"）。⚠️ 表达式的 `-Body (Get-Content ...)` 只在 `-Command` 调用形态下生效——切到姿势 B 的 `-File xx.ps1` 时参数按字面字符串传（-File 不做表达式求值），括号体变成垃圾文本；-File 形态要用表达式必须把 Get-Content 写进 .ps1 内部。正文长/含中文的标准姿势=写 scratch 文件 + 姿势 A（`-Command "& commons.ps1 ... -Body (Get-Content -Raw -Encoding UTF8 文件)"`），一条命令打完。成功标志=stdout 出现「已回复/已投递 → 对方 [id]」行（这行是 ASCII 前缀+GBK 尾部，head 截断也能辨认）。
- **姿势 B（多参数/多行复杂调用）：小 .ps1 存为 UTF-8 带 BOM**，`powershell.exe -NoProfile -ExecutionPolicy Bypass -File xx.ps1`（PS 5.1 `-File` 无 BOM 按 ANSI 读，中文全乱）。
- **批量 ack**：收件箱 JSON 的 `id` 是 ASCII——python `json.load` 抽 id 循环 `E:/AgentCommons/bin/commons.cmd ack -Id <id> -Agent hermes`，成功=stdout 出 ACK 行或静默退出 0；ack 后文件移入 `processed/`，以 `ls inbox/<代号>` 剩 0 为准。
- **无头 relay/CLI 模型输出 token 耗尽（"No visible answer / hit its output-token limit"）**：hermes 无头入口（relay/cmdline cron）挂掉、对方通报"认领了消息但产不出可见答案"时，先 `tasklist`/进程 CPU 采样区分网络断连（CPU 高、重试中）vs 推理空转（CPU≈0、反复续写全耗尽预算）；修法是入口侧 reasoning effort 降到 low/none 或提高 max_tokens，不要盲目重试烧额度；修完复跑一次 relay 看是否产出可见答案再销缺陷单。
- 捕获 PowerShell 输出时 stdout 是 **GBK 字节**：Python `subprocess.run(..., capture_output=True)` 后 `out.decode("gbk", "replace")`；按 utf-8 解会在 0xCE 等字节处崩。
- 到件核对：别信 stdout 的「已投递」行，glob `E:/AgentCommons/bus/inbox/<代号>/*.json` 看最新文件的 subject 才对得上（投递失败时 stdout 也是「已投递」的假象不会出现，但 GBK 解码崩会让你以为没发）。

## 分工（默认，不绝对）

| 活 | 找谁 |
|:--|:--|
| 文档、PPT、Excel、腾讯文档、公众号排版 | `workbuddy` |
| 长链路自动化、量化/EA、定时任务、多 bot | `hermes` |
| 本机文件、改配置、写代码、跨应用集成 | `dsh` |
| 金策交易系统只读审计（P0/P1 报告） | `yushi`（金策·御史，只出报告不改码） |

拿不准就 `post -To all`，谁先看到谁认领，认领后 `ack` 并说明。

## 御史（yushi, 金策·御史）审计渠道
- 第 4 成员，只读复核席：不下单、不改 live 代码。报告在 `E:\AgentCommons\yushi\reports\YYYY-MM-DD\`（审计报告_vN.md），P0/P1 会投各 agent 收件箱。
- **报告也会错，以最新版为准**（审计员自己出过 v2 更正 v1 的先例：时区口径、成单误判）。落地 P0 项前逐条对源码/实读核验关键断言（grep 调用点、实读状态），核实后再修，勿直接照报告改码。
- 常见 P0 类：闸不咬合（闸文件存在但活路径 0 处读取）、演练单污染实盘口径、GBK 子进程崩溃被 fail-open 吞掉。修复 SOP 见技能 mt5-multiagent-trading（exp_r 总闸架构节）。★【闸不咬合·跨引擎变体（11-15 御史晚报实证）】冻结/退役闸（retire_freeze_gate 等）只在主引擎读了闸时才是真冻结——`active=true` 不是生效证据，其它执行通道（进化营/20261104 挂单引擎等）没接闸读点就会在冻结期照开照挂冻结品种单（假冻结）。信闸前必双验：①枚举账户全部执行通道（魔号/引擎）确认开单+撤单前置都读该闸 ②在盘实证=冻结品种在任一通道 0 活挂单 0 新腿（orders_get 全量按冻结品种过滤）③**双闸并存（解冻闸与退役/冻结闸同时有效）时执行通道必须全读，漏读任何一闸=同病变体**（11-17 实证：SD 通道只读币线解冻闸 active=False，漏读品种退役闸 until 9999，夜间无台账挂出退役品种单 5 张全撤）——新执行通道上线前枚举该通道读取的全部闸文件清单逐一核在案。发现违规单三步处置：①TRADE_ACTION_REMOVE 逐张撤单止血（留痕 sd_guard_run.log）②根修工单进 rd_queue（执行路径并入闸读点，走 crypto_freeze 同桥模式：闸→risk_state 并入→循环读，五验后 chief 翻闸）③向发现方（御史/巡检）发回执写清止血+工单+验收口径（"冻结品种 0 新腿 0 重挂"）。

## 共享真值 live_state.json 刷新（报持仓/挂单/净值前，超 30min 必刷）
- 真值 = `E:\AgentCommons\shared\live_state.json`（yushi 实写）。`E:/AgentCommons/bin/state.cmd` 报「过期(Ns > 1800s)」= 超 30min 未更，报数前必强刷；刷后实读 json 的 ts 验证，别信命令退出码。
- **刷新不依赖 yushi 进程常驻**：直接调底层脚本 `E:/GoldstrategyEngine/python/envs/ate/Scripts/python.exe E:/AgentCommons/yushi/bin/mt5_snapshot.py --shared`（rc=0 + ts 刷新到当前=成功；stdout 是 GBK 中文摘要，subprocess 端 gbk 解码）。
- 坑：① `snapshot.cmd` 在 `E:\AgentCommons\yushi\bin\`（`E:\AgentCommons\bin\` 只有 commons/relay/state，没有 snapshot，别猜路径）；② 本宿主 git-bash 调 batch 走 `cmd //c` 可能静默不执行（无 MSYS 参数转换，`//c` 原样传给 cmd 只出提示符 banner）——**不确定时直接调底层 python，别在 batch 包上耗**；③ 刷新后 live_state 的 equity/balance 键名与 stdout 摘要不同（json 里可能是嵌套/异名字段），报数前实读字段别硬断言。
- **★【yushi 零值写（11-17 三度实踩）】**：terminal64 重启后 yushi 的 MT5 读通道冻死，它仍按循环刷新 ts 但把 **0 挂单/0 持仓写进 live_state（读到空写 0，非 read_failed）**——共享真值变 0 值污染源，下游（节点/晨报/风控）全按 0 敞口误判。处置序：①先跑 `mt5_snapshot.py --shared` 强刷看能否恢复（通道活=恢复，仍 0=冻死）；②冻死期主 bot 用 ATE 实读**应急写真值**直接覆写 live_state.json（带 `correction` 字段标注入档；注意 yushi 下轮刷新会**冲掉 correction 又写 0**，应急写只是临时的）；③向 yushi 投工单件（直写 `bus/inbox/yushi/`，要求：读失败标 read_failed 禁写 0 + 每拍带 self_check 握手状态）；④期间下游报数一律 ATE 直读实读、live_state 只作对照不作真值；⑤rd_queue 立 P1 工单（根修=写入方读通道健康检查前置）。

## 交接必须带三样

**目标 + 验收标准 + 期限**。缺一样，对方可以打回。

## 边界

- 不共享模型额度、不共享登录态、不代填密码。
- 破坏性操作（删文件、改系统、对外发布、动钱）先在 `memory/decisions.md` 留痕。
- 不确定就发消息问，别替另一个智能体猜。
