#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch M15+H1 for JPN225/US30 from the connected MT5 demo terminal (read-only),
write CSVs into research/liquid_wfo_liq12_data/ (research dir only, data/ untouched).
Same CSV layout as data/*_M15.csv so W.load_csv works unchanged."""
import os, datetime as dt
import MetaTrader5 as mt5

ROOT = "E:/GoldstrategyEngine"
OUT = os.path.join(ROOT, "research", "liquid_wfo_liq12_data")
os.makedirs(OUT, exist_ok=True)
N_M15 = 40000
N_H1 = 40000

def rates_to_csv(sym, tf, n, path):
    rates = mt5.copy_rates_from_pos(sym, tf, 0, n)
    if rates is None or len(rates) == 0:
        print(f"{sym} tf={tf}: EMPTY (mt5_last_error={mt5.last_error()})")
        return 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write("time,open,high,low,close,tick_volume,spread,real_volume\n")
        for r in rates:
            t = dt.datetime.utcfromtimestamp(r["time"]).strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{t},{r['open']:.5f},{r['high']:.5f},{r['low']:.5f},{r['close']:.5f},"
                    f"{r['tick_volume']},{r['spread']},{r['real_volume']}\n")
    print(f"{sym} tf={tf}: {len(rates)} bars -> {path}")
    return len(rates)

ok = mt5.initialize()
print("mt5 init:", ok)
if not ok:
    raise SystemExit("MT5 terminal unavailable -> JPN225/US30 stay DATA_UNAVAILABLE")
for sym in ["JPN225", "US30"]:
    mt5.symbol_select(sym, True)
    rates_to_csv(sym, mt5.TIMEFRAME_M15, N_M15, os.path.join(OUT, f"{sym}_M15.csv"))
    rates_to_csv(sym, mt5.TIMEFRAME_H1, N_H1, os.path.join(OUT, f"{sym}_H1.csv"))
mt5.shutdown()
print("DONE")
