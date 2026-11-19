"""Debug: test v10.4 backtest signal generation on real data"""
import sys, os, json, warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
warnings.filterwarnings('ignore')

BASE = r"E:\GoldstrategyEngine"
DATA_DIR = os.path.join(BASE, "data")

# Load data
h1 = pd.read_csv(os.path.join(DATA_DIR, "XAUUSD_H1.csv"), parse_dates=["time"])
h4 = pd.read_csv(os.path.join(DATA_DIR, "XAUUSD_H4.csv"), parse_dates=["time"])
d1 = pd.read_csv(os.path.join(DATA_DIR, "XAUUSD_D1.csv"), parse_dates=["time"])

print(f"H1: {len(h1)} bars, {h1['time'].iloc[0]} ~ {h1['time'].iloc[-1]}")
print(f"H4: {len(h4)} bars, {h4['time'].iloc[0]} ~ {h4['time'].iloc[-1]}")
print(f"D1: {len(d1)} bars")

# Check data quality
print(f"\nH1 volume stats: min={h1['tick_volume'].min()}, max={h1['tick_volume'].max()}, mean={h1['tick_volume'].mean():.0f}")
print(f"H1 price range: ${h1['low'].min():.2f} - ${h1['high'].max():.2f}")

# Check time coverage
h1_hours = h1['time'].dt.hour.value_counts().sort_index()
print(f"\nH1 bars by hour:")
for h, c in h1_hours.items():
    print(f"  {h:02d}:00: {c} bars")

# Check session filter: how many bars in 15-00 session?
session_bars = h1[(h1['time'].dt.hour >= 15) | (h1['time'].dt.hour == 0)]
print(f"\nSession 15-00 bars: {len(session_bars)} / {len(h1)} ({len(session_bars)/len(h1)*100:.1f}%)")

# Check ADX on valid data
def calc_adx(high, low, close, period=14):
    if len(close) < period * 2:
        return np.zeros(len(close))
    tr = np.maximum(high[1:] - low[1:],
                    np.maximum(np.abs(high[1:] - close[:-1]),
                               np.abs(low[1:] - close[:-1])))
    up = high[1:] - high[:-1]
    dn = low[:-1] - low[1:]
    plus_dm = np.where((up > dn) & (up > 0), up, 0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0)
    atr_s = pd.Series(tr).ewm(span=period).mean().values
    pdi = 100 * pd.Series(plus_dm).ewm(span=period).mean().values / (atr_s + 1e-10)
    mdi = 100 * pd.Series(minus_dm).ewm(span=period).mean().values / (atr_s + 1e-10)
    dx = 100 * np.abs(pdi - mdi) / (pdi + mdi + 1e-10)
    result = pd.Series(dx).ewm(span=period).mean().values
    return np.concatenate([np.zeros(len(close) - len(result)), result])

adx = calc_adx(h1['high'].values, h1['low'].values, h1['close'].values)
adx_gt22 = sum(adx >= 22)
print(f"\nADX >= 22: {adx_gt22} / {len(adx)} ({adx_gt22/len(adx)*100:.1f}%)")
print(f"ADX mean: {adx.mean():.1f}, median: {np.median(adx):.1f}")

# Quick zone detection test on H4
from collections import namedtuple
Zone = namedtuple('Zone', ['type', 'top', 'bottom', 'strength', 'age', 'fresh'])

def detect_zones(close, high, low):
    zones = []
    if len(close) < 20:
        return zones
    lookback = 3
    for i in range(lookback, len(close) - lookback):
        if high[i] == max(high[i-lookback:i+lookback+1]):
            for j in range(max(0, i-2), min(len(close), i+3)):
                if close[j] < high[i] * 0.98:
                    retrace = (high[i] - low[max(0,i-2):i+3].min()) / max(high[i], 1)
                    if 0.2 <= retrace <= 0.85:
                        zones.append(Zone("S", high[i]*1.02, high[i]*0.98, min(5, retrace*5+1), len(close)-i, len(close)-i <= 20))
                    break
        if low[i] == min(low[i-lookback:i+lookback+1]):
            for j in range(max(0, i-2), min(len(close), i+3)):
                if close[j] > low[i] * 1.02:
                    retrace = (high[max(0,i-2):i+3].max() - low[i]) / max(low[i], 1)
                    if 0.2 <= retrace <= 0.85:
                        zones.append(Zone("D", low[i]*1.02, low[i]*0.98, min(5, retrace*5+1), len(close)-i, len(close)-i <= 20))
                    break
    return zones

# Test on last 100 bars
test_h4_close = h4['close'].values[-200:]
test_h4_high = h4['high'].values[-200:]
test_h4_low = h4['low'].values[-200:]
zones = detect_zones(test_h4_close, test_h4_high, test_h4_low)
print(f"\n=== H4 Zone Detection Test (last 200 bars) ===")
print(f"Zones found: {len(zones)}")
for z in zones:
    print(f"  {z.type}: ${z.bottom:.2f}-${z.top:.2f} (str={z.strength:.1f}, age={z.age})")

# Test last H4 bar
price = h1['close'].iloc[-1]
print(f"\n=== Current Price Test ===")
print(f"Last H1 close: ${price:.2f}")
print(f"Last H4 close: ${h4['close'].iloc[-1]:.2f}")

# Check D1 EMA filter
d1_close = d1['close'].values
def calc_ema(values, period):
    result = np.full(len(values), np.nan)
    result[period-1] = np.mean(values[:period])
    alpha = 2 / (period+1)
    for i in range(period, len(values)):
        result[i] = values[i] * alpha + result[i-1] * (1-alpha)
    return result

ema9 = calc_ema(d1_close, 9)
ema21 = calc_ema(d1_close, 21)
print(f"\n=== D1 Direction (last 5 days) ===")
for i in range(-5, 0):
    d = d1['time'].iloc[i]
    e9 = ema9[i] if not np.isnan(ema9[i]) else 0
    e21 = ema21[i] if not np.isnan(ema21[i]) else 0
    dir_ = "UP" if e9 > e21 else "DOWN"
    print(f"  {d[:10]}: EMA9={e9:.2f}, EMA21={e21:.2f} -> {dir_}")

# Try to find a tradeable scenario
print(f"\n=== Searching for tradeable scenario ===")
h4_start = max(0, -200)
h4_close_slice = h4['close'].values[h4_start:]
h4_high_slice = h4['high'].values[h4_start:]
h4_low_slice = h4['low'].values[h4_start:]

zones = detect_zones(h4_close_slice, h4_high_slice, h4_low_slice)
h4a = np.mean(np.diff(h1['close'].values[-60:])) * 20  # ~H4 ATR

zm = 1.2
for z in zones:
    if z.strength >= zm:
        if z.type == "D" and price > z.top and price - z.top < h4a * 3:
            print(f"  DEMAND zone hit! ${z.bottom:.2f}-${z.top:.2f}, strength={z.strength:.1f}, price=${price:.2f}")
        if z.type == "S" and price < z.bottom and z.bottom - price < h4a * 3:
            print(f"  SUPPLY zone hit! ${z.bottom:.2f}-${z.top:.2f}, strength={z.strength:.1f}, price=${price:.2f}")

print(f"\nH4 ATR (approx): ${h4a:.2f}")
print(f"Price near zones? Checking last 100 bars...")
