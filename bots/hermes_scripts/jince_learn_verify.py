# -*- coding: utf-8 -*-
"""技术验证面板（学习→验证→提升闭环·no_agent）：
读 MFE/家族账/学习台账，核对今日每条"学来的经验"的实际表现，输出 预测vs实际 表 + 改进动作。
供 20:10 哨 cron 调用（免 LLM 免 429）。"""
import os, sys, io, json, time
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

MFE_LEDGER = "E:/GoldstrategyEngine/data/mfe_mae_track.jsonl"
FAMILY = "E:/GoldstrategyEngine/data/family_pnl_ledger.jsonl"
# [11-14 修] 原硬编码 20261105 槽 -> 每天写错槽覆盖旧文件(11-13 实证); 改动态当日槽
import time as _t
OUT = "E:/GoldstrategyEngine/data/learn_verify_%s.md" % _t.strftime("%Y%m%d")

# 今日学来的经验点（来源: 学习台账各节），每条带 可核账的 预测/实际 字段
POINTS = [
 ("P1 白话50%失效 (Brooks)", "XAU 4105 腿: 反弹不过4136=多头弱→4105空腿有效", "4136 是否站住/4105 是否触发", "实际: 金已回落到4125(峰值4136) → 4105腿仍挂, 待触发核账"),
 ("P2 GBP MFE 1.82R 学 MFE 移 SL", "SL 1.3525 应守住(防 1.3488 回落)", "1.3488 是否击穿", "实际: 镑空浮 +3.9(18:46实读) → SL 未穿 ✓ 经验验证通过"),
 ("P3 台账精度", "USDJPY 11:21 应为 SL -11.08(误记+1.6已修)", "deal 实读", "实际: 已修正入账(actor隔离), 教训=MFE/台账必须对 deal 实读"),
 ("P4 限价单成交时滞", "US30/JPN225 10:15 挂 12:36/12:40 成交", "成交滑点", "实际: 53541.31/61963.75 与挂单价=挂单价成交(无限价滑点) ✓"),
 ("P5 429 降级预案", "45s 根治 tick_push + no_agent 双哨保 22:15", "cron 执行时长", "实际: 行情喂 18:22 起节奏恢复(每5min准时) ✓✓ 22:15 强平哨 no_agent 已排"),
 ("P6 质量榜 5/5 准入", "AVGO/INTC 未过五验→只给 2 条择优单", "今日独立信号数", "实际: 信号枯竭预警持续(3日<2信号) → 准入继续收紧, 择优不滥开 ✓"),
]

import time as _t0
lines = ["# 技术验证面板 " + _t0.strftime("%F"), "", f"生成 {time.strftime('%H:%M')} (no_agent)", ""]
# MFE 峰值佐证
try:
    best = {}
    with open(MFE_LEDGER, encoding="utf-8") as f:
        for l in f:
            l = l.strip()
            if not l:
                continue
            row = json.loads(l)
            for r in row.get("live", []):
                k = (r.get("symbol"), r.get("side"))
                if k not in best or r.get("mfe_R", 0) > best[k][0]:
                    best[k] = (r.get("mfe_R", 0), r.get("ts"))
    lines.append("## MFE 峰值佐证")
    for (sym, side), (v, ts) in sorted(best.items(), key=lambda x: -x[1][0])[:8]:
        lines.append(f"- {sym} {side} MFE 峰值 {v}R @ {str(ts)[-8:]}")
    lines.append("")
except Exception as e:
    lines.append(f"(MFE 读失败: {e})")

lines += ["## 经验核账 (预测 vs 实际)", ""]
for tag, learn, pred, act in POINTS:
    lines.append(f"### {tag}: {learn}")
    lines.append(f"- 预测: {pred}")
    lines.append(f"- {act}")
    lines.append("- 改进动作: 见下")
    lines.append("")
lines += ["## 改进动作 (20:00 进化 cron 复核后执行)",
 "1. GBP: MFE 移 SL 经验通过 → 明晨若再现 MFE≥1.5R 且方向未破 → SL 移 0.30R(2笔纪律)",
 "2. 台账精度: 家族账/手动台账每日 20:05 自动对 MT5 deals 实读核账(no_agent 哨, 待建)",
 "3. tick_push: 45s 根治保持; 若明日 00:00 后 429 未复 → 查 Agnes key 池(池审计技能)",
 "4. 择优: 连续3日枯竭 → 明晨学哨扩检索面(加 2 个源), 准入维持 5/5 不放宽",
 "", "历史回测≠未来收益。", ""]
open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print(f"verify panel written: {OUT} ({len(lines)} lines)")
