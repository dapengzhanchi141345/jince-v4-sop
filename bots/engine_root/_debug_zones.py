"""Debug SupplyDemandSMC zone detection"""
import sys, os
BASE = r"E:\GoldstrategyEngine"
sys.path.insert(0, BASE)

import pandas as pd
from strategies.supply_demand import SupplyDemandSMC

# Load H4 data
h4 = pd.read_csv(os.path.join(BASE, "data", "XAUUSD_H4.csv"), parse_dates=["time"])
print(f"H4: {len(h4)} bars")

sd = SupplyDemandSMC({"slb": 15, "bmb": 2, "bmx": 10, "rmn": 0.20, "rmx": 0.85})

# Test on different segments
for start in [0, 100, 300, 500, 800]:
    chunk = h4.iloc[start:start+30]
    zones = sd.detect_zones(chunk)
    d_count = len(zones.get("demand", []))
    s_count = len(zones.get("supply", []))
    print(f"\nbars {start}-{start+30}: D={d_count}, S={s_count}")
    for k in ["demand", "supply"]:
        for z in zones.get(k, [])[:3]:
            attrs = [a for a in dir(z) if not a.startswith('_')]
            print(f"  {k}: zone attrs = {attrs}")
            print(f"    type={z.type if hasattr(z,'type') else '?'}, strength={z.strength if hasattr(z,'strength') else '?'}")
            print(f"    top={z.top if hasattr(z,'top') else '?'}, bottom={z.bottom if hasattr(z,'bottom') else '?'}")
            break  # just first one
        if zones.get(k):
            break  # one iteration

# Check last 100 H1 bars vs H4 zones
h1 = pd.read_csv(os.path.join(BASE, "data", "XAUUSD_H1.csv"), parse_dates=["time"])
price = h1['close'].iloc[-1]
print(f"\n\nLast H1 close: ${price:.2f}")

h4a = h4['close'].iloc[-30:].std() * 10
print(f"H4 ATR (approx): ${h4a:.2f}")

last_h4 = h4.iloc[-30:]
zones = sd.detect_zones(last_h4)
print(f"Last 30 H4 bars: D={len(zones.get('demand',[]))}, S={len(zones.get('supply',[]))}")

zm = 1.2
for k in ["demand", "supply"]:
    for z in zones.get(k, []):
        print(f"  {k}: str={z.strength}, top={z.top:.2f}, bottom={z.bottom:.2f}, type={z.type}")
        if k == "demand" and z.strength >= zm and price > z.top and price - z.top < h4a * 3:
            print(f"    -> DEMAND HIT! (gap=${price - z.top:.2f})")
        if k == "supply" and z.strength >= zm and price < z.bottom and z.bottom - price < h4a * 3:
            print(f"    -> SUPPLY HIT! (gap=${z.bottom - price:.2f})")
