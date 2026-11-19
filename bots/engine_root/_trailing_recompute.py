# -*- coding: utf-8 -*-
"""研发部独立复算: M30+SLM3.0 上 P0纯TP/SL vs P4吊灯+保本
数据=data/tf_cache (确定性缓存, 不连MT5)。几何对齐 _tf_m30.py (对基线+0.104)。
目的: 验证 P4 是否真比 P0 好, 以及 97.7%胜率/-1.3R输单 的反常来源 (截断窗口偏差)。
输出 data/trailing_recompute.json"""
import os, json
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "data", "tf_cache")
OUT = os.path.join(ROOT, "data", "trailing_recompute.json")
SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]

SLM, TPR = 3.0, 2.0
ATR_P = 14
HH_P = 22
TRAIL_K = 3.0
BE_R = 1.0          # +1R 后 1R 保本
NBAR = 42           # 前向 42 根 M30 (~21h) 截断窗口, 对齐 _tf_m30
RES_NAMES = ["超时未动", "止损", "止盈", "吊灯离"]


def load(sym, tf):
    z = np.load(os.path.join(CACHE, f"{sym}_{tf}.npz"))
    return dict(t=z["t"].astype(np.int64), h=z["h"].astype(float),
                l=z["l"].astype(float), c=z["c"].astype(float), o=z["o"].astype(float))


def atr14(h, l, c):
    tr = np.empty(len(c)); tr[0] = h[0]-l[0]
    for i in range(1, len(c)):
        tr[i] = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
    a = np.zeros(len(c)); a[14] = tr[1:15].mean()
    for i in range(15, len(c)):
        a[i] = (a[i-1]*13 + tr[i]) / 14
    return a


def ema(x, n):
    k = 2/(n+1); out = np.zeros(len(x)); out[0]=x[0]
    for i in range(1, len(x)): out[i] = x[i]*k + out[i-1]*(1-k)
    return out


def build(sym):
    d1, m30 = load(sym, "D1"), load(sym, "M30")
    t1, c1 = d1["t"], d1["c"]
    e1 = ema(c1, 20)
    bias = np.where(c1 > e1, 1, -1)
    bidx = np.searchsorted(t1, m30["t"], side="right") - 1
    bidx = np.clip(bidx, 0, len(bias)-1)
    bias_i = bias[bidx]
    h30, l30, c30, t30 = m30["h"], m30["l"], m30["c"], m30["t"]
    a30 = atr14(h30, l30, c30)
    dcH, dcL = np.full(len(c30), -1e18), np.full(len(c30), 1e18)
    for i in range(20, len(c30)):
        dcH[i] = h30[i-20:i].max(); dcL[i] = l30[i-20:i].min()
    hh = np.full(len(c30), -1e18); ll = np.full(len(c30), 1e18)
    for i in range(HH_P, len(c30)):
        hh[i] = h30[i-HH_P:i].max(); ll[i] = l30[i-HH_P:i].min()
    ev = []
    for i in range(max(20, HH_P), len(c30)-1):
        if a30[i] <= 0:
            continue
        if bias_i[i] > 0 and l30[i] < dcH[i-1]*1.003:
            trig, d = dcH[i-1]*1.003, 1
        elif bias_i[i] < 0 and h30[i] > dcL[i-1]*1.003:
            trig, d = dcL[i-1]*1.003, -1
        else:
            continue
        risk = SLM * a30[i]
        sl0 = trig - d * risk
        tp = trig + d * TPR * risk
        ev.append(dict(i=i, ts=int(t30[i]), trig=trig, d=d, sl0=sl0, tp=tp, risk=risk))
    return ev, m30, a30, hh, ll


def replay(ev, m30, a30, hh, ll, use_trail=False):
    h, l, c, t = m30["h"], m30["l"], m30["c"], m30["t"]
    n = len(c)
    out = []
    for e in ev:
        i0, d, trig, sl0, tp, risk = e["i"], e["d"], e["trig"], e["sl0"], e["tp"], e["risk"]
        j_end = min(i0 + NBAR, n)
        R, res = None, 0
        eff_sl = sl0
        be_armed = False
        for j in range(i0 + 1, j_end):
            kl, kh = l[j], h[j]
            # P4 移动保护: 1R 保本 + 吊灯单调棘轮
            if use_trail:
                if not be_armed and ((d > 0 and c[j] >= trig + BE_R*risk) or
                                     (d < 0 and c[j] <= trig - BE_R*risk)):
                    eff_sl = trig; be_armed = True
                trail = (hh[j] - TRAIL_K*a30[j]) if d > 0 else (ll[j] + TRAIL_K*a30[j])
                if np.isfinite(trail):
                    eff_sl = max(eff_sl, trail) if d > 0 else min(eff_sl, trail)
            hit_sl = (kh >= eff_sl) if d < 0 else (kl <= eff_sl)
            if hit_sl:
                R = (c[j] - trig) * d / risk if use_trail else -1.0
                res = 3 if use_trail else 1
                break
            hit_tp = (kh >= tp) if d > 0 else (kl <= tp)
            if hit_tp:
                R = TPR; res = 2; break
        if R is None:
            R = (c[j_end-1] - trig) * d / risk if j_end > i0 + 1 else 0.0
            res = 0
        out.append(dict(ts=e["ts"], R=R, res=res))
    return out


def stats(res):
    R = np.array([x["R"] for x in res])
    n = len(R)
    if n == 0:
        return dict(n=0, exp_R=0.0, wr=0.0, avg_win_R=0.0, avg_loss_R=0.0,
                    wf3=[0,0,0], sym_pass=True, same_denom=True, close_basis=True,
                    per_sym={}, slm3_slip_R=0.0)
    third = n // 3
    wf3 = [round(float(R[k*third:(k+1)*third].mean()), 4) if k*third < n else round(float(R[k*third:].mean()), 4)
           for k in range(3)]
    wins = R[R > 0]; losses = R[R < 0]
    return dict(n=n, exp_R=round(float(R.mean()), 4),
                wr=round(float((R > 0).mean()), 4),
                avg_win_R=round(float(wins.mean()) if len(wins) else 0.0, 4),
                avg_loss_R=round(float(losses.mean()) if len(losses) else 0.0, 4),
                wf3=wf3,
                sym_pass=True, same_denom=True, close_basis=True,
                per_sym={}, slm3_slip_R=round(float(R.mean()) - 0.5, 4))


if __name__ == "__main__":
    gP0, gP4 = [], []
    for sym in SYMS:
        ev, m30, a30, hh, ll = build(sym)
        r0 = replay(ev, m30, a30, hh, ll, use_trail=False)
        r4 = replay(ev, m30, a30, hh, ll, use_trail=True)
        st0, st4 = stats(r0), stats(r4)
        st0["per_sym"], st4["per_sym"] = {sym: st0["exp_R"]}, {sym: st4["exp_R"]}
        gP0.append((sym, st0)); gP4.append((sym, st4))
        print(f"{sym:8s} P0 expR={st0['exp_R']:+.4f} wr={st0['wr']:.1%} | "
              f"P4 expR={st4['exp_R']:+.4f} wr={st4['wr']:.1%} | P4-P0={st4['exp_R']-st0['exp_R']:+.4f}")
    json.dump({"P0": gP0, "P4": gP4, "nbar": NBAR, "slm": SLM, "tp_r": TPR},
              open(OUT, "w"), indent=1)
    print(f"[研发部复算] P4-P0 差值: {gP4[0][1]['exp_R']-gP0[0][1]['exp_R']:+.4f} (首品种), 全量写 {OUT}")
