# -*- coding: utf-8 -*-
"""net20261115_m15_fetch.py — 纯研究: 拉 5 WATCH 品种 M15 K线(含 tick_volume) 前向 OOS 接力
供 s5s6_obs_tag_oos 同分母五验 S6 定位图闸. 产物落 research/net20261115_m15/.
红线: 只连 60137964 demo, REAL 零动, 不碰挂单/闸源."""
import os
os.environ.setdefault("MT5_TERMINAL", r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe")
os.environ.setdefault("MT5_LOGIN", "60137964")
import MetaTrader5 as mt5
import numpy as np
import datetime as dt

ROOT = "E:/GoldstrategyEngine"
OUT = os.path.join(ROOT, "research", "net20261115_m15")
os.makedirs(OUT, exist_ok=True)
SYMS = ["XAUUSD", "EURUSD", "BTCUSD", "ETHUSD", "BNBUSD"]
N_M15 = 40000  # ~417 天, 与 11-14 批同窗口径

ok = mt5.initialize()
print("mt5 init:", ok, mt5.last_error(), flush=True)
if not ok:
    raise SystemExit("MT5 不可用 -> DATA_UNAVAILABLE")
acct = mt5.account_info()
assert int(acct.login) == 60137964, f"unexpected account {acct.login}"
for sym in SYMS:
    if not mt5.symbol_select(sym, True):
        print(f"{sym}: symbol_select FAILED {mt5.last_error()}", flush=True)
        continue
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, N_M15)
    if rates is None or len(rates) == 0:
        print(f"{sym}: EMPTY M15 {mt5.last_error()}", flush=True)
        continue
    arr = dict(t=np.asarray(rates["time"], "int64"),
               o=np.asarray(rates["open"], "float64"),
               h=np.asarray(rates["high"], "float64"),
               l=np.asarray(rates["low"], "float64"),
               c=np.asarray(rates["close"], "float64"),
               tv=np.asarray(rates["tick_volume"], "float64"))
    p = os.path.join(OUT, f"{sym}_M15.npz")
    np.savez(p, **arr)
    print(f"{sym}: {len(arr['t'])} bars {dt.datetime.utcfromtimestamp(int(arr['t'][0]))} -> "
          f"{dt.datetime.utcfromtimestamp(int(arr['t'][-1]))} UTC -> {p}", flush=True)
mt5.shutdown()
print("DONE", flush=True)
