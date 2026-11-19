# 「深度学习X做单技巧/务必精准掌握」类任务交付形态与 WFO 派单协议（11-13 落地, 永久）

用户令「深度学习高流动性品种的做单技巧，务必精准掌握」——学习成果的交付物 = 深度融合进系统，不是聊天摘要（李彦明铁律）。三步形态：

## 1. 技巧台账落盘（不是总结文档）
- 逐项一行表：**什么（大白话）/ 引擎落点（具体闸或函数名）/ 证据（五验实数或OOS）/ 状态（LIVE-OBSERVE-WATCH）/ 未证伪点**，写 `E:\GoldstrategyEngine\research\` 技巧台账 md。
- 与外部规则映射表（如 workbuddy 21条映射）互认时**逐条对账**：LIVE 互认 / OBSERVE 只当否决门·观察（不放大仓位）/ 冲突出仲裁件（对/补/驳，bus 回执）。
- 外部「样本内最优」结论（如 deco 1:1 盈亏比）= 最多 OOS 方向证据；**1:1 TP/SL 在 0.095R 成本口径下 1.0+0.095=1.095<1.95 质量闸地板，数学上必被拒——永不采为引擎默认**（裁定时直接用此算术一句打回，不重跑回测）。

## 2. 重型同分母 WFO → delegate_task 子代理（协议写死在指令里）
- 品种**各自裁定**：APPROVE=五验≥4/5 且 OOS test 净>base 且>0；WATCH=3/5 或 OOS 弱但样本内正；REJECT=OOS 崩/负。DATA 薄/陈旧品种单独标 DATA_THIN/STALE_DATA 不硬判。
- **禁止跨品种平均掩盖单品种崩盘**；子集胜率差=选择效应不算 edge（李彦明铁律）。
- 统一口径：OOS 70/30 时间切（只在 train 上寻参）+ 成本 0.095R + 五验 T1-T5 + 三窗稳健。
- 子代理**只写 research/ 目录**：不碰 tools/、不碰 l24_feature_flags.json、不重启进程、不下单。
- 输出 JSON 结构 `per_symbol`/`verdicts`/`flip_ready`；chief 收回结果**先核同分母口径**（分母/成本/OOS 切分一致）再翻闸，子代理自报「跑通」≠ 结果可信。

## 3. 翻闸=按品种名单粒度（继承 [11-12] 五验灰度规则）
- 仅过闸品种翻 DEMO 灰度（0.01 手 + SL/TP + 12h 哨全保留），变差品种不拖入翻闸（11-13 例：黄金 ATR 基准点位 WATCH 级灰度，白银同改明确变差=白银不动）。
- 三件留痕：task_ledger + rd_ledger_24h + flag note；WATCH 进 rd_watchlist 前向 OOS 接力（次日 21:30 学习哨自动复验）。

## 4. chief 收件执行细节（12品种WFO实证）
- **薄OOS降级条款**：OOS 净>0 但 净/n < 0.01R/笔（扛不住实滑点，数学正而经济无意义）一律降级 WATCH 攒样不翻闸，防止 APPROVE 门槛把 +0.008R/笔 放进灰度（11-13 实证 +0.81/103 笔）。
- **持有帽 gap 留痕**：回测 max_hold（18-24h）vs 引擎 12h 必平哨 → 前向 OOS 系统性低于回测口径；翻闸时必注此 gap，前向对账前不放大。
- **wfo_syms 覆盖键**：l24_feature_flags.json 现有 4 键（rrpref/adx_max/atrop_syms/wfo_syms）；wfo_syms={SYM:{sl_mult,tp_mult,adx_min,note}}，引擎 L24_WFO_SYMS 块只消费 sl/tp（WFO 的 adx_min 放宽门默认不采=最小影响：引擎 ADX35 地板/H1共振/点差闸全保留）。
- **子代理共编核验**：收活先核 jince_live24.py / flag 文件 mtime 对照派发前基准——进化营并行共编是常态，子代理声称「未碰 tools/」不可全信（文件可能同时被他人动过）；重启前复核己方 L24_* 标记块（FLAGS/RRPREF/ADX_MAX/ATROP_SYMS/WFO_SYMS）完好 + py_compile 过。
- **重启验活程序（git-bash 坑）**：taskkill //F //PID 被 MSYS 乱序成无效参数 → 一律 powershell `Stop-Process -Id N -Force`；杀后看门狗可能 5min 内不拍，勿死等 → 按看门狗同款手动拉起：powershell `Start-Process '<3.13.12 python>' -ArgumentList 'jince_live24.py' -WorkingDirectory 'E:\GoldstrategyEngine\tools' -WindowStyle Hidden -RedirectStandardOutput data/l24_stdout.log -RedirectStandardError data/l24_stderr.log`（零参数=默认 magic，flag 文件启动时读取）→ 验活=锁文件 pid 刷新 + 桥 connected + 日志闸在流。
- **带中文/引号的重型 python**：terminal heredoc 内联易翻车（括号/转义）→ 写成 scratch 目录 .py 文件再执行，台账更新/回执写盘一律此式。
- **外部风控提案（御史早报红标件/进化营通报）到件先 grep 引擎既有闸**：机制已存在但阈值形同虚设 = **只收紧阈值、不新建机制**（收紧=重启验活+回执认讫+台账, 旧宽松值注释注明被何证据推废止用, 与进化营品种层闸两层互补不冲突）。**但收紧前过阶段闸（金策全授权v4 用户裁定, 优先于本条）**: 练习(DEMO)阶段组合级日亏熔断(DAILY_LOSS_PCT 类)保持原值——样本攒量/多开单优先, 红标证据保留在案(存 research/ 留档文件)不做处置动作, 组合级熔断移交实盘(REAL)阶段与 build_real_profile 档位一并评; 品种层坏腿闸(如 SYMBOL_PAUSE 连亏停手)挡的是单品种坏腿, 不约束练习, 两阶段均可收紧。用户令回退已落地的收紧时, 先代码回原值+重启验活, 再按 jince-bus-and-heartbeat-ops §7 四地留痕。
- **tool_call 多 call 数组(同块多个独立 tool_call)在本机调度器下解析易失败(JSON 报错, CJK 长 prompt 尤甚)**: 失败即改逐块单 call 发, 不循环重试同数组(3 连败实证)。

## 5. 学习类任务的报告交付形态（缺口/全网学习类, 李彦明「出个报告再说」）
- 交付物 = 精美 Word 报告（封面+目录+彩色表格+matplotlib 图表+页码, 微软雅黑）存 `E:\workbuddy\内容中心\交付\<主题>_<日期>.docx`, 用 docx 技能生成后 `docx_validate.py` 验证, 聊天里以 `MEDIA:` 发文件 + 一页大白话表格摘要（外部发现 → 对我们意味着什么, 逐行对应）。
- **图表/docx 生成解释器**: matplotlib/python-docx/numpy 只在 `D:/jince_sass/.venv/Scripts/python.exe`（hermes venv 与 execute_code 沙箱都没有）→ 画图+spec+docx_create.py 全链统一用它跑, 不试装不绕路。
- **外部网络研究证据（论文/行业研究/券商市况）只当方向印证, 不当结论**：与本地尸检/回测同分母核对后才写进报告「印证」列；一切翻闸以同分母回测验收为准（李彦明铁律：子集胜率差是选择效应不算 edge）。
- 学习产出的升级项一律注册 rd_queue 课题（字段同 SKILL.md rd_queue 条, `five_gate=true` + accept 写同分母验收口径 + 「只否决/降档不放大」边界写进 task 正文）, 不直接改引擎；全程不碰实盘/持仓/手数, 报告带 L5 红线声明（翻闸须风控 officer + 李彦明双裁）。

## 6. 深度优化派发类（李彦明「深度优化架构和策略并派发下去」）: 架构件 + 工单化
- **确定性架构件（面板/哨）配方**: 落 `E:/GoldstrategyEngine/scripts/`（0 LLM 纯确定性）, 读真源数据 → 逐族/逐维度统计 → 阈值自动裁定（如「族样本≥N 且 效率<X → 出课题」）→ 写真源 JSON（如 data/exit_panel.json）+ 摘要 print；进 30min 巡检循环刷。异常数据（如 |R|>50 的坏样本）**剔除+计数留痕**不当数用；数据面缺陷（跟踪器漏录字段等）不阻塞建面板, 列 rd 修 tracker 课题并如实报「缺口」。
- **课题升级工单（派发闭环）**: 注册进 rd_queue 的课题再升级成可执行工单——条目加 `owner`（岗位）字段, task 正文写死: ①代码位置（jince_live24.py 新常量名）②观察模式（先 N 天只 log 不拒单）③回退开关（关常量/mult=1.0）④五验口径（OOS70/30+扣0.095R）⑤「只否决/降档不放大」；改写前 `shutil.copy` 备份 `.bak_<tag>`（同 rd_queue 整文件重写铁律）, 台账+状态卡各记一笔。工单标准=30min 循环取件后实施方**照抄即可动手**, 无需再解读。
- 全部观察优先: 未过五验+风控双裁前, 新闸一律观察模式(log-only), 不直接改变开单行为。

## 7. 夜间深研 R 系列拍（分品系多轮 LLM 拍 + 汇总拍, 11-15 定型）
- **形态**: 每晚 4 轮分品系深研拍（R1 币系/R2 金银 FX/R3 股指 ORB 等, 各 1 次性 LLM 拍, 读品系卡+外网 3 源+本机同分母小回测）+ 1 个 R4 汇总拍。每拍交付物固定四件: ①回测产物 json+可重跑脚本（research/ 下, 文件名带 8 位日期）②品系卡 md 更新（原句保留可追溯）③rd_queue 工单注增量（备份 .bak_<tag>）④family_deep_study_log.jsonl 追加 1 行（ts/topic/hypothesis/evidence/verdict/action, 含数据源+快照+新鲜度）。
- **汇总拍（R4）必须 no_agent 脚本, 禁 LLM 一次性拍**: 汇总=读日志→分类（exec=verdict 明写翻闸/过五验且无 OBSERVE 字样, negated=FAIL/证伪/无 edge, 其余 watch）→写 family_playbook.json（每参数必带证据单号=日志行号+ts+样本+快照, 缺=拒写入）→开 live24 挂点 rd_queue 工单（幂等）→stdout 大白话总账（内容 hash 去重门, 当日同内容=零输出）。参照 jince_r4_rollup.py 形态。LLM 汇总拍=读多写多+长群报, 反复截断（'Response remained truncated after N continuation attempts' 全挂=任务形态错, 替代规则见 guardian-selfheal-and-delivery-verify §2）。
- **收 LLM 深研拍必验四件再销账**: 该族拍有连三拍假交付实证（宣称「日志追加/第 N 行」均未落盘, 产物 json/脚本都在=半交付）。主 bot 收口动作: wc -l 日志 + ls 产物 json/脚本 + grep 品系卡命中 + ls rd_queue 备份, 四件齐才销账; 缺日志=主 bot 按同口径补记（actor 标「主 bot 补记」+补记说明+redo_flag）, 并把该族产物命名变体扩进交付验活哨检查面④ regex（防第四次）。
