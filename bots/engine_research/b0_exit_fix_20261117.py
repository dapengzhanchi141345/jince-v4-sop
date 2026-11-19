# -*- coding: utf-8 -*-
"""b0_exit_fix_20261117.py — B0早退病 确定性五验 (李彦明11-17令'全面深度优化', 池堵自跑0-LLM)
====================================================================
背景: 30d验尸 B0_INVALID 52笔 0胜 -70.09 = 最大亏损源; 机制=进场后浮盈回撤即秒退,
      结构没走出来就被扫. 复现器里的 B0 等价物 = ratchet 早退 (giveback×dist 回撤锁SL).
测试: 同事件集同SL/TP距离(dist/tp_d 固定=gen_signals 输出), 只动 giveback 离场宽容度:
      base=0.6 | 1.0 | 1.5 | off(ratchet基本不触发, 纯SL/TP/18h). 每格独立五验+⑥线+OOS70/30.
红线: 纯研究, 引擎/REAL 零动; 产物 data/rd_verify_batch_b0exit_20261117.json.
"""
import os, json, sys, datetime as dt
import numpy as np

ROOT = "E:/GoldstrategyEngine"
sys.path.insert(0, os.path.join(ROOT, "research"))
from rd_verify_batch_20261114 import (prepare30, gen_signals, simulate, five_gates,
                                      verdict_of, COST, COST_T5, SYMS)

GB_GRID = [1.0, 1.5, 9.9]   # 0.6=base; 9.9≈ratchet关(回撤9.9R内不锁)
OUT = os.path.join(ROOT, "data", "rd_verify_batch_b0exit_20261117.json")
MAJOR = ["XAUUSD", "EURUSD", "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]


def main():
    params = json.load(open(os.path.join(ROOT, "data", "practice_params_all_symbols.json"), encoding="utf-8"))
    out = dict(desc="B0早退病给回(giveback)宽容度五验: 同事件集同SL/TP距离, 只动离场ratchet",
               base_giveback=0.6, grid=GB_GRID, cost=0.095, cost_t5=0.15,
               generated=dt.datetime.now().strftime("%Y-%m-%d %H:%M"), cells={})
    for s in MAJOR:
        try:
            P = prepare30(s)
        except Exception as ex:
            out["cells"][s] = dict(note=f"prepare fail {ex}")
            continue
        p = params.get(s, {})
        g = dict(adx_min=float(p.get("adx_min", 35.0)), break_margin=0.6, min_body=0.3,
                 h1_on=False, max_hold_h=18, giveback=0.6,
                 sl_mult=float(p.get("sl_mult", 1.0)), tp_mult=float(p.get("tp_mult", 3.0)))
        k, sgn, dist0, tp0 = gen_signals(P, g)
        if k.size == 0:
            out["cells"][s] = dict(note="无信号")
            continue
        base_res = simulate(P, g, k, sgn, dist=dist0, tp_d=tp0, cost=COST)
        base = dict(net=float(base_res["R"].sum()), avg=float(base_res["R"].mean()),
                    win=float((base_res["R"] > 0).mean()), n=int(base_res["R"].size), R=base_res["R"])
        base_res15 = simulate(P, g, k, sgn, dist=dist0, tp_d=tp0, cost=COST_T5)
        oos_cut = float(np.quantile(P["t"][k], 0.70))
        etb = base_res["et"]
        mask_tr = etb <= oos_cut
        trd = dict(net=float(base_res15["R"][mask_tr].sum()), avg=float(base_res15["R"][mask_tr].mean()) if mask_tr.any() else 0.0)
        ted = dict(net=float(base_res15["R"][~mask_tr].sum()), avg=float(base_res15["R"][~mask_tr].mean()) if (~mask_tr).any() else 0.0)
        out["cells"][s] = dict(base={kk: vv for kk, vv in base.items() if kk != "R"}, grid={})
        print(f"{s:8s} base gb0.6: n{base['n']} {base['net']:+8.1f} win{base['win']:.2f}")
        for gv in GB_GRID:
            g2 = dict(g, giveback=gv)
            r = simulate(P, g2, k, sgn, dist=dist0, tp_d=tp0, cost=COST)
            r15 = simulate(P, g2, k, sgn, dist=dist0, tp_d=tp0, cost=COST_T5)
            cand = dict(net=float(r["R"].sum()), avg=float(r["R"].mean()), win=float((r["R"] > 0).mean()), R=r["R"], n=int(r["R"].size))
            cand015 = dict(net=float(r15["R"].sum()))
            et = r["et"]
            mtr = et <= oos_cut
            trd_c = dict(net=float(r15["R"][mtr].sum()), avg=float(r15["R"][mtr].mean()) if mtr.any() else 0.0)
            ted_c = dict(net=float(r15["R"][~mtr].sum()), avg=float(r15["R"][~mtr].mean()) if (~mtr).any() else 0.0)
            gates = five_gates(base, cand, cand015, trd_c, ted_c)
            verd = verdict_of(gates, base, cand)
            key = f"gb{gv}"
            out["cells"][s]["grid"][key] = dict(net=cand["net"], win=cand["win"],
                                                delta=round(cand["net"] - base["net"], 1),
                                                oos_pos=trd_c["net"] > 0 and ted_c["net"] > 0,
                                                five_gate=gates["passed"], verdict=verd,
                                                detail=gates)
            print(f"   {key:8s} {cand['net']:+8.1f} (Δ{cand['net']-base['net']:+7.1f}) oos+{trd_c['net']>0 and ted_c['net']>0} "
                  f"gates{gates['passed']}/6 -> {verd}")
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n产物:", OUT)
    print("裁定口径: 过6/6=参数表v3可翻闸 | 3-5/6=WATCH前向攒样 | <3/6=REJECT不动; 0放大")


if __name__ == "__main__":
    main()
