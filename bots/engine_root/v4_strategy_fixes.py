# -*- coding: utf-8 -*-
"""
V4策略修复版 - 确保信号数量合理
================================
"""

import numpy as np
import pandas as pd
from typing import List, Dict


# ═══════════════════════════════════════════════════════════════
# SDP V4.0 修复版
# ═══════════════════════════════════════════════════════════════

def gen_sdp_v4_fixed(h1, h4, d1, cfg) -> List[Dict]:
    """SDP V4.0 修复版 - 放宽过滤条件"""
    hc = h1['close'].values.astype(float)
    hh = h1['high'].values.astype(float)
    hl = h1['low'].values.astype(float)

    from advanced_strategies import ema, sma, atr, adx, find_swing, find_zones

    adx_v = adx(hh, hl, hc)
    atr_v = atr(hh, hl, hc)
    e50 = ema(hc, 50)
    e200 = ema(hc, 200)

    # H4供需区 (使用V1.0方法)
    h4_zones = find_zones(h4)

    # D1趋势
    dc = d1['close'].values.astype(float)
    de9 = ema(dc, 9)
    de21 = ema(dc, 21)

    adx_min = cfg.get('adx_min', 20)
    sl_mult = cfg.get('sl_mult', 1.5)
    tp_mult = cfg.get('rr_mult', 3.0)
    lots = cfg.get('lot', 0.1)

    sig = []
    for i in range(100, len(h1)):
        price = hc[i]
        if np.isnan(adx_v[i]) or adx_v[i] < adx_min:
            continue
        if np.isnan(e50[i]) or np.isnan(e200[i]):
            continue

        a = atr_v[i]
        if np.isnan(a) or a <= 0:
            continue

        # 趋势方向
        trend = 'UP' if e50[i] > e200[i] else 'DOWN'
        d1i = min(i // 24, len(dc) - 1)
        d1_dir = 'UP' if (d1i >= 20 and de9[d1i] > de21[d1i]) else 'DOWN'

        # 寻找供需区 (放宽条件)
        zc = None
        zt = None
        for z in h4_zones.get('demand', []) + h4_zones.get('supply', []):
            if trend == 'UP' and z['type'] == 'D' and price > z['bottom'] and price - z['bottom'] < a * 3:
                zc, zt = z, 'D'
                break
            elif trend == 'DOWN' and z['type'] == 'S' and price < z['top'] and z['top'] - price < a * 3:
                zc, zt = z, 'S'
                break

        if not zc:
            continue

        # 方向确认 (放宽)
        if d1_dir == 'UP' and zt == 'D':
            direction = 'BUY'
        elif d1_dir == 'DOWN' and zt == 'S':
            direction = 'SELL'
        elif trend == 'UP' and zt == 'D':
            direction = 'BUY'
        elif trend == 'DOWN' and zt == 'S':
            direction = 'SELL'
        else:
            continue

        # SL/TP
        buf = max(a * 0.1, 0.5 * cfg.get('pip', 0.0001))
        if direction == 'BUY':
            sl = zc['bottom'] - buf
            sl_cap = max(a * sl_mult, 4.0 * cfg.get('pip', 0.0001))
            sl = max(sl, price - sl_cap)
            if sl >= price:
                continue
            tp = price + (price - sl) * tp_mult
        else:
            sl = zc['top'] + buf
            sl_cap = max(a * sl_mult, 4.0 * cfg.get('pip', 0.0001))
            sl = min(sl, price + sl_cap)
            if sl <= price:
                continue
            tp = price - (sl - price) * tp_mult

        sig.append({
            'bar': i, 'side': 1 if direction == 'BUY' else -1,
            'entry': price, 'sl': sl, 'tp': tp,
            'regime': f'sdp_v4_trend', 'strat': 'SDP', 'lot': lots,
            'adx': adx_v[i], 'atr': a
        })

    return sig


# ═══════════════════════════════════════════════════════════════
# MR V4.0 修复版
# ═══════════════════════════════════════════════════════════════

def gen_mr_v4_fixed(h1, h4, d1, cfg) -> List[Dict]:
    """MR V4.0 修复版 - 使用标准Z-Score"""
    hc = h1['close'].values.astype(float)
    hh = h1['high'].values.astype(float)
    hl = h1['low'].values.astype(float)

    from advanced_strategies import sma, std, atr, adx

    ma = sma(hc, 20)
    sd = std(hc, 20)
    atr_v = atr(hh, hl, hc)
    adx_v = adx(hh, hl, hc)

    lots = cfg.get('lot', 0.1)
    adx_min = cfg.get('adx_min', 20)

    sig = []
    for i in range(40, len(h1)):
        if np.isnan(ma[i]) or np.isnan(sd[i]) or np.isnan(atr_v[i]) or np.isnan(adx_v[i]):
            continue
        if adx_v[i] > adx_min + 10:  # 趋势市禁用MR
            continue

        price = hc[i]
        a = atr_v[i]
        z = (price - ma[i]) / (sd[i] + 1e-10)

        if z <= -2.0:
            sl = hl[max(0, i-5):i+1].min() - a * 0.5
            tp = ma[i]
            if sl < price:
                sig.append({'bar': i, 'side': 1, 'entry': price, 'sl': sl, 'tp': tp,
                           'regime': f'mr_v4_z{z:.2f}', 'strat': 'MR', 'lot': lots, 'z_score': z})
        elif z >= 2.0:
            sl = hh[max(0, i-5):i+1].max() + a * 0.5
            tp = ma[i]
            if sl > price:
                sig.append({'bar': i, 'side': -1, 'entry': price, 'sl': sl, 'tp': tp,
                           'regime': f'mr_v4_z{z:.2f}', 'strat': 'MR', 'lot': lots, 'z_score': z})

    return sig


if __name__ == "__main__":
    print("=" * 70)
    print("V4策略修复版测试")
    print("=" * 70)

    np.random.seed(42)
    n = 2000
    closes = [100.0]
    for i in range(1, n):
        trend = 0.02 * np.sin(i * 0.005)
        noise = np.random.randn() * 0.3
        closes.append(closes[-1] * (1 + trend + noise * 0.01))
    closes = np.array(closes)
    opens = closes + np.random.randn(n) * 0.05
    highs = np.maximum(closes, opens) + np.abs(np.random.randn(n)) * 0.2
    lows = np.minimum(closes, opens) - np.abs(np.random.randn(n)) * 0.2
    times = np.arange(n) * 3600
    h1 = pd.DataFrame({'open': opens, 'high': highs, 'low': lows, 'close': closes, 'time': times})
    h4 = pd.DataFrame({'open': opens[::4], 'high': highs[::4], 'low': lows[::4], 'close': closes[::4], 'time': times[::4]})
    d1 = pd.DataFrame({'open': opens[::20], 'high': highs[::20], 'low': lows[::20], 'close': closes[::20], 'time': times[::20]})
    cfg = {'pip': 0.01, 'lot': 0.1, 'adx_min': 20, 'sl_mult': 1.5, 'rr_mult': 3.0}

    from advanced_strategies import gen_sdp, gen_meanrev

    print(f'\\nSDP:')
    print(f'  V1.0: {len(gen_sdp(h1, h4, d1, cfg))} 信号')
    print(f'  V4.0修复: {len(gen_sdp_v4_fixed(h1, h4, d1, cfg))} 信号')

    print(f'\\nMR:')
    print(f'  V1.0: {len(gen_meanrev(h1, h4, d1, cfg))} 信号')
    print(f'  V4.0修复: {len(gen_mr_v4_fixed(h1, h4, d1, cfg))} 信号')

    print('\\n' + '=' * 70)
    print('✅ 修复版测试完成')
    print('=' * 70)
