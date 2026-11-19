# -*- coding: utf-8 -*-
"""sl_width_tp_study_20261117.py — SL宽度×TP距离 网格同分母五验 (李彦明11-17令: 止损是不是太小/要能赚钱)
====================================================================
红线: 纯研究. 引擎/REAL 30261104 零动. 产物只落 data/ 与 research/.
复用 rd_verify_batch_20261114.py 引擎复现器(M30+D1 同分母, base=现行参数).
网格: SL ∈ {0.5, 0.8, 1.2}×ATR(摆动锚±0.3ATR 在 base 上) × TP ∈ {1.5R, 2.0R, 3.0R}(封顶12ATR)
      = 9 候选格点 vs base(现行 sl_mult/tp_mult). 每格独立五验+⑥线, 逐品种裁定禁跨品种平均.
北极星: ①TP命中率(ty==1 占比) ②扣0.095R净R ③OOS70/30两段 ④最大单笔R ⑤T5(0.15R压力)仍正.
裁定: APPROVE=6/6 | WATCH=T1-T5>=3且⑥<1 | REJECT=其余. 过线=参数表v3提案(SL/TP格点)走chief R11.
"""
import os, json, sys, datetime as dt
import numpy as np

ROOT = "E:/GoldstrategyEngine"
sys.path.insert(0, os.path.join(ROOT, "research"))
from rd_verify_batch_20261114 import (prepare30, gen_signals, simulate, five_gates,
                                      verdict_of, COST, COST_T5, WINSOR_LO, WINSOR_HI, REAL_SL_CAP, SYMS)

SL_GRID = [0.5, 0.8, 1.2]     # ×ATR(M15口径≈M30 ATR 的 0.58 折算, 此处直接用 M30 ATR 乘数口径, 与 base sl_mult 同分母)
TP_GRID = [1.5, 2.0, 3.0]     # ×R (R=dist)
OUT = os.path.join(ROOT, "data", "rd_verify_batch_sl_width_20261117.json")


def run_cell(P, g, k, s, sig_atr, slm, tpm):
    """同事件集(k,s 同 base), 换 SL/TP 距离重放出场. sig_atr = 信号bar ATR 数组."""
    dist = slm * np.maximum(sig_atr, 1e-9)
    tp_d = np.minimum(tpm * dist, 12.0 * np.maximum(sig_atr, 1e-9))
    res = simulate(P, g, k, s, dist=dist, tp_d=tp_d, cost=COST)
    R, et, ty = res["R"], res["et"], res["ty"]
    n = int(R.size)
    return dict(n=n, net=round(float(R.sum()), 2),
                avg=round(float(R.mean()), 4) if n else 0.0,
                win=round(float((R > 0).mean()), 4) if n else 0.0,
                tp_rate=round(float((ty == 1).mean()), 4) if n else 0.0,
                max_adverse=round(float(R.min()), 2) if n else 0.0), et


def main():
    params = json.load(open(os.path.join(ROOT, "data", "practice_params_all_symbols.json"), encoding="utf-8"))
    prepped = {}
    for s in SYMS:
        try:
            prepped[s] = prepare30(s)
        except Exception as ex:
            print("SKIP", s, ex)
    out = dict(kline_source="mt5_readonly_60137964 tf_cache npz M30+D1 (复用rd_verify_batch_20261114数据窗, XAU/EUR末端11-13/币系11-14)",
               cost=0.095, cost_t5=0.15, sl_grid=SL_GRID, tp_grid=TP_GRID,
               generated=dt.datetime.now().strftime("%Y-%m-%d %H:%M"), cells={})
    print(f"{'sym':8s} {'base':>14s} " + " ".join(f"{slm}x{tpm}"[:7] for slm in SL_GRID for tpm in TP_GRID))
    best = {}
    for s in prepped:
        P = prepped[s]
        p = params.get(s, {})
        g = dict(adx_min=float(p.get("adx_min", 35.0)), break_margin=0.6, min_body=0.3,
                 h1_on=False, max_hold_h=18, giveback=0.6,
                 sl_mult=float(p.get("sl_mult", 1.0)), tp_mult=float(p.get("tp_mult", 3.0)))
        k, sgn, dist0, tp0 = gen_signals(P, g)
        if k.size == 0:
            out["cells"][s] = dict(base=None, grid={}, note="无信号")
            print(f"{s:8s} 无信号, 跳过")
            continue
        oos_cut = float(np.quantile(P["t"], 0.70))
        sig_atr = np.maximum(P["atr"][k], 1e-9)
        base, _ = run_cell(P, g, k, sgn, sig_atr, g["sl_mult"], g["tp_mult"])
        out["cells"][s] = dict(base=base, grid={})
        row = [f"n{base['n']} {base['net']:+7.1f}tp{base['tp_rate']:.2f}"]
        for slm in SL_GRID:
            for tpm in TP_GRID:
                m, et = run_cell(P, g, k, sgn, sig_atr, slm, tpm)
                sig_dist = slm * sig_atr
                m015_res = simulate(P, g, k, sgn, dist=sig_dist,
                                    tp_d=np.minimum(tpm * sig_dist, 12 * sig_atr), cost=COST_T5)
                m015 = dict(net=round(float(m015_res["R"].sum()), 2))
                mask_tr = et <= oos_cut
                tr = m015_res["R"][mask_tr]; te = m015_res["R"][~mask_tr]
                cand = dict(net=m["net"], avg=m["avg"], win=m["win"], n=m["n"], R=m015_res["R"])
                cand015 = dict(net=m015["net"])
                trd = dict(net=float(tr.sum()), avg=float(tr.mean()) if tr.size else 0.0)
                ted = dict(net=float(te.sum()), avg=float(te.mean()) if te.size else 0.0)
                gates = five_gates(base, cand, cand015, trd, ted)
                verd = verdict_of(gates, base, cand)
                key = f"SL{slm}_TP{tpm}R"
                out["cells"][s]["grid"][key] = dict(m, net_015=m015["net"], oos_pos=trd["net"] > 0 and ted["net"] > 0,
                                                     five_gate=gates["passed"], verdict=verd)
                star = "★" if verd == "APPROVE" else (" " if verd == "WATCH" else " ")
                row.append(f"{key}{star} n{m['n']}{m['net']:+7.1f}tp{m['tp_rate']:.2f}")
                if verd == "APPROVE" and s not in best:
                    best[s] = key
        print(f"{s:8s} " + " ".join(row[:1]) + " | " + "  ".join(row[1:]))
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n产物:", OUT)
    print("APPROVE 格点:", best if best else "无(0翻闸, WATCH攒样口径)")
    print("声明: 历史回测≠未来收益; 未过⑥线一律WATCH前向攒样, 0放大.")


if __name__ == "__main__":
    main()
