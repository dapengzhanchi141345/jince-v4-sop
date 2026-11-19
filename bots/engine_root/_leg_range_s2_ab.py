# -*- coding: utf-8 -*-
# 震荡腿五验 step2: 全史H4布林带事件 A/B 参数面
# 6 T1币 x ~2600根H4 (MT5, 取不到则本地CSV), 36参数组合, 同事件全集.
# 现参数 k=2.0/20/中轨TP/SL=1.0xATR. 结果 append 到 leg_range_polish.json['ab_grid']
import json, os, math
import numpy as np
import MetaTrader5 as mt5

ROOT = "E:/GoldstrategyEngine"
MT5_OK = bool(mt5.initialize()) or True
T1 = ["BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD", "XRPUSD", "LTCUSD"]
N_BARS = 2600
JP = ROOT + "/data/leg_range_polish.json"

def merge_out(rec):
    d = {}
    if os.path.exists(JP):
        try:
            d = json.load(open(JP, encoding="utf-8"))
        except Exception:
            d = {}
    d.update(rec)
    json.dump(d, open(JP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def atr_wilder(h, l, c, period=14):
    n = len(c)
    out = np.zeros(n)
    tr = np.zeros(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    out[period - 1] = tr[1:period + 1].mean()
    for i in range(period, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out

def fetch(sym, count=N_BARS):
    if MT5_OK:
        for _ in range(3):
            mt5.symbol_select(sym, True)
            r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, count)
            if r is not None and len(r) > 400:
                r = np.array(r)
                return r["high"], r["low"], r["close"], "mt5"
            import time as _t
            _t.sleep(1)
    p = os.path.join(ROOT, "data", sym + "_H4.csv")
    if os.path.exists(p):
        df = np.genfromtxt(p, delimiter=",", names=True)
        d = min(count, len(df["high"]))
        return df["high"][-d:], df["low"][-d:], df["close"][-d:], "csv"
    return None

# 1) 事件全集: k=2.0/20 布林带 上下轨触及 (审计脚本同口径)
events = []  # dict(sym, i, entry, side, atr, c, l, h, idxs=[i..i+24])
for sym in T1:
    hlc = fetch(sym)
    if hlc is None:
        print("[!] %s 无数据" % sym)
        continue
    h, l, c, src = hlc
    a14 = atr_wilder(h, l, c)
    n = len(c)
    for i in range(21, n - 3):
        if a14[i] <= 0:
            continue
        m20 = c[i - 20:i].mean(); s20 = c[i - 20:i].std()
        up, dn = m20 + 2.0 * s20, m20 - 2.0 * s20
        touch_hi = up <= l[i] and h[i] >= up          # 本bar收盘前价曾在上轨外
        touch_dn = dn >= h[i] and l[i] <= dn
        if not (touch_hi or touch_dn):
            continue
        entry = up if touch_hi else dn
        side = -1 if touch_hi else 1
        events.append(dict(sym=sym, i=i, side=side, entry=entry, atr=float(a14[i]),
                           mid=m20,
                           fwd_c=c[i + 1:i + 3], fwd_h=h[i + 1:i + 3], fwd_l=l[i + 1:i + 3],
                           prev_c=float(c[i - 1]), src=src, idx=n))
    print("[OK] %s(%s) events=%d bars=%d" % (sym, src, sum(1 for e in events if e["sym"] == sym), n))
print("[OK] total events=%d" % len(events))

# 2) 参数面
KS = [2.0, 2.5, 3.0]
PS = [20, 30]
TGS = ["mid", "half"]   # 中轨 / 0.5回撤(中轨与触带间取半)
SLS = [1.0, 1.5, 2.0]
HOLD = 24               # 最长 24根H4 ≈ 4天
SPREAD_ATR = 0.001     # 成本≈0.001×ATR(点差侵蚀近似)

def evaluate(k, p, tgt, slf):
    """同事件全集(仅取 周期p/系数k 下也构成事件者)算 胜率/期望R/最大回撤(单笔R口径累计)"""
    out = {}
    for sym in T1:
        ev = [e for e in events if e["sym"] == sym and e["src"] == "mt5"]
        hlc = CACHE[sym]
        h, l, c = hlc["h"], hlc["l"], hlc["c"]
        n = len(c)
        wins = 0; n_tot = 0; eq = 0.0; peak = 0.0; mdd_r = 0.0; expR_sum = 0.0; n_r = 0
        for i in range(max(p + 1, 60), n - HOLD - 1):
            w = c[i - p:i]
            m = w.mean(); sd = w.std()
            if sd <= 0:
                continue
            up, dn = m + k * sd, m - k * sd
            a = hlc["atr"][i]
            if a <= 0:
                continue
            touch_hi = up <= l[i] and h[i] >= up
            touch_dn = dn >= h[i] and l[i] <= dn
            if not (touch_hi or touch_dn):
                continue
            side = -1 if touch_hi else 1
            entry = up if touch_hi else dn
            if tgt == "mid":
                tp = m
            else:
                tp = (entry + m) / 2   # 0.5回撤: 入场带位与中轨中点
            rr_dist = abs(tp - entry)
            if rr_dist <= 0:
                continue
            sl = entry - slf * a * side
            risk = abs(entry - sl)
            if risk <= 0:
                continue
            win = False
            R = None
            for j in range(i + 1, min(i + 1 + HOLD, n)):
                if side == 1:
                    if h[j] >= tp:
                        win, R = True, rr_dist / risk
                        break
                    if l[j] <= sl:
                        win, R = False, -1.0
                        break
                else:
                    if l[j] <= tp:
                        win, R = True, rr_dist / risk
                        break
                    if h[j] >= sl:
                        win, R = False, -1.0
                        break
            if R is None:
                R = side * (c[min(i + HOLD, n - 1)] - entry) / risk
                win = R > 0
            R -= SPREAD_ATR  # 点差侵蚀
            n_tot += 1
            if win:
                wins += 1
            eq += R
            peak = max(peak, eq)
            mdd_r = max(mdd_r, peak - eq)
            expR_sum += R
            n_r += 1
        out[sym] = dict(n=n_tot, wr=(wins / n_tot if n_tot else None),
                         expR=(expR_sum / n_r if n_r else None), mddR=round(mdd_r, 3))
    return out

CACHE = {}
print("[OK] 拉数据缓存...")
for sym in T1:
    hlc = fetch(sym)
    if hlc is None:
        print("[!] %s 无数据" % sym)
        continue
    h, l, c, src = hlc
    CACHE[sym] = dict(h=h, l=l, c=c, atr=atr_wilder(h, l, c), src=src, n=len(c))
    print("[OK] %s src=%s n=%d" % (sym, src, len(c)))

results = {}
combos = []
for k in KS:
    for p in PS:
        for tgt in TGS:
            for slf in SLS:
                combos.append((k, p, tgt, slf))
print("[OK] combos=%d" % len(combos))
for combo in combos:
    results["%s/%s/%s/%s" % combo] = evaluate(*combo)

# 最优 (按全体 expR 均值), 现参数
def agg_expR(combo_key):
    vals = [v["expR"] for v in results[combo_key].values()
            if isinstance(v, dict) and v.get("expR") is not None]
    return float(np.mean(vals)) if vals else None

best_key = max(results.keys(), key=agg_expR)
cur_key = "2.0/20/mid/1.0"
best_expR, cur_expR = agg_expR(best_key), agg_expR(cur_key)
print("[OK] best=%s expR=%.3f | cur=%s expR=%.3f" % (best_key, best_expR, cur_key, cur_expR))
print("[OK] top5:")
for kk in sorted(results.keys(), key=agg_expR, reverse=True)[:5]:
    print("  %s expR=%.3f" % (kk, agg_expR(kk)))

ab = {
    "ts": int(__import__("time").time()),
    "n_events_total": len(events),
    "per_sym_events": {s: sum(1 for e in events if e["sym"] == s) for s in T1},
    "hold_bars": HOLD, "spread_atr": SPREAD_ATR,
    "results": results,
    "best": best_key, "best_expR": round(best_expR, 4),
    "cur": cur_key, "cur_expR": round(cur_expR, 4),
}
merge_out({"ab_grid": ab})
print("[OK] wrote ab_grid ->", JP)
mt5.shutdown()
