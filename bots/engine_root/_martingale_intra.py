# -*- coding: utf-8 -*-
"""震荡/日内腿 × 马丁加仓网格 (用户指定: 震荡和日内最适合马丁)
几何=日内腿 _intra_tfsweep.py 全时段(00-24) close口径: 前日PDL×0.998 BUY_STOP / 前日PDH×1.002 SELL_STOP,
SL=0.75×ATR14(Wilder), 目标前日中值, 前向24根M30(=12h), 扣0.095R实测滑点
加仓引擎同 _martingale_grid.py: 同向连亏后下次信号加仓, 间距{0,4,8,16,24bar}×次数{1,2,3}×倍数{平添1.5,递倍,倍增},
风险纪律全保留(1%基础×倍数, 每品种≤3单/日, 日亏10%熔断)
输出: data/night_rd_martin_intra.json"""
import os, json, time
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "data", "tf_cache")
OUT = os.path.join(ROOT, "data", "night_rd_martin_intra.json")
SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]
SL_ATR = 0.75
LOOK = 24
FILL = 4
BPD = 48


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


def day_key(ts):
    return ts // 86400 * 86400


def intra_signals(sym):
    """_intra_tfsweep.py 几何: UTC日界, 首个M30 bar的day_key=UTC日 → 前日D1中值/PDHigh/PDLow"""
    d1, m = load(sym, "D1"), load(sym, "M30")
    t, h, l, c = m["t"], m["h"], m["l"], m["c"]
    atr = atr_wilder(h, l, c)
    dt, dh, dl, dc = d1["t"], d1["h"], d1["l"], d1["c"]
    # 每M30 bar 对应其 UTC 日
    m_day = day_key(t)
    pos = np.searchsorted(dt, m_day, side="left")  # m_day >= dt[j] 的最小 j
    sig = []
    n = len(c)
    for i in range(1, n - LOOK - 2):
        pd = m_day[i] - 86400
        j = pos[i]
        if j < 1 or day_key(int(dt[j - 1])) != pd:
            continue
        if int(dc[j - 1]) <= 0:
            continue
        mid, pdh, pdl = float(dc[j - 1]), float(dh[j - 1]), float(dl[j - 1])
        a = atr[i]
        if np.isnan(a) or a <= 0:
            continue
        risk = SL_ATR * a
        trig_b, trig_s = pdl * 0.998, pdh * 1.002
        pending = []
        if trig_b > 0 and mid > trig_b:
            pending.append(("BUY", trig_b, mid, trig_b - risk))
        if trig_s > 0 and mid < trig_s:
            pending.append(("SELL", trig_s, mid, trig_s + risk))
        if not pending:
            continue
        seg_h, seg_l = h[i + 1:i + 1 + FILL], l[i + 1:i + 1 + FILL]
        filled = None
        for sd, trig, tp, sl in pending:
            if sd == "BUY" and seg_l.min() <= trig:
                filled = (sd, trig, tp, sl, "t")
                break
            if sd == "SELL" and seg_h.max() >= trig:
                filled = (sd, trig, tp, sl, "t")
                break
        if filled is None:
            continue
        sd, trig, tp, sl, _ = filled
        j0 = i + 1
        R, k_ex, done = None, LOOK - 1, False
        for k in range(j0, min(j0 + LOOK, n)):
            hit_sl = (l[k] <= sl) if sd == "BUY" else (h[k] >= sl)
            hit_tp = (h[k] >= tp) if sd == "BUY" else (l[k] <= tp)
            if hit_sl:
                R, k_ex, done = -1.0, k - j0, True
                break
            if hit_tp:
                R, k_ex, done = (tp - trig) / risk if sd == "BUY" else (trig - tp) / risk, k - j0, True
                break
        if R is None:
            kk = min(j0 + LOOK - 1, n - 1)
            R = ((c[kk] - trig) / risk if sd == "BUY" else (trig - c[kk]) / risk)
            k_ex = LOOK - 1
        R = float(max(min(R, 3.0), -1.0))
        exit_ts = int(t[min(j0 + k_ex, n - 1)])
        sig.append(dict(ts=int(t[i + 1]), exit_ts=exit_ts, R=R - 0.095, side=sd))
    return sig


def engine(all_sig, cooldown_bars, cap, scheme, equity0=10000.0):
    mlvl = {"flat15": [1.0, 1.5, 1.5, 1.5, 1.5],
            "step": [1.0, 1.5, 2.0, 2.0, 2.0],
            "dbl": [1.0, 2.0, 4.0, 8.0, 16.0]}[scheme][:cap + 1] or [1.0]
    events = []
    for s in all_sig:
        events.append((s["ts"], "open", s))
        events.append((s["exit_ts"], "close", s))
    events.sort(key=lambda x: (x[0], 0 if x[1] == "close" else 1))
    state = {sym: dict(consec=0, day=None, day_pnl=0.0, day_start=equity0, cnt=0, last_exit=-10**18)
             for sym in SYMS}
    equity = equity0
    curve = [(0, equity)]
    open_pos = {}
    n_orders = 0
    for ts, typ, s in events:
        sym = s.get("sym")
        if typ == "close":
            st = state[sym]
            if sym in open_pos:
                oR, orisk = open_pos.pop(sym)
                pnl = orisk * oR
                equity += pnl
                st["day_pnl"] += pnl
                st["consec"] = st["consec"] + 1 if oR < 0 else 0
                st["last_exit"] = ts
            curve.append((ts, equity))
        else:
            st = state[sym]
            d = day_key(ts)
            if st["day"] != d:
                st["day"], st["cnt"], st["day_pnl"], st["day_start"] = d, 0, 0.0, equity
            if sym in open_pos:
                continue
            if st["day_pnl"] <= -0.10 * st["day_start"]:
                continue
            if st["cnt"] >= 3:
                continue
            if ts < st["last_exit"] + cooldown_bars * 1800:
                continue
            lvl = min(st["consec"], len(mlvl) - 1)
            open_pos[sym] = (s["R"], equity * 0.01 * mlvl[lvl])
            st["cnt"] += 1
            n_orders += 1
    if open_pos:
        for sym, (oR, orisk) in open_pos.items():
            equity += orisk * oR
        curve.append((events[-1][0], equity))
    return dict(final_equity=round(equity, 2), n_orders=n_orders, curve=curve)


def metrics(curve, equity0=10000.0):
    daily = {}
    for ts, e in curve:
        daily[day_key(ts)] = e
    dv = np.array(list(daily.values()))
    logret = float(np.log(dv[-1] / dv[0])) if dv[-1] > 0 else -99.0
    peak = np.maximum.accumulate(dv)
    mdd = float(((peak - dv) / peak).max())
    sharpe = float(dv.mean() / dv.std() * np.sqrt(365)) if len(dv) > 2 and dv.std() > 0 else 0.0
    return dict(mdd=round(mdd, 4), sharpe=round(sharpe, 3), log_ret=round(logret, 2),
                cagr=round((dv[-1] / equity0) ** (365.0 / max(len(dv), 1)) - 1, 4) if dv[-1] > 0 else None,
                final_equity=round(dv[-1], 2), days=len(dv))


def wf3(all_sig, cd, cap, scheme):
    tms = sorted(s["ts"] for s in all_sig)
    t1, t2 = tms[len(tms) // 3], tms[2 * len(tms) // 3]
    out = []
    for seg in ([s for s in all_sig if s["ts"] < t1],
                [s for s in all_sig if t1 <= s["ts"] < t2],
                [s for s in all_sig if s["ts"] >= t2]):
        out.append(metrics(engine(seg, cd, cap, scheme)["curve"])["log_ret"])
    return out


def main():
    t0 = time.time()
    all_sig, per_sig = [], {}
    for sym in SYMS:
        s = intra_signals(sym)
        for x in s:
            x["sym"] = sym
        per_sig[sym] = len(s)
        all_sig.extend(s)
    Rs = np.array([x["R"] for x in all_sig])
    print(f"日内腿信号全集 n={len(all_sig)} per_sym={per_sig}")
    print(f"基线毛值(扣0.095滑点)={Rs.mean():.4f}  胜率={(Rs>0).mean()*100:.1f}%  (官方口径-0.15R)")
    res = {}
    for cd_bars, cd_h in [(0, "0h"), (4, "2h"), (8, "4h"), (16, "8h"), (24, "12h")]:
        for cap in [0, 1, 2, 3]:
            for scheme in (["flat15"] if cap == 0 else ["flat15", "step", "dbl"]):
                tag = f"cd{cd_h}_cap{cap}" + ("" if cap == 0 else "_" + scheme)
                sg = engine(all_sig, cd_bars, cap, scheme)
                m = metrics(sg["curve"])
                res[tag] = dict(mdd=m["mdd"], sharpe=m["sharpe"], log_ret=m["log_ret"],
                                cagr=m["cagr"], n_orders=sg["n_orders"], wf3_log=wf3(all_sig, cd_bars, cap, scheme))
                print(f"{tag}: " + json.dumps(res[tag]))
    base_cagr = res["cd0h_cap0"]["cagr"]
    better = [k for k, v in res.items() if k != "cd0h_cap0" and v["cagr"] is not None
              and base_cagr is not None and v["cagr"] > base_cagr]
    improved = [k for k in better if all(x > 0 for x in res[k]["wf3_log"])]
    print(f"\n基线cd0h_cap0 CAGR={base_cagr} | 跑赢基线的格: {len(better)} | 且三段wf全正: {len(improved)}")
    ranked = sorted(res.keys(), key=lambda k: -(res[k]["cagr"] or -99))
    json.dump({
        "family": "fam6b_日内腿马丁加仓",
        "baseline_exp_R": round(float(Rs.mean()), 4), "baseline_wr": round(float((Rs > 0).mean()), 4),
        "n_signals": len(all_sig), "per_sym": per_sig,
        "baseline_cagr": base_cagr, "n_cells_beat_baseline": len(better), "cells_wf3_pos_and_better": improved,
        "grid": res, "top3_cagr": ranked[:3],
        "note": "日内腿(前日PDL/PDH stop, SL=0.75ATR, 目标中值, 12h窗口) 毛值-0.15R × 马丁加仓50格",
    }, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("TOP3 CAGR:", ranked[:3], "WROTE", OUT, "ELAPSED", round(time.time() - t0, 1))


if __name__ == "__main__":
    main()
