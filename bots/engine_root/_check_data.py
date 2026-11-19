"""Check MT5 data availability for 2-year backtest"""
import MetaTrader5 as mt5
from datetime import datetime
import pandas as pd

print("=" * 60)
print("MT5 Connection Test")
print("=" * 60)

# Try auto-detect first
if not mt5.initialize():
    err = mt5.last_error()
    print(f"Auto init FAILED: {err}")
    # Try with login
    mt5.shutdown()
    import time
    time.sleep(2)
    if not mt5.initialize():
        print(f"Retry FAILED: {mt5.last_error()}")
        exit(1)

login_ok = mt5.login(60043976, password="", server="TradeMaxGlobal-Demo")
if not login_ok:
    print(f"Login FAILED: {mt5.last_error()}")
    mt5.shutdown()
    exit(1)
print("MT5 connected OK\n")

# Check 2 years of XAUUSD data
utc_from = int(datetime(2024, 7, 5).timestamp())
utc_to = int(datetime(2026, 7, 5).timestamp())

# H1
h1 = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_H1, utc_from, utc_to)
if h1 is None or len(h1) == 0:
    print(f"H1 data: FAILED - {mt5.last_error()}")
else:
    h1d = pd.DataFrame(h1)
    print(f"H1 XAUUSD: {len(h1d)} bars")
    print(f"  From: {pd.to_datetime(h1d['time'].iloc[0], unit='s')}")
    print(f"  To:   {pd.to_datetime(h1d['time'].iloc[-1], unit='s')}")
    print(f"  Real bars: {len(h1d[h1d['real_volume'] > 0])}")

# H4
h4 = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_H4, utc_from, utc_to)
if h4 is not None:
    h4d = pd.DataFrame(h4)
    print(f"\nH4 XAUUSD: {len(h4d)} bars")

# D1
d1 = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_D1, utc_from, utc_to)
if d1 is not None:
    d1d = pd.DataFrame(d1)
    print(f"D1 XAUUSD: {len(d1d)} bars")

mt5.shutdown()
print("\nDone")
