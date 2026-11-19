"""Debug: comprehensive zone detection test"""
import sys, os
BASE = r"E:\GoldstrategyEngine"
sys.path.insert(0, BASE)

import pandas as pd
from strategies.supply_demand import SupplyDemandSMC

h4 = pd.read_csv(os.path.join(BASE, "data", "XAUUSD_H4.csv"), parse_dates=["time"])
h1 = pd.read_csv(os.path.join(BASE, "data", "XAUUSD_H1.csv"), parse_dates=["time"])

print(f"H4: {len(h4)} bars")
print(f"H1: {len(h1)} bars\n")

sd = SupplyDemandSMC({"slb": 15, "bmb": 2, "bmx": 10, "rmn": 0.20, "rmx": 0.85})

# Test full dataset in chunks
total_d, total_s = 0, 0
chunk_size = 60
for start in range(0, len(h4) - chunk_size, chunk_size // 2):
    chunk = h4.iloc[start:start+chunk_size]
    zones = sd.detect_zones(chunk)
    d = len(zones.get("demand", []))
    s = len(zones.get("supply", []))
    total_d += d
    total_s += s

print(f"Total zones from {len(range(0, len(h4)-chunk_size, chunk_size//2))} chunks:")
print(f"  Demand: {total_d}")
print(f"  Supply: {total_s}")

# Also test with full H4 passed at once
print(f"\nPassing full H4 dataset ({len(h4)} bars):")
zones = sd.detect_zones(h4)
print(f"  Demand: {len(zones.get('demand', []))}")
print(f"  Supply: {len(zones.get('supply', []))}")
for z in zones.get("demand", [])[:5]:
    print(f"    D: top={z.top:.2f}, bottom={z.bottom:.2f}, str={z.strength:.1f}, type={z.type}")
for z in zones.get("supply", [])[:5]:
    print(f"    S: top={z.top:.2f}, bottom={z.bottom:.2f}, str={z.strength:.1f}, type={z.type}")

# Price
price = h1['close'].iloc[-1]
print(f"\nLast H1 close: ${price:.2f}")

# H4 ATR
h4_high = h4['high'].values
h4_low = h4['low'].values
h4_close = h4['close'].values
tr = np.maximum(h4_high[1:]-h4_low[1:], 
                np.maximum(np.abs(h4_high[1:]-h4_close[:-1]),
                          np.abs(h4_low[1:]-h4_close[:-1])))
h4a = float(pd.Series(tr).ewm(span=14).mean().iloc[-1])
print(f"H4 ATR: ${h4a:.2f}")

# Check zones near price
import numpy as np
zm = 1.2
for k, label in [("demand", "D"), ("supply", "S")]:
    for z in zones.get(k, []):
        if z.strength >= zm:
            if k == "demand" and price > z.top and price - z.top < h4a * 3:
                print(f"  DEMAND HIT! ${z.bottom:.2f}-${z.top:.2f}, gap=${price-z.top:.2f}, str={z.strength:.1f}")
            if k == "supply" and price < z.bottom and z.bottom - price < h4a * 3:
                print(f"  SUPPLY HIT! ${z.bottom:.2f}-${z.top:.2f}, gap=${z.bottom-price:.2f}, str={z.strength:.1f}")

# Scan all H1 bars for tradeable scenarios
print(f"\n=== Scanning ALL H1 bars for signals ===")
signal_count = 0
for i in range(200, len(h1)):
    bar_time = h1['time'].iloc[i]
    bar_hour = pd.Timestamp(bar_time).hour
    # Session filter
    if not (15 <= bar_hour < 24):
        continue
    
    price = h1['close'].iloc[i]
    h4_idx = min(i // 4, len(h4) - 1)
    
    if h4_idx < 30:
        continue
    
    chunk = h4.iloc[h4_idx-30:h4_idx+1]
    zones = sd.detect_zones(chunk)
    
    found = False
    for z in zones.get("demand", []):
        if z.strength >= 1.2 and price > z.top and price - z.top < h4a * 3:
            found = True
            break
    if not found:
        for z in zones.get("supply", []):
            if z.strength >= 1.2 and price < z.bottom and z.bottom - price < h4a * 3:
                found = True
                break
    
    if found:
        signal_count += 1
        if signal_count <= 5:
            print(f"  Signal at bar {i}, {bar_time}, price=${price:.2f}")

print(f"\nTotal signals found: {signal_count} out of {len(h1)} bars")
