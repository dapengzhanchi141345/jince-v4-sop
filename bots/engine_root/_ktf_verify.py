
# -*- coding: utf-8 -*-
# K线周期匹配五验 (干净重写): 趋势周期(D1/H4) + 进场周期(H4/H1) + 持仓周期
# 因果铁律: 突破信号用已完结K线(shift1); D1方向闸只用已完结D1; 成交/出场逐根回放无未来函数
import json
import numpy as np
import MetaTrader5 as mt5

SYMS = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD","XAUUSD"]
TF = {"D1": mt5.TIMEFRAME_D1, "H4": mt5.TIMEFRAME_H4, "H1": mt5.TIMEFRAME_H1}
BARSEC = {"D1": 86400, "H4": 14400, "H1": 3600}
mt5.initialize(); assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")

def load(sym, tf, n):
    r = mt5.copy_rates_from_pos(sym, tf, 0, n)
    return None if r is None else dict(t=r["time"].astype(np.int64), h=r["high"].astype(float),
                                        l=r["low"].astype(float), c=r["close"].astype(float))

def d1gate(d1, ts, side_hint):
    """ts时刻已完结D1方向: 1=多 0=空 None=无. 根k已完结 iff k.t+86400<=ts."""
    ok = d1["t"] + 86400 <= ts
    if not ok.any(): return None
    idx = np.where(ok)[0][-1]
    if idx < 1: return None
    return 1 if d1["c"][idx] > d1["c"][idx-1] else 0

def donc20(h, l):
    hi = np.zeros_like(h); lo = np.zeros_like(h)
    for i in range(20, len(h)):
        hi[i] = max(h[i-19:i+1]); lo[i] = min(l[i-19:i+1])
    return hi, lo

def atr_series(h, l, c, p=14):
    tr = np.empty(len(c)); tr[0] = h[0]-l[0]
    tr[1:] = np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1])))
    out = np.zeros(len(c))
    if len(c) <= p: return out
    out[p] = tr[1:p+1].mean()
    for i in range(p+1, len(c)):
        out[i] = (out[i-1]*(p-1) + tr[i])/p
    return out

def bt(sym, tf_trend, tf_entry, n_days=450, hold_h1=24, max_hold_h1=72):
    """趋势腿回放: 趋势周期K线收盘触发Donchian突破(1.003缓冲, D1方向闸) → 次根起在进场周期找成交
    → 吊灯SL=突破点∓2×H1-ATR, TP=2R, 超时max_hold_h1根H1按最后收盘平仓. 返回每单R."""
    trend = load(sym, TF[tf_trend], 900)
    h1    = load(sym, TF["H1"], 5500)
    d1    = load(sym, TF["D1"], 700)
    if not (trend and h1 and d1): return []
    th, tl, tc, tt = trend["h"], trend["l"], trend["c"], trend["t"]
    eh, el, ec, et = h1["h"], h1["l"], h1["c"], h1["t"]
    atr1 = atr_series(eh, el, ec)
    hi, lo = donc20(th, tl)
    H1SEC = 3600
    res = []
    for i in range(25, len(th)-1):
        sig_ts = int(tt[i]) + BARSEC[tf_trend]          # 该K线收盘时刻
        d = d1gate(d1, sig_ts, 1)
        if d is None or hi[i-1] <= 0 or lo[i-1] <= 0: continue
        a1 = atr1[np.searchsorted(et, sig_ts, side="left")] or 1e-9
        if a1 <= 0: continue
        if d == 1 and tt[i] < hi[i-1]*1.003:           # 价格回落到20期高点下方 → 等突破
            entry = hi[i-1]*1.003; side = 1
        elif d == 0 and tt[i] > lo[i-1]/1.003:
            entry = lo[i-1]/1.003; side = -1
        else:
            continue
        sl = entry - 2*a1 if side == 1 else entry + 2*a1
        tp = entry + 2*(entry-sl) if side == 1 else entry - 2*(sl-entry)
        # 在进场周期找成交 (sig_ts 后 max_hold_h1 根H1内)
        i0 = np.searchsorted(et, sig_ts, side="left")
        seg_h = eh[i0:i0+max_hold_h1]; seg_l = el[i0:i0+max_hold_h1]
        if side == 1:
            f = np.where(seg_h >= entry)[0]
        else:
            f = np.where(seg_l <= entry)[0]
        if len(f) == 0: continue
        fi = f[0]
        fill_ts = int(et[i0+fi]); fill_px = float(seg_h[fi] if side == 1 else seg_l[fi])
        # 出场: 吊灯SL 或 TP 或 超时 hold_h1 根
        i1 = i0 + fi
        exit_px, win = fill_px, False
        seg2_h = eh[i1+1:min(i1+1+max_hold_h1, len(eh))]
        seg2_l = el[i1+1:min(i1+1+max_hold_h1, len(el))]
        if side == 1:
            k_sl = np.where(seg2_l <= sl)[0]; k_tp = np.where(seg2_h >= tp)[0]
        else:
            k_sl = np.where(seg2_h >= sl)[0]; k_tp = np.where(seg2_l <= tp)[0]
        if len(k_sl) and (len(k_tp)==0 or k_sl[0] < k_tp[0]):
            exit_px, win = sl, False
        elif len(k_tp):
            exit_px, win = tp, True
        elif len(seg2_h) == 0:
            exit_px = fill_px
        else:
            jh = min(hold_h1, len(seg2_h)-1)
            exit_px = float(eh[i1+1+jh]); win = exit_px > fill_px if side == 1 else exit_px < fill_px
        risk = abs(fill_px - sl)
        if risk <= 0: continue
        pnl = (exit_px - fill_px)/risk if side == 1 else (fill_px - exit_px)/risk
        res.append(pnl)
    return res

COMBOS = {
  "D1趋势+H4进场+72h": ("D1","H4",72),
  "D1趋势+H1进场+72h": ("D1","H1",72),
  "H4趋势+H1进场+48h": ("H4","H1",48),
  "H4趋势+H4进场+48h": ("H4","H4",48),
}
out = {}
for name,(tt_,te,hold) in COMBOS.items():
    per, allr = {}, []
    for s in SYMS:
        r = bt(s, tt_, te, hold_h1=hold)
        if r:
            arrs = np.array(r, dtype=float)
            per[s] = {"n": len(r), "wr": round(float((arrs>0).mean()),3), "exp_R": round(float(arrs.mean()),3)}
            allr.extend(r)
    arr = np.array(allr)
    out[name] = {"per_sym": per, "n_total": len(arr),
                 "wr": round(float((arr>0).mean()),4) if len(arr) else None,
                 "exp_R": round(float(arr.mean()),4) if len(arr) else None}
    print(f"[OK] {name}: n={len(arr)} wr={out[name]['wr']} exp_R={out[name]['exp_R']}")
json.dump(out, open("E:/GoldstrategyEngine/data/ktf_match_verify.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("written data/ktf_match_verify.json")
mt5.shutdown()
