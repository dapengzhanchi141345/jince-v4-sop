# -*- coding: utf-8 -*-
"""sl_spec_v2_20261117.py — 止损规格v2 确定性五验 (李彦明11-17令'教材止损全面深度优化')
====================================================================
教材原文层(E:\\李彦明\\学习资料\\机构订单\\extracted\\, 11-17 17:5x 全读止损原文):
  Brooks区间/趋势: ①保护性止损=信号棒1跳动(结构锚) ②紧凑通道内"不应过早把止损移至盈亏平衡"
  (L9106/L9714) ③反转交易坚持初始止损不提前离场 ④宽止损+小仓位=风险恒定
  Seiden: ⑤3:1利润阈值后 保护止损调至盈亏平衡(L4047) ⑥保护性止损尽可能小(L5307, 前提=结构位进场+仓位配损)
失败史(6案): 11-06窄损点差碾 / 11-15区外远损扫损爆表 / 11-17 GBP 3.7pip被扫 /
  B0早退giveback0.6秒退 / 11-12亏损单验尸挂账 / 11-15 v1表符号反作废
测试: 同事件集同SL/TP距离(gen_signals base 输出固定), 只动 离场层:
  base gb0.6 | gb1.5 | regime_gb(ADX≥40→gb9.9不提早退, <40→gb1.5紧凑锁) | be3r(3R后锁BE) | regime_gb+be3r
每格五验+⑥线+OOS70/30 同分母. 纯研究, 引擎/REAL 零动; 产物 data/rd_verify_batch_sl_spec_v2_20261117.json
"""
import os, json, sys, datetime as dt
import numpy as np

ROOT = "E:/GoldstrategyEngine"
sys.path.insert(0, os.path.join(ROOT, "research"))
from rd_verify_batch_20261114 import (prepare30, gen_signals, simulate, five_gates,
                                      verdict_of, COST, COST_T5, SYMS)
from rd_verify_batch_20261114 import REAL_SL_CAP, WINSOR_LO, WINSOR_HI

OUT = os.path.join(ROOT, "data", "rd_verify_batch_sl_spec_v2_20261117.json")
MAJOR = ["XAUUSD", "EURUSD", "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]


def simulate_sl2(P, g, k, s, dist, tp_d, cost, mode="base"):
    """simulate() 的加法扩展: 离场层变体 (gb_arr 逐单 giveback + be3r 锁BE), 其余逻辑同原件."""
    N = P["n"]
    e = k + 1
    ok = e < N
    k, s, e = k[ok], s[ok], e[ok]
    dist = dist[ok]
    tp_d = tp_d[ok]
    nC = len(k)
    if nC == 0:
        return dict(R=np.array([]), et=np.array([]))
    Lmax = int(g["max_hold_h"] / 0.5)
    idx = e[:, None] + np.arange(Lmax)[None, :]
    beyond = idx >= N
    ic = np.minimum(idx, N - 1)
    Hs = P["h"][ic] * s[:, None]
    Ls = P["l"][ic] * s[:, None]
    HI = np.maximum(Hs, Ls)
    LO = np.minimum(Hs, Ls)
    Cs = P["c"][ic] * s[:, None]
    A = P["atr"][ic]
    HI = np.where(beyond, -np.inf, HI)
    LO = np.where(beyond, -np.inf, LO)
    entry = P["o"][e] * s
    SL0 = entry - dist
    TP = entry + tp_d
    R = np.zeros(nC)
    ext = entry.copy()
    SL = SL0.copy()
    alive = np.ones(nC, dtype=bool)
    exit_t = np.full(nC, P["t"][np.minimum(e + Lmax - 1, N - 1)])
    # 逐单 giveback (入场ADX条件)
    dx_e = P["dx"][k]
    if mode in ("regime_gb", "regime_gb_be3r"):
        gb_arr = np.where(dx_e >= 40, 9.9, 1.5)
    else:
        gb_arr = np.full(nC, g.get("giveback", 0.6))
    be3r = mode in ("be3r", "regime_gb_be3r")
    for kk in range(Lmax):
        if not alive.any():
            break
        hi, lo, cc, aa = HI[:, kk], LO[:, kk], Cs[:, kk], A[:, kk]
        hit_sl = alive & (lo <= SL)
        hit_tp = alive & (~hit_sl) & (hi >= TP)
        if hit_sl.any():
            px = np.minimum(SL, hi)
            R[hit_sl] = (px[hit_sl] - entry[hit_sl]) / dist[hit_sl] - cost
            exit_t[hit_sl] = P["t"][ic[hit_sl, kk]]
            alive[hit_sl] = False
        if hit_tp.any():
            R[hit_tp] = (TP[hit_tp] - entry[hit_tp]) / dist[hit_tp] - cost
            exit_t[hit_tp] = P["t"][ic[hit_tp, kk]]
            alive[hit_tp] = False
        bend = alive & beyond[:, kk]
        if bend.any():
            R[bend] = (cc[bend] - entry[bend]) / dist[bend] - cost
            exit_t[bend] = P["t"][ic[bend, kk]]
            alive[bend] = False
        ext = np.where(alive, np.maximum(ext, hi), ext)
        r = (ext - entry) / dist
        cand = np.full(nC, -np.inf)
        cand = np.where(r >= 0.5, entry + 0.2 * dist, cand)
        cand = np.where(r >= 1.0, np.maximum(cand, entry + 1.2 * dist), cand)
        trm = np.where(r >= 1.0, np.where(r >= 1.5, 0.5, 0.8), np.nan)
        trail = ext - trm * np.maximum(aa, P["atr"][k] * 0.5)
        cand = np.where(np.isfinite(trail), np.maximum(cand, trail), cand)
        gf = ext - gb_arr * dist
        cand = np.where(r > 0, np.maximum(cand, gf), cand)
        if be3r:
            cand = np.where(r >= 3.0, np.maximum(cand, entry), cand)
        SL = np.where(alive & np.isfinite(cand), np.maximum(SL, cand), SL)
    if alive.any():
        last = Cs[:, -1]
        R[alive] = (last[alive] - entry[alive]) / dist[alive] - cost
        exit_t[alive] = P["t"][ic[alive, -1]]
    R = np.clip(np.where(np.isfinite(R), R, 0.0), WINSOR_LO, WINSOR_HI)
    exit_bar = np.minimum(e + Lmax - 1, N - 1)
    order = np.argsort(k)
    taken = []
    nb = -1
    for i in order:
        if k[i] >= nb:
            taken.append(i)
            nb = exit_bar[i]
    taken = np.array(taken, dtype=np.int64)
    return dict(R=R[taken], et=exit_t[taken])


MODES = ["gb15", "regime_gb", "be3r", "regime_gb_be3r"]


def main():
    params = json.load(open(os.path.join(ROOT, "data", "practice_params_all_symbols.json"), encoding="utf-8"))
    out = dict(desc="止损规格v2五验: 同事件集同SL/TP, 离场层4变体(regime条件giveback+3:1锁BE)",
               base_giveback=0.6, modes=MODES, cost=0.095, cost_t5=0.15,
               generated=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
               basis="教材原文: Brooks紧凑通道不早移BE(L9106/9714)+Seiden 3:1->BE(L4047)",
               cells={})
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
        base_res = simulate_sl2(P, g, k, sgn, dist0, tp0, COST, "base")
        base = dict(net=float(base_res["R"].sum()), avg=float(base_res["R"].mean()),
                    win=float((base_res["R"] > 0).mean()), n=int(base_res["R"].size), R=base_res["R"])
        base_res15 = simulate_sl2(P, g, k, sgn, dist0, tp0, COST_T5, "base")
        oos_cut = float(np.quantile(P["t"][k], 0.70))
        etb = base_res["et"]
        mtr = etb <= oos_cut
        trd = dict(net=float(base_res15["R"][mtr].sum()), avg=float(base_res15["R"][mtr].mean()) if mtr.any() else 0.0)
        ted = dict(net=float(base_res15["R"][~mtr].sum()), avg=float(base_res15["R"][~mtr].mean()) if (~mtr).any() else 0.0)
        out["cells"][s] = dict(base={kk: vv for kk, vv in base.items() if kk != "R"}, grid={})
        print(f"{s:8s} base gb0.6: n{base['n']} {base['net']:+8.1f} win{base['win']:.2f}")
        for md in MODES:
            r = simulate_sl2(P, g, k, sgn, dist0, tp0, COST, md)
            r15 = simulate_sl2(P, g, k, sgn, dist0, tp0, COST_T5, md)
            cand = dict(net=float(r["R"].sum()), avg=float(r["R"].mean()), win=float((r["R"] > 0).mean()), R=r["R"], n=int(r["R"].size))
            et = r["et"]
            mt2 = et <= oos_cut
            trd_c = dict(net=float(r15["R"][mt2].sum()), avg=float(r15["R"][mt2].mean()) if mt2.any() else 0.0)
            ted_c = dict(net=float(r15["R"][~mt2].sum()), avg=float(r15["R"][~mt2].mean()) if (~mt2).any() else 0.0)
            gates = five_gates(base, cand, dict(net=float(r15["R"].sum())), trd_c, ted_c)
            verd = verdict_of(gates, base, cand)
            out["cells"][s]["grid"][md] = dict(net=cand["net"], win=cand["win"],
                                                delta=round(cand["net"] - base["net"], 1),
                                                oos_pos=bool(trd_c["net"] > 0 and ted_c["net"] > 0),
                                                five_gate=gates["passed"], verdict=verd, detail=gates)
            print(f"   {md:16s} {cand['net']:+8.1f} (Δ{cand['net']-base['net']:+7.1f}) "
                  f"oos+={trd_c['net']>0 and ted_c['net']>0} gates{gates['passed']}/6 -> {verd}")
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n产物:", OUT)
    print("裁定口径: 6/6=可接线离场层 | 3-5/6=WATCH前向攒样 | <3/6=REJECT不动")


if __name__ == "__main__":
    main()
