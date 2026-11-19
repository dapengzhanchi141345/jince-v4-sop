# 事件闸口径与跨通道持仓对账（11-10 RED 教训沉淀）

## 事件冻结闸：真闸在 event_calendar.json，新闻 time 字段不可信
- 三段冻结时刻表（S1 halt/观察/放行）的上游 = `data/event_calendar.json` 的 `windows`（event_time=Bjt unix 戳）；`event_risk.json` 只是新闻事件体温通道（level/MED 聚合）。
- `event_risk.json` 新闻事件 `time` 字段 = **采集时刻非发生时刻** → event_intel 预判层会把未发生的数据事件误判 PUBLISHED（0-2h 跟进窗失灵）。冻结闸本体只看 calendar；news 条目 PUBLISHED ≠ 冻结状态，勿混。
- **数据源被阻时 calendar 可能 0 条**（windows 空 + high_events_in_24h=0）= 当天大事件未排入 = 三段冻结闸当日失灵（RED）。核法：读 `event_calendar.json` mtime+windows 条数；再读 `data/event_guard_windows.json`（event_guard 快通道 5min 拍输出）看 now_phase_hint 是否含该事件。
- **人工兜底补刀**（生成方修复前保命手，加法）：向 `event_calendar.json.windows` 追加 1 条 `{event_time: 真实BJT戳, title: "…[chief人工兜底]", grade: "HIGH", note: "manual_chief_…"}` 且 `high_events_in_24h=1`，不动生成方既有字段 → event_guard 下拍自动拾取 → **验活 = 读 `event_guard_windows.json` 确认 S1/S2/S3 时点**（S1=数据前 T0_MIN halt：停新仓+撤趋势/Stop、震荡 Limit 保留；S3=数据后 30min 结构确认放行；display grade 可能被"窗口内降档 A→B→C→D"规则显示为 MED，冻结效力不变）。
- **覆盖风险**：生成方（daily_advisory/研究循环）重写 calendar 会冲掉 manual 条目 → 固定验证点（如 18:30）再读 calendar，被冲=再补+总线急件升级；急件写明"再生成时保留 manual 条目或含该事件窗"。
- **美东事件时区规则（11 月后必查）**：美数据事件（CPI/PPI/非农 08:30 美东）BJT 折法随冬夏令切换：夏令（3 月-11 月初）BJT=美东+12h=20:30 BJT；**冬令（11 月第一个周日-次年 3 月）BJT=美东+13h=21:30 BJT**。11 月 US CPI = 21:30 BJT，写 23:30/20:30 都错——排冻结窗前先判当前 EST/EDT，勿凭旧记。

## 跨通道持仓对账：新仓出现/消失先实读定位再归因
- 节点开评/对账/投递卡报"活持仓 N 张"变化时核三件事：
  1. `mt5.positions_get()` 实读现持仓；
  2. `mt5.history_deals_get(起, 今)` 按 symbol 找 entry==1 出金行——**deals 有落史滞后（几十分钟至 2h），查不到先扩大时间窗再下结论**；
  3. 出金行 `comment/reason` 定真因：`L24_B0_INVAL`=结构失效早退（结果驱动四件套①生效，砍亏小钱，**不是 SL 触发**；先认 comment 再归因，错归 SL 会误导调参）。
- 余额跳变≠刚平仓：节点余额快照可能数小时前陈旧（同一 $959.19 连投 8h 见过），先 deals 定位平仓时刻再报。
- 开平仓属进化营通道（magic 30261103 / comment=JINCE_LIVE24）时**不干预**（其 0.01 样本腿 + RR2.0 三件套在其引擎闸内合法），但**台账双写断口要补**：向 `data/order_lifecycle.jsonl` 补 open/close 行（owner=进化营 live24 层, magic, SL/TP, close_due, status）；每晚 22:00 看门狗销账做"全持仓 vs 台账"自动补差。观察名单外的新腿（小币种非 4 大 close-only、博德 tm=ANY 可开）=进化营新思路，登记不否决，除非破 0.01 样本腿纪律或缺三件套。
- **ticket open_time 时区坑**：本账户 position/deal ticket 时间戳 ≠ BJT（15:0x 节点已现 ticket 16:4x 开仓单；GER40 ticket 18:30 则≈BJT）——报开平仓时刻以台账/节点出现时间反推 BJT 并注明不确定度，勿把 ticket 时间当 BJT 直报。
- **MT5 Python API 坑**：`mt5.orders_get(ticket=N)` / `mt5.positions_get(ticket=N)` 必须命名参数，位置参数报 `Unnamed arguments not allowed`（(-2) 系统错误）；无 `order_get_ticket`（只有 `orders_get`）。

## 预开位（broker 预注册未来开仓）：识别、计数、事件窗门闸
- **识别三特征**（TradeMax 类小 broker 的「定时预开」形态）：`positions_get()` 返回的持仓中，`p.time`（开仓时刻）晚于当前时间 + 该品种该时段 `history_deals_get` 无对应 entry deal + `orders_get()` 无 pending 挂单——三者齐 = **预开位**（注册在册、尚未成交；有浮盈试算、ticket 已分配）。
- **报数铁律**：报「活持仓 N 张」时把已成交持仓与预开位分开报（预开位标注开仓时刻）；混报会把「尚未成交」当实仓，冻结窗/强平哨/对账口径全歪。
- **事件窗门闸漏洞**：halt 闸（event_guard/三段冻结）只拦「新挂单/新开仓动作」，**不拦预开位在冻结窗 [halt, release] 内的开仓时刻**——预开位注册在冻结前、开仓点落在数据落地瞬间或观测窗内 = 违规。冻结窗生效前必扫一遍现存预开位开仓时刻：落在窗内的移窗后（≥release+5min）或撤注册；撤未成交的预开位零成本（无 deal、无盈亏），撤/移走引擎侧通道（非 orders API——它不在 pending 簿里）。

## 共享真值（live_state.json）使用前置交叉验
- 报持仓/挂单/净值前先 MT5 实读，`live_state.json` 只作留痕/线索；其 `open_positions` 与 MT5 实读不一致（典型：写 0 而实读 N 张，equity 却正常）= **写侧 bug（P1 数据契约违规，全下游吃错值）**——总线报写侧修字段，别把 0 当真值报下去，也别静默用旧数顶。
- 判定时点：live_state 的 ts 新鲜（几分钟内）+ open_positions 与实读差 = 写错而非滞后；ts 陈旧（>30min）才按「过期」论（跑 snapshot 重刷）。

## 人工补事件窗条目：必须带全 schema + 下拍验活
- 向 `event_calendar.json.windows` 手工追加事件条目时，**必须与自动条目同 schema 完整**（`event_time`=BJT unix 戳是关键驱动字段，事件三段时刻由引擎从 event_time 推导；只写 title/grade/note 而 event_time 缺失/None = 闸静默空转，冻结不生效）。落盘后 ≤5min 读 `data/event_guard_windows.json` 确认该事件 S1/S2/S3 时刻出现才算验活；未出现 = 条目畸形，按完整 schema 重注，勿假设「写进去了=闸生效了」。
- 总线回执类口径待决（如冻结三段时刻定稿）：以引擎在案项为准拍板确认即可，双方同源不改口径，回执里顺带要求生成方修好后保留 manual 条目。
