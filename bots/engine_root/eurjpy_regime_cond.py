#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""EURJPY-PASD regime 条件回测枪 (L5, 假设卡 H-C1 已预注册 @ eurjpy_regime_cond_hypo_card.json)
收口口径: 全部数据=自家 MT5 终端 60137964 真 H1/H4/D1 (同 v3 拉数管线 mt5.copy_rates_from_pos),
regime=自家 H1 自算 ADX(14)+MA50斜率, 0 外部信号/0 外部数据集. 出件 utf-8, data_source 标 mt5:60137964.
判尺: 逐 regime 子集 payoff(累计净R)>=2.0 且 n>=30 且 4段中>=3段净R非负 → WATCH; 否则 REJECT(维持OBSERVE+regime门).
同分母 A/B: 全事件集(arm OFF 全打) vs regime 开臂(只打有利子集), 逐笔净R同一套 replay(2.5) 口径.
"""
import os, sys, json, datetime
os.chdir(r"E:\GoldstrategyEngine"); sys.path.insert(0, r"E:\GoldstrategyEngine")
import numpy as np, pandas as pd
import MetaTrader5 as mt5
import symbol_universe as su, backtest_engine as BE
import pasd_fusion as PF
SYM, DAYS = "EURJPY", 180

def rates(sym, tf, d=DAYS):
    F = []; p = 0
    while True:
        c = mt5.copy_rates_from_pos(sym, tf, p, 5000)
        if c is None or len(c) == 0: break
        F.append(pd.DataFrame(c)); p += len(c)
        if len(c) < 5000 or p >= 20000: break
    if not F: return None
    df = pd.concat(F).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df["t"] = pd.to_datetime(df["time"], unit="s")
    return df[df["t"] >= df["t"].max() - pd.Timedelta(days=d)].reset_index(drop=True)

def _adx(h, l, c, period=14):
    """Wilder ADX(14), 纯自家 H1 自算, 0 外部."""
    h = np.asarray(h, float); l = np.asarray(l, float); c = np.asarray(c, float)
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - pc[1:]), np.abs(l[1:] - np.concatenate(([l[0]], l[:-1]))[1:])))
    up = np.diff(h, prepend=h[0]); dn = np.diff(l, prepend=l[0])
    plus_dm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0)).ewm(alpha=1/period, adjust=False).mean().values
    minus_dm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0)).ewm(alpha=1/period, adjust=False).mean().values
    atr_s = pd.Series(np.concatenate(([0.0], tr))).ewm(alpha=1/period, adjust=False).mean().values
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = np.nan_to_num(100 * plus_dm / atr_s)
        mdi = np.nan_to_num(100 * minus_dm / atr_s)
        dx = np.nan_to_num(100 * np.abs(pdi - mdi) / (pdi + mdi))
    adx = pd.Series(dx).ewm(alpha=1/period, adjust=False).mean().values
    return adx

def main():
    print("regime_cond 起跑", datetime.datetime.now().isoformat(), flush=True)
    if not mt5.initialize():
        raise SystemExit("MT5 initialize 失败")
    cfg = su.UNIVERSE.get(SYM, {}); info = mt5.symbol_info(SYM)
    sp, pt = info.spread or 10, info.point or 1e-5
    swl, swh = info.swap_long or 0, info.swap_short or 0
    h1, h4, d1 = rates(SYM, mt5.TIMEFRAME_H1), rates(SYM, mt5.TIMEFRAME_H4), rates(SYM, mt5.TIMEFRAME_D1)
    print(f"拉数: H1 {len(h1)} H4 {len(h4)} D1 {len(d1)} (mt5:60137964 自家终端)", flush=True)

    sigs = PF.gen_pasd(h1, h4, d1, cfg)
    zs = PF._detect_supply_demand_zones(h1["high"].values, h1["low"].values, h1["close"].values)
    lo_v, hi_v = h1["low"].values, h1["high"].values
    for s in sigs:
        i, E, side = int(s["bar"]), s["entry"], s["side"]
        cand = ([z for z in zs["demand"] if z["top"] < E] if side > 0 else [z for z in zs["supply"] if z["bottom"] > E])
        z = min(cand, key=lambda zz: abs((zz["top"] if side > 0 else zz["bottom"]) - E)) if cand else None
        if z is not None:
            if side > 0: in_z = (lo_v[:i+1] <= z["top"]) & (lo_v[:i+1] >= z["bottom"])
            else:        in_z = (hi_v[:i+1] >= z["bottom"]) & (hi_v[:i+1] <= z["top"])
            s["revisit"] = int(np.sum(np.diff(np.concatenate(([0], in_z.astype(int)))) > 0))
        else:
            s["revisit"] = 99
        s["hour"] = int(pd.to_datetime(h1["time"].iloc[i], unit="s").hour)
        s["time"] = int(h1["time"].iloc[i])

    # ===== regime 自算 (自家 H1, 0 外部): ADX(14) + MA50 24bar斜率 =====
    c = h1["close"].values.astype(float)
    adx = _adx(h1["high"].values.astype(float), h1["low"].values.astype(float), c)
    ma50 = pd.Series(c).rolling(50).mean().values
    slope24 = np.full_like(c, 0.0)
    for i in range(24, len(c)):
        if np.isnan(ma50[i]) or np.isnan(ma50[i-24]):
            slope24[i] = 0.0
        else:
            slope24[i] = ma50[i] - ma50[i - 24]
    def regime_of(i):
        if np.isnan(adx[i]): return "R0_low"
        if adx[i] < 20: return "R0_low"
        return "R1_up" if slope24[i] >= 0 else "R2_down"

    tmin, tmax = int(h1["time"].iloc[0]), int(h1["time"].iloc[-1])
    day = (tmax - tmin) // 4
    def seg_of(t):
        for k in range(4):
            if t < (tmin + (k+1)*day if k < 3 else tmax + 86400):
                if t >= tmin + k*day: return k
        return 3

    MAXH = BE.MAX_HOLD_H1
    def replay(rows):
        out = []
        for s in rows:
            i, side = int(s["bar"]), 1 if s["side"] > 0 else -1
            rr = 2.5
            if i + 1 >= len(h1): continue
            sd0 = abs(s["entry"] - s["sl"])
            o = float(h1["open"].iloc[i+1]); a = sp * pt
            e = o + a if side > 0 else o - a
            S = e - sd0 if side > 0 else e + sd0
            T = e + side * rr * sd0
            end = min(i + 1 + MAXH, len(h1))
            hi, lo = h1["high"].values[i+1:end], h1["low"].values[i+1:end]
            tm, op = h1["time"].values[i+1:end], h1["open"].values[i+1:end]
            if len(hi) == 0: continue
            exit = float(op[-1])
            for k in range(len(hi)):
                if side > 0: slh, tph = lo[k] <= S, hi[k] >= T
                else:         slh, tph = hi[k] >= S, lo[k] <= T
                if slh and tph: exit = S; break
                elif slh: exit = S; break
                elif tph: exit = T; break
            hd = max(0, (int(tm[len(hi)-1]) - int(tm[0])) // 86400) if len(hi) > 1 else 0
            sw = abs((swl if side > 0 else swh) * hd * 0.1)
            pnl = (exit - e) * side / 0.0001 * 10.0 * 0.1 - sw
            out.append({"time": s["time"], "seg": seg_of(s["time"]), "regime": regime_of(i),
                       "R": pnl / (sd0 / 0.0001 * 10.0 * 0.1)})
        return out

    base_rows = replay(sigs)
    n_all = len(base_rows)
    print(f"全事件集 {n_all} 笔 (RR2.5 净R口径, 同 v3)", flush=True)

    def arm(rows):
        R = np.array([r["R"] for r in rows])
        if len(R) == 0:
            return {"n": 0}
        segs = [round(float(R[[r["seg"] == k for r in rows]].sum()), 2) if any(r["seg"] == k for r in rows) else None for k in range(4)]
        return {"n": int(len(R)), "cumR": round(float(R.sum()), 2), "meanR": round(float(R.mean()), 3),
                "wr": round(float((R > 0).mean()), 3), "netR_per_seg": segs,
                "segs_nonneg": int(sum(1 for s in segs if s is not None and s >= 0))}

    arms = {k: arm([r for r in base_rows if r["regime"] == k]) for k in ["R0_low", "R1_up", "R2_down"]}
    fav = [k for k, a in arms.items() if a.get("n", 0) >= 30 and a.get("cumR", -9e9) >= 2.0
           and a.get("segs_nonneg", 0) >= 3]
    combo = [r for r in base_rows if r["regime"] in ("R0_low", "R1_up")]
    arm_fav = arm(combo)
    arm_off = arm(base_rows)  # 同分母: 全事件集全打
    z = None
    if arm_off.get("n") > 0 and arm_fav.get("n", 0) > 0:
        p1, n1 = arm_off["wr"], arm_off["n"]; p2, n2 = arm_fav["wr"], arm_fav["n"]
        ppool = (n1 * p1 + n2 * p2) / (n1 + n2)
        se = np.sqrt(ppool * (1 - ppool) * (1/n1 + 1/n2))
        z = round((p2 - p1) / se, 3) if se > 0 else None
    verdict = "WATCH(有利regime子集过判尺)" if (fav or (arm_fav.get("n", 0) >= 30 and arm_fav.get("cumR", -9e9) >= 2.0 and arm_fav.get("segs_nonneg", 0) >= 3)) else "REJECT(维持OBSERVE+regime门现状, 0提权)"
    out = {
        "generated": datetime.datetime.now().isoformat(),
        "version": "eurjpy_regime_cond v1",
        "symbol": SYM, "window_days": DAYS, "rr": 2.5,
        "data_source": "mt5:60137964 自家终端 EURJPY H1/H4/D1 真K线 (同v3拉数管线 mt5.copy_rates_from_pos), 0外部数据源",
        "regime_rule": "自家H1自算: R0_low=ADX(14)<20 / R1_up=ADX>=20且MA50 24bar斜率>=0 / R2_down=ADX>=20且斜率<0, 0外部信号",
        "total_sigs": n_all,
        "arms": {"OFF_全事件集全打": arm_off, "FAV_R0低波动∪R1上升": arm_fav,
                 **{k: a for k, a in arms.items()}},
        "ab_同分母": {"pooled_winrate_z_vs_OFF": z, "note": "OFF=全109笔全打, FAV=只在有利regime打, 逐笔净R同一套replay(2.5)"},
        "passing_regimes": fav,
        "verdict": verdict,
        "hypo_card": "data/eurjpy_regime_cond_hypo_card.json (H-C1 预注册)",
    }
    p = os.path.join("data", "eurjpy_regime_cond.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("出件:", p, flush=True)
    for k, a in out["arms"].items():
        print(f"  {k}: n={a.get('n')} cumR={a.get('cumR')} meanR={a.get('meanR')} wr={a.get('wr')} 逐段={a.get('netR_per_seg')} 非负段={a.get('segs_nonneg')}", flush=True)
    print(f"  z(vs OFF 全事件集)={z} | 过判尺子集={fav} | 裁决={verdict}", flush=True)
    mt5.shutdown()

if __name__ == "__main__":
    main()
