# -*- coding: utf-8 -*-
"""
PASD V3.0: 价格行为+供需深度融合策略 (深度优化版)
==================================================
V3.0 升级要点:
1. **动态共振检测** — 对每个bar独立计算供需区和共振得分
2. **趋势柔性过滤** — 仅H4/H1共识即可，降低刚性门槛
3. **质量门槛自适应** — 高分信号缩短冷却，低分信号延长冷却
4. **PB形态分级** — Pin Bar 2分, Engulf 3分, MSS 2分
5. **回测修复** — 检查高低点触发SL/TP，不再只看收盘价

目标: 胜率≥50%, PF≥1.8
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from collections import defaultdict


# ═══════════════════════════════════════════════════════════════
# 配置常量 (V3.0 动态参数)
# ═══════════════════════════════════════════════════════════════
SWING_LOOKBACK = 5
ZONE_MIN_STRENGTH = 1.0
ZONE_MAX_AGE = 60

PB_LOOKBACK = 10
PIN_BAR_BODY_RATIO = 0.35
ENGULF_THRESHOLD = 0.4

TREND_EMA_FAST = 50
TREND_EMA_SLOW = 200
TREND_STRENGTH_MIN = 0.002

# V3.0 动态冷却
SIGNAL_COOLDOWN_BASE = 20
ZONE_COOLDOWN_BASE = 40

# V3.0 动态质量门槛
MIN_RESONANCE_BASE = 0.1
MIN_PB_SCORE_BASE = 2

SL_ATR_MULT = 1.2
TP_RR = 2.5
ENTRY_CONFIRM_BARS = 3


# ═══════════════════════════════════════════════════════════════
# 基础指标函数
# ═══════════════════════════════════════════════════════════════

def _atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, period: int = 14) -> np.ndarray:
    tr = np.maximum(
        h[1:] - l[1:],
        np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1]))
    )
    atr = np.full(len(h), np.nan)
    if len(tr) >= period:
        atr[period] = np.mean(tr[:period])
        for i in range(period + 1, len(h)):
            atr[i] = tr[i-1] / period + atr[i-1] * (period - 1) / period
    return pd.Series(atr).ffill().fillna(np.mean(tr[:period])).values


def _ema(v: np.ndarray, period: int) -> np.ndarray:
    k = 2.0 / (period + 1)
    result = np.full(len(v), np.nan)
    if len(v) > 0:
        result[0] = v[0]
        for i in range(1, len(v)):
            result[i] = v[i] * k + result[i-1] * (1 - k)
    return result


def _find_swing_points(h: np.ndarray, l: np.ndarray, lb: int = SWING_LOOKBACK):
    highs, lows = [], []
    for i in range(lb, len(h) - lb):
        if h[i] == max(h[i-lb:i+lb+1]) and h[i] > max(h[max(0,i-lb-5):i]):
            highs.append((i, h[i]))
        if l[i] == min(l[i-lb:i+lb+1]) and l[i] < min(l[max(0,i-lb-5):i]):
            lows.append((i, l[i]))
    return highs, lows


# ═══════════════════════════════════════════════════════════════
# 供需区检测
# ═══════════════════════════════════════════════════════════════

def _detect_supply_demand_zones(h: np.ndarray, l: np.ndarray, c: np.ndarray,
                                 min_strength: float = ZONE_MIN_STRENGTH) -> Dict:
    supply_zones, demand_zones = [], []
    n = len(c)
    if n < 30:
        return {'supply': [], 'demand': []}

    sw_h, sw_l = _find_swing_points(h, l, SWING_LOOKBACK)

    # 供应区: RBD模式
    for idx, high_price in sw_h:
        if idx < SWING_LOOKBACK or idx > n - 5:
            continue
        base_start = max(0, idx - 10)
        base_end = min(n - 1, idx + 3)
        base_high = np.max(h[base_start:base_end+1])
        base_low = np.min(l[base_start:base_end+1])
        base_range = base_high - base_low
        if base_range <= 0:
            continue
        drop = high_price - np.min(l[idx+1:idx+4])
        strength = drop / base_range if base_range > 0 else 0
        if strength >= min_strength:
            supply_zones.append({
                'type': 'RBD', 'top': base_high, 'bottom': base_low - base_range * 0.05,
                'strength': strength, 'age': n - idx, 'base_range': base_range
            })

    # 需求区: DBR模式
    for idx, low_price in sw_l:
        if idx < SWING_LOOKBACK or idx > n - 5:
            continue
        base_start = max(0, idx - 10)
        base_end = min(n - 1, idx + 3)
        base_high = np.max(h[base_start:base_end+1])
        base_low = np.min(l[base_start:base_end+1])
        base_range = base_high - base_low
        if base_range <= 0:
            continue
        rally = np.max(h[idx+1:idx+4]) - low_price
        strength = rally / base_range if base_range > 0 else 0
        if strength >= min_strength:
            demand_zones.append({
                'type': 'DBR', 'top': base_high + base_range * 0.05, 'bottom': base_low,
                'strength': strength, 'age': n - idx, 'base_range': base_range
            })

    return {'supply': supply_zones, 'demand': demand_zones}


# ═══════════════════════════════════════════════════════════════
# 趋势检测
# ═══════════════════════════════════════════════════════════════

def _detect_trend(c: np.ndarray) -> Dict:
    if len(c) < TREND_EMA_SLOW:
        return {'direction': 'NEUTRAL', 'strength': 0, 'ema_fast': np.nan, 'ema_slow': np.nan}

    ema_fast = _ema(c, TREND_EMA_FAST)
    ema_slow = _ema(c, TREND_EMA_SLOW)

    fast = ema_fast[-1]
    slow = ema_slow[-1]

    if np.isnan(fast) or np.isnan(slow) or slow == 0:
        return {'direction': 'NEUTRAL', 'strength': 0, 'ema_fast': fast, 'ema_slow': slow}

    spread = (fast - slow) / abs(slow)
    direction = 'UP' if spread > 0 else 'DOWN'
    strength = abs(spread)

    return {
        'direction': direction,
        'strength': strength,
        'ema_fast': fast,
        'ema_slow': slow,
        'spread': spread
    }


# ═══════════════════════════════════════════════════════════════
# 价格行为检测
# ═══════════════════════════════════════════════════════════════

def _detect_pin_bar(h: np.ndarray, l: np.ndarray, c: np.ndarray, i: int):
    if i < 1 or i >= len(c) - 1:
        return None
    body = abs(c[i] - c[i-1])
    upper_wick = h[i] - max(c[i], c[i-1])
    lower_wick = min(c[i], c[i-1]) - l[i]
    total_range = h[i] - l[i]
    if total_range <= 0 or body / total_range > PIN_BAR_BODY_RATIO:
        return None
    if lower_wick > body * 2 and upper_wick < body:
        return {'type': 'bullish_pin', 'wick_ratio': lower_wick / (body + 1e-10), 'score': 2}
    if upper_wick > body * 2 and lower_wick < body:
        return {'type': 'bearish_pin', 'wick_ratio': upper_wick / (body + 1e-10), 'score': -2}
    return None


def _detect_engulfing(h: np.ndarray, l: np.ndarray, c: np.ndarray, i: int):
    if i < 2:
        return None
    curr_open, curr_close = c[i-1], c[i]
    prev_open, prev_close = c[i-2], c[i-1]
    curr_body = abs(curr_close - curr_open)
    prev_body = abs(prev_close - prev_open)
    if curr_body <= 0 or prev_body <= 0:
        return None
    if curr_close > curr_open and prev_close < prev_open:
        if curr_open <= prev_close and curr_close >= prev_open:
            return {'type': 'bullish_engulf', 'body_ratio': curr_body / (prev_body + 1e-10), 'score': 3}
    if curr_close < curr_open and prev_close > prev_open:
        if curr_open >= prev_close and curr_close <= prev_open:
            return {'type': 'bearish_engulf', 'body_ratio': curr_body / (prev_body + 1e-10), 'score': -3}
    return None


def _detect_mss(h: np.ndarray, l: np.ndarray, sw_h, sw_l, i: int):
    if not sw_h or not sw_l:
        return None
    recent_highs = [(idx, price) for idx, price in sw_h if idx > i - 25 and idx < i]
    recent_lows = [(idx, price) for idx, price in sw_l if idx > i - 25 and idx < i]
    if recent_highs:
        last_idx, last_high = recent_highs[-1]
        if h[i] > last_high and i > last_idx + 5:
            return {'type': 'bullish_mss', 'score': 2}
    if recent_lows:
        last_idx, last_low = recent_lows[-1]
        if l[i] < last_low and i > last_idx + 5:
            return {'type': 'bearish_mss', 'score': -2}
    return None


def calculate_pb_score(h: np.ndarray, l: np.ndarray, c: np.ndarray, i: int) -> Dict:
    score, signals = 0, []
    pin = _detect_pin_bar(h, l, c, i)
    if pin:
        score += pin['score']; signals.append(pin['type'])
    engulf = _detect_engulfing(h, l, c, i)
    if engulf:
        score += engulf['score']; signals.append(engulf['type'])
    sw_h, sw_l = _find_swing_points(h, l, SWING_LOOKBACK)
    mss = _detect_mss(h, l, sw_h, sw_l, i)
    if mss:
        score += mss['score']; signals.append(mss['type'])
    return {'score': score, 'signals': signals, 'strength': min(5.0, max(-5.0, score))}


# ═══════════════════════════════════════════════════════════════
# V3.0 多时间框架供需共振分析
# ═══════════════════════════════════════════════════════════════

def analyze_multiframe_zones_v3(h1: pd.DataFrame, h4: pd.DataFrame, d1: pd.DataFrame,
                                 current_idx: int) -> Dict:
    """V3.0 动态共振检测 — 对指定bar独立计算"""
    # 截取到当前bar的数据
    h1_cur = h1.iloc[:current_idx+1]
    h4_cur = h4.iloc[:min(current_idx//4+1, len(h4))]
    d1_cur = d1.iloc[:min(current_idx//20+1, len(d1))]

    current_price = h1_cur['close'].values[-1]

    h1_supply = _detect_supply_demand_zones(h1_cur['high'].values, h1_cur['low'].values, h1_cur['close'].values)['supply']
    h1_demand = _detect_supply_demand_zones(h1_cur['high'].values, h1_cur['low'].values, h1_cur['close'].values)['demand']
    h4_supply = _detect_supply_demand_zones(h4_cur['high'].values, h4_cur['low'].values, h4_cur['close'].values)['supply']
    h4_demand = _detect_supply_demand_zones(h4_cur['high'].values, h4_cur['low'].values, h4_cur['close'].values)['demand']
    d1_supply = _detect_supply_demand_zones(d1_cur['high'].values, d1_cur['low'].values, d1_cur['close'].values)['supply']
    d1_demand = _detect_supply_demand_zones(d1_cur['high'].values, d1_cur['low'].values, d1_cur['close'].values)['demand']

    near_threshold = 0.05

    def find_zone_in_direction(zones, price, direction, threshold):
        for z in zones:
            if direction == 'up':
                if z['bottom'] > price and (z['bottom'] - price) / price < threshold:
                    return z
            else:
                if z['top'] < price and (price - z['top']) / price < threshold:
                    return z
        return None

    h1_demand_zone = find_zone_in_direction(h1_demand, current_price, 'down', near_threshold)
    h1_supply_zone = find_zone_in_direction(h1_supply, current_price, 'up', near_threshold)
    h4_demand_zone = find_zone_in_direction(h4_demand, current_price, 'down', near_threshold)
    h4_supply_zone = find_zone_in_direction(h4_supply, current_price, 'up', near_threshold)
    d1_demand_zone = find_zone_in_direction(d1_demand, current_price, 'down', near_threshold)
    d1_supply_zone = find_zone_in_direction(d1_supply, current_price, 'up', near_threshold)

    # 计算共振得分
    score = 0.0
    if h1_demand_zone or h1_supply_zone:
        score += 0.15
    if h4_demand_zone or h4_supply_zone:
        score += 0.2
    if d1_demand_zone or d1_supply_zone:
        score += 0.25

    # 同向共振加分
    if h1_demand_zone and h4_demand_zone and d1_demand_zone:
        score += 0.3
    elif h1_supply_zone and h4_supply_zone and d1_supply_zone:
        score += 0.3
    elif h1_demand_zone and h4_demand_zone:
        score += 0.2
    elif h1_supply_zone and h4_supply_zone:
        score += 0.2

    total_zones = len(h1_supply) + len(h1_demand) + len(h4_supply) + len(h4_demand) + len(d1_supply) + len(d1_demand)
    if total_zones > 0:
        score = max(score, 0.1)

    return {
        'zones': {'supply': h1_supply + h4_supply + d1_supply,
                  'demand': h1_demand + h4_demand + d1_demand},
        'resonance_score': min(score, 1.0),
        'primary_tf': 'D1' if score >= 0.6 else 'H4' if score >= 0.4 else 'H1',
        'near_zones': {
            'd1_supply': d1_supply_zone, 'd1_demand': d1_demand_zone,
            'h4_supply': h4_supply_zone, 'h4_demand': h4_demand_zone,
            'h1_supply': h1_supply_zone, 'h1_demand': h1_demand_zone
        }
    }


# ═══════════════════════════════════════════════════════════════
# V3.0 主策略函数
# ═══════════════════════════════════════════════════════════════

def gen_pasd(h1: pd.DataFrame, h4: pd.DataFrame, d1: pd.DataFrame, cfg: dict) -> List[Dict]:
    """
    PASD V3.0 — 价格行为+供需深度融合策略 (深度优化版)

    核心改进:
    1. 动态共振检测 (每bar独立计算)
    2. 趋势柔性过滤
    3. 质量门槛自适应
    4. PB形态分级
    """
    hc = h1['close'].values.astype(float)
    hh = h1['high'].values.astype(float)
    hl = h1['low'].values.astype(float)
    h4c = h4['close'].values.astype(float)
    dc = d1['close'].values.astype(float)

    atr_v = _atr(hh, hl, hc)
    lots = cfg.get('lot', 0.1)
    n = len(h1)

    # 趋势检测
    trend_h1 = _detect_trend(hc)
    trend_h4 = _detect_trend(h4c)
    trend_d1 = _detect_trend(dc)

    trend_up = sum(1 for t in [trend_h1, trend_h4, trend_d1] if t['direction'] == 'UP')
    trend_dn = sum(1 for t in [trend_h1, trend_h4, trend_d1] if t['direction'] == 'DOWN')
    trend_strength = max(trend_h1['strength'], trend_h4['strength'], trend_d1['strength'])

    # 预计算PB得分
    pb_scores = [calculate_pb_score(hh, hl, hc, i) for i in range(n)]

    # V3.0 冷却记录
    last_buy_bar = -999
    last_sell_bar = -999
    last_zone_bar = {}

    sig = []
    for i in range(60, n):
        price = hc[i]
        if np.isnan(atr_v[i]) or atr_v[i] <= 0:
            continue
        a = atr_v[i]
        pb = pb_scores[i]

        # V3.0: 动态共振检测
        mf_cur = analyze_multiframe_zones_v3(h1, h4, d1, i)
        mf_zones = mf_cur['zones']
        mf_resonance = mf_cur['resonance_score']

        # V3.0: 动态质量门槛 (高分信号降低门槛)
        dynamic_min_resonance = MIN_RESONANCE_BASE * (1.0 - mf_resonance * 0.5)
        dynamic_min_pb = max(1, MIN_PB_SCORE_BASE - int(mf_resonance * 2))

        if mf_resonance < dynamic_min_resonance or abs(pb['score']) < dynamic_min_pb:
            continue

        # V3.0: 柔性趋势过滤 (仅H4/H1共识即可)
        if trend_up >= 2 and pb['score'] < 0:
            continue
        if trend_dn >= 2 and pb['score'] > 0:
            continue
        if trend_strength < TREND_STRENGTH_MIN:
            continue

        # V3.0: 动态冷却 (高分信号缩短冷却)
        cooldown_mult = max(0.5, 1.0 - abs(pb['score']) * 0.1)
        dynamic_cooldown = int(SIGNAL_COOLDOWN_BASE * cooldown_mult)

        if pb['score'] > 0:
            if i - last_buy_bar < dynamic_cooldown:
                continue
        else:
            if i - last_sell_bar < dynamic_cooldown:
                continue

        # 需求区买入
        if pb['score'] > 0:
            for idx_z, z in enumerate(mf_zones['demand']):
                if not (price <= z['top'] and price >= z['bottom'] - a * 2.0):
                    continue
                zone_key = f"D{idx_z}"
                zone_cooldown = int(ZONE_COOLDOWN_BASE * (1.0 - z['strength'] * 0.1))
                if i - last_zone_bar.get(zone_key, -999) < zone_cooldown:
                    continue

                if i >= 3:
                    confirm_bars = hc[i-3:i]
                    if not np.all(confirm_bars < price + a * 0.3):
                        continue

                entry = min(price, z['top'])
                sl = z['bottom'] - a * SL_ATR_MULT
                if sl >= entry:
                    continue
                tp = entry + (entry - sl) * TP_RR

                sig.append({
                    'bar': i, 'side': 1, 'entry': entry, 'sl': sl, 'tp': tp,
                    'regime': f'pasd_v3_demand_r{mf_resonance:.2f}', 'strat': 'PASD',
                    'lot': lots, 'zone_strength': z['strength'],
                    'pb_score': pb['score'], 'mf_resonance': mf_resonance,
                    'trend': trend_h1['direction'], 'atr': a
                })
                last_buy_bar = i
                last_zone_bar[zone_key] = i
                break
            continue

        # 供应区卖出
        if pb['score'] < 0:
            for idx_z, z in enumerate(mf_zones['supply']):
                if not (price >= z['bottom'] and price <= z['top'] + a * 2.0):
                    continue
                zone_key = f"S{idx_z}"
                zone_cooldown = int(ZONE_COOLDOWN_BASE * (1.0 - z['strength'] * 0.1))
                if i - last_zone_bar.get(zone_key, -999) < zone_cooldown:
                    continue

                if i >= 3:
                    confirm_bars = hc[i-3:i]
                    if not np.all(confirm_bars > price - a * 0.3):
                        continue

                entry = max(price, z['bottom'])
                sl = z['top'] + a * SL_ATR_MULT
                if sl <= entry:
                    continue
                tp = entry - (sl - entry) * TP_RR

                sig.append({
                    'bar': i, 'side': -1, 'entry': entry, 'sl': sl, 'tp': tp,
                    'regime': f'pasd_v3_supply_r{mf_resonance:.2f}', 'strat': 'PASD',
                    'lot': lots, 'zone_strength': z['strength'],
                    'pb_score': pb['score'], 'mf_resonance': mf_resonance,
                    'trend': trend_h1['direction'], 'atr': a
                })
                last_sell_bar = i
                last_zone_bar[zone_key] = i
                break

    return sig


# ═══════════════════════════════════════════════════════════════
# V3.0 回测函数
# ═══════════════════════════════════════════════════════════════

def backtest_pasd_v3(h1_data: pd.DataFrame, h4_data: pd.DataFrame, d1_data: pd.DataFrame,
                     initial_equity: float = 10000.0, pip_usd: float = 10.0) -> Dict:
    """PASD V3.0 回测"""
    signals = gen_pasd(h1_data, h4_data, d1_data, {'pip': 0.01, 'lot': 0.1})
    if not signals:
        return {'signals': 0, 'trades': 0, 'win_rate': 0, 'pnl': 0}

    equity = initial_equity
    trades = []
    position = 0
    entry_price = 0
    sl_price = 0
    tp_price = 0
    lot = 0.1

    for i, sig in enumerate(signals):
        if position == 0:
            position = sig['side']
            entry_price = sig['entry']
            sl_price = sig['sl']
            tp_price = sig['tp']
            lot = sig.get('lot', 0.1)
            continue

        end = min(i + 50, len(h1_data))
        path = h1_data.iloc[i:end]

        for _, row in path.iterrows():
            high = row['high']; low = row['low']

            if position == 1:
                if low <= sl_price:
                    pnl = (entry_price - sl_price) * 100 * lot * pip_usd / 100
                    trades.append({'type': 'BUY', 'result': 'loss', 'pnl': pnl})
                    position = 0; break
                if high >= tp_price:
                    pnl = (tp_price - entry_price) * 100 * lot * pip_usd / 100
                    trades.append({'type': 'BUY', 'result': 'win', 'pnl': pnl})
                    position = 0; break
            else:
                if high >= sl_price:
                    pnl = (sl_price - entry_price) * 100 * lot * pip_usd / 100
                    trades.append({'type': 'SELL', 'result': 'loss', 'pnl': pnl})
                    position = 0; break
                if low <= tp_price:
                    pnl = (entry_price - tp_price) * 100 * lot * pip_usd / 100
                    trades.append({'type': 'SELL', 'result': 'win', 'pnl': pnl})
                    position = 0; break

    if not trades:
        return {'signals': len(signals), 'trades': 0, 'win_rate': 0.0, 'total_pnl': 0.0, 'profit_factor': 0.0, 'wins': 0, 'losses': 0}

    wins = [t for t in trades if t['result'] == 'win']
    losses = [t for t in trades if t['result'] == 'loss']
    total_pnl = sum(t['pnl'] for t in trades)

    return {
        'signals': len(signals),
        'trades': len(trades),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': len(wins) / len(trades) * 100 if trades else 0,
        'total_pnl': total_pnl,
        'avg_win': np.mean([t['pnl'] for t in wins]) if wins else 0,
        'avg_loss': np.mean([t['pnl'] for t in losses]) if losses else 0,
        'profit_factor': abs(sum(t['pnl'] for t in wins) / sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses) != 0 else float('inf'),
    }


# 自检
if __name__ == "__main__":
    print("=== PASD V3.0 自检 ===\n")
    np.random.seed(42)
    n = 300
    trend = np.linspace(100, 108, n)
    noise = np.random.randn(n) * 0.3
    closes = trend + noise
    highs = closes + np.abs(np.random.randn(n)) * 0.2
    lows = closes - np.abs(np.random.randn(n)) * 0.2
    times = np.arange(n) * 3600
    h1 = pd.DataFrame({'open': closes, 'high': highs, 'low': lows, 'close': closes, 'time': times})
    h4 = pd.DataFrame({'open': closes[::4], 'high': highs[::4], 'low': lows[::4], 'close': closes[::4], 'time': times[::4]})
    d1 = pd.DataFrame({'open': closes[::20], 'high': highs[::20], 'low': lows[::20], 'close': closes[::20], 'time': times[::20]})

    cfg = {'pip': 0.01, 'lot': 0.1}
    signals = gen_pasd(h1, h4, d1, cfg)
    print(f"信号数: {len(signals)}")
    if signals:
        buys = [s for s in signals if s['side'] == 1]
        sells = [s for s in signals if s['side'] == -1]
        print(f"  买入: {len(buys)}, 卖出: {len(sells)}")
        print(f"  平均PB: {np.mean([s['pb_score'] for s in signals]):.1f}")
        print(f"  平均共振: {np.mean([s['mf_resonance'] for s in signals]):.2f}")

    result = backtest_pasd_v3(h1, h4, d1)
    print(f"\n回测结果:")
    print(f"  信号: {result['signals']}, 交易: {result['trades']}")
    print(f"  胜率: {result['win_rate']:.1f}%, 盈亏: ${result['total_pnl']:.2f}")
    print(f"  PF: {result['profit_factor']:.2f}")
    print("\n=== V3.0 自检完成 ===")
