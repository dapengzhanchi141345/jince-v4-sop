
# -*- coding: utf-8 -*-
# 验证 daily_forecaster: 实盘sanity + 全史五验(次日区间法挂单 vs 50%基准, 同分母)
import sys, json, math
sys.path.insert(0, "E:/GoldstrategyEngine"); sys.path.insert(0, "E:/GoldstrategyEngine/multi_agent/trading")
import numpy as np, MetaTrader5 as mt5
import daily_forecaster as dfc

SYMS = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD","XAUUSD"]
mt5.initialize(); assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")

# ── ① 实盘 sanity ──
for sym in ["BTCUSD","XAUUSD","SOLUSD"]:
    f = dfc.from_mt5(sym)
    print(f"[{sym}] {f['state']}  次日带[{f['next_lo']:.5g}~{f['next_hi']:.5g}]  枢轴{f['pivot']:.5g}  R1/S1 {f['r1']:.5g}/{f['s1']:.5g}  前日{f['pdl']:.5g}~{f['pdh']:.5g}")

# ── ② 全史: 每根已完结D1 → 次日区间法挂单, fwd回放H4验证 ──
# 方法: 次日预期高(上沿)挂 SELL, 目标=枢轴, SL=上沿+1×日ATR; 下沿对称. 次日(H4回放)先触SL/谁先到
def back(sym, range_mult=1.5, atr_mult=1.0):
    d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 1800)
    h4 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, 7000)
    if d1 is None or h4 is None or len(d1) < 200: return None
    h=d1["high"].astype(float); l=d1["low"].astype(float); c=d1["close"].astype(float)
    from daily_forecaster import _wilder_atr
    atr = _wilder_atr(h,l,c)
    th=h4["time"].astype(np.int64); h4h=h4["high"].astype(float); h4l=h4["low"].astype(float)
    wins, loses, cancels = 0,0,0
    for i in range(60, len(d1)-2):
        a = atr[i]
        if a <= 0: continue
        pdh,pdl = h[i], l[i]
        p = (pdh+pdl+c[i])/3
        hi, lo = p + range_mult*a, p - range_mult*a
        # 次日H4窗口 = i+1 日(从第i+1根D1时间起, 4根H4)
        t0 = int(d1["time"][i+1])
        w = np.where((th >= t0) & (th < t0 + 86400))[0]
        if len(w) < 4: continue
        seg_h = h4h[w]; seg_l = h4l[w]
        # 上沿单(若价格到hi挂SELL_LIMIT) 目标p SL=hi+a*atr_mult
        if (seg_h >= hi).any() and (hi - p) / a >= 0.3:   # 有到上沿的幅度才值得
            k = np.where(seg_h >= hi)[0][0]
            rest_h, rest_l = seg_h[k:], seg_l[k:]
            sl = hi + atr_mult*a; win_k = np.where(rest_l <= p)[0]; lose_k = np.where(rest_h >= sl)[0]
            if len(lose_k) and (len(win_k)==0 or lose_k[0] <= win_k[0]): loses += 1
            elif len(win_k): wins += 1
            else: cancels += 1
        if (seg_l <= lo).any() and (p - lo) / a >= 0.3:
            k = np.where(seg_l <= lo)[0][0]
            rest_h, rest_l = seg_h[k:], seg_l[k:]
            sl2 = lo - atr_mult*a; win_k = np.where(rest_h >= p)[0]; lose_k = np.where(rest_l <= sl2)[0]
            if len(lose_k) and (len(win_k)==0 or lose_k[0] <= win_k[0]): loses += 1
            elif len(win_k): wins += 1
            else: cancels += 1
    n = wins + loses
    return {"sym": sym, "wins": wins, "loses": loses, "cancels": cancels,
            "wr": round(wins/n, 4) if n else None, "n": n}

rows = [back(s) for s in SYMS]
rows = [r for r in rows if r]
tot_w = sum(r["wins"] for r in rows); tot_l = sum(r["loses"] for r in rows)
tot = tot_w + tot_l
p = 2*(1 - 0.5*(1+math.erf(((tot_w/tot - 0.5)/math.sqrt(0.25/tot))/math.sqrt(2)))) if tot else None
out = {"rows": rows, "tot_n": tot, "wr": round(tot_w/tot,4) if tot else None, "p_vs_50": None if p is None else round(p,4),
       "verdict": ("接" if (tot>=1000 and tot_w/tot>0.53 and p<0.05) else "维持/观察")}
json.dump(out, open("E:/GoldstrategyEngine/data/daily_forecast_verify.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
for r in rows: print(f"[{r['sym']}] n={r['n']} wr={r['wr']}")
print("TOTAL n=", tot, "wr=", out["wr"], "p=", out["p_vs_50"], "verdict=", out["verdict"])
mt5.shutdown()
