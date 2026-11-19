# 7 主流品种 D 级否决数据缺口（2026-10-08 挂账，strategy-rd 根治）

全链扫描/节点会拦 XAUUSD/AUDCHF/USDJPY/GBPUSD/XAGUSD/CHFJPY/EURJPY 7 个主流品种：
研究部判 D 级硬否决，根因 = **当日研判 daily_advisory_*.json 读不到这几个品种的逐条研判条目
→ 全品种同向闸 fail-closed 不挂**（安全向，零交易风险，别误当漏单）。

- **治本方向（李彦明确认：不降闸放行）**：让 strategy-rd 在研判生成层补上 7 主流品种的逐条研判，
  使 D 闸读得到条目 → 自然放行/自然否决，不是把闸降成 WARN。明早 04:00 趋势 CTA 段顺带认领出结论，
  22:00 日报单列。
- **判据速查**：全链简报写"某品种当日研判读不到该品种条目 → 全品种同向闸 fail-closed" = 此缺口复发，
  认它不是故障；要根治查 daily_advisory_当日.json 里 sections 是否含该品种逐条
  （`{date, sections}` 结构 4MB，按 sections 组织，**别按 symbol 顶层键读**——读 0 条是读错层）。
- **fail-closed 是纪律不是故障**：缺研判就该收手，顶配是补数据攒证据，不是"再加单赌回本"。
  当前 0 仓 0 单 = 对的，守住别破。
