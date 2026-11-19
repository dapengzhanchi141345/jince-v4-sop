# -*- coding: utf-8 -*-
# H1 周期回放: 趋势腿几何 (Donchian20x1.003 + D1方向闸) 在 H1 K线上逐根回放
# 严格因果: 指标全用 i 之前数据; 事件检测+回放都在 H1; 前向42根走完->收盘计R(不截断)
# 对称自检: mirror(h'=-l, l'=-h, c'=-c, trig'=-trig, d1bull<->d1bear) 时
#   镜像SELL事件序列 == 原BUY事件序列 逐事件精确相等
import json, os
import numpy as np
import MetaTrader5 as mt5

ROOT = r"E:/GoldstrategyEngine"
SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]
SLMS = [1.5, 2.0, 3.0]
SLM_MAIN = 2.0
FILL_WIN = 4      # 含触发根, 前向4根内成交
RESOLVE_WIN = 42  # 含触发根, 走完42根
SLA = 1.003

def fetch(sym):
    d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 3000)
    h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 50000)
    return d1, h1

def atr_wilder(h, l, c, period=14):
    n = len(c)
    tr = np.empty(n, dtype=np.float64)
    tr[0] = h[0] - l[0]
    if n > 1:
        pc = c[:-1]
        tr[1:] = np.maximum(h[1:] - l[1:], np.abs(h[1:] - pc))
        tr[1:] = np.maximum(tr[1:], np.abs(l[1:] - pc))
    atr = np.full(n, np.nan)
    if n >= period:
        v = tr[1:period + 1].mean()
        atr[period] = v
        for i in range(period + 1, n):
            v = (v * (period - 1) + tr[i]) / period
            atr[i] = v
    return atr

def d1_gate(ht, d1):
    """每根 H1 bar i: 最后一个已完结 D1 bar (t_d1+86400 <= ts_h1_i) close vs prev_close.
    bull = cc>cc_prev, bear = cc<cc_prev (因果: 只用已完结日)."""
    n = len(ht)
    bull = np.zeros(n, dtype=bool)
    bear = np.zeros(n, dtype=bool)
    t = d1["time"].astype(np.int64)
    cc = d1["close"].astype(np.float64)
    if len(t) < 2:
        return bull, bear
    idx = np.searchsorted(t, ht.astype(np.int64) - 86400, side="right") - 1
    ok = idx >= 1
    if ok.any():
        bull[ok] = cc[idx[ok]] > cc[idx[ok] - 1]
        bear[ok] = cc[idx[ok]] < cc[idx[ok] - 1]
    return bull, bear

def donchian_prev(h, l):
    """dc_hi[i] = max(h[i-20:i]), dc_lo[i] = min(l[i-20:i]), i>=20, 因果 (不含 i)."""
    n = len(h)
    dc_hi = np.full(n, np.nan)
    dc_lo = np.full(n, np.nan)
    for i in range(20, n):
        dc_hi[i] = h[i - 20:i].max()
        dc_lo[i] = l[i - 20:i].min()
    return dc_hi, dc_lo

def replay(h, l, c, bull, bear, SLM, t=None):
    """返回 list of (t_event, R, filled). 未成交记 R=0.0, filled=False.
    事件 i: 多头 trig=dc_hi[i-1]*1.003 且 c[i-1]<trig 且 d1_bull; 空头对称.
    Stop成交: BUY等 h>=trig / SELL等 l<=trig, 前向 FILL_WIN 根内未成交记0.
    SL=trig∓SLM*ATR(因果atr[i]); TP=trig±2R; 同根双触判SL; 前向 RESOLVE_WIN 根走完收盘计R(不截断)."""
    n = len(c)
    dc_hi, dc_lo = donchian_prev(h, l)
    atr = atr_wilder(h, l, c)
    events = []
    i = 1
    while i < n - RESOLVE_WIN + 1:
        trig = None
        side = 0
        if not np.isnan(dc_hi[i - 1]) and bull[i] and c[i - 1] < dc_hi[i - 1] * SLA:
            trig, side = dc_hi[i - 1] * SLA, 1
        elif not np.isnan(dc_lo[i - 1]) and bear[i] and c[i - 1] > dc_lo[i - 1] / SLA:
            trig, side = dc_lo[i - 1] / SLA, -1
        if trig is None:
            i += 1
            continue
        a_i = atr[i]
        if np.isnan(a_i) or a_i <= 0:
            i += 1
            continue
        R = SLM * a_i
        sl = trig - R if side == 1 else trig + R
        tp = trig + 2 * R if side == 1 else trig - 2 * R
        filled = False
        for j in range(i, min(i + FILL_WIN, n)):
            if side == 1 and h[j] >= trig:
                filled = True
                break
            if side == -1 and l[j] <= trig:
                filled = True
                break
        te = int(t[i]) if t is not None else 0
        if not filled:
            events.append((te, 0.0, False))
            i += 1
            continue
        res = None
        for j in range(i, min(i + RESOLVE_WIN, n)):
            sl_hit = (l[j] <= sl) if side == 1 else (h[j] >= sl)
            tp_hit = (h[j] >= tp) if side == 1 else (l[j] <= tp)
            if sl_hit:
                res = -1.0
                break
            if tp_hit:
                res = 1.0
                break
        if res is None:
            last = c[min(i + RESOLVE_WIN, n) - 1]
            res = float((last - trig) / R * side)
        events.append((te, float(res), True))
        i += RESOLVE_WIN
    return events

def main():
    if not mt5.terminal_info():
        mt5.initialize()
    if not mt5.login(60137964, password="", server="TradeMaxGlobal-Demo"):
        print("LOGIN FAILED")
        return
    out = {"tf": "H1"}
    per_sym = {}
    all_events_main = []   # (sym, t, R, filled)
    cache = {}
    for sym in SYMS:
        d1, h1 = fetch(sym)
        if h1 is None or d1 is None:
            print(f"[{sym}] data fetch failed: {mt5.last_error()}")
            continue
        t = h1["time"].astype(np.int64)
        h = h1["high"].astype(np.float64)
        l = h1["low"].astype(np.float64)
        c = h1["close"].astype(np.float64)
        bull, bear = d1_gate(t, d1)
        cache[sym] = (h, l, c, bull, bear, t)
        evs_main = replay(h, l, c, bull, bear, SLM_MAIN, t)
        rs = [r for (_, r, _) in evs_main]
        filled_n = sum(1 for (_, _, f) in evs_main if f)
        for (te, r, f) in evs_main:
            all_events_main.append((sym, te, r, f))
        per_sym[sym] = {
            "n_events": len(rs),
            "n_filled": filled_n,
            "expR": round(float(np.mean(rs)), 4) if rs else 0.0,
            "wr": round(float(np.mean([1.0 if r > 0 else 0.0 for r in rs])), 4) if rs else 0.0,
        }
        print(f"[{sym}] bars={len(t)} events={len(rs)} filled={filled_n} expR={per_sym[sym]['expR']:+.4f} wr={per_sym[sym]['wr']:.3f}")

    # SLM 网格 (每个 SLM 独立全量回放)
    grid = {}
    for s in SLMS:
        all_rs = []
        for sym in SYMS:
            if sym not in cache:
                continue
            h, l, c, bull, bear, t = cache[sym]
            evs = replay(h, l, c, bull, bear, s, t)
            all_rs.extend(r for (_, r, _) in evs)
        arr = np.asarray(all_rs, dtype=np.float64)
        grid[str(s)] = round(float(arr.mean()), 4) if len(arr) else 0.0
    out["grid"] = grid
    out["exp_R"] = grid["2.0"]

    # 成交n / 事件n / wr (main SLM 2.0, 全品种汇总)
    main_rs = [r for (_, _, r, _) in all_events_main]
    n_events = len(all_events_main)
    n_filled = sum(1 for (_, _, _, f) in all_events_main if f)
    wr = float(np.mean([1.0 if r > 0 else 0.0 for r in main_rs])) if main_rs else 0.0
    out["events"] = n_events
    out["n"] = n_filled
    out["wr"] = round(wr, 4)
    out["per_sym"] = per_sym

    # walk-forward 3 段: 全部事件按时间戳全局三等分
    seg_times = [te for (_, te, _, _) in all_events_main]
    if seg_times:
        tmin, tmax = min(seg_times), max(seg_times)
        b1 = tmin + (tmax - tmin) // 3
        b2 = tmin + 2 * (tmax - tmin) // 3
        seg_rs = [[], [], []]
        for (sym, te, r, f) in all_events_main:
            if te < b1:
                seg_rs[0].append(r)
            elif te < b2:
                seg_rs[1].append(r)
            else:
                seg_rs[2].append(r)
        out["wf3"] = [round(float(np.mean(s)), 4) if s else None for s in seg_rs]
    else:
        out["wf3"] = [None, None, None]

    # 对称自检: 镜像序列 (h'=-l, l'=-h, c'=-c, d1bull<->d1bear) 事件序列应逐事件精确相等
    sym_ok = True
    checked = 0
    for sym in SYMS:
        if sym not in cache:
            continue
        h, l, c, bull, bear, t = cache[sym]
        ev_orig = replay(h, l, c, bull, bear, SLM_MAIN, t)
        ev_mir = replay(-l, -h, -c, bear, bull, SLM_MAIN, t)
        checked += 1
        if len(ev_orig) != len(ev_mir):
            print(f"[symcheck {sym}] count mismatch {len(ev_orig)} vs {len(ev_mir)}")
            sym_ok = False
            continue
        for (to, ro, fo), (tm, rm, fm) in zip(ev_orig, ev_mir):
            if abs(ro - rm) > 1e-9 or fo != fm:
                print(f"[symcheck {sym}] t={to} orig_R={ro} mirror_R={rm} filled {fo}/{fm}")
                sym_ok = False
                break
    out["symmetry_pass"] = bool(sym_ok and checked > 0)
    out["sym_checked_syms"] = checked
    out["exp_R_sensitivity"] = {"slip0.5R": round(out["exp_R"] - 0.5, 4)}
    out["_meta"] = {"note": "H1 trend-leg replay; n=成交数; events=全部事件(未成交记0R计入均值); 前向42根收盘计R不截断"}

    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "data", "intra_tf_h1.json"), "w"), indent=1)
    print("H1 RESULT")
    print(json.dumps(out, indent=1))
    mt5.shutdown()

if __name__ == "__main__":
    main()
