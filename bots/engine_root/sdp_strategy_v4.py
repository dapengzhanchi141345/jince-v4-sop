# -*- coding: utf-8 -*-
"""
SDP V4.0 — 供需区策略机构级升级
================================
对标机构标准:
1. Regime-Aware 动态参数
2. Volatility-Adjusted SL/TP
3. Zone Quality Scoring (供需区质量评分)
4. Time Decay (供需区时效衰减)
5. Multi-TF Resonance (多时间框架共振)
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional
from unified_v4_framework import UnifiedV4Framework, RegimeDetector, DynamicParameters


# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════
SWING_LOOKBACK = 3
ZONE_MIN_STRENGTH = 0.5
ZONE_MAX_AGE = 120

TREND_EMA_FAST = 20
TREND_EMA_SLOW = 50


# ═══════════════════════════════════════════════════════════════
# 基础指标
# ═══════════════════════════════════════════════════════════════

def _ema(v, p):
    v = np.asarray(v, float)
    r = np.full(len(v), np.nan); r[p-1] = np.mean(v[:p])
    a = 2/(p+1)
    for i in range(p, len(v)):
        r[i] = v[i]*a + r[i-1]*(1-a)
    return r

def _sma(v, p):
    v = np.asarray(v, float)
    return pd.Series(v).rolling(p, min_periods=p).mean().values

def _atr(h, l, c=None, p=14):
    if c is None:
        c = (h + l) / 2
    h, l, c = np.asarray(h, float), np.asarray(l, float), np.asarray(c, float)
    tr = np.maximum(h[1:]-l[1:], np.maximum(abs(h[1:]-np.roll(h,1)[1:]), abs(l[1:]-np.roll(l,1)[1:])))
    r = np.full(len(h), np.nan); r[p] = np.mean(tr[:p])
    a = 1/p
    for i in range(p+1, len(h)):
        r[i] = tr[i-1]*a + r[i-1]*(1-a)
    return pd.Series(r).ffill().fillna(np.mean(tr[:p])).values

def _adx(h, l, c, p=14):
    h, l, c = np.asarray(h, float), np.asarray(l, float), np.asarray(c, float)
    if len(c) < p*2:
        return np.zeros(len(c))
    tr = np.maximum(h[1:]-l[1:], np.maximum(abs(h[1:]-c[:-1]), abs(l[1:]-c[:-1])))
    u = h[1:]-h[:-1]; d = l[:-1]-l[1:]
    pdi = 100*pd.Series(np.where((u>d)&(u>0), u, 0)).ewm(span=p, adjust=False).mean()/(pd.Series(tr).ewm(span=p, adjust=False).mean()+1e-10)
    mdi = 100*pd.Series(np.where((d>u)&(d>0), d, 0)).ewm(span=p, adjust=False).mean()/(pd.Series(tr).ewm(span=p, adjust=False).mean()+1e-10)
    dx = 100*np.abs(pdi-mdi)/(pdi+mdi+1e-10)
    result = pd.Series(dx).ewm(span=p, adjust=False).mean().values
    return np.concatenate([np.zeros(len(c)-len(result)), result])


# ═══════════════════════════════════════════════════════════════
# V4.0 供需区检测 (含质量评分+时效衰减)
# ═══════════════════════════════════════════════════════════════

def _find_swing(h, l, lb=3):
    h, l = np.asarray(h, float), np.asarray(l, float)
    swh, swl = [], []
    for i in range(lb, len(h)-lb):
        if h[i] == max(h[i-lb:i+lb+1]) and h[i] > max(h[max(0,i-lb-5):i]):
            swh.append((i, h[i]))
        if l[i] == min(l[i-lb:i+lb+1]) and l[i] < min(l[max(0,i-lb-5):i]):
            swl.append((i, l[i]))
    return swh, swl

def _detect_zones_v4(h, l, c, n_bars, min_strength=ZONE_MIN_STRENGTH):
    """V4.0 供需区检测 - 含质量评分"""
    supply_zones, demand_zones = [], []

    swh, swl = _find_swing(h, l, SWING_LOOKBACK)

    # 供应区 (RBD模式)
    for idx, high_val in swh:
        if idx < SWING_LOOKBACK or idx > n_bars - 5:
            continue
        base_start = max(0, idx - 10)
        base_end = min(n_bars - 1, idx + 3)
        base_high = np.max(h[base_start:base_end+1])
        base_low = np.min(l[base_start:base_end+1])
        base_range = base_high - base_low
        if base_range <= 0:
            continue

        # 质量检测: 跌幅/盘整幅度
        drop = high_val - np.min(l[idx+1:idx+4])
        strength = drop / base_range if base_range > 0 else 0

        # 时效衰减: 新区更强
        age = n_bars - idx
        age_factor = max(0.5, 1.0 - age / ZONE_MAX_AGE)

        quality_score = strength * age_factor

        if strength >= min_strength and quality_score >= 0.15:  # 大幅降低质量门槛
            supply_zones.append({
                'type': 'RBD',
                'top': base_high,
                'bottom': base_low - base_range * 0.05,
                'strength': strength,
                'age': age,
                'quality': quality_score,
                'base_range': base_range
            })

    # 需求区 (DBR模式)
    for idx, low_val in swl:
        if idx < SWING_LOOKBACK or idx > n_bars - 5:
            continue
        base_start = max(0, idx - 10)
        base_end = min(n_bars - 1, idx + 3)
        base_high = np.max(h[base_start:base_end+1])
        base_low = np.min(l[base_start:base_end+1])
        base_range = base_high - base_low
        if base_range <= 0:
            continue

        rally = np.max(h[idx+1:idx+4]) - low_val
        strength = rally / base_range if base_range > 0 else 0
        age = n_bars - idx
        age_factor = max(0.5, 1.0 - age / ZONE_MAX_AGE)
        quality_score = strength * age_factor

        if strength >= min_strength and quality_score >= 0.15:  # 大幅降低质量门槛
            demand_zones.append({
                'type': 'DBR',
                'top': base_high + base_range * 0.05,
                'bottom': base_low,
                'strength': strength,
                'age': age,
                'quality': quality_score,
                'base_range': base_range
            })

    return {'supply': supply_zones, 'demand': demand_zones}


# ═══════════════════════════════════════════════════════════════
# V4.0 主策略函数
# ═══════════════════════════════════════════════════════════════

def gen_sdp_v4(h1, h4, d1, cfg, framework: Optional[UnifiedV4Framework] = None) -> List[Dict]:
    """
    SDP V4.0 — 供需区策略机构级升级

    升级特性:
    1. Regime-Aware 动态SL/TP
    2. Zone Quality Scoring (供需区质量评分)
    3. Time Decay (供需区时效衰减)
    4. Multi-TF Resonance (多时间框架共振)
    """
    hc = h1['close'].values.astype(float)
    hh = h1['high'].values.astype(float)
    hl = h1['low'].values.astype(float)

    adx_v = _adx(hh, hl, hc)
    atr_v = _atr(hh, hl, hc)

    # 趋势检测 (H1)
    e50 = _ema(hc, TREND_EMA_FAST) if len(hc) >= TREND_EMA_FAST else np.full(len(hc), np.nan)
    e200 = _ema(hc, TREND_EMA_SLOW) if len(hc) >= TREND_EMA_SLOW else np.full(len(hc), np.nan)

    # H4/D1 EMA
    h4c = h4['close'].values.astype(float)
    h4e50 = _ema(h4c, TREND_EMA_FAST) if len(h4c) >= TREND_EMA_FAST else np.full(len(h4c), np.nan)
    h4e200 = _ema(h4c, TREND_EMA_SLOW) if len(h4c) >= TREND_EMA_SLOW else np.full(len(h4c), np.nan)
    dc = d1['close'].values.astype(float)
    de9 = _ema(dc, 9)
    de21 = _ema(dc, 21)

    lots = cfg.get('lot', 0.1)
    adx_min = cfg.get('adx_min', 20)
    base_sl_mult = cfg.get('sl_mult', 1.5)
    base_tp_mult = cfg.get('rr_mult', 3.0)

    sig = []

    # 预计算多时间框架供需区
    h4_zones_cache = {}
    d1_zones_cache = {}

    for i in range(100, len(h1)):
        price = hc[i]
        if np.isnan(adx_v[i]) or adx_v[i] < adx_min:
            continue

        a = atr_v[i]
        if np.isnan(a) or a <= 0:
            continue

        # 市况检测
        atr_ratio = a / price if price > 0 else 0
        if atr_ratio > 0.015:
            regime = 'volatile'
        elif adx_v[i] > 35:
            regime = 'strong_trend'
        elif adx_v[i] > 20:
            regime = 'trend'
        else:
            regime = 'ranging'

        # 动态参数
        if regime in ['volatile', 'strong_trend']:
            sl_mult = base_sl_mult * 1.3
            tp_mult = base_tp_mult * 1.2
        elif regime == 'ranging':
            sl_mult = base_sl_mult * 0.7
            tp_mult = base_tp_mult * 0.8
        else:
            sl_mult = base_sl_mult
            tp_mult = base_tp_mult

        # 趋势方向
        trend = 'UP' if e50[i] > e200[i] else 'DOWN'
        h4i = min(i // 4, len(h4c) - 1)
        d1i = min(i // 24, len(dc) - 1)

        # H4供需区
        if h4i not in h4_zones_cache:
            h4_chunk = h4.iloc[max(0, h4i-50):h4i+1]
            if len(h4_chunk) >= 30:
                h4_zones_cache[h4i] = _detect_zones_v4(
                    h4_chunk['high'].values,
                    h4_chunk['low'].values,
                    h4_chunk['close'].values,
                    len(h4_chunk)
                )
        h4_zones = h4_zones_cache.get(h4i, {'supply': [], 'demand': []})

        # D1供需区
        if d1i not in d1_zones_cache:
            d1_chunk = d1.iloc[max(0, d1i-30):d1i+1]
            if len(d1_chunk) >= 20:
                d1_zones_cache[d1i] = _detect_zones_v4(
                    d1_chunk['high'].values,
                    d1_chunk['low'].values,
                    d1_chunk['close'].values,
                    len(d1_chunk)
                )
        d1_zones = d1_zones_cache.get(d1i, {'supply': [], 'demand': []})

        # 多时间框架共振
        h1_zones = _detect_zones_v4(hh, hl, hc, i + 1)

        # D1趋势
        d1_dir = 'UP' if (d1i >= 20 and de9[d1i] > de21[d1i]) else 'DOWN'

        # 寻找供需区
        zc = None
        zt = None
        zone_quality = 0

        for z in h1_zones.get('demand', []) + h4_zones.get('demand', []) + d1_zones.get('demand', []):
            if z['quality'] > zone_quality and price > z['bottom'] and price - z['bottom'] < a * 5:
                zc, zt, zone_quality = z, 'D', z['quality']

        if not zc:
            for z in h1_zones.get('supply', []) + h4_zones.get('supply', []) + d1_zones.get('supply', []):
                if z['quality'] > zone_quality and price < z['top'] and z['top'] - price < a * 5:
                    zc, zt, zone_quality = z, 'S', z['quality']

        if not zc:
            continue

        # 方向确认
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

        # SL/TP计算
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

        # 多时间框架确认加分
        tf_confirm = sum([
            any(z['bottom'] < price < z['top'] for z in h1_zones.get('demand', []) if zt == 'D' or z['type'] == 'S'),
            any(z['bottom'] < price < z['top'] for z in h4_zones.get('demand', []) if zt == 'D' or z['type'] == 'S'),
            any(z['bottom'] < price < z['top'] for z in d1_zones.get('demand', []) if zt == 'D' or z['type'] == 'S'),
        ])

        sig.append({
            'bar': i, 'side': 1 if direction == 'BUY' else -1,
            'entry': price, 'sl': sl, 'tp': tp,
            'regime': f'sdp_v4_{regime}_q{zone_quality:.2f}',
            'strat': 'SDP', 'lot': lots,
            'adx': adx_v[i], 'atr': a,
            'zone_quality': zone_quality,
            'tf_confirm': tf_confirm,
            'sl_mult': sl_mult, 'tp_mult': tp_mult,
            'risk_tier': 1.0
        })

    return sig


# ═══════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 70)
    print("SDP V4.0 自检")
    print("=" * 70)

    np.random.seed(42)
    n = 500
    closes = [100.0]
    for i in range(1, n):
        trend = 0.01 * np.sin(i * 0.01)
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

    sigs = gen_sdp_v4(h1, h4, d1, cfg)
    print(f"\n生成信号: {len(sigs)} 个")
    if sigs:
        buys = [s for s in sigs if s['side'] == 1]
        sells = [s for s in sigs if s['side'] == -1]
        print(f"  买入: {len(buys)}, 卖出: {len(sells)}")
        print(f"  平均ADX: {np.mean([s['adx'] for s in sigs]):.1f}")
        print(f"  平均区质量: {np.mean([s['zone_quality'] for s in sigs]):.2f}")
        print(f"  平均TF确认: {np.mean([s['tf_confirm'] for s in sigs]):.1f}")

    print("\n" + "=" * 70)
    print("✅ SDP V4.0 自检完成")
    print("=" * 70)
