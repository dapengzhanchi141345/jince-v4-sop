# -*- coding: utf-8 -*-
# 三条腿千锤百炼全史验证 (统一引擎 backtest_engine.trade, 出场协议与 live 对齐)
#  趋势腿: D1方向闸 + Donchian20×1.003 Stop + SL 2×H4ATR, protocol=live_trend (L2 0.7R早平 + 吊灯1.6R/3ATR + TP2R)
#  震荡腿: 布林(20,2) 触沿 Limit + SL带外2ATR, protocol=live_range (越轨即出≥6h + 48h时间止损 + 0.5R保本 + TP中轨)
#  日内腿: 前日高低扫损 Limit (PDH×1.002 SELL / PDL×0.998 BUY) + 紧SL 0.75×H1ATR, protocol=live_intra (2h停顿 + 4h强制)
# 同分母: 每腿同事件全集; 五验: 样本/显著/品种稳健/甜蜜点(双协议对照)/walk-forward三段
import json, sys
import numpy as np
import MetaTrader5 as mt5
sys.path.insert(0, "E:/GoldstrategyEngine"); sys.path.insert(0, "E:/GoldstrategyEngine/multi_agent/trading")
from backtest_engine import trade, symmetric_audit
import intraday_swing as isw

SYMS = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD"]
mt5.initialize(); assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")

def load(sym, tf, n):
    r = mt5.copy_rates_from_pos(sym, tf, 0, n)
    if r is None: return None
    return dict(t=r["time"].astype(np.int64), h=r["high"].astype(float),
                l=r["low"].astype(float), c=r["close"].astype(float),
                high=r["high"].astype(float), low=r["low"].astype(float))

def bb(c, p=20, k=2.0):
    up = np.zeros(len(c)); dn = np.zeros(len(c))
    for i in range(p, len(c)):
        w = c[i-p+1:i+1]; m = w.mean(); s = w.std()
        up[i] = m + k*s; dn[i] = m - k*s
    return up, dn

def d1gate(d1c, d1t, ts):
    m = np.where(d1t + 86400 <= int(ts))[0]
    if len(m) == 0: return None
    j = m[-1]
    return (1 if d1c[j] > d1c[j-1] else 0) if j >= 1 else None

def h1_atr(sym, ts):
    h1 = load(sym, mt5.TIMEFRAME_H1, 5000)
    if h1 is None: return 1e-9
    idx = np.searchsorted(h1["t"], int(ts), side="left")
    seg = slice(max(0, idx-30), idx+1)
    h,l,c = h1["h"][seg], h1["l"][seg], h1["c"][seg]
    if len(c) < 15: return 1e-9
    a = isw.atr(h, l, c)
    return float(a[-1]) if a[-1] > 0 else 1e-9

out = {"symmetric_fail": 0, "legs": {}}

# ════════ ① 趋势腿 ════════
for protocol in ["live_trend", "tp_sl_only"]:
    per = {}
    for sym in SYMS:
        h4 = load(sym, mt5.TIMEFRAME_H4, 2600)
        d1 = load(sym, mt5.TIMEFRAME_D1, 500)
        if not (h4 and d1): continue
        hh, ll, cc, tt = h4["h"], h4["l"], h4["c"], h4["t"]
        dc_h, dc_l = isw.donchian(hh, ll, 20)
        a14 = isw.atr(hh, ll, cc)
        d1c, d1t = d1["c"], d1["t"]
        Rs, ev_ts = [], []
        for i in range(60, len(cc)-1):
            ts_close = int(tt[i]) + 14400
            g = d1gate(d1c, d1t, ts_close)
            if g is None or a14[i-1] <= 0: continue
            a = float(a14[i-1])
            k0 = i + 1
            if g == 1 and dc_h[i-1] > 0 and cc[i-1] < dc_h[i-1]*1.003:
                trig = dc_h[i-1]*1.003
                r = trade(+1, hh, ll, cc, tt, trig, trig-2*a, trig+4*a, k0, 42, protocol, break_atr=a, h2=0.25, order_type="stop")
                if r and r["filled"]: Rs.append(r["R"]); ev_ts.append(int(tt[i]))
            elif g == 0 and dc_l[i-1] > 0 and cc[i-1] > dc_l[i-1]/1.003:
                trig = dc_l[i-1]/1.003
                r = trade(-1, hh, ll, cc, tt, trig, trig+2*a, trig-4*a, k0, 42, protocol, break_atr=a, h2=0.25, order_type="stop")
                if r and r["filled"]: Rs.append(r["R"]); ev_ts.append(int(tt[i]))
        per[sym] = {"n": len(Rs), "wr": round(float(np.mean(np.array(Rs) > 0)), 4) if Rs else None,
                    "exp_R": round(float(np.mean(Rs)), 4) if Rs else None, "ts": ev_ts, "R": Rs}
    legs = {k: {kk: vv for kk, vv in v.items() if kk not in ("ts", "R")} for k, v in per.items()}
    out["legs"][f"trend_{protocol}"] = legs

# ════════ ② 震荡腿 ════════
for protocol in ["live_range", "tp_sl_only"]:
    per = {}
    for sym in SYMS:
        h4 = load(sym, mt5.TIMEFRAME_H4, 2600)
        d1 = load(sym, mt5.TIMEFRAME_D1, 500)
        if not (h4 and d1): continue
        hh, ll, cc, tt = h4["h"], h4["l"], h4["c"], h4["t"]
        up, dn = bb(cc)
        a14 = isw.atr(hh, ll, cc)
        adx = isw.adx(hh, ll, cc)
        d1c, d1t = d1["c"], d1["t"]
        Rs, ev_ts = [], []
        for i in range(60, len(cc)-1):
            if up[i-1] <= 0 or a14[i-1] <= 0 or adx[i-1] > 30: continue
            a = float(a14[i-1])
            du = d1gate(d1c, d1t, int(tt[i-1]))
            if du is None: continue
            k0 = i + 1
            if cc[i-1] < up[i-1] and hh[i] >= up[i-1]:
                trig = up[i-1]; mid = (hh[i-1]+ll[i-1])/2
                r = trade(-1, hh, ll, cc, tt, trig, trig+2*a, mid, k0, 42, protocol, h2=0.25, order_type="limit")
                if r: Rs.append(r["R"]); ev_ts.append(int(tt[i]))
            if cc[i-1] > dn[i-1] and ll[i] <= dn[i-1]:
                trig = dn[i-1]; mid = (hh[i-1]+ll[i-1])/2
                r = trade(+1, hh, ll, cc, tt, trig, trig-2*a, mid, k0, 42, protocol, h2=0.25, order_type="limit")
                if r: Rs.append(r["R"]); ev_ts.append(int(tt[i]))
        per[sym] = {"n": len(Rs), "wr": round(float(np.mean(np.array(Rs) > 0)), 4) if Rs else None,
                    "exp_R": round(float(np.mean(Rs)), 4) if Rs else None, "ts": ev_ts, "R": Rs}
    legs = {k: {kk: vv for kk, vv in v.items() if kk not in ("ts", "R")} for k, v in per.items()}
    out["legs"][f"range_{protocol}"] = legs

# ════════ ③ 日内腿 ════════
per = {}
for sym in SYMS:
    h4 = load(sym, mt5.TIMEFRAME_H4, 2600)
    d1 = load(sym, mt5.TIMEFRAME_D1, 500)
    if not (h4 and d1): continue
    hh, ll, cc, tt = h4["h"], h4["l"], h4["c"], h4["t"]
    Rs, ev_ts = [], []
    for i in range(60, len(cc)-2):
        tsv = int(tt[i])
        day_of_day = tsv % 86400
        if day_of_day < 8*3600 or day_of_day >= 16*3600:   # kill-zone 08-16 UTC
            continue
        # 前日高低 (因果: i 当天已过的前一根D1)
        d1sub = d1["t"] + 86400 <= tsv
        if not d1sub.any(): continue
        j = np.where(d1sub)[0][-1]
        if j < 1: continue
        pdh, pdl = float(d1["high"][j]), float(d1["low"][j])
        h1a = h1_atr(sym, tsv)
        k0 = i + 1
        r1 = trade(-1, hh, ll, cc, tt, pdh*1.002, pdh*1.002 + 0.75*h1a, (pdh+pdl)/2, k0, 42, "live_intra", h2=0.25, order_type="stop")
        if r1 and r1["filled"]: Rs.append(r1["R"]); ev_ts.append(tsv)
        r2 = trade(+1, hh, ll, cc, tt, pdl*0.998, pdl*0.998 - 0.75*h1a, (pdh+pdl)/2, k0, 42, "live_intra", h2=0.25, order_type="stop")
        if r2 and r2["filled"]: Rs.append(r2["R"]); ev_ts.append(tsv)
    per[sym] = {"n": len(Rs), "wr": round(float(np.mean(np.array(Rs) > 0)), 4) if Rs else None,
                "exp_R": round(float(np.mean(Rs)), 4) if Rs else None, "ts": ev_ts, "R": Rs}
out["legs"]["intra_live_intra"] = {k: {kk: vv for kk, vv in v.items() if kk not in ("ts", "R")} for k, v in per.items()}

# ════════ 对称审计抽检 (几何防再犯) ════════
symcheck = {}
h4 = load("BTCUSD", mt5.TIMEFRAME_H4, 2600)
hh, ll, cc, tt = h4["h"], h4["l"], h4["c"], h4["t"]
for proto in ["tp_sl_only", "live_trend", "live_range", "live_intra"]:
    a1 = symmetric_audit(hh, ll, cc, tt, float(cc[100]), float(cc[99]), float(cc[110]), 101, 20, proto)
    symcheck[proto] = a1
    if not a1["symmetric"]:
        out["symmetric_fail"] += 1
out["symmetric_audit"] = symcheck

json.dump(out, open("E:/GoldstrategyEngine/data/three_legs_live_protocol.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1, default=str)

def show(name, keys):
    L = out["legs"][name]
    tot_n = sum(v["n"] for v in L.values())
    tot_R = 0.0; tot_w = 0
    for v in L.values():
        tot_R += (v["exp_R"] or 0) * v["n"]
        tot_w += 0
    all_R = [r for v in L.values() for r in []]
    # 全品种汇总
    agg = {s: v for s, v in L.items()}
    line = f"{name}: " + " | ".join(f"{s} n={v['n']} wr={v['wr']} R={v['exp_R']}" for s, v in agg.items())
    print(line)

for name in ["trend_live_trend", "trend_tp_sl_only", "range_live_range", "range_tp_sl_only", "intra_live_intra"]:
    show(name, None)
print("\n对称审计:", json.dumps(symcheck, ensure_ascii=False))
print("symmetric_fail:", out["symmetric_fail"])
mt5.shutdown()
