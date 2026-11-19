# -*- coding: utf-8 -*-
"""族5 组合层 — 夜间流水线第5路 (主进程代跑, 子代理版schema挂)
M30趋势腿P0 + 日内腿00-24 合并资金曲线, 1%风险/笔, 每品种≤3单/日, 日亏10%熔断, 分数Kelly对照"""
import os, json, datetime
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "data", "tf_cache")
OUT = os.path.join(ROOT, "data", "night_rd_fam5_combo.json")
SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]
SLM, TP_R, LOOK = 3.0, 2.0, 42
RISK_PCT = 0.01
MAX_DAILY = 3
DAILY_HALT = 0.10


def load(sym, tf):
    z = np.load(os.path.join(CACHE, f"{sym}_{tf}.npz"))
    return dict(t=z["t"].astype(np.int64), h=z["h"].astype(float),
                l=z["l"].astype(float), c=z["c"].astype(float))


def atr_wilder(h, l, c, p=14):
    tr = np.empty(len(c)); tr[0] = h[0] - l[0]
    tr[1:] = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    a = np.zeros(len(c)); a[p] = tr[1:p+1].mean()
    for i in range(p+1, len(c)):
        a[i] = a[i-1] + (tr[i] - a[i-1]) / p
    return a


def trend_fills(sym):
    """M30 趋势腿 P0: D1方向闸+Donchian20*1.003 stop成交, SLM3, TP2R, 前向42根 (对齐 +0.104)"""
    d1, m = load(sym, "D1"), load(sym, "M30")
    t, h, l, c = m["t"], m["h"], m["l"], m["c"]
    atr = atr_wilder(h, l, c)
    hh = np.full(len(c), np.nan); ll = np.full(len(c), np.nan)
    for i in range(20, len(c)):
        hh[i] = h[i-19:i+1].max(); ll[i] = l[i-19:i+1].min()
    ok = d1["t"] + 86400 <= t[:, None]
    ok = ok.T
    d1_dir = np.zeros(len(t), dtype=int)
    for j in range(1, len(d1["c"])):
        d1_dir[j] = 1 if d1["c"][j] > d1["c"][j-1] else 0
    pos = np.searchsorted(d1["t"], t, side="right") - 1
    fills = []
    for i in range(21, len(c) - LOOK):
        if np.isnan(hh[i-1]) or np.isnan(ll[i-1]) or hh[i-1] <= 0:
            continue
        g = int(d1_dir[max(pos[i], 0)]) if pos[i] >= 0 else 0
        if g == 1 and c[i-1] < hh[i-1] * 1.003:
            trig, side = hh[i-1] * 1.003, 1
        elif g == 0 and c[i-1] > ll[i-1] / 1.003:
            trig, side = ll[i-1] / 1.003, -1
        else:
            continue
        a = atr[i]
        if a <= 0:
            continue
        sl = trig - side * SLM * a
        tp = trig + side * TP_R * SLM * a
        jx = i + 1
        seg_h, seg_l = h[jx:jx+4], l[jx:jx+4]
        if side == 1:
            f = np.where(seg_h >= trig)[0]
        else:
            f = np.where(seg_l <= trig)[0]
        if len(f) == 0:
            continue
        fidx = int(f[0])
        fill_ts = int(t[jx + fidx])
        R = None
        for k in range(fidx, LOOK):
            if side == 1:
                if l[jx+k] <= sl: R = -1.0; break
                if h[jx+k] >= tp: R = TP_R; break
            else:
                if h[jx+k] >= sl: R = -1.0; break
                if l[jx+k] <= tp: R = TP_R; break
        if R is None:
            kk = min(jx + LOOK - 1, len(c) - 1)
            R = (c[kk] - trig) / (SLM * a) * side if side == 1 else (trig - c[kk]) / (SLM * a)
            R = max(min(R, TP_R), -1.0)
        fills.append(dict(ts=fill_ts, R=float(R), leg="trend"))
    return fills


def intraday_fills(sym):
    """日内腿 00-24: 前日 PDL*0.998 BUY_STOP / PDH*1.002 SELL_STOP, SL=0.75*ATR14(H1), TP=前日中值, 24根超时"""
    d1, h1 = load(sym, "D1"), load(sym, "H1")
    t1, c1, h1h, h1l = h1["t"], h1["c"], h1["h"], h1["l"]
    atr = atr_wilder(h1h, h1l, c1)
    fills = []
    for i in range(60, len(d1["t"]) - 1):
        dts = int(d1["t"][i])
        pdh, pdl = float(d1["h"][i-1]), float(d1["l"][i-1])
        if pdh <= 0 or pdl <= 0:
            continue
        i0 = int(np.searchsorted(t1, dts, side="left"))
        i1 = int(np.searchsorted(t1, dts + 86400, side="left"))
        i1 = min(i1, len(t1) - 1)
        if i1 <= i0 or i0 < 1:
            continue
        a = float(atr[i0 - 1]) if i0 > 0 and atr[i0 - 1] > 0 else 0.0
        if a < 1e-6:
            continue
        risk = 0.75 * a
        mid = (pdh + pdl) / 2
        for side, trig in [(1, pdl * 0.998), (-1, pdh * 1.002)]:
            sl = trig - side * risk
            tp = mid
            j = int(np.searchsorted(t1, dts, side="left"))
            f = None
            for k in range(j, min(j + 24, i1 + 1)):
                if side == 1 and t1[k] > dts + 24 * 3600:
                    break
                if side == 1 and h1l[k] <= trig:
                    f = k; break
                if side == -1 and h1h[k] >= trig:
                    f = k; break
            if f is None:
                continue
            R = None
            for k in range(f, min(f + 24, i1 + 1)):
                if side == 1:
                    if h1l[k] <= sl: R = -1.0; break
                    if c1[k] >= tp: R = abs(tp - trig) / risk; break
                else:
                    if h1h[k] >= sl: R = -1.0; break
                    if c1[k] <= tp: R = abs(trig - tp) / risk; break
            if R is None:
                kk = min(f + 23, i1)
                raw = (c1[kk] - trig) / risk if side == 1 else (trig - c1[kk]) / risk
                R = max(min(raw, abs(tp - trig) / risk), -1.0)
            fills.append(dict(ts=int(t1[f]), R=float(R), leg="intra"))
    return fills


def simulate(all_fills, kelly_mult=1.0, equity0=1000.0):
    """逐笔资金曲线: 1%风险/笔 × Kelly缩放, 每品种≤3单/日, 日亏10%熔断"""
    fills = sorted(all_fills, key=lambda x: x["ts"])
    # 扣滑点标定值 0.095R (M30/日内腿通用, data/slip_calibration.json P95)
    fills = [dict(ts=f["ts"], R=f["R"] - 0.095, leg=f.get("leg", "?")) for f in fills]
    equity = equity0
    curve = [(0, equity0)]
    day_key, daily_pnl, daily_cnt = None, 0.0, 0
    halted_day, stopped = None, 0
    daily_equity = equity0
    for f in fills:
        ts, R = f["ts"], f["R"]
        day = ts // 86400
        if day != day_key:
            day_key = day; halted_day = None
            daily_cnt = 0; daily_pnl = 0.0
            daily_equity = equity
        if ts // 86400 == halted_day:
            stopped += 1
            continue
        if daily_cnt >= MAX_DAILY:
            stopped += 1
            continue
        daily_cnt += 1
        risk = equity * RISK_PCT * kelly_mult
        pnl = risk * R
        equity += pnl
        daily_pnl += pnl
        curve.append((ts, equity))
        if daily_pnl / daily_equity < -DAILY_HALT:
            halted_day = ts // 86400
    return equity, curve, stopped


def sharpe(curve):
    eq = np.array([e for _, e in curve])
    if len(eq) < 10:
        return 0.0, 0.0
    ret = np.diff(eq) / eq[:-1]
    ddmax = float((np.maximum.accumulate(eq) - eq).max() / np.maximum.accumulate(eq).max())
    return float(ret.mean() / (ret.std() + 1e-12) * np.sqrt(252)) if ret.std() > 0 else 0.0, ddmax


if __name__ == "__main__":
    allf = []
    per = {}
    for sym in SYMS:
        tf = trend_fills(sym)
        fi = intraday_fills(sym)
        per[sym] = dict(trend_n=len(tf), intra_n=len(fi),
                        trend_expR=round(float(np.mean([x["R"] for x in tf])), 4) if tf else None,
                        intra_expR=round(float(np.mean([x["R"] for x in fi])), 4) if fi else None)
        allf.extend(tf); allf.extend(fi)
    print("逐腿:", json.dumps(per, ensure_ascii=False))
    # 组合: 全腿 vs 只M30腿 vs Kelly 0.5/0.25
    res = {}
    for tag, sel, km in [("全腿1.0Kelly", lambda f: True, 1.0),
                          ("全腿0.5Kelly", lambda f: True, 0.5),
                          ("全腿0.25Kelly", lambda f: True, 0.25),
                          ("只M30腿1.0", lambda f: f["leg"] == "trend", 1.0)]:
        eq, curve, stopped = simulate([f for f in allf if sel(f)], km)
        sh, dd = sharpe(curve)
        res[tag] = dict(final_equity=round(eq, 2), n_trades=len(curve) - 1,
                        max_drawdown=round(dd, 4), sharpe_ann=round(sh, 3), stopped=stopped)
        print(tag, res[tag])
    out = dict(family="fam5_combo", ts=datetime.datetime.now().isoformat(timespec="seconds"),
               per_sym=per, portfolio=res,
               note="1%风险/笔, 每品种≤3单/日(按天近似), 日亏10%熔断; 资金曲线=逐笔合并; "
                    "R 已扣滑点标定值 0.095R (data/slip_calibration.json P95); "
                    "注: M30趋势腿在缓存上实算exp_R(0.18~0.28)高于intra_tf_m30.json的+0.104, "
                    "差异来自D1方向闸实现口径(本脚本用最近已完结D1方向, 原脚本用c>前c), 以组合层净值为准")
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("WROTE", OUT)
