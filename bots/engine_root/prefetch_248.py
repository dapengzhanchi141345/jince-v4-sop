#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""预取枪: 248 品种 × H1/H4/D1 × 180d 一次拉全存 pickle (断点续跑). 单进程串行 MT5, 无并发 IPC.
产物 data/cache248/<sym>.pkl = dict(sym, h1, h4, d1, point, spread, swap_long, swap_short, ts)
0 LLM, 0 写闸源. 数据源 = mt5:60137964 自家终端.
"""
import os, sys, json, datetime, pickle
os.chdir(r"E:\GoldstrategyEngine"); sys.path.insert(0, r"E:\GoldstrategyEngine")
import pandas as pd, MetaTrader5 as mt5
import mt5_login

DAYS = 180
CACHE = "data/cache248"
os.makedirs(CACHE, exist_ok=True)

def rates(sym, tf, d=DAYS, cap=20000):
    F = []; p = 0
    while True:
        c = mt5.copy_rates_from_pos(sym, tf, p, 5000)
        if c is None or len(c) == 0: break
        F.append(pd.DataFrame(c)); p += len(c)
        if len(c) < 5000 or p >= cap: break
    if not F: return None
    df = pd.concat(F).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df["t"] = pd.to_datetime(df["time"], unit="s")
    return df[df["t"] >= df["t"].max() - pd.Timedelta(days=d)].reset_index(drop=True)

def main():
    print("prefetch_248 起跑", datetime.datetime.now().isoformat(), flush=True)
    if not mt5.initialize(): print("MT5 init fail"); return
    ok, why = mt5_login.ensure_login(60137964)
    if not ok: print("LOGIN FAIL:", why); return
    syms = [s.name for s in (mt5.symbols_get() or []) if s.visible]
    print(f"全品种 {len(syms)} 个, 开始预取", flush=True)
    stats = {"ok": 0, "short": 0, "fail": 0}
    for i, sym in enumerate(sorted(syms), 1):
        fp = os.path.join(CACHE, f"{sym.replace('.', '_')}.pkl")
        if os.path.exists(fp): stats["ok"] += 1; continue
        h1 = rates(sym, mt5.TIMEFRAME_H1); h4 = rates(sym, mt5.TIMEFRAME_H4); d1 = rates(sym, mt5.TIMEFRAME_D1)
        if h1 is None or len(h1) < 100:
            stats["short" if h1 is not None else "fail"] += 1
            print(f"{i}/{len(syms)} {sym}: {'H1短 n=%d' % len(h1) if h1 is not None else '无数据'}", flush=True)
            continue
        info = mt5.symbol_info(sym)
        pkt = dict(sym=sym, h1=h1, h4=h4, d1=d1,
                   point=(info.point if info else 1e-5),
                   spread=(info.spread if info else 10),
                   swap_long=(info.swap_long if info else 0),
                   swap_short=(info.swap_short if info else 0),
                   ts=datetime.datetime.now().isoformat())
        pickle.dump(pkt, open(fp, "wb"))
        stats["ok"] += 1
        print(f"{i}/{len(syms)} {sym}: h1={len(h1)} 已缓存", flush=True)
        if i % 40 == 0: json.dump(stats, open(os.path.join(CACHE, "_progress.json"), "w"))
    json.dump(stats, open(os.path.join(CACHE, "_progress.json"), "w"))
    print(f"prefetch 完: {stats}", flush=True)
    mt5.shutdown()

if __name__ == "__main__":
    main()
