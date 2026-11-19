# -*- coding: utf-8 -*-
"""第二腿几何下沉(向量化版): 4 日内候选几何找第二个正期望
G1 ORB30 / G2 ORB60 / G3 M30s24 / G4 M30+H1偏差闸; SL=1×ATR TP=2R, 扣0.095R滑点
全向量化: sliding_window_view 算 Donchian/ATR 批量, 事件级向量化成交+前瞻"""
import os, json, time
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "data", "tf_cache")
OUT = os.path.join(ROOT, "data", "night_rd_leg2_geometry.json")
SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]
SLM, TPR, LOOK, FILL = 1.0, 2.0, 24, 4
W = 20  # Donchian 窗口


def load(sym, tf):
    z = np.load(os.path.join(CACHE, f"{sym}_{tf}.npz"))
    return dict(t=z["t"].astype(np.int64), h=z["h"].astype(float),
                l=z["l"].astype(float), c=z["c"].astype(float))


def atr_wilder(h, l, c, p=14):
    n = len(c)
    tr = np.empty(n); tr[0] = h[0] - l[0]
    tr[1:] = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    out = np.zeros(n)
    out[p] = tr[1:p + 1].mean()
    for i in range(p + 1, n):
        out[i] = (out[i - 1] * (p - 1) + tr[i]) / p
    return out


def ema(x, n):
    k = 2.0 / (n + 1)
    out = np.zeros(len(x)); out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = x[i] * k + out[i - 1] * (1 - k)
    return out


def donchian(h, l, w=W):
    hi = np.full(len(h), np.nan); lo = np.full(len(h), np.nan)
    if len(h) > w:
        hi[w - 1:] = swv(h, w).max(axis=1)
        lo[w - 1:] = swv(l, w).min(axis=1)
    return hi, lo


def sim_events(events, m, atr, side_arr, trig_arr, look, day_stop=None):
    """向量化交易引擎: events=bar索引数组(升序, 无重叠约束时), 每事件前瞻look根找SL/TP/超时
    返回 R 数组 (扣滑点前)"""
    t, h, l, c = m["t"], m["h"], m["l"], m["c"]
    n = len(c)
    R = np.empty(len(events))
    for idx, i in enumerate(events):
        side = int(side_arr[idx]); trig = float(trig_arr[idx])
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            R[idx] = 0.0; continue
        risk = SLM * a
        tp = trig + side * TPR * risk
        j0 = i + 1
        sh, sl_ = h[j0:j0 + FILL], l[j0:j0 + FILL]
        f = (sh >= trig) if side == 1 else (sl_ <= trig)
        if not f.any() or j0 + FILL >= n + FILL:
            R[idx] = 0.0; continue
        k_ex = j0 + int(np.argmax(f))
        seg_end = min(k_ex + look, n)
        if day_stop is not None:
            seg_end = min(seg_end, day_stop)
        hh, ll, tt = h[k_ex:seg_end], l[k_ex:seg_end], t[k_ex:seg_end]
        if side == 1:
            sl_hit = ll <= trig - risk
            tp_hit = hh >= tp
        else:
            sl_hit = hh >= trig + risk
            tp_hit = ll <= tp
        if day_stop is not None:
            in_day = tt < day_stop
            sl_hit = sl_hit & in_day; tp_hit = tp_hit & in_day
        sl_i = int(np.argmax(sl_hit)) if sl_hit.any() else len(hh)
        tp_i = int(np.argmax(tp_hit)) if tp_hit.any() else len(hh)
        if sl_hit.any() and sl_i <= (tp_i if tp_hit.any() else 10**9):
            R[idx] = -1.0
        elif tp_hit.any():
            R[idx] = TPR
        else:
            kk = min(seg_end - 1, n - 1)
            R[idx] = ((c[kk] - trig) / risk * side)
            R[idx] = float(max(min(R[idx], TPR), -1.0))
    return R


def geo_g1g2(sym, geo):
    """ORB: 开盘区间 bars=2(G1)/4(G2), 破高做多/破低做空, 当日时间止损, 每日多空各一次"""
    m = load(sym, "M30")
    t, h, l, c = m["t"], m["h"], m["l"], m["c"]
    n = len(c)
    atr = atr_wilder(h, l, c)
    bars = 2 if geo == "G1" else 4
    look = 16
    day = t // 86400 * 86400
    # 逐日批量: 找每日第0根
    uniq_days, first_idx = np.unique(day, return_index=True)
    ev_b, ev_s, ev_trig, ev_dayend = [], [], [], []
    for d0, fi in zip(uniq_days, first_idx):
        oi, oi_e = fi, fi + bars
        if oi_e >= n:
            continue
        oh, ol = h[oi:oi_e].max(), l[oi:oi_e].min()
        tb, ts = oh * 1.002, ol / 1.002
        # 区间结束后找首个 close 触发
        scan_e = min(oi_e + 4, n)
        seg = c[oi_e:scan_e]
        ib = np.where(seg >= tb)[0]
        ist = np.where(seg <= ts)[0]
        day_end = d0 + 86400
        if len(ib):
            ev_b.append(oi_e + int(ib[0])); ev_s.append(1); ev_trig.append(tb); ev_dayend.append(day_end)
        if len(ist):
            ev_b.append(oi_e + int(ist[0])); ev_s.append(-1); ev_trig.append(ts); ev_dayend.append(day_end)
    if not ev_b:
        return []
    ev_b = np.array(ev_b); ev_s = np.array(ev_s); ev_trig = np.array(ev_trig); ev_dayend = np.array(ev_dayend)
    R = sim_events(ev_b, m, atr, ev_s, ev_trig, look)
    # 每日多空各一次: 按 (day,side) 去重取首个
    R2 = []
    seen = set()
    for i in range(len(ev_b)):
        key = (int(day[ev_b[i]]), int(ev_s[i]))
        if key in seen:
            continue
        seen.add(key)
        R2.append(R[i])
    return [r - 0.095 for r in R2 if r != 0.0]


def geo_g3(sym):
    """M30 P0 几何 (Donchian20×1.003+D1方向闸) 持有截断24根(12h)"""
    d1, m = load(sym, "D1"), load(sym, "M30")
    t, h, l, c = m["t"], m["h"], m["l"], m["c"]
    n = len(c)
    atr = atr_wilder(h, l, c)
    hi, lo = donchian(h, l)
    h_prev = np.roll(hi, 1); l_prev = np.roll(lo, 1)
    h_prev[0] = np.nan; l_prev[0] = np.nan
    pos = np.searchsorted(d1["t"], t // 86400 * 86400, side="left")
    d1_dir = np.zeros(len(d1["c"]), dtype=int)
    for j in range(1, len(d1["c"])):
        d1_dir[j] = 1 if d1["c"][j] > d1["c"][j - 1] else 0
    g = d1_dir[pos]
    valid = (~np.isnan(h_prev)) & (h_prev > 0) & (g >= 0) & (np.arange(n) >= W)
    side = np.zeros(n, dtype=int)
    trig = np.zeros(n)
    b = valid & (g == 1) & (c < h_prev * 1.003)
    s = valid & (g == 0) & (c > l_prev / 1.003)
    side[b] = 1; side[s] = -1
    trig[b] = h_prev[b] * 1.003; trig[s] = l_prev[s] / 1.003
    ev = np.where((side != 0) & (atr > 0))[0]
    R = sim_events(ev, m, atr, side[ev], trig[ev], 24)
    return [r - 0.095 for r in R]


def geo_g4(sym):
    """M30 stop几何 + H1 EMA20 偏差闸 (日内尺度 MTF)"""
    h1, m = load(sym, "H1"), load(sym, "M30")
    t, h, l, c = m["t"], m["h"], m["l"], m["c"]
    n = len(c)
    atr = atr_wilder(h, l, c)
    hi, lo = donchian(h, l)
    h_prev = np.roll(hi, 1); l_prev = np.roll(lo, 1)
    h_prev[0] = np.nan; l_prev[0] = np.nan
    e1 = ema(h1["c"], 20)
    bias1 = np.where(h1["c"] > e1, 1, 0)
    bpos = np.clip(np.searchsorted(h1["t"], t, side="right") - 1, 0, len(bias1) - 1)
    g = bias1[bpos]
    valid = (~np.isnan(h_prev)) & (h_prev > 0) & (g >= 0) & (np.arange(n) >= W)
    side = np.zeros(n, dtype=int); trig = np.zeros(n)
    b = valid & (g == 1) & (c < h_prev * 1.003)
    s = valid & (g == 0) & (c > l_prev / 1.003)
    side[b] = 1; side[s] = -1
    trig[b] = h_prev[b] * 1.003; trig[s] = l_prev[s] / 1.003
    ev = np.where((side != 0) & (atr > 0))[0]
    R = sim_events(ev, m, atr, side[ev], trig[ev], LOOK)
    return [r - 0.095 for r in R]


def main():
    t0 = time.time()
    GEOS = ["G1", "G2", "G3", "G4"]
    fn = {"G1": lambda s: geo_g1g2(s, "G1"), "G2": lambda s: geo_g1g2(s, "G2"),
          "G3": geo_g3, "G4": geo_g4}
    allR = {g: [] for g in GEOS}
    per_sym = {g: {} for g in GEOS}
    for sym in SYMS:
        for g in GEOS:
            R = fn[g](sym)
            allR[g].extend(R)
            per_sym[g][sym] = round(float(np.mean(R)), 4) if R else None
            print(f"[{sym}]{g} n={len(R)}", flush=True)
    res = {}
    for g in GEOS:
        Rs = np.array(allR[g])
        n = len(Rs)
        third = max(n // 3, 1)
        wf3 = [round(float(Rs[k * third:(k + 1) * third].mean()), 4) for k in range(2)] + \
              [round(float(Rs[2 * third:].mean()), 4)]
        res[g] = dict(n=n, exp_R=round(float(Rs.mean()), 4) if n else None,
                      wr=round(float((Rs > 0).mean()), 4) if n else None,
                      wf3=wf3, per_sym=per_sym[g],
                      sym_pos=sum(1 for v in per_sym[g].values() if v and v > 0))
        print(f"{g}: n={n} exp_R={res[g]['exp_R']} wr={res[g]['wr']} wf3={wf3} pos={res[g]['sym_pos']}/6")
    json.dump({"family": "fam7_第二腿几何下沉",
               "meta": "M30日内候选几何 G1 ORB30/G2 ORB60/G3 M30s24/G4 M30+H1偏差闸; SL=1×ATR TP=2R 扣0.095R",
               "results": res,
               "note": "找第二个正期望日内几何; 过五验才进观察名单"},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("WROTE", OUT, "ELAPSED", round(time.time() - t0, 1))


if __name__ == "__main__":
    main()
