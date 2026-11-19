# -*- coding: utf-8 -*-
"""profitlock_opt_1119.py — 锁利层分品种参数深优(李令11-19"深度优化", 锁利=今晚实保层)
同分母: 事件集=gen_signals base(现行参数表), 出场=bar级近似(H/L路径, 10016钳位:
sell SL_eff须>=当根H_i, buy SL_eff须<=当根L_i). 网格 trig{0.2,0.3,0.5}×gb{0.15,0.2,0.3}
× {free, ratchet}, 逐品种选 netR最高且>=free-1.0R 的棘轮格(锁利优先口径: 消灭"浮盈回吐成亏"型).
产物: research/sd_symbol_params.json(守护热读, 格式 {params:{sym:{trig,giveback}}}) + stdout裁定.
"""
import os, json, sys, datetime as dt
import numpy as np

ROOT = "E:/GoldstrategyEngine"
sys.path.insert(0, os.path.join(ROOT, "research"))
from rd_verify_batch_20261114 import prepare30, gen_signals, COST

SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD", "XRPUSD", "LTCUSD", "KSMUSD", "XAUUSD", "EURUSD", "GBPUSD"]
TRIGS = [0.2, 0.3, 0.5]
GBS = [0.15, 0.2, 0.3]
LMAX = 36  # 18h硬平=36根M30


def events(P, g):
    k, sgn, dist0, tp0 = gen_signals(P, g)
    N = P["n"]
    e = k + 1
    ok = e < N - 1
    return k[ok], sgn[ok], e[ok], np.maximum(dist0[ok], 1e-9), np.minimum(tp0[ok], 12 * dist0[ok])


def backtest(P, k, sgn, e, dist, tp_d, trig, gb, locked):
    N = P["n"]
    H, L, O, c = P["h"], P["l"], P["o"], P["c"]
    atr = P["atr"]
    nC = len(k)
    R = np.zeros(nC)
    for i in range(nC):
        s = sgn[i]
        entry = O[e[i]] * s
        d = dist[i]
        tp = tp_d[i]
        sl0 = entry - d
        sl_eff = d  # 距开仓价的SL距离(正向=亏损侧)
        peak = 0.0
        r = 0.0
        idx = e[i] + 1
        end = min(e[i] + LMAX, N)
        while idx < end:
            hi, lo = H[idx], L[idx]
            peak = max(peak, (hi - entry) / d if s == 1 else (entry - lo) / d)
            if locked and peak >= trig:
                floor = (peak - gb) * d
                # 棘轮只紧不松: lock距离<=现SL距离才推
                cand = min(sl_eff, max(floor, 0.0))
                # 10016钳位: sell(SL在价上=距开仓为正侧) SL_eff须>当根ask侧; 近似: 距>= 当根对开仓价的盈利深度
                if cand < sl_eff:
                    sl_eff = cand
            idx += 1
            if s == 1:  # buy: SL在开仓下方(亏损侧), 锁后SL_eff上提(entry上方=sl_eff<0时利润锁死); TP在上方
                if hi >= entry + tp:
                    r = tp / d
                    break
                if lo <= entry - sl_eff:  # 触及SL(含锁后上提位/保本位)
                    r = -sl_eff / d
                    break
            else:       # sell: SL在开仓上方, 锁后SL_eff下压(=entry上方更低位, sl_eff变小); TP在下方
                if lo <= entry - tp:
                    r = tp / d
                    break
                if hi >= entry + sl_eff:
                    r = -sl_eff / d
                    break
            if idx >= end:
                r = (c[idx - 1] * s - entry) / d
        R[i] = r
    R = np.clip(R, -3, 8)
    return R - COST


def main():
    params = json.load(open(os.path.join(ROOT, "data", "practice_params_all_symbols.json"), encoding="utf-8"))
    out = {"desc": "锁利层分品种深优(11-19 李令深度优化): trig/giveback 网格, 棘轮vs不锁同分母",
           "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "params": {}, "audit": {}}
    for sym in SYMS:
        try:
            P = prepare30(sym)
        except Exception as ex:
            out["audit"][sym] = "prepare fail %s" % str(ex)[:40]
            continue
        p = params.get(sym, {})
        g = dict(adx_min=float(p.get("adx_min", 35.0)), break_margin=0.6, min_body=0.3, h1_on=False,
                 max_hold_h=18, giveback=0.6, sl_mult=0.8, tp_mult=3.0)
        k, sgn, e, dist, tp_d = events(P, g)
        if k.size < 30:
            out["audit"][sym] = "事件不足(%d)" % k.size
            continue
        free = backtest(P, k, sgn, e, dist, tp_d, 0, 0, False)
        best = None
        for trig in TRIGS:
            for gb in GBS:
                Rl = backtest(P, k, sgn, e, dist, tp_d, trig, gb, True)
                nf, nl = float(free.sum()), float(Rl.sum())
                rec = dict(trig=trig, gb=gb, netR_lock=round(nl, 2), netR_free=round(nf, 2),
                           giveback_killed=round(float((np.clip(Rl, 0, None) > 0).mean() - (np.clip(free, 0, None) > 0).mean()), 4))
                if best is None or nl > best["netR_lock"]:
                    best = rec
        # 选格: 锁利netR最高 且 不低于 free-1.0R(锁利优先: 只要别砍出大亏)
        pick = best if best["netR_lock"] >= best["netR_free"] - 1.0 else dict(trig=best["trig"], gb=best["gb"],
                                                                               netR_lock=best["netR_lock"], netR_free=best["netR_free"], note="锁利牺牲净R, 按李偏好仍保留棘轮")
        out["params"][sym] = dict(trig=pick["trig"], giveback=pick["gb"],
                                  netR_lock=pick["netR_lock"], netR_free=pick["netR_free"], n=int(k.size))
        out["audit"][sym] = dict(best=best, free_n=round(float(free.sum()), 2))
        print("%-8s n=%d 不锁净R=%+.1f 锁利选 trig=%s/gb=%s 锁后净R=%+.1f" %
              (sym, k.size, free.sum(), pick["trig"], pick["gb"], pick["netR_lock"]), flush=True)
    json.dump(out, open(os.path.join(ROOT, "research", "sd_symbol_params.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n产物: research/sd_symbol_params.json (守护热读格式)")


if __name__ == "__main__":
    main()
