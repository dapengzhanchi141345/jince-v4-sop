# -*- coding: utf-8 -*-
"""金策 L5 · 追踪器 payoff 数据源劈叉修复 (确定性, 0 改实盘/verdict)
[2026-10-14] @risk-officer L4 点名: 追踪器 payoff=None vs edge_tracker 实拉 EURJPY pf=2.203.
修复: 从 edge_tracker.json (我 L5 单一数据源) 把每腿 pf 真值 + oos_reached_30 计算值
同步进 training_graduation_tracker, 让"出徒四件齐的 payoff 件"读实数不读空字段.
红线: 0 改 oos_now / 0 改 verdict / 0 碰实盘; 只补 payoff + oos_reached_30 两字段.
"""
import json, os, time

D = r"E:\GoldstrategyEngine\data"
TP = os.path.join(D, "training_graduation_tracker.json")
EP = os.path.join(D, "edge_tracker.json")

PAYOFF_GATE = 2.0  # 出徒四件齐 payoff>=2 线


def main():
    tr = json.load(open(TP, encoding="utf-8"))
    try:
        et = json.load(open(EP, encoding="utf-8")).get("symbols", {})
    except Exception:
        et = {}
    now_ts = int(time.time())
    filled = []
    for leg in tr.get("legs", []):
        nm = leg.get("leg", "")
        src = et.get(nm)
        oos_now = leg.get("oos_now", 0)
        oos_target = leg.get("oos_target", 30)
        # payoff 真值: edge_tracker pf (数据源单一真相), 无样本源 -> None(数据不可靠)
        leg["payoff"] = (src or {}).get("pf")
        leg["payoff_src"] = "edge_tracker.symbols.%s.pf" % nm if src else "NO_SAMPLE_SOURCE"
        # oos_reached_30 计算值: 我算, 不靠 L4 假判据
        leg["oos_reached_30"] = bool(oos_now >= oos_target)
        # 四件齐实判: OOS30 ∧ payoff过线 (SL/L4 件仍由各自域判, 我只补数据件)
        payoff_ok = leg["payoff"] is not None and leg["payoff"] >= PAYOFF_GATE
        leg["four_gate_data"] = {
            "oos_30": leg["oos_reached_30"],
            "payoff_ge_2": payoff_ok,
            "note": "数据件自判; SL件/L4件由风控域判, 本脚本 0 越界"
        }
        filled.append("%s pf=%s oos_reached=%s payoff_ge2=%s" %
                      (nm, leg["payoff"], leg["oos_reached_30"], payoff_ok))
    tr["payoff_sync"] = {"ts": now_ts, "by": "strategy-rd L5",
                         "source": "edge_tracker.json (L5 单一数据源)",
                         "fix": "补齐 payoff + oos_reached_30, 修 @risk-officer 点名的数据源劈叉 (payoff=None 假判据)"}
    tr["updated_ts"] = now_ts
    tr["updated_by"] = "strategy-rd L5 payoff_sync"
    json.dump(tr, open(TP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("payoff_sync OK (%d 腿):" % len(filled))
    for f in filled:
        print("  " + f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
