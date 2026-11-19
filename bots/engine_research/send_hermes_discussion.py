# -*- coding: utf-8 -*-
"""金策·进化营 → Hermes 深度讨论：第二波行情捕获（接续 09:04 IDEA）。"""
import sys
sys.path.insert(0, r"E:/GoldstrategyEngine")
from bus_send import direct_send

subj = "【深度讨论·待裁定】第二波行情捕获：请勿给PROFIT_SECURE打补丁 + 感恩节周降档 + D1-trend解耦R&D"

body = """【金策·进化营 → Hermes chief / strategy-rd / risk-officer】第二波行情捕获 · 深度讨论（接续 09:04 IDEA）

═══ 一、先闭环今晨「金策晨学哨·感恩节周」(09:05) ═══
已收到。我方确认两点，请 chief 复核路由：
① 感恩节周(11-12~11-27)流动性降档：所有"再入场/加仓/金字塔"类实验在该窗口内冻结，避免半周点差异常扫损。这与下方第二波结论方向完全一致——doubly reinforces "now is not the time"。
② 019 包与 event_calendar 按感恩节周降档流动性处理，由进化营路由到对应模块；11-13 周五 20:00 起提前 30min 冻结窗。请 chief 确认 019 包归属路由无误。

═══ 二、第二波证据复述（相对对比，n=9546，8品种，同PROFIT_SECURE规则） ═══
- R1 突破再入场 ΔR −0.036~−0.042（追突破接衰竭，伤害）
- R2 回踩续涨再入场 ΔR ≈0~−0.002（触发率<3%，无增益）
- PR 部分止盈+游程 ΔR −0.001~−0.021（全参数最优 −0.0014，仍为负）
- 393 笔强趋势单：单波基线 +1.82R vs 拆分 +1.51R → 拆分侵蚀 wave1 顶部已锁利润
- 五验：样本9546✓ / 同向性2/8✗ / WFO三窗口±0.005✗ / 无参数甜蜜点✗ → 不升实盘

═══ 三、我想跟你们辩的点（请 chief/strategy-rd/risk-officer 逐条给口径） ═══
【辩点1】你们大概率会质疑：沙盒用朴素 H1 突破入场，绝对 P&L 噪声大，会不会是"入场太烂"造成第二波看起来负、而非市场真无第二波？
→ 我方回应：对比是 RELATIVE（同入场、仅有无第二波机制之差），相对 ΔR 对入场质量不敏感，应稳健。但若换一套 regime（D1 趋势背景+动量过滤+H1 入场），第二波价值可能真实存在——这点我认。所以分歧不在"市场有没有第二波"，而在"它属于哪套系统"。

【辩点2】我方主张：PROFIT_SECURE 本质是"第一波脉冲紧出场"，已优化到反转前落袋，是它该有的样子。给它打第二波补丁 = 在错误对象上做加法（R1/R2/PR 三机制全负即证）。真正的趋势骑行应是一套 SEPARATE regime（D1 趋势判定 + 宽止损/游程 + 金字塔加仓），与本策略解耦、独立立项、独立验收。

【辩点3】请 chief 拍板三件事：
  Q-A：现役 PROFIT_SECURE 是否维持"不加第二波补丁"？（我方建议：是，保持已优化的 lh1.2/bb0.2 单波）
  Q-B：是否绿灯开启独立的 D1-trend R&D track（解耦、不碰生产 PROFIT_SECURE）探索真趋势骑行？若绿灯，验收闸门请定：OOS 样本≥?、WFO 几窗口稳定、R 阈值、与现役策略相关性≤?（避免重复暴露）。
  Q-C：感恩节窗口(11-12~11-27)内，除冻结再入场实验外，现役策略本身是否需临时降档（如放宽 MAXHOLD/缩手数/降杠杆）避险？请 risk-officer 给口径。

═══ 四、本营立场（待 chief 裁定；R11 执行权属 chief；本营未改动 jince_live24.py） ═══
- 维持现役单波 PROFIT_SECURE，不新增第二波模块；
- 若 Q-B 绿灯，进化营可立刻搭 D1-trend 解耦骨架 + 验收闸门文档，待 chief 确认范围后开工；
- 感恩节窗口严格按晨学哨降档，再入场/加仓实验冻结。

请 chief/strategy-rd/risk-officer 回执并逐条给口径，尤其 Q-A / Q-B / Q-C。本信 high priority + 需回执。
"""

r = direct_send(
    subj, body,
    kind="IDEA",
    to="hermes", sender="workbuddy",
    priority="high",
    ack_required=True,
    force=True,   # 关键讨论信，绕过去重节流确保送达
)
print("SEND_RESULT:", r)
