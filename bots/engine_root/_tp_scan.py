
# -*- coding: utf-8 -*-
# 趋势腿 TP 倍数五验 A/B: 现参数(缓冲1.003/SL2.0×ATR/TP2.0R) vs TP∈{1.0,1.5,2.0,2.5,3.0,4.0}R
# 同事件全集(缓冲1.003突破事件), H4 2600根×6币T1, D1方向闸, 前向10日扫描
import json, math
import numpy as np
import MetaTrader5 as mt5
import sys; sys.path.insert(0, "E:/GoldstrategyEngine/multi_agent/trading")

SYMS = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD"]
TP_GRID = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
mt5.initialize(); assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")

def donchian20(h, l):
    hi = np.full(len(h), np.nan); lo = np.full(len(l), np.nan)
    for i in range(20, len(h)):
        hi[i] = h[i-20:i].max(); lo[i] = l[i-20:i].min()
    return hi, lo

def atr_series(h, l, c, p=14):
    tr = np.empty(len(c)); tr[0] = h[0]-l[0]
    tr[1:] = np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1])))
    out = np.zeros(len(c))
    out[p] = tr[1:p+1].mean()
    for i in range(p+1, len(c)):
        out[i] = (out[i-1]*(p-1) + tr[i]) / p
    return out

def d1_gate(d1c, d1t, ts):
    """已完结D1方向: 1多/0空/None"""
    ok = d1t + 86400 <= ts
    if not ok.any(): return None
    idx = np.where(ok)[0][-1]
    if idx < 1: return None
    return 1 if d1c[idx] > d1c[idx-1] else 0

events = []   # (sym, ts, side, trig, sl, risk, fill_ts_or_None, fwd h4 arrays...)
per_sym_events = {}
for sym in SYMS:
    h4 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, 2600)
    d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 500)
    if h4 is None or d1 is None: continue
    h = h4["high"].astype(float); l = h4["low"].astype(float); c = h4["close"].astype(float)
    t = h4["time"].astype(np.int64)
    dc = d1["close"].astype(float); dtt = d1["time"].astype(np.int64)
    hi, lo = donchian20(h, l)
    atr = atr_series(h, l, c)
    evs = []
    for i in range(60, len(h)-45):
        ts_close = int(t[i]) + 14400
        g = d1_gate(dc, dtt, ts_close)
        if g is None: continue
        risk0 = 2.0 * atr[i-1]
        if g == 1 and not np.isnan(hi[i-1]) and c[i-1] < hi[i-1]:
            trig = hi[i-1] * 1.003
            if c[i-1] >= trig: continue
            evs.append(dict(sym=sym, i=i, side=1, trig=trig, sl=trig - risk0))
        elif g == 0 and not np.isnan(lo[i-1]) and c[i-1] > lo[i-1]:
            trig = lo[i-1] / 1.003
            if c[i-1] <= trig: continue
            evs.append(dict(sym=sym, i=i, side=-1, trig=trig, sl=trig + risk0))
    per_sym_events[sym] = evs
    events.extend(evs)
    print(f"[{sym}] n_events={len(evs)}")

def resolve(evs, tp_m):
    """对每事件: 前向42根H4(10日)内 先成交→再判SL/TP/超时(收盘平仓)"""
    out = []
    for sym in SYMS:
        h4 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, 2600)
        h = h4["high"].astype(float); l = h4["low"].astype(float)
        for e in per_sym_events.get(sym, []):
            risk = abs(e["trig"] - e["sl"])
            if risk <= 0: continue
            tp = e["trig"] + tp_m * risk if e["side"] == 1 else e["trig"] - tp_m * risk
            k0 = e["i"] + 1
            seg_h = h[k0:k0+42]; seg_l = l[k0:k0+42]
            if e["side"] == 1:
                kf = np.where(seg_h >= e["trig"])[0]
            else:
                kf = np.where(seg_l <= e["trig"])[0]
            if len(kf) == 0:
                out.append(None)   # 未成交
                continue
            f = kf[0]
            sh = seg_h[f:]; sl2 = seg_l[f:]
            if e["side"] == 1:
                ksl = np.where(sl2 <= e["sl"])[0]
                ktp = np.where(sh >= tp)[0]
            else:
                ksl = np.where(sh >= e["sl"])[0]
                ktp = np.where(sl2 <= tp)[0]
            if len(ksl) and (len(ktp) == 0 or ksl[0] <= ktp[0]):
                out.append(-1.0)
            elif len(ktp):
                out.append(float(tp_m))
            else:
                last = sh[-1] if e["side"] == 1 else 0
                px = (last - e["trig"]) / risk if e["side"] == 1 else (e["trig"] - last) / risk
                out.append(max(min(px, tp_m), -1.0) if False else px)  # 超时按实际浮盈亏R
            # 简化: 超时桶单独记
        if False: pass
    return out

# 上面简化逻辑有歧义, 直接重写 resolve (超时 → 记实际R, 分桶标记)
def resolve2(evs_all, tp_m, h4_cache):
    res = []
    for e in evs_all:
        sym = e["sym"]; risk = abs(e["trig"] - e["sl"])
        if risk <= 0: continue
        tp = e["trig"] + tp_m*risk if e["side"] == 1 else e["trig"] - tp_m*risk
        hh = h4_cache[sym]["h"]; ll = h4_cache[sym]["l"]
        k0 = e["i"] + 1
        sh = hh[k0:k0+42]; sl_ = ll[k0:k0+42]
        kf = np.where(sh >= e["trig"])[0] if e["side"] == 1 else np.where(sl_ <= e["trig"])[0]
        if len(kf) == 0:
            res.append((e["sym"], None, 0))   # 未成交
            continue
        f = int(kf[0])
        a = sh[f:]; b = sl_[f:]
        if e["side"] == 1:
            ksl = np.where(b <= e["sl"])[0]; ktp = np.where(a >= tp)[0]
        else:
            ksl = np.where(a >= e["sl"])[0]; ktp = np.where(b <= tp)[0]
        if len(ksl) and (len(ktp) == 0 or ksl[0] <= ktp[0]):
            res.append((sym, -1.0, 1))
        elif len(ktp):
            res.append((sym, tp_m, 1))
        else:
            px = a[-1] if len(a) else e["trig"]
            r = (px - e["trig"]) / risk if e["side"] == 1 else (e["trig"] - px) / risk
            res.append((sym, r, 2))
    return res

h4_cache = {}
for sym in SYMS:
    h4 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, 2600)
    h4_cache[sym] = {"h": h4["high"].astype(float), "l": h4["low"].astype(float)}

results = {}
for m in TP_GRID:
    res = resolve2(events, m, h4_cache)
    filled = [x for x in res if x[1] is not None]
    sl_hit = [x for x in filled if x[2] == 1 and x[1] == -1.0]
    tp_hit = [x for x in filled if x[2] == 1 and x[1] == m]
    timeout = [x for x in filled if x[2] == 2]
    wr = (len(tp_hit)) / max(len(filled), 1)
    expR = np.mean([x[1] for x in filled]) if filled else 0.0
    # 品种稳健: 各品种期望R方向
    per_sym = {}
    for s in SYMS:
        rs = [x[1] for x in filled if x[0] == s]
        per_sym[s] = round(float(np.mean(rs)), 3) if rs else None
    results[m] = {"n_filled": len(filled), "n_timeout": len(timeout),
                  "wr": round(wr, 4), "exp_R": round(float(expR), 4),
                  "per_sym": per_sym,
                  "tp_n": len(tp_hit), "sl_n": len(sl_hit), "to_n": len(timeout)}
    print(f"[TP={m}R] filled={len(filled)} wr={wr:.4f} exp_R={expR:.4f} per_sym={per_sym}")

# 同分母: 所有 TP 格共用同一事件全集, 直接比较 exp_R (天然同分母)
best_m = max(TP_GRID, key=lambda m: results[m]["exp_R"])
cur = results[2.0]
# 配对 p: 逐事件配对收益差, 符号检验
res20 = resolve2(events, 2.0, h4_cache)
resb = resolve2(events, best_m, h4_cache)
pairs = [(a[1] if a[1] is not None else 0.0, b[1] if b[1] is not None else 0.0) for a, b in zip(res20, resb)]
diffs = [b - a for a, b in pairs if (a != 0.0 or b != 0.0)]
pos = sum(1 for d in diffs if d > 0)
from math import comb
def sign_test_p(n, k):
    # 二项精确 p (双侧), k=pos
    from math import factorial
    pval = (sum(comb(n, j) for j in range(0, min(k, n)+1)) + sum(comb(n, j) for j in range(max(n-k, 0), n+1))) / 2**n
    return pval
p_sign = sign_test_p(len(diffs), pos) if diffs else None
# walk-forward 三段
wf = []
third = len(diffs) // 3
segs = [diffs[:third], diffs[third:2*third], diffs[2*third:]]
for s in segs:
    wf.append(round(float(np.mean(s)) if s else 0.0, 4))
json.dump({"tp_grid": {str(k): v for k, v in results.items()},
           "best_m": best_m, "cur_expR": cur["exp_R"], "best_expR": results[best_m]["exp_R"],
           "delta_abs": round(results[best_m]["exp_R"] - cur["exp_R"], 4),
           "sign_test_p": p_sign, "n_pairs": len(diffs), "walk_forward_3seg": wf,
           "verdict": ("接" if (results[best_m]["n_filled"] >= 300 and results[best_m]["exp_R"] > cur["exp_R"] and p_sign is not None and p_sign < 0.05 and min(wf) >= 0 and len([v for v in per if v is not None and v > 0]) >= 4) else "维持现参数"),
           "per_sym_best": results[best_m]["per_sym"]},
          open("E:/GoldstrategyEngine/data/trend_tp_scan.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("BEST:", best_m, "delta:", results[best_m]["exp_R"] - cur["exp_R"], "p:", p_sign, "wf:", wf)
mt5.shutdown()
