# -*- coding: utf-8 -*-
"""net20261114_m15_fetch.py — 纯研究: MT5 只读(60137964 模拟)拉 8 品种 M15 K线(含 tick_volume),
供网络证据候选(CVD 否决门)验证. 产物只落 research/net20261114_m15/.
红线: REAL 30261104 零动; jince_live24.py 只读; 不对外发送."""
import os, datetime as dt

os.environ.setdefault("MT5_TERMINAL", r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe")
os.environ.setdefault("MT5_LOGIN", "60137964")

import MetaTrader5 as mt5
import numpy as np

ROOT = "E:/GoldstrategyEngine"
OUT = os.path.join(ROOT, "research", "net20261114_m15")
os.makedirs(OUT, exist_ok=True)
SYMS = ["XAUUSD", "EURUSD", "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]
N_M15 = 40000  # ~417 天, 尽量贴近 M30 近端区间 (2025-01 ~ 11-14)

ok = mt5.initialize()
print("mt5 init:", ok, mt5.last_error(), flush=True)
if not ok:
    raise SystemExit("MT5 terminal unavailable -> CAND_D CVD gate DATA_UNAVAILABLE")

acct = mt5.account_info()
print("account:", acct.login, "mode:", acct.server, flush=True)
assert int(acct.login) == 60137964, f"unexpected account {acct.login}"

for sym in SYMS:
    if not mt5.symbol_select(sym, True):
        print(f"{sym}: symbol_select FAILED {mt5.last_error()}", flush=True)
        continue
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, N_M15)
    if rates is None or len(rates) == 0:
        print(f"{sym}: EMPTY M15 {mt5.last_error()}", flush=True)
        continue
    d = rates  # record array, fields: time,open,high,low,close,tick_volume,spread,real_volume
    arr = dict(
        t=np.asarray(d["time"], dtype="int64"),
        o=np.asarray(d["open"], dtype="float64"),
        h=np.asarray(d["high"], dtype="float64"),
        l=np.asarray(d["low"], dtype="float64"),
        c=np.asarray(d["close"], dtype="float64"),
        tv=np.asarray(d["tick_volume"], dtype="float64"),
    )
    p = os.path.join(OUT, f"{sym}_M15.npz")
    np.savez(p, **arr)
    t0 = dt.datetime.utcfromtimestamp(int(arr["t"][0]))
    t1 = dt.datetime.utcfromtimestamp(int(arr["t"][-1]))
    print(f"{sym}: {len(arr['t'])} bars {t0} -> {t1} UTC -> {p}", flush=True)

mt5.shutdown()
print("DONE", flush=True)
