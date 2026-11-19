# -*- coding: utf-8 -*-
"""多周期数据统一缓存: 6品种 x 5周期 -> data/tf_cache/{SYM}_{TF}.npz
子代理只读缓存, 不再并发抢 MT5 连接 (今天4路子代理全死于脏数据+429)"""
import os, time
import numpy as np
import MetaTrader5 as mt5

SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]
TFS = [("D1", mt5.TIMEFRAME_D1, 3000),
       ("H4", mt5.TIMEFRAME_H4, 30000),
       ("H1", mt5.TIMEFRAME_H1, 60000),
       ("M30", mt5.TIMEFRAME_M30, 60000),
       ("M15", mt5.TIMEFRAME_M15, 100000)]
OUT = "E:/GoldstrategyEngine/data/tf_cache"
os.makedirs(OUT, exist_ok=True)

ok = mt5.initialize()
if not ok:
    ok = mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
assert ok, "MT5 init failed"

rep = []
for sym in SYMS:
    for name, tf, want in TFS:
        path = f"{OUT}/{sym}_{name}.npz"
        got = 0
        for _ in range(4):
            try:
                mt5.symbol_select(sym, True)
            except Exception:
                pass
            r = mt5.copy_rates_from_pos(sym, tf, 0, want)
            if r is not None and len(r) >= min(want // 10, 500):
                np.savez_compressed(path,
                                    t=r["time"].astype(np.int64),
                                    o=r["open"].astype(np.float32),
                                    h=r["high"].astype(np.float32),
                                    l=r["low"].astype(np.float32),
                                    c=r["close"].astype(np.float32))
                got = len(r)
                break
            time.sleep(2)
        rep.append(f"{sym} {name}: {got}")
print("CACHED:\n" + "\n".join(rep))
