import MetaTrader5 as mt5
import numpy as np
mt5.initialize()
assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
for tf, nm, want in [(mt5.TIMEFRAME_M5, "M5", 100000),
                     (mt5.TIMEFRAME_M15, "M15", 100000)]:
    ok, total = 0, 0
    for n in [5000, 20000, 50000, 100000]:
        r = mt5.copy_rates_from_pos("BTCUSD", tf, 0, n)
        got = 0 if r is None else len(r)
        total = max(total, got)
        print(f"{nm} n={n} -> {got}")
        if got >= 50000:
            break
    print(f"{nm} usable max: {total}")
