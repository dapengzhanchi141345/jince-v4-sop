# -*- coding: utf-8 -*-
"""all_symbols_deep_opt_20261117.py — 全品种 SL×TP 深度优化(李彦明11-17令'所有品种深度优化一下再说')
====================================================================
全 M30 可回测品种(11: BNB/BTC/ETH/EUR/GBP/KSM/LTC/SOL/US30/XAU/XRP) 同分母五验:
  事件集=gen_signals base(现行参数), 只换 SL/TP 距离; 数据=tf_cache 全量刷新后(数据官 0 陈旧)
网格: SL∈{0.5,0.8,1.2,2.0}×ATR (2.0=李令'亏损放大先别扫损'宽SL口径) × TP∈{1.5,2.0,3.0}R = 12格/品种
每格五验+⑥线+OOS70/30; 逐品种裁定, 禁跨品种平均. 纯研究, 引擎/REAL 零动.
产物: data/rd_verify_batch_all_sym_deep_20261117.json
"""
import os, json, sys, datetime as dt
import numpy as np

ROOT = "E:/GoldstrategyEngine"
sys.path.insert(0, os.path.join(ROOT, "research"))
from rd_verify_batch_20261114 import (prepare30, gen_signals, simulate, five_gates,
                                      verdict_of, COST, COST_T5)

ALL = ["BNBUSD", "BTCUSD", "ETHUSD", "EURUSD", "GBPUSD", "KSMUSD", "LTCUSD", "SOLUSD", "US30", "XAUUSD", "XRPUSD"]
SL_GRID = [0.5, 0.8, 1.2, 2.0]
TP_GRID = [1.5, 2.0, 3.0]
OUT = os.path.join(ROOT, "data", "rd_verify_batch_all_sym_deep_20261117.json")


def run_cell(P, g, k, s, sig_atr, slm, tpm):
    dist = slm * np.maximum(sig_atr, 1e-9)
    tp_d = np.minimum(tpm * dist, 12.0 * np.maximum(sig_atr, 1e-9))
    res = simulate(P, g, k, s, dist=dist, tp_d=tp_d, cost=COST)
    R, ty = res["R"], res["ty"]
    n = int(R.size)
    return dict(n=n, net=round(float(R.sum()), 2),
                avg=round(float(R.mean()), 4) if n else 0.0,
                win=round(float((R > 0).mean()), 4) if n else 0.0,
                tp_rate=round(float((ty == 1).mean()), 4) if n else 0.0), res["et"], res


def main():
    params = json.load(open(os.path.join(ROOT, "data", "practice_params_all_symbols.json"), encoding="utf-8"))
    out = dict(desc="全品种深度优化: 11品种×SL{0.5,0.8,1.2,2.0}×TP{1.5,2,3} 同分母五验 (数据官刷新后)",
               sl_grid=SL_GRID, tp_grid=TP_GRID, cost=0.095,
               generated=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
               note="2.0SL格=李令'亏损放大先别扫损'口径; 裁定: 6/6=APPROVE可翻闸 | 3-5=WATCH前向攒样 | <3=REJECT",
               cells={})
    summary = {}
    for s in ALL:
        try:
            P = prepare30(s)
        except Exception as ex:
            out["cells"][s] = dict(note=f"prepare fail {ex}")
            print(f"{s:8s} SKIP {str(ex)[:40]}")
            continue
        p = params.get(s, {})
        g = dict(adx_min=float(p.get("adx_min", 35.0)), break_margin=0.6, min_body=0.3,
                 h1_on=False, max_hold_h=18, giveback=0.6,
                 sl_mult=float(p.get("sl_mult", 1.0)), tp_mult=float(p.get("tp_mult", 3.0)))
        k, sgn, dist0, tp0 = gen_signals(P, g)
        if k.size == 0:
            out["cells"][s] = dict(note="无信号")
            print(f"{s:8s} 无信号")
            continue
        oos_cut = float(np.quantile(P["t"], 0.70))
        sig_atr = np.maximum(P["atr"][k], 1e-9)
        base, etb, _ = run_cell(P, g, k, sgn, sig_atr, g["sl_mult"], g["tp_mult"])
        base_full = dict(base, R=None)
        out["cells"][s] = dict(base=base, base_sl=g["sl_mult"], base_tp=g["tp_mult"], grid={})
        bres = simulate(P, g, k, sgn, cost=COST_T5, dist=dist0, tp_d=tp0) if False else None
        best = None
        print(f"{s:8s} base(SL{g['sl_mult']}/TP{g['tp_mult']}): n{base['n']} {base['net']:+8.1f} win{base['win']:.2f} tp_hit{base['tp_rate']:.2f}")
        for slm in SL_GRID:
            for tpm in TP_GRID:
                m, et, _ = run_cell(P, g, k, sgn, sig_atr, slm, tpm)
                sig_dist = slm * sig_atr
                r15 = simulate(P, g, k, sgn, dist=sig_dist, tp_d=np.minimum(tpm * sig_dist, 12 * sig_atr), cost=COST_T5)
                m015_net = float(r15["R"].sum())
                mtr = et <= oos_cut
                tr = r15["R"][mtr]; te = r15["R"][~mtr]
                cand = dict(net=m["net"], avg=m["avg"], win=m["win"], n=m["n"], R=r15["R"])
                cand015 = dict(net=m015_net)
                trd = dict(net=float(tr.sum()), avg=float(tr.mean()) if tr.size else 0.0)
                ted = dict(net=float(te.sum()), avg=float(te.mean()) if te.size else 0.0)
                base5 = dict(net=base["net"], avg=base["avg"], win=base["win"], n=base["n"], R=None)
                gates = five_gates({kk: vv for kk, vv in base.items()}, cand, cand015, trd, ted)
                verd = verdict_of(gates, base, cand)
                key = f"SL{slm}_TP{tpm}R"
                out["cells"][s]["grid"][key] = dict(net=m["net"], win=m["win"], tp_rate=m["tp_rate"],
                                                     delta=round(m["net"] - base["net"], 1),
                                                     oos_pos=bool(trd["net"] > 0 and ted["net"] > 0),
                                                     five_gate=gates["passed"], verdict=verd,
                                                     n=m["n"], sl=slm, tp=tpm)
                if verd == "APPROVE" and (best is None or gates["passed"] > best[1]):
                    best = (key, gates["passed"])
                elif verd == "WATCH" and best is None:
                    best = (key, gates["passed"])
        out["cells"][s]["best"] = best
        summary[s] = best
        print(f"   -> 最优格: {best[0] if best else '无(全REJECT)'} ({best[1] if best else 0}/6)")
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n产物:", OUT)
    print("全品种最优格:", json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
