# -*- coding: utf-8 -*-
# 日内腿 edge 排雷: 滑点敏感性 + walk-forward 三段 (统一引擎 live_intra 口径)
import json, sys
import numpy as np
import MetaTrader5 as mt5
sys.path.insert(0, "E:/GoldstrategyEngine"); sys.path.insert(0, "E:/GoldstrategyEngine/multi_agent/trading")
from backtest_engine import trade
import intraday_swing as isw

SYMS = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD"]
mt5.initialize(); assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")

def load(sym, tf, n):
    r = mt5.copy_rates_from_pos(sym, tf, 0, n)
    if r is None: return None
    return dict(t=r["time"].astype(np.int64), h=r["high"].astype(float),
                l=r["low"].astype(float), c=r["close"].astype(float),
                high=r["high"].astype(float), low=r["low"].astype(float))

def h1_atr(sym, ts):
    h1 = load(sym, mt5.TIMEFRAME_H1, 5000)
    if h1 is None: return 1e-9
    idx = np.searchsorted(h1["t"], int(ts), side="left")
    seg = slice(max(0, idx-30), idx+1)
    h,l,c = h1["h"][seg], h1["l"][seg], h1["c"][seg]
    if len(c) < 15: return 1e-9
    a = isw.atr(h, l, c)
    return float(a[-1]) if a[-1] > 0 else 1e-9

events = []   # (ts, sym, R)
for sym in SYMS:
    h4 = load(sym, mt5.TIMEFRAME_H4, 2600)
    d1 = load(sym, mt5.TIMEFRAME_D1, 500)
    if not (h4 and d1): continue
    hh, ll, cc, tt = h4["h"], h4["l"], h4["c"], h4["t"]
    for i in range(60, len(cc)-2):
        tsv = int(tt[i])
        hod = tsv % 86400
        if hod < 8*3600 or hod >= 16*3600: continue
        d1sub = d1["t"] + 86400 <= tsv
        if not d1sub.any(): continue
        j = np.where(d1sub)[0][-1]
        if j < 1: continue
        pdh, pdl = float(d1["high"][j]), float(d1["low"][j])
        h1a = h1_atr(sym, tsv)
        k0 = i + 1
        r1 = trade(-1, hh, ll, cc, tt, pdh*1.002, pdh*1.002 + 0.75*h1a, (pdh+pdl)/2, k0, 42, "live_intra", h2=0.25, order_type="stop")
        if r1 and r1["filled"]: events.append((tsv, sym, r1["R"]))
        r2 = trade(+1, hh, ll, cc, tt, pdl*0.998, pdl*0.998 - 0.75*h1a, (pdh+pdl)/2, k0, 42, "live_intra", h2=0.25, order_type="stop")
        if r2 and r2["filled"]: events.append((tsv, sym, r2["R"]))

Rs = np.array([e[2] for e in events]); ts_all = sorted(e[0] for e in events)
n = len(Rs)
print(f"总事件 n={n}")

# ── 滑点敏感性: 每笔扣 s (0.1/0.25/0.5R, 代表成交价+止损单侧滑点) ──
slip = {}
for s in [0.0, 0.1, 0.25, 0.5, 1.0]:
    adj = Rs - s
    slip[str(s)] = {"n": n, "exp_R": round(float(adj.mean()), 4), "wr": round(float((adj > 0).mean()), 4)}
    print(f"滑点-{s}R: 期望R={adj.mean():+.4f} wr={(adj>0).mean():.3f}")

# ── walk-forward 三段 (零滑点) ──
ts_arr = np.array(ts_all)
b1 = ts_arr.min() + (ts_arr.max()-ts_arr.min())//3
b2 = ts_arr.min() + 2*(ts_arr.max()-ts_arr.min())//3
segs = {}
for name, lo, hi in [("前段", ts_arr.min(), b1), ("中段", b1, b2), ("后段", b2, ts_arr.max())]:
    Rseg = np.array([e[2] for e in events if lo <= e[0] < hi])
    segs[name] = {"n": len(Rseg), "exp_R": round(float(Rseg.mean()),4) if len(Rseg) else None,
                  "exp_R_slip0.5": round(float((Rseg-0.5).mean()),4) if len(Rseg) else None}
    print(f"wf {name}: n={len(Rseg)} 期望R={Rseg.mean():+.4f} (扣0.5R滑点={(Rseg-0.5).mean():+.4f})")

# 品种×滑点
per = {}
for s in SYMS:
    Rs_s = np.array([e[2] for e in events if e[1]==s])
    per[s] = {"n": len(Rs_s), "exp_R": round(float(Rs_s.mean()),3), "exp_R_slip0.5": round(float((Rs_s-0.5).mean()),3)}

json.dump({"slippage_sensitivity": slip, "walk_forward_3seg": segs, "per_sym": per,
           "verdict": ("接" if (n>=1000 and (Rs-0.5).mean()>0.5 and all(v.get("exp_R") and v["exp_R"]>0 for v in segs.values())) else "观察")},
          open("E:/GoldstrategyEngine/data/intra_edge_audit.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("verdict:", "接" if ((Rs-0.5).mean()>0.5 and all(v.get("exp_R") and v["exp_R"]>0 for v in segs.values())) else "观察")
mt5.shutdown()
