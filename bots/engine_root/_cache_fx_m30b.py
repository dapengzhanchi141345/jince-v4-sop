# -*- coding: utf-8 -*-
"""_cache_fx_m30b.py — 拉 2025-10-06 起 6 品种 M30 全日内 K 线 -> data/tf_cache_fx2/
数据源限制已探明: 经纪商历史仅 2025-10 起完整, 更早是数据洞.
每 3 个月拉一页, 保证全区间; 落盘后校验 48根完整日数量."""
import os, time
import numpy as np
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

OUT = "E:/GoldstrategyEngine/data/tf_cache_fx2"
os.makedirs(OUT, exist_ok=True)
ok = mt5.initialize()
if not ok:
    ok = mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
assert ok, "MT5 init failed"

SYMS = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDCAD", "USDJPY"]
START = datetime(2025, 10, 6, tzinfo=timezone.utc)
END = datetime.now(timezone.utc)

for sym in SYMS:
    allr = []
    t0 = START
    while t0 < END:
        t1 = min(t0 + timedelta(days=90), END)
        r = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M30, t0, t1)
        if r is not None and len(r):
            allr.append(r)
        t0 = t1
        time.sleep(0.5)
    if not allr:
        print(sym, "EMPTY")
        continue
    a = np.concatenate(allr)
    a = a[np.argsort(a["time"])]
    mask = np.concatenate(([True], a["time"][1:] != a["time"][:-1]))
    a = a[mask]
    np.savez_compressed(f"{OUT}/{sym}_M30.npz",
                       t=a["time"].astype(np.int64),
                       o=a["open"].astype(np.float32),
                       h=a["high"].astype(np.float32),
                       l=a["low"].astype(np.float32),
                       c=a["close"].astype(np.float32))
    # full days
    days = np.unique(a["time"] // 86400)
    full = 0
    for d0 in days:
        m = a["time"][(a["time"] >= d0) & (a["time"] < d0 + 86400)]
        if len(m) == 48:
            full += 1
    print(sym, "bars", len(a), "first", datetime.fromtimestamp(int(a["time"][0]), tz=timezone.utc),
          "full_days", full, "of", len(days), "days")
