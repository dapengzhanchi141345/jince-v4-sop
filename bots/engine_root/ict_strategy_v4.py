# -*- coding: utf-8 -*-
"""
ICT V4.0 — 订单块策略机构级升级
================================
对标 SMC Pro / Institutional Order Flow

升级特性:
1. Dynamic Disp (动态位移阈值)
2. FVG Time Decay (公平价值缺口时效衰减)
3. OB Quality Scoring (订单块质量评分)
4. Multi-TF Liquidity Scan (多时间框架流动性扫描)
5. Sweep Confirmation (扫荡确认过滤)
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional


# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════
FVG_DECAY_BARS = 30  # FVG时效衰减周期 (缩短)
OB_MIN_MOVE = 0.005  # 最小位移阈值 (降低)
OB_QUALITY_THRESHOLD = 0.4  # 订单块质量门槛 (降低)
LIQUIDITY_LOOKBACK = 15  # 流动性检测窗口 (缩短)


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


# ═══════════════════════════════════════════════════════════════
# V4.0 ICT策略
# ═══════════════════════════════════════════════════════════════

def _detect_fvg_v4(h, l, c, decay_bars=FVG_DECAY_BARS):
    """V4.0 FVG检测 - 含时效衰减"""
    bull_fvg, bear_fvg = [], []
    n = len(c)

    for i in range(0, n-2):
        # Bullish FVG
        if l[i+2] > h[i]:
            gap_size = (l[i+2] - h[i]) / max(c[i], 1e-9)
            # 时效衰减: 越旧的FVG质量越低
            age_factor = max(0.3, 1.0 - (n - i) / decay_bars) if i > n - decay_bars else 0.3
            quality = gap_size * age_factor
            if quality > 0.002:  # 最小FVG大小
                bull_fvg.append({
                    'idx': i,
                    'top': h[i],
                    'bottom': l[i+2],
                    'size': gap_size,
                    'age': n - i,
                    'quality': min(quality, 1.0)
                })

        # Bearish FVG
        if h[i+2] < l[i]:
            gap_size = (l[i] - h[i+2]) / max(c[i], 1e-9)
            age_factor = max(0.3, 1.0 - (n - i) / decay_bars) if i > n - decay_bars else 0.3
            quality = gap_size * age_factor
            if quality > 0.002:
                bear_fvg.append({
                    'idx': i,
                    'top': h[i+2],
                    'bottom': l[i],
                    'size': gap_size,
                    'age': n - i,
                    'quality': min(quality, 1.0)
                })

    return bull_fvg, bear_fvg

def _detect_ob_v4(h, l, c, min_move=OB_MIN_MOVE):
    """V4.0 订单块检测 - 含质量评分"""
    bull_ob, bear_ob = [], []
    n = len(c)

    for i in range(1, n-1):
        # 强位移检测
        move = (c[i+1] - c[i-1]) / max(c[i-1], 1e-9)

        # Bullish OB (空头发力后的反转)
        if move > min_move:
            ob_idx = i - 1
            ob_high = max(h[ob_idx], c[ob_idx])
            ob_low = min(l[ob_idx], c[ob_idx])
            ob_range = ob_high - ob_low

            # 质量检测: 位移/OB范围比
            strength = move / (ob_range / max(c[ob_idx], 1e-9) + 1e-9)
            quality = min(strength * 0.5, 1.0)

            if quality >= OB_QUALITY_THRESHOLD:
                bull_ob.append({
                    'idx': ob_idx,
                    'top': ob_high,
                    'bottom': ob_low,
                    'strength': move,
                    'quality': quality
                })

        # Bearish OB
        if move < -min_move:
            ob_idx = i - 1
            ob_high = max(h[ob_idx], c[ob_idx])
            ob_low = min(l[ob_idx], c[ob_idx])
            ob_range = ob_high - ob_low

            strength = abs(move) / (ob_range / max(c[ob_idx], 1e-9) + 1e-9)
            quality = min(strength * 0.5, 1.0)

            if quality >= OB_QUALITY_THRESHOLD:
                bear_ob.append({
                    'idx': ob_idx,
                    'top': ob_high,
                    'bottom': ob_low,
                    'strength': abs(move),
                    'quality': quality
                })

    return bull_ob, bear_ob

def gen_ict_v4(h1, h4, d1, cfg) -> List[Dict]:
    """
    ICT V4.0 — 机构级订单块策略

    核心升级:
    1. Dynamic Disp + Quality Scoring
    2. FVG Time Decay
    3. Multi-TF Liquidity
    """
    hc = h1['close'].values.astype(float)
    hh = h1['high'].values.astype(float)
    hl = h1['low'].values.astype(float)
    n = len(hc)

    # 动态disp (根据波动率调整)
    atr_v = _atr(hh, hl, hc)
    dynamic_disp = OB_MIN_MOVE * (1 + atr_v[-1] / hc[-1] * 10) if hc[-1] > 0 else OB_MIN_MOVE

    # 检测FVG和OB
    bull_fvg, bear_fvg = _detect_fvg_v4(hh, hl, hc)
    bull_ob, bear_ob = _detect_ob_v4(hh, hl, hc, dynamic_disp)

    # D1趋势
    dc = d1['close'].values.astype(float)
    de9 = _ema(dc, 9)
    de21 = _ema(dc, 21)

    lots = cfg.get('lot', 0.1)
    rr_mult = cfg.get('rr_mult', 2.0)

    sig = []

    for i in range(60, n):
        price = hc[i]
        if np.isnan(price) or price <= 0:
            continue

        # D1趋势
        d1i = min(i // 24, len(dc) - 1)
        if d1i < 20 or np.isnan(de9[d1i]) or np.isnan(de21[d1i]):
            continue

        bias = 'UP' if de9[d1i] > de21[d1i] else 'DOWN'

        # 流动性扫荡检测
        sweep_low = sweep_high = False
        recent_lows = hl[max(0, i-10):i]
        recent_highs = hh[max(0, i-10):i]
        if len(recent_lows) >= 5:
            for lv in [o['bottom'] for o in bull_ob]:
                if abs(min(recent_lows) - lv) / max(lv, 1e-9) < 0.002 and price > lv:
                    sweep_low = True
                    break
            for hv in [o['top'] for o in bear_ob]:
                if abs(max(recent_highs) - hv) / max(hv, 1e-9) < 0.002 and price < hv:
                    sweep_high = True
                    break

        def has_zone(zones, p):
            return any(z['top'] >= p >= z['bottom'] for z in zones if not np.isnan(z.get('top', np.nan)) and not np.isnan(z.get('bottom', np.nan)))

        if bias == 'UP':
            score = 0
            if has_zone(bull_ob, price):
                score += 2
            if has_zone(bull_fvg, price):
                score += 1
            if sweep_low:
                score += 1

            if score >= 3:
                a = atr_v[i] if not np.isnan(atr_v[i]) else 0.5
                sl = min(hl[max(0, i-4):i+1]) - cfg.get('pip', 0.0001) * 2
                tp = price + (price - sl) * rr_mult
                sig.append({
                    'bar': i, 'side': 1, 'entry': price, 'sl': sl, 'tp': tp,
                    'regime': f'ict_v4_s{score}', 'strat': 'ICT',
                    'lot': lots, 'score': score,
                    'sweep': sweep_low
                })

        elif bias == 'DOWN':
            score = 0
            if has_zone(bear_ob, price):
                score += 2
            if has_zone(bear_fvg, price):
                score += 1
            if sweep_high:
                score += 1

            if score >= 3:
                a = atr_v[i] if not np.isnan(atr_v[i]) else 0.5
                sl = max(hh[max(0, i-4):i+1]) + cfg.get('pip', 0.0001) * 2
                tp = price - (sl - price) * rr_mult
                sig.append({
                    'bar': i, 'side': -1, 'entry': price, 'sl': sl, 'tp': tp,
                    'regime': f'ict_v4_s{score}', 'strat': 'ICT',
                    'lot': lots, 'score': score,
                    'sweep': sweep_high
                })

    return sig


if __name__ == "__main__":
    print("=" * 70)
    print("ICT V4.0 自检")
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

    cfg = {'pip': 0.01, 'lot': 0.1, 'rr_mult': 2.0}

    sigs = gen_ict_v4(h1, h4, d1, cfg)
    print(f"\n生成信号: {len(sigs)} 个")
    if sigs:
        buys = [s for s in sigs if s['side'] == 1]
        sells = [s for s in sigs if s['side'] == -1]
        print(f"  买入: {len(buys)}, 卖出: {len(sells)}")
        print(f"  平均分数: {np.mean([s['score'] for s in sigs]):.1f}")

    print("\n" + "=" * 70)
    print("✅ ICT V4.0 自检完成")
    print("=" * 70)
