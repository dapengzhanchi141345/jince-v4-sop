#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
liquid_wfo_m15_v3.py —— 以【固定 1ATR 绝对收益】为目标的 M15 深度优化 (黄金优先)
=============================================================================
v2 用相对 R(=以SL距离为1R) 做目标, 会偏好窄 SL 把 R 数值放大 -> 归一化假象
(audit.json 实证: ETHUSD 相对 +41.31R 但绝对 -18.63; 黄金 sl_mult=0.6 在绝对口径下
 反而劣于 1.2)。本版修正: 目标函数与五验一律用 R_abs = (R_rel+cost)*sl_mult - cost,
即"每笔以 1.0ATR 为单位的真实价格收益", 与 SL 宽度无关, 才是真·更赚钱。

复刻引擎逻辑同 v2 (signal_of / H1共振 / PROFIT_SECURE / REAL 1.2ATR封顶 / R:R>=2)。
扩域: ADX_MIN [10..50], sl_mult [0.4..1.2]; 加三窗稳健筛选; 成本 0.05/0.10 双档。
纯研究, 不改 live; 参数变更须 Hermes chief R11 翻闸。
"""
import os, json, time, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import liquid_wfo_m15_v2 as W

OUT = W.OUT
COST = W.COST_R

GRID3 = dict(
    adx_min=[10., 15., 20., 25., 30., 35., 40., 45., 50.],
    break_margin=[0.3, 0.6, 1.0],
    vol_k=[0.5, 0.6, 0.7, 0.9],
    min_body=[0.1, 0.3, 0.5],
    h1_on=[True, False],
    max_hold_h=[12, 18, 24, 30],
    giveback=[0.4, 0.6, 0.8],
    sl_mult=[0.4, 0.5, 0.6, 0.8, 1.0, 1.2],   # REAL 封顶 1.2
    tp_mult=[2.0, 3.0, 4.0, 5.0, 7.0],
)
ORDER = ["adx_min", "sl_mult", "vol_k", "h1_on", "break_margin",
         "min_body", "tp_mult", "giveback", "max_hold_h"]


def ev(P, g, cost=COST):
    k, s = W.gen_signals(P, g)
    R, _, _ = W.simulate(P, g, k, s, cost=cost)
    n = len(R)
    if n == 0:
        return dict(n=0, net=0., avg=0., win=0., R=np.array([]), seg8=0)
    slm = min(g['sl_mult'], W.REAL_SL_CAP)
    Ra = (R + cost) * slm - cost          # 固定 1ATR 分母的绝对收益
    seg = np.array_split(Ra, 8) if n >= 8 else [Ra]
    return dict(n=n, net=float(Ra.sum()), avg=float(Ra.mean()),
                win=float((R > 0).mean()), R=Ra,
                seg8=sum(1 for x in seg if x.sum() > 0))


def score(e, n_req):
    if e['n'] < n_req:
        return -1e9
    # 主目标=绝对每笔收益; 惩罚三窗不平衡(避免单时段独大)
    w = np.array_split(e['R'], 3) if e['n'] >= 3 else [e['R']]*3
    ws = [float(x.sum()) for x in w]
    penalty = 0.0
    if min(ws) < 0:
        penalty += 0.02 * abs(min(ws)) / max(1, e['n'])   # 任一窗为负轻微惩罚
    return e['avg'] - penalty


def coord(P, g0, rounds=3, n_req=100, label=""):
    g = dict(g0); cur = ev(P, g); sc = score(cur, n_req); curve = []
    for rd in range(rounds):
        improved = False
        for key in ORDER:
            bv, bs, be, cv = g[key], sc, cur, []
            for v in GRID3[key]:
                q = dict(g); q[key] = v
                e = ev(P, q); s_ = score(e, n_req)
                cv.append((float(v) if isinstance(v, float) else (1 if v else 0), round(e['avg'], 5)))
                if s_ > bs + 1e-7:
                    bs, bv, be = s_, v, e
            if key == 'adx_min': curve = cv
            if bv != g[key]:
                g[key] = bv; sc, cur = bs, be; improved = True
        if label:
            print("    [%s] r%d 绝对avgR=%.4f n=%d ADX=%s SL=%s" %
                  (label, rd+1, cur['avg'], cur['n'], g['adx_min'], g['sl_mult']), flush=True)
        if not improved: break
    return g, cur, curve


def five(b, o, curve):
    if b['n'] == 0 or o['n'] == 0:
        return dict(T1=0,T2=0,T3=0,T4=0,T5=0,passed=0)
    T1 = (o['avg'] > b['avg']) and (o['net'] > b['net'])
    T2 = o['win'] >= b['win'] - 0.02
    T3 = o['seg8'] >= 6
    T4 = False
    if curve and len(curve) >= 3:
        v = [x[1] for x in curve]; mx = max(v); bi = v.index(mx)
        T4 = (0 < bi < len(v)-1) and min(v[max(0,bi-1):bi+2]) >= mx*0.80
    wb = np.array_split(b['R'], 3) if b['n'] >= 3 else [b['R']]*3
    wo = np.array_split(o['R'], 3) if o['n'] >= 3 else [o['R']]*3
    T5 = all(wo[i].sum() > wb[i].sum() for i in range(3))
    return dict(T1=int(T1),T2=int(T2),T3=int(T3),T4=int(T4),T5=int(T5),
                passed=sum([T1,T2,T3,T4,T5]))


def main():
    live = W.load_live(); res = {}
    t0 = time.time()
    print("=== v3 固定1ATR绝对收益深度优化 (黄金优先) ===", flush=True)
    for sym in W.SYMS:
        p = os.path.join(W.DATA, f"{sym}_M15.csv")
        if not os.path.exists(p): continue
        P = W.prepare(sym)
        if P['n'] < 10000:
            print("  %-8s M15仅%d根 -> 样本不足, 不出候选" % (sym, P['n']), flush=True)
            res[sym] = dict(verdict="INSUFFICIENT_M15", bars=P['n']); continue
        B = dict(W.BASE); B['sl_mult'] = live[sym]['sl']; B['tp_mult'] = live[sym]['tp']
        b = ev(P, B)
        print("  %-8s bars=%d 基线(绝对) n=%d net=%+.2f avg=%+.4f WR=%.1f%%" %
              (sym, P['n'], b['n'], b['net'], b['avg'], b['win']*100), flush=True)
        g, o, curve = coord(P, B, rounds=3 if sym == "XAUUSD" else 2,
                            n_req=120 if sym == "XAUUSD" else 100, label=sym)
        o = ev(P, g)
        st = ev(P, g, cost=W.COST_R_STRESS); bst = ev(P, B, cost=W.COST_R_STRESS)
        ft = five(b, o, curve)
        res[sym] = dict(
            bars=P['n'],
            base=dict(g=B, n=b['n'], net=round(b['net'],2), avg=round(b['avg'],5),
                      win=round(b['win'],4), seg8=b['seg8']),
            opt=dict(g=g, n=o['n'], net=round(o['net'],2), avg=round(o['avg'],5),
                     win=round(o['win'],4), seg8=o['seg8']),
            d_net=round(o['net']-b['net'],2), d_avg=round(o['avg']-b['avg'],5),
            d_trades=o['n']-b['n'], five=ft,
            stress_avg=round(st['avg'],5), stress_pass=int(st['avg'] > bst['avg'] and st['avg'] > 0),
            adx_curve=curve,
            verdict=("VALIDATED" if ft['passed'] == 5 and st['avg'] > bst['avg']
                     else "PARTIAL" if (o['net'] > b['net'] and o['avg'] > b['avg']) else "REJECT"),
        )
        print("    -> n=%d net=%+.2f avg=%+.4f Δnet=%+.2f Δavg=%+.4f 五验=%d/5 %s 压力=%+.4f %s" %
              (o['n'], o['net'], o['avg'], o['net']-b['net'], o['avg']-b['avg'],
               ft['passed'], "".join(str(ft[k]) for k in ("T1","T2","T3","T4","T5")),
               st['avg'], res[sym]['verdict']), flush=True)
    with open(os.path.join(OUT, "results_v3.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print("用时 %.1fs -> results_v3.json" % (time.time()-t0), flush=True)


if __name__ == "__main__":
    main()
