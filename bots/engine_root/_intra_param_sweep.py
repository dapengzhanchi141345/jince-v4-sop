# -*- coding: utf-8 -*-
# 日内腿参数面甜蜜点扫描 (统一引擎口径, 同事件全集, 保守同根先SL)
# 事件: kill-zone h8-16 UTC, 前日高低扫损 (PDH×1.002 SELL / PDL×0.998 BUY)
# 网格: SL{0.5,0.75,1.0,1.5}×H1ATR × stall{off,4h} × night{off,4h} × target{前日中值, 中值∓0.5×日ATR截断}
import json, sys
import numpy as np
import MetaTrader5 as mt5
sys.path.insert(0, "E:/GoldstrategyEngine"); sys.path.insert(0, "E:/GoldstrategyEngine/multi_agent/trading")
import intraday_swing as isw

SYMS = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD"]
mt5.initialize(); assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")

def load(sym, tf, n):
    r = mt5.copy_rates_from_pos(sym, tf, 0, n)
    if r is None: return None
    return dict(t=r["time"].astype(np.int64), h=r["high"].astype(float),
                l=r["low"].astype(float), c=r["close"].astype(float),
                high=r["high"].astype(float), low=r["low"].astype(float))

CACHE, EV, H1A = {}, [], {}
for sym in SYMS:
    h4 = load(sym, mt5.TIMEFRAME_H4, 2600)
    d1 = load(sym, mt5.TIMEFRAME_D1, 500)
    h1 = load(sym, mt5.TIMEFRAME_H1, 6000)
    if not (h4 and d1 and h1): continue
    CACHE[sym] = (h4["h"], h4["l"], h4["c"], h4["t"])
    d1c, d1t = d1["c"], d1["t"]
    hh, ll, cc, tt = CACHE[sym]
    for i in range(60, len(cc)-2):
        tsv = int(tt[i])
        hod = tsv % 86400
        if hod < 8*3600 or hod >= 16*3600: continue
        m = np.where(d1t + 86400 <= tsv)[0]
        if len(m) == 0: continue
        j = m[-1]
        if j < 1: continue
        pdh, pdl = float(d1["high"][j]), float(d1["low"][j])
        idx = int(np.searchsorted(h1["t"], tsv, side="left"))
        seg = slice(max(0, idx-30), idx+1)
        a = isw.atr(h1["h"][seg], h1["l"][seg], h1["c"][seg])
        h1a = float(a[-1]) if a[-1] > 0 else 1e-9
        H1A[(sym, i)] = h1a
        EV.append((sym, -1, i+1, pdh*1.002, h1a, (pdh+pdl)/2, tsv))   # SELL stop
        EV.append((sym, +1, i+1, pdl*0.998, h1a, (pdh+pdl)/2, tsv))   # BUY stop
print(f"事件全集 N={len(EV)}")

def replay(sym, side, k0, trig, h1a, tp_mid, sl_m, stall, night):
    hh, ll, cc, tt = CACHE[sym]
    risk = sl_m * h1a
    if risk < 1e-9: return 0.0, False
    sl = trig + side * risk
    d = 1 if side > 0 else -1
    fill_k = None
    for k in range(k0, min(k0+4, len(hh))):
        if (hh[k] >= trig) if d > 0 else (ll[k] <= trig):
            fill_k = k; break
    if fill_k is None: return 0.0, False
    R = None
    last_k = min(fill_k + 41, len(cc)-1)
    for k in range(fill_k, last_k+1):
        kh, kl, kc = hh[k], ll[k], cc[k]
        hit_sl = (kl <= sl) if d > 0 else (kh >= sl)
        hit_tp = (kc >= tp_mid) if d > 0 else (kc <= tp_mid)   # live用tick, 回放保守用close
        if hit_sl: R = -1.0; break
        if hit_tp: R = abs(tp_mid-trig)/risk; break
        if stall and k - fill_k == 1 and ((d < 0 and kc > tp_mid) or (d > 0 and kc < tp_mid)) is False:
            pass
        # 4h stall (H4 1根=4h): 第一根收盘没朝目标走 → 早退
        if stall and k == fill_k and ((d < 0 and kc >= trig) or (d > 0 and kc <= trig)):
            R = max(min(d*(kc-trig)/risk, abs(tp_mid-trig)/risk), -1.0); break
        if night and k - fill_k == 1:
            R = max(min(d*(kc-trig)/risk, abs(tp_mid-trig)/risk), -1.0); break
    if R is None:
        R = max(min(d*(cc[last_k]-trig)/risk, abs(tp_mid-trig)/risk), -1.0)
    return R, True

def five(rs, ts_all):
    arr = np.array(rs)
    if len(arr) < 100: return {"n": len(arr), "exp_R": None}
    tmin, tmax = min(ts_all), max(ts_all)
    b1 = tmin + (tmax-tmin)//3; b2 = tmin + 2*(tmax-tmin)//3
    wf = [float(np.mean([r for r,t in zip(rs,ts_all) if t < b1])),
          float(np.mean([r for r,t in zip(rs,ts_all) if b1 <= t < b2])),
          float(np.mean([r for r,t in zip(rs,ts_all) if t >= b2]))]
    return {"n": len(arr), "exp_R": round(float(arr.mean()),4), "wr": round(float((arr>0).mean()),4),
            "wf3": [round(x,4) for x in wf], "wf_all_pos": all(x>0 for x in wf),
            "exp_slip0.5": round(float((arr-0.5).mean()),4)}

out = {}
best = {"key": None, "exp_R": -9, "sl_m": 0.75, "stall": False, "night": False}
for sl_m in [0.5, 0.75, 1.0, 1.5]:
    for stall in [False, True]:
        for night in [False, True]:
            rs, ts_all = [], []
            for (sym, side, k0, trig, h1a, tp_mid, tsv) in EV:
                R, filled = replay(sym, side, k0, trig, h1a, tp_mid, sl_m, stall, night)
                if filled: rs.append(R); ts_all.append(tsv)
            key = f"SL{sl_m}x/stall{'on' if stall else 'off'}/night{'on' if night else 'off'}"
            out[key] = five(rs, ts_all)
            v = out[key]
            if v.get("exp_R") is not None and v["exp_R"] > best["exp_R"]:
                best = {"key": key, "exp_R": v["exp_R"], "sl_m": sl_m, "stall": stall, "night": night}
            print(f"[{key}] {v}")

# 品种稳健 (最优格, 直接用追踪到的参数, 不解析字符串)
print(f"\n最优格: {best['key']}")
rs_by_sym = {}
for s in SYMS:
    rs, ts_all = [], []
    for (sym, side, k0, trig, h1a, tp_mid, tsv) in EV:
        if sym != s: continue
        R, filled = replay(s, side, k0, trig, h1a, tp_mid, best["sl_m"], best["stall"], best["night"])
        if filled: rs.append(R); ts_all.append(tsv)
    a = np.array(rs)
    rs_by_sym[s] = {"n": len(rs), "exp_R": round(float(a.mean()),4) if len(rs) else None}
out["per_sym_best"] = rs_by_sym
best_v = out[best["key"]]
out["verdict"] = "接" if (best_v.get("exp_R") and best_v["exp_R"] > 0.5
                          and best_v.get("wf_all_pos")
                          and sum(1 for v in rs_by_sym.values() if (v["exp_R"] or 0) > 0) >= 5) else "维持现参数"
json.dump(out, open("E:/GoldstrategyEngine/data/intra_param_sweep.json","w",encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("verdict:", out["verdict"], " | per_sym:", {k: v["exp_R"] for k,v in rs_by_sym.items()})
mt5.shutdown()
