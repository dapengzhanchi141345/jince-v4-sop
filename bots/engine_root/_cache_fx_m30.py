# -*- coding: utf-8 -*-
"""Cache M30 for session ORB target symbols -> data/tf_cache_fx/{SYM}_M30.npz"""
import os, time
import numpy as np
import MetaTrader5 as mt5

OUT = "E:/GoldstrategyEngine/data/tf_cache_fx"
os.makedirs(OUT, exist_ok=True)
ok = mt5.initialize()
if not ok:
    ok = mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
assert ok, "MT5 init failed"

SYMS = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDCAD", "USDJPY"]
WANT = 60000  # M30 bars (~2.5 years)
for sym in SYMS:
    for _ in range(4):
        try:
            mt5.symbol_select(sym, True)
        except Exception:
            pass
        r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M30, 0, WANT)
        if r is not None and len(r) >= 1000:
            np.savez_compressed(f"{OUT}/{sym}_M30.npz",
                                t=r["time"].astype(np.int64),
                                o=r["open"].astype(np.float32),
                                h=r["high"].astype(np.float32),
                                l=r["low"].astype(np.float32),
                                c=r["close"].astype(np.float32))
            print(sym, "cached", len(r))
            break
        time.sleep(2)
    else:
        print(sym, "FAILED to cache")
