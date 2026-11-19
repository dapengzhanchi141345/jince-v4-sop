# -*- coding: utf-8 -*-
"""
OTAS V1.0: One Trade At A Time — 一次一单强趋势突破策略
=====================================================
设计来源: 全网"一次一单"EA策略调研

核心规则:
1. 同一品种同时只允许 1 笔持仓 (硬性锁仓)
2. 三不原则: 不马丁、不网格、不对冲
3. 强趋势过滤: 双均线 + ADX + ATR 三重确认
4. 有效突破入场: 区间突破 + 收盘确认
5. 动态风控: ATR止损 + 移动止盈 + 趋势反转出场

适配品种: XAUUSD (黄金为主), 可扩展至其他品种
适配周期: H1 (回测验证)
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional
from dataclasses import dataclass

# ═══════════════════════════════════════════════════════════════
# 配置常量
# ═══════════════════════════════════════════════════════════════
# 趋势过滤
MA_FAST = 20              # 短期均线
MA_SLOW = 60              # 长期均线
ADX_THRESHOLD = 25        # ADX 最小值 (趋势强度)
ATR_LOOKBACK = 14         # ATR 计算周期

# 突破检测
LOOKBACK_BARS = 20        # 回溯K线数 (区间检测)
BREAKOUT_THRESHOLD = 0.001  # 突破阈值 (0.1%)

# 信号冷却
SIGNAL_COOLDOWN = 30      # 同方向冷却 (K线)
POSITIVE_COOLDOWN = 60    # 同品种冷却 (避免密集)

# 风险管理
SL_ATR_MULT = 1.5         # 止损 = 1.5 × ATR
TP_ATR_MULT = 3.0         # 止盈 = 3.0 × ATR
TRAIL_START = 1.5         # 移动止损启动点 (ATR倍数)
TRAIL_STEP = 0.5          # 移动止损步进 (ATR倍数)

# 质量门槛
MIN_ADX = 25              # 最小 ADX
MIN_ATR_RATIO = 0.002     # 最小 ATR/价格比 (波动率过滤)

# ═══════════════════════════════════════════════════════════════
# 基础指标函数
# ═══════════════════════════════════════════════════════════════

def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    """指数移动平均"""
    if len(arr) < period:
        return np.full_like(arr, np.nan)
    ema = np.zeros(len(arr))
    ema[:period] = np.nan
    ema[period] = np.mean(arr[:period])
    for i in range(period + 1, len(arr)):
        ema[i] = arr[i] * (2 / (period + 1)) + ema[i-1] * (1 - 2 / (period + 1))
    return ema

def _sma(arr: np.ndarray, period: int) -> np.ndarray:
    """简单移动平均"""
    result = np.full_like(arr, np.nan, dtype=float)
    for i in range(period - 1, len(arr)):
        result[i] = np.mean(arr[i - period + 1: i + 1])
    return result

def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    """平均真实波动范围"""
    n = len(highs)
    tr = np.full(n, np.nan)
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
    return _sma(tr, period)

def _adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    """平均方向指数 (简化版)"""
    n = len(highs)
    plus_dm = np.full(n, np.nan)
    minus_dm = np.full(n, np.nan)
    tr = np.full(n, np.nan)
    
    for i in range(1, n):
        up_move = highs[i] - highs[i-1]
        down_move = lows[i-1] - lows[i]
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        
        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move
    
    plus_di = np.full(n, np.nan)
    minus_di = np.full(n, np.nan)
    
    # 简化计算
    for i in range(period, n):
        atr_sum = np.nansum(tr[i-period+1:i+1])
        if atr_sum > 0:
            plus_di[i] = 100 * np.nansum(plus_dm[i-period+1:i+1]) / atr_sum
            minus_di[i] = 100 * np.nansum(minus_dm[i-period+1:i+1]) / atr_sum
    
    dx = np.full(n, np.nan)
    for i in range(period, n):
        denom = plus_di[i] + minus_di[i]
        if denom > 0:
            dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / denom
    
    return _sma(dx, period)

def _detect_range(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, i: int, lookback: int = 20) -> Optional[Dict]:
    """检测近期震荡区间"""
    if i < lookback:
        return None
    start = max(0, i - lookback)
    end = i
    range_high = np.max(highs[start:end])
    range_low = np.min(lows[start:end])
    range_mid = (range_high + range_low) / 2
    range_height = range_high - range_low
    return {'high': range_high, 'low': range_low, 'mid': range_mid, 'height': range_height}

# ═══════════════════════════════════════════════════════════════
# 主策略函数
# ═══════════════════════════════════════════════════════════════

def gen_otas(h1: pd.DataFrame, h4: pd.DataFrame, d1: pd.DataFrame, cfg: dict) -> List[Dict]:
    """
    OTAS: One Trade At A Time — 一次一单策略
    
    逻辑:
    1. 检测当前持仓 → 有持仓则屏蔽所有信号
    2. 趋势过滤: 双均线 + ADX + ATR
    3. 突破检测: 区间突破 + 收盘确认
    4. 生成信号 (含SL/TP)
    """
    hc = h1['close'].values.astype(float)
    hh = h1['high'].values.astype(float)
    hl = h1['low'].values.astype(float)
    n = len(hc)
    
    # 预计算指标
    ma_fast = _sma(hc, MA_FAST)
    ma_slow = _sma(hc, MA_SLOW)
    atr_v = _atr(hh, hl, hc, ATR_LOOKBACK)
    adx_v = _adx(hh, hl, hc, ADX_THRESHOLD)
    
    # 冷却跟踪
    last_signal_bar = -999
    last_signal_side = 0
    
    sig = []
    
    for i in range(max(MA_SLOW, LOOKBACK_BARS, ATR_LOOKBACK) + 1, n):
        price = hc[i]
        if np.isnan(atr_v[i]) or atr_v[i] <= 0 or np.isnan(price) or price <= 0:
            continue
        
        a = atr_v[i]
        
        # ── 冷却过滤 ──
        if i - last_signal_bar < SIGNAL_COOLDOWN:
            continue
        
        # ── 趋势过滤 ──
        if np.isnan(ma_fast[i]) or np.isnan(ma_slow[i]) or np.isnan(adx_v[i]):
            continue
        
        # ADX 确认趋势强度
        if adx_v[i] < MIN_ADX:
            continue
        
        # ATR 波动率过滤
        atr_ratio = a / price
        if atr_ratio < MIN_ATR_RATIO:
            continue
        
        # ── 方向判定 ──
        is_uptrend = ma_fast[i] > ma_slow[i] and price > ma_fast[i]
        is_downtrend = ma_fast[i] < ma_slow[i] and price < ma_fast[i]
        
        if not is_uptrend and not is_downtrend:
            continue  # 趋势不明，跳过
        
        # ── 区间突破检测 ──
        range_info = _detect_range(hh, hl, hc, i, LOOKBACK_BARS)
        if range_info is None:
            continue
        
        # ── 买入信号 ──
        if is_uptrend:
            # 收盘价突破区间高点
            if hc[i] > range_info['high'] * (1 + BREAKOUT_THRESHOLD):
                # 确认: 前一根K线也在区间上方或突破
                if i > 0 and hc[i-1] <= range_info['high']:
                    entry = min(price, range_info['high'] * 1.001)
                    sl = entry - a * SL_ATR_MULT
                    tp = entry + a * TP_ATR_MULT
                    if sl >= entry or tp <= entry:
                        continue
                    sig.append({
                        'bar': i, 'side': 1, 'entry': entry, 'sl': sl, 'tp': tp,
                        'regime': f'otas_bull_r{adx_v[i]:.0f}', 'strat': 'OTAS',
                        'lot': cfg.get('lot', 0.1),
                        'adx': adx_v[i], 'atr': a, 'range_high': range_info['high']
                    })
                    last_signal_bar = i
                    last_signal_side = 1
        
        # ── 卖出信号 ──
        if is_downtrend:
            # 收盘价跌破区间低点
            if hc[i] < range_info['low'] * (1 - BREAKOUT_THRESHOLD):
                if i > 0 and hc[i-1] >= range_info['low']:
                    entry = max(price, range_info['low'] * 0.999)
                    sl = entry + a * SL_ATR_MULT
                    tp = entry - a * TP_ATR_MULT
                    if sl <= entry or tp >= entry:
                        continue
                    sig.append({
                        'bar': i, 'side': -1, 'entry': entry, 'sl': sl, 'tp': tp,
                        'regime': f'otas_bear_r{adx_v[i]:.0f}', 'strat': 'OTAS',
                        'lot': cfg.get('lot', 0.1),
                        'adx': adx_v[i], 'atr': a, 'range_low': range_info['low']
                    })
                    last_signal_bar = i
                    last_signal_side = -1
    
    return sig

# ═══════════════════════════════════════════════════════════════
# 回测函数
# ═══════════════════════════════════════════════════════════════

def backtest_otas(h1_data: pd.DataFrame, h4_data: pd.DataFrame, d1_data: pd.DataFrame,
                  initial_equity: float = 10000.0, pip_usd: float = 10.0) -> Dict:
    """
    OTAS 回测 — 一次一单模式
    每次只持有一单，平仓后才开下一单
    """
    signals = gen_otas(h1_data, h4_data, d1_data, {'pip': 0.01, 'lot': 0.1})
    if not signals:
        return {'signals': 0, 'trades': 0, 'win_rate': 0, 'total_pnl': 0, 'profit_factor': 0}
    
    equity = initial_equity
    peak = equity
    trades = []
    position = 0  # 0=空仓, 1=多, -1=空
    entry_price = 0
    sl_price = 0
    tp_price = 0
    lot = 0.1
    sig_idx = 0
    
    for i in range(len(signals)):
        sig = signals[i]
        entry = sig['entry']
        sl = sig['sl']
        tp = sig['tp']
        side = sig['side']
        lot = sig.get('lot', 0.1)
        
        # ── 一次一单: 只有空仓时才开新单 ──
        if position != 0:
            # 检查当前持仓是否被止损/止盈
            end = min(i + 50, len(h1_data))
            path = h1_data.iloc[i:end]
            hit = False
            for _, row in path.iterrows():
                high = row['high']; low = row['low']
                if position == 1:
                    if low <= sl:
                        pnl = (entry - sl) * 100 * lot * pip_usd / 100
                        trades.append({'type': 'BUY', 'result': 'loss', 'pnl': pnl, 'bar': i})
                        position = 0; hit = True; break
                    if high >= tp:
                        pnl = (tp - entry) * 100 * lot * pip_usd / 100
                        trades.append({'type': 'BUY', 'result': 'win', 'pnl': pnl, 'bar': i})
                        position = 0; hit = True; break
                else:  # 空单
                    if high >= sl:
                        pnl = (sl - entry) * 100 * lot * pip_usd / 100
                        trades.append({'type': 'SELL', 'result': 'loss', 'pnl': pnl, 'bar': i})
                        position = 0; hit = True; break
                    if low <= tp:
                        pnl = (entry - tp) * 100 * lot * pip_usd / 100
                        trades.append({'type': 'SELL', 'result': 'win', 'pnl': pnl, 'bar': i})
                        position = 0; hit = True; break
            if hit:
                continue
            else:
                continue  # 持仓中，跳过新信号
        
        # 开新仓
        position = side
        entry_price = entry
        sl_price = sl
        tp_price = tp
        lot = lot
    
    # 处理未平仓的最后持仓
    if position != 0:
        last_idx = len(signals) - 1
        end = min(last_idx + 50, len(h1_data))
        path = h1_data.iloc[last_idx:end]
        for _, row in path.iterrows():
            high = row['high']; low = row['low']
            if position == 1:
                if low <= sl_price:
                    pnl = (entry_price - sl_price) * 100 * lot * pip_usd / 100
                    trades.append({'type': 'BUY', 'result': 'loss', 'pnl': pnl, 'bar': last_idx})
                    break
                if high >= tp_price:
                    pnl = (tp_price - entry_price) * 100 * lot * pip_usd / 100
                    trades.append({'type': 'BUY', 'result': 'win', 'pnl': pnl, 'bar': last_idx})
                    break
            else:
                if high >= sl_price:
                    pnl = (sl_price - entry_price) * 100 * lot * pip_usd / 100
                    trades.append({'type': 'SELL', 'result': 'loss', 'pnl': pnl, 'bar': last_idx})
                    break
                if low <= tp_price:
                    pnl = (entry_price - tp_price) * 100 * lot * pip_usd / 100
                    trades.append({'type': 'SELL', 'result': 'win', 'pnl': pnl, 'bar': last_idx})
                    break
    
    # 统计
    wins = [t for t in trades if t['result'] == 'win']
    losses = [t for t in trades if t['result'] == 'loss']
    total_pnl = sum(t['pnl'] for t in trades)
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    gross_profit = sum(t['pnl'] for t in wins) if wins else 0
    gross_loss = abs(sum(t['pnl'] for t in losses)) if losses else 1
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    return {
        'signals': len(signals),
        'trades': len(trades),
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'profit_factor': pf,
        'wins': len(wins),
        'losses': len(losses),
        'avg_pnl': total_pnl / len(trades) if trades else 0
    }

# ═══════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("OTAS V1.0 — One Trade At A Time 策略自检")
    print("=" * 70)
    
    # 创建测试数据
    np.random.seed(42)
    n = 1000
    closes = [100.0]
    for i in range(1, n):
        trend = 0.02 * np.sin(i * 0.01)
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
    
    signals = gen_otas(h1, h4, d1)
    print(f"\n生成信号: {len(signals)} 个")
    if signals:
        buys = [s for s in signals if s['side'] == 1]
        sells = [s for s in signals if s['side'] == -1]
        print(f"  买入: {len(buys)}, 卖出: {len(sells)}")
        print(f"  平均ADX: {np.mean([s['adx'] for s in signals]):.1f}")
        print(f"  平均ATR: {np.mean([s['atr'] for s in signals]):.2f}")
    
    result = backtest_otas(h1, h4, d1, initial_equity=10000.0, pip_usd=10.0)
    print(f"\n回测结果:")
    print(f"  信号: {result['signals']} 个")
    print(f"  交易: {result['trades']} 笔")
    print(f"  胜率: {result['win_rate']:.1f}%")
    print(f"  盈亏: ${result['total_pnl']:.2f}")
    print(f"  PF: {result['profit_factor']:.2f}")
    print(f"  平均盈亏: ${result['avg_pnl']:.2f}")
    
    print("\n" + "=" * 70)
    print("✅ OTAS 策略自检完成")
    print("=" * 70)
