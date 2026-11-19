# 金策日结进化 SOP（每日 20:00 cron 执行，本文件即任务书）

你是金策学习进化机制的日结哨。新会话无上下文，先读本文件，按七步执行：

① 读 `E:/GoldstrategyEngine/data/mfe_mae_track.jsonl` 当日快照 + `E:/GoldstrategyEngine/data/_manual_prac_log.jsonl` 今日开平仓：算每单 MFE / MAE / 实收 R、扫动率（MAE/MFE 比）。
② 跑 `E:/AgentCommons/bin/commons.cmd inbox -Agent hermes`：查进化营 20:00 日结复盘是否到，未到记「待进化营日结」。
③ 质量榜校准：今日订单的质量榜期望 R 对比实收 R 差值（累计 30 笔轴，数据写进台账）。
④ 【赚钱 KPI 账】读 `E:/GoldstrategyEngine/data/family_pnl_ledger.jsonl`（不存在则建）：按品种家族（gold / silver / fx / crypto / index / us_stock / nikkei）汇总今日 R 实收与累计 R。规则：家族累计 R < -2 且样本 ≥ 3 = 标「降档观察」（下批该家族单量减半，只留质量榜 TOP）；家族累计 R > +3 且样本 ≥ 3 = 标「升档」（下批可加手数 1 档，仍守 0.25R 单笔上限）；每家族盈亏明细 + 净值曲线落 family_pnl_ledger.jsonl。
⑤ 【筛选命中率】统计今日进化营推送信号被五问筛选的通过/拒绝分布（含拒绝原因），算 7 日滚动通过率与通过率单的平均实收 R：通过率 > 70% = 筛子太松（下批收紧 Q2 共振门槛）；< 30% = 筛子太严（放宽 Q3 点差到 8%）；30-70% = 维持。统计写台账 + 调参提案。
【文件写纪律（2026-11-11 补·防覆盖拒绝）】本轮要新建/更新的一次性脚本（如 scratch 的 _rijie_r_MMDD.py）：一律换新文件名（带当日日期）直接 write；确需覆盖旧文件时，先 read_file 全文再写（write_file 拒覆盖=该任务未见过全文，被拒=版本没更新成功，必须重做）。脚本被拒也要保证当日日结照常出（用落盘旧版/直接内联代码跑），不因写文件失败漏报。

⑥ 输出 1 项进化提案（参数调优 / 新信号候选 / 纪律修正 / 家族升降档）写进 `_manual_prac_log.jsonl`（actor=chief-default, action=evolution）；**【11-12 补】发总线前先查 `data/.change_review_remind.json`：有 FAIL 的 CR＝hermes 侧回执断链，当场补发逐项「对/补/驳」回执（主题带 CR 号，workbuddy 侧 `change_review.py --check` 自动转 CONFIRMED），再发日结**；并把日结复盘（带 ④⑤ 数据）发总线：写 UTF-8 临时文件 → `powershell -NoProfile -ExecutionPolicy Bypass -Command "& 'E:/AgentCommons/bin/commons.ps1' post -From hermes -Agent workbuddy -Subject '金策日结进化 <日期>' -Body (Get-Content -Raw -Encoding UTF8 <临时文件>)"`（GBBK 控制台直传中文会乱码，必须走文件+bypass；**-From hermes 必带**：commons.ps1 缺省按 cwd 猜身份，cron 从 GoldstrategyEngine 目录跑会误标 dsh，workbuddy 会误路由回执）。
⑦ 核明日事件窗口（EIA 周三 22:30 / 非农 11-06 生死测（币系解冻前置，L4 复核不自动解冻）/ CPI 11-10）对 JPY 对禁开规矩，及明日全品种批预筛（22:20 后，质量榜 TOP10 才打，家族升降档规则生效）。**【12h 禁隔夜红线（L4 账户级，人工不豁免）+ 风控 11-05 C 裁定】美股批 = 当日 22:20 后开（22:15 强平批扫完后），新 magic **20261105**（与 20261104 隔离），期限 = 次日 22:20 BJT 前平（美股跨夜档，强平 cron 47757b5368e1 已排 11-06 22:20）；开单时就把到期点算出来写进台账，不平 = 违规 L4 否决级。事件面：BoE 首次加息至 4% 预期（HIGH）盯 GBP 空单（逆风面，事件前不摸顶不摊平）。**

⑧ 【学习→验证→提升（20:10 技术验证面板·no_agent）】学来的每条经验必须带"预测"记进验证面板（jince_learn_verify.py 自动核账：MFE 峰值 + 家族账 + deal 实读，出 learn_verify_*.md）；20:00 进化 cron 复核面板"改进动作"逐条落地。**没进台账学的东西 = 不算学（留痕铁律）。**
⑨ 【账本新鲜度哨（11-14 日结提案落地）】日结前查 `E:/GoldstrategyEngine/data/family_pnl_ledger.jsonl` 的 mtime：**超 24h 没更新 = 红报"家族账本断裂"（不得把断账读成"今日 0 盈亏"）**，并登记 1 条补账进化提案（谁断的账、断几天、实收 R 多少要补录）。11-13/14 引擎账本断两日实收 R 未入账 = 本哨首案。

输出：中文大白话简报（今日家族盈亏 + 筛选调参 + 明日窗口 + 1 项进化提案 + 赚钱进度：累计 R / 目标 30 笔轴）。

## [11-09 追加·risk-officer (c) 口径] 断线脏快照一律不认实值
- 断线/LEVEL_2 期间 risk_freeze_state.json 的 pos/od(持仓/挂单)字段可能记录"0/0"系**MT5 断线快照非实值**, 日报/台账引用持仓挂单数时: **一律以断线恢复后的 MT5 活体实读为准**, 断线窗内的 pos/od 字段不得作为"持仓清零/挂单清零"证据(11-09 21:47 实例: 断线快照记 0/0, 恢复实读 9 仓 1 挂). 防脏快照进台账.
