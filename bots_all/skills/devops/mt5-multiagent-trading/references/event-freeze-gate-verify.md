# 美重大数据日 · 事件冻结闸核验与人工补刀 SOP

适用：美重大数据点（CPI/PPI/NFP/FOMC/非农）临近当天开盘后跑一次，别留到事件前几小时。

## 步骤（按序）
1. **验真时点（先于一切）**：美数据多 EST/EDT 08:30 发布。先判美国当下夏令/冬令（3月第2个周日~11月第1个周日=EDT，其余=EST），EDT→BJT +12h，EST→+13h，算出真实 BJT 发布时刻，与晨学哨/外部情报的人学时点互证。**别信状态卡/旧记法里的时点数字**（曾记 23:30 实为 21:30，冬令切换少算 1h 是高频错法）。
   - 一行验算：`python -c "from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime(年,月,日,8,30,tzinfo=ZoneInfo('America/New_York')).astimezone(ZoneInfo('Asia/Shanghai')))"`
2. **读三段时刻表源**：`E:/GoldstrategyEngine/data/event_calendar.json` 的 `windows` + `high_events_in_24h`。**windows=0 或该事件不在 = 三段冻结闸当晚失灵（RED）**——event_guard 的 S1/S2/S3（数据前30min halt/数据后10min obs/后30min放行）由它驱动，日历空了闸就不响。
3. **读闸活体快照**：`data/event_guard_windows.json`（event_guard 5min 快通道每拍重写）：`now_phase_hint` 里该事件三段时刻齐全且 phase=SCHEDULED = 闸在位；文件 mtime 陈旧 >15min = 快通道没在拍，另查 JinCeEventGuard 任务。
4. **缺失 = 人工补刀（加法，改数据不改码）**：向 `event_calendar.json` 追加 1 条 windows 条目：
   ```json
   {"event_time": <真实发布时刻unix>, "title": "美X月CPI公布(headline+core) EST08:30=BJT21:30 [chief人工兜底: 生成方漏排]", "grade": "HIGH", "note": "manual_chief_<日期>"}
   ```
   同时 `high_events_in_24h` 置真实数。不动其他条目/字段；**绝不改 event_guard/live24 闸码**——数据写对，5min 快通道自动认。
5. **验活**：等下一拍 event_guard 快通道（≤5min）重写 `event_guard_windows.json`，确认该事件出现、三段时刻正确：S1=t−30min（halt 停新仓+撤趋势/Stop，震荡 Limit 保留）、obs 至 t+10min、放行 t+30min。显示 grade 可能被窗口内降档规则打成 MED，**冻结效力不变**，别当漏配。
6. **冲掉风险管理**：日历由自动源周期重建（外网源被阻时 windows 可能持续为 0），人工条目**会被覆盖**——当天排一个晚点验证点（task_ledger + 状态卡登记"被冲=再补+升级"）；同批发总线急件给生成方（`E:/AgentCommons/bus/inbox/workbuddy/`，DEFECT 类），要它修日历源 + 再生成时保留 manual 条目 + 回执。

## 坑（附机制）
- **`event_risk.json` 新闻事件 `time` 字段=采集时刻，非事件发生时刻**：预判层（event_intel）按 `time−now` 判 phase，当晚的发布会被全判 PUBLISHED，事件后 0-2h 跟进窗失灵。它走 level/scale 通道，**不影响三段冻结闸**，但别拿它的 PUBLISHED/level 当"事件已被处理"的证据；修复归生成方。
- **补刀前实读 mtime 判日历陈旧度**：`event_calendar.json` mtime 停在昨天 + high_events_in_24h=0 且当天有已知重大数据 = 生成方已掉线（多为外网财经源被阻），按本 SOP 补，不等它自己回来。
- 补刀条目 title 里带"chief人工兜底"字样 = 下轮全链/他人读到能识别这不是自动源产物，别被静默清掉。
