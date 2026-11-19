# -*- coding: utf-8 -*-
# 趋势腿出场协议扫描 (统一引擎口径, 事件全集 N 固定同分母, 已禁 L2 — 与 live 现状一致)
# 事件: D1方向闸 + Donchian20×1.003 Stop, H4 全史2600根×6币T1, 前向42根
# 协议: P0 纯TP/SL | P1 +吊灯 | P2 +0.5R保本 | P3 吊灯+保本 | P4 吊灯+保本+8根无进展 | P5 半仓1R锁定+余仓吊灯
# 网格: TP{1.5,2,3}R × SL{1.5,2,2.5}×ATR (P0口径)
import json, sys
import numpy as np
import MetaTrader5 as mt5
sys.path.insert(0, "E:/GoldstrategyEngine"); sys.path.insert(0, "E:/GoldstrategyEngine/multi_agent/trading")
from backtest_engine import symmetric_audit
import intraday_swing as isw

SYMS = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD"]
mt5.initialize(); assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")

def load(sym, tf, n):
    r = mt5.copy_rates_from_pos(sym, tf, 0, n)
    if r is None: return None
    return dict(t=r["time"].astype(np.int64), h=r["high"].astype(float),
                l=r["low"].astype(float), c=r["close"].astype(float))

CACHE, EV = {}, []
for sym in SYMS:
    h4 = load(sym, mt5.TIMEFRAME_H4, 2600)
    d1 = load(sym, mt5.TIMEFRAME_D1, 500)
    if not (h4 and d1): continue
    hh, ll, cc, tt = h4["h"], h4["l"], h4["c"], h4["t"]
    dc_h, dc_l = isw.donchian(hh, ll, 20)
    a14 = isw.atr(hh, ll, cc)
    d1c, d1t = d1["c"], d1["t"]
    CACHE[sym] = (hh, ll, cc, tt)
    for i in range(60, len(cc)-1):
        ts_close = int(tt[i]) + 14400
        m = np.where(d1t + 86400 <= ts_close)[0]
        if len(m) == 0: continue
        j = m[-1]
        if j < 1: continue
        g = 1 if d1c[j] > d1c[j-1] else 0
        if a14[i-1] <= 0: continue
        k0 = i + 1
        if g == 1 and dc_h[i-1] > 0 and cc[i-1] < dc_h[i-1]*1.003:
            EV.append((sym, +1, k0, float(dc_h[i-1]*1.003), float(a14[i-1]), int(tt[i])))
        elif g == 0 and dc_l[i-1] > 0 and cc[i-1] > dc_l[i-1]/1.003:
            EV.append((sym, -1, k0, float(dc_l[i-1]/1.003), float(a14[i-1]), int(tt[i])))
print(f"事件全集 N={len(EV)}")

def replay_one(sym, side, k0, trig, a, sl_atr, tp_r, chand, be, timestop, split):
    """自实现 (保守同根: 先SL; limit语义不适用, 全Stop). 返回 (R, filled, ts)"""
    hh, ll, cc, tt = CACHE[sym]
    risk = sl_atr * a
    if risk <= 0: return 0.0, False
    sl0 = trig - side * risk
    tp = trig + side * tp_r * risk
    d = 1 if side > 0 else -1
    fill_k = None
    for k in range(k0, min(k0 + 4, len(hh))):
        if (hh[k] >= trig) if d > 0 else (ll[k] <= trig):
            fill_k = k; break
    if fill_k is None: return 0.0, False
    if split:
        peak = trig; R = None; half1 = False
        for k in range(fill_k, min(fill_k + 42, len(cc))):
            kh, kl, kc = hh[k], ll[k], cc[k]
            profit_r = d*(kc - trig)/risk
            new_sl = sl0
            if profit_r >= 1.6:
                peak = max(peak, kh) if d > 0 else min(peak, kl)
                cand = peak - 3*a if d > 0 else peak + 3*a
                new_sl = cand if (d > 0 and cand > new_sl) or (d < 0 and cand < new_sl) else new_sl
            if not half1 and profit_r >= 1.0: half1 = True
            hit_sl = (kl <= new_sl) if d > 0 else (kh >= new_sl)
            hit_tp = (kh >= tp) if d > 0 else (kl <= tp)
            if hit_sl:
                R = (0.5*1.0 + 0.5*(-1.0)) if half1 else -1.0
                break
            if hit_tp:
                R = 0.5*1.0 + 0.5*tp_r
                break
        if R is None:
            last_r = d*(cc[min(fill_k + 41, len(cc)-1)] - trig)/risk
            R = 0.5*1.0 + 0.5*max(min(last_r, tp_r), -1.0) if half1 else max(min(last_r, tp_r), -1.0)
        return R, True
    peak = trig; R = None
    for k in range(fill_k, min(fill_k + 42, len(cc))):
        kh, kl, kc = hh[k], ll[k], cc[k]
        profit_r = d*(kc - trig)/risk
        new_sl = sl0
        if chand and profit_r >= 1.6:
            peak = max(peak, kh) if d > 0 else min(peak, kl)
            cand = peak - 3*a if d > 0 else peak + 3*a
            new_sl = cand if (d > 0 and cand > new_sl) or (d < 0 and cand < new_sl) else new_sl
        if be and profit_r >= 0.5:
            new_sl = trig if (d > 0 and new_sl < trig) or (d < 0 and new_sl > trig) else new_sl
        hit_sl = (kl <= new_sl) if d > 0 else (kh >= new_sl)
        hit_tp = (kh >= tp) if d > 0 else (kl <= tp)
        if hit_sl:
            R = 0.0 if (new_sl == trig) else -1.0
            break
        if timestop and k - fill_k >= 8 and profit_r < 0.3:
            R = max(min(profit_r, tp_r), -1.0)
            break
        if hit_tp:
            R = tp_r
            break
    if R is None:
        last_r = d*(cc[min(fill_k + 41, len(cc)-1)] - trig)/risk
        R = max(min(last_r, tp_r), -1.0)
    return R, True

def run(name, chand=False, be=False, timestop=False, split=False, tp_r=2.0, sl_atr=2.0):
    Rs, ts_all = [], []
    for (sym, side, k0, trig, a, ts) in EV:
        R, filled = replay_one(sym, side, k0, trig, a, sl_atr, tp_r, chand, be, timestop, split)
        if filled: Rs.append(R); ts_all.append(ts)
    arr = np.array(Rs)
    tmin, tmax = min(ts_all), max(ts_all)
    b1 = tmin + (tmax-tmin)//3; b2 = tmin + 2*(tmax-tmin)//3
    wf = [float(np.mean([r for r, t in zip(Rs, ts_all) if t < b1])),
          float(np.mean([r for r, t in zip(Rs, ts_all) if b1 <= t < b2])),
          float(np.mean([r for r, t in zip(Rs, ts_all) if t >= b2]))]
    # 品种稳健在下方 per_sym 段单独重放 (各品种事件子集)
    return {"n": len(Rs), "exp_R": round(float(arr.mean()), 4), "wr": round(float((arr>0).mean()), 4),
            "wf3": [round(x, 4) for x in wf], "wf_all_pos": all(x > 0 for x in wf)}

out = {}
for name, kw in [
    ("P0_纯TPSL", {}),
    ("P1_吊灯", dict(chand=True)),
    ("P2_保本0.5R", dict(be=True)),
    ("P3_吊灯+保本", dict(chand=True, be=True)),
    ("P4_P3+8根无进展", dict(chand=True, be=True, timestop=True)),
    ("P5_半仓1R+余仓吊灯", dict(split=True)),
]:
    out[name] = run(name, **kw)
    print(f"[{name}] {out[name]}")

# 品种稳健: 对 P0/P3 按品种重放 (事件子集, 各品种自身同分母)
for name, kw in [("P0_纯TPSL", {}), ("P3_吊灯+保本", dict(chand=True, be=True))]:
    per_sym = {}
    for s in SYMS:
        sub = [e for e in EV if e[0] == s]
        Rs = []
        for (sym_, side, k0, trig, a, ts) in sub:
            R, filled = replay_one(sym_, side, k0, trig, a, 2.0, 2.0, kw.get("chand", False), kw.get("be", False), False, False)
            if filled: Rs.append(R)
        per_sym[s] = {"n": len(Rs), "exp_R": round(float(np.mean(Rs)), 4) if Rs else None}
    out[name + "_per_sym"] = per_sym
    pos = sum(1 for v in per_sym.values() if (v["exp_R"] or 0) > 0)
    print(f"[{name} 品种] 正期望={pos}/6 {per_sym}")

# TP/SL 网格 (P0 口径, 事件全集)
grid = {}
for tpr in [1.5, 2.0, 3.0]:
    for sla in [1.5, 2.0, 2.5]:
        g = run(f"G_{tpr}_{sla}", tp_r=tpr, sl_atr=sla)
        grid[f"TP{tpr}R/SL{sla}ATR"] = g
out["tp_sl_grid"] = grid
for k, v in grid.items(): print(f"[{k}] exp_R={v['exp_R']} wf3={v['wf3']}")

# 对称审计抽检
hh, ll, cc, tt = CACHE["BTCUSD"]
out["对称审计"] = symmetric_audit(hh, ll, cc, tt, float(cc[100]), float(cc[99]), float(cc[110]), 101, 20, "tp_sl_only", "stop")
json.dump(out, open("E:/GoldstrategyEngine/data/trend_exit_sweep.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("written data/trend_exit_sweep.json")
mt5.shutdown()
