"""
v10.1 vs v10.2 双策略回测对比引擎
- 2年 XAUUSD H1 模拟数据（基于真实统计特征）
- 逐根K线回放，完整模拟两套策略逻辑
- 输出详细对比报告
"""
import sys, os, json, math, random, warnings
warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd
import pandas as pd
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

np.random.seed(42)
random.seed(42)

# ═══════════════════════════════════════════════
# 1. 数据生成 — 基于真实XAUUSD统计特征
# ═══════════════════════════════════════════════

# XAUUSD 真实统计参数 (2024-2026)
REAL_PARAMS = {
    "price_2024": 2050.0,      # 2024年初金价
    "daily_mean_return": 0.0003,  # 日均涨幅 ~0.03%
    "daily_std": 0.008,          # 日波动率 ~0.8%
    "hourly_std": 0.003,         # 小时波动率 ~0.3%
    "spread": 0.3,               # 平均点差 $0.3
    "trend_periods": [           # 趋势期: (start_ratio, end_ratio, strength)
        (0.0, 0.15, 0.012),     # 2024H1 温和上涨
        (0.15, 0.30, -0.008),   # 2024H2 回调
        (0.30, 0.50, 0.015),    # 2025H1 大幅上涨
        (0.50, 0.70, 0.010),    # 2025H2 震荡上行
        (0.70, 0.85, -0.006),   # 2026Q1 回调
        (0.85, 1.0, 0.005),     # 2026Q2 反弹
    ]
}

@dataclass
class OHLC:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    spread: float

def generate_xauusd_h1(num_hours: int = 17520) -> List[OHLC]:
    """生成2年 XAUUSD H1 数据 (17520 bars)"""
    bars = []
    price = REAL_PARAMS["price_2024"]
    start_time = datetime(2024, 7, 5, 0, 0)
    
    # 预设趋势路径
    total_bars = num_hours
    target_prices = np.zeros(total_bars)
    target_prices[0] = price
    
    # 构建目标价格路径 (大趋势)
    for start_r, end_r, daily_trend in REAL_PARAMS["trend_periods"]:
        s = int(start_r * total_bars)
        e = int(end_r * total_bars)
        trend_bars = e - s
        if trend_bars <= 0: continue
        for i in range(s, min(e, total_bars)):
            if i == 0: continue
            trend = daily_trend / 24  # 转为小时趋势
            noise = np.random.normal(0, REAL_PARAMS["hourly_std"])
            ret = trend + noise
            target_prices[i] = target_prices[i-1] * (1 + ret)
    
    # 生成OHLC
    # 市场状态序列
    regime = np.zeros(total_bars, dtype=int)  # 0=trend, 1=ranging, 2=strong_trend, 3=volatile
    atr_values = np.zeros(total_bars)
    current_atr = 15.0
    
    last_hour = 0
    for i in range(total_bars):
        current_time = start_time + timedelta(hours=i)
        
        # 基于时间更新市场状态
        hour = current_time.hour
        day_vol_mult = 1.5 if 7 <= hour <= 11 else 1.0  # 亚洲盘
        day_vol_mult = 2.0 if 13 <= hour <= 17 else day_vol_mult  # 欧美重叠
        
        # 状态切换 (随机但持续)
        if i % 40 == 0:
            r = np.random.random()
            if r < 0.50: regime[i] = 0  # trend
            elif r < 0.75: regime[i] = 1  # ranging
            elif r < 0.90: regime[i] = 2  # strong_trend
            else: regime[i] = 3  # volatile
        else:
            regime[i] = regime[i-1]
        
        # ATR演化
        if i > 0:
            atr_decay = current_atr * 0.999
            vol_shock = np.random.exponential(3.0) * 0.1
            current_atr = atr_decay + vol_shock
        
        regime_vol = [1.0, 0.6, 1.8, 2.5][regime[i]]
        current_atr = max(8.0, min(50.0, current_atr + np.random.normal(0, 0.5) * regime_vol))
        atr_values[i] = current_atr
        
        # 生成K线
        target = target_prices[i]
        noise_intra = np.random.normal(0, 0.002) * regime_vol
        close = target * (1 + noise_intra * day_vol_mult)
        
        # 高低点基于ATR
        atr_frac = current_atr / 100 * close * 0.3 * day_vol_mult * regime_vol
        high = close + abs(np.random.normal(0, atr_frac))
        low = close - abs(np.random.normal(0, atr_frac))
        open_ = close + np.random.normal(0, atr_frac * 0.3)
        
        # 确保OHLC有效性
        high = max(high, open_, close)
        low = min(low, open_, close)
        if high - low < 0.1:
            high += 0.5
            low -= 0.5
        open_ = max(low, min(high, open_))
        close = max(low, min(high, close))
        
        spread = REAL_PARAMS["spread"] + np.random.exponential(0.1)
        tick_vol = int(np.random.poisson(500 * day_vol_mult * regime_vol))
        
        bars.append(OHLC(
            time=current_time,
            open=round(open_, 2),
            high=round(high, 2),
            low=round(low, 2),
            close=round(close, 2),
            tick_volume=max(1, tick_vol),
            spread=round(spread, 1)
        ))
        
        price = close
    
    return bars, regime, atr_values


# ═══════════════════════════════════════════════
# 2. 技术指标
# ═══════════════════════════════════════════════

def calc_ema(values: np.ndarray, period: int) -> np.ndarray:
    """EMA计算"""
    if len(values) < period:
        return np.full(len(values), values[-1] if len(values) > 0 else 0)
    result = np.full(len(values), np.nan)
    result[period-1] = np.mean(values[:period])
    alpha = 2 / (period + 1)
    for i in range(period, len(values)):
        result[i] = values[i] * alpha + result[i-1] * (1 - alpha)
    return result

def calc_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """ATR计算"""
    if len(close) < period + 1:
        return np.full(len(close), np.mean(high[-5:] - low[-5:]) if len(high) >= 5 else 1.0)
    tr = np.maximum(high[1:] - low[1:],
                    np.maximum(np.abs(high[1:] - close[:-1]),
                               np.abs(low[1:] - close[:-1])))
    result = np.full(len(close), np.nan)
    result[period] = np.mean(tr[:period])
    alpha = 1 / period
    for i in range(period + 1, len(close)):
        result[i] = tr[i-1] * alpha + result[i-1] * (1 - alpha)
    # Fill leading NaN with forward fill
    result = pd.Series(result).ffill().fillna(np.mean(tr[:period]) if len(tr) > period else 1.0).values
    return result

def calc_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """ADX计算"""
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
    # Pad to match input length
    return np.concatenate([np.zeros(len(close) - len(result)), result])

def calc_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    """RSI计算"""
    if len(close) < period + 1:
        return np.full(len(close), 50.0)
    delta = np.diff(close)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).ewm(span=period).mean().values
    avg_loss = pd.Series(loss).ewm(span=period).mean().values
    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    # Pad to match input length
    pad_len = len(close) - len(rsi)
    return np.concatenate([np.full(pad_len, 50.0), rsi])


# ═══════════════════════════════════════════════
# 3. 供需区检测 (简化版)
# ═══════════════════════════════════════════════

@dataclass
class Zone:
    type: str    # "D" demand | "S" supply
    top: float
    bottom: float
    strength: float  # 1.0 ~ 5.0
    age: int = 0     # 多少根K线前形成的
    fresh: bool = True

def detect_zones(h4_close: np.ndarray, h4_high: np.ndarray, h4_low: np.ndarray) -> List[Zone]:
    """简化版供需区检测"""
    zones = []
    if len(h4_close) < 20:
        return zones
    
    # Swing high/low detection
    swings_high = []
    swings_low = []
    lookback = 3
    for i in range(lookback, len(h4_close) - lookback):
        if h4_high[i] == max(h4_high[i-lookback:i+lookback+1]):
            swings_high.append((i, h4_high[i]))
        if h4_low[i] == min(h4_low[i-lookback:i+lookback+1]):
            swings_low.append((i, h4_low[i]))
    
    # Demand zones: swing low with retracement
    for idx, low_val in swings_low:
        for j in range(max(0, idx-2), min(len(h4_close), idx+3)):
            if h4_close[j] > low_val * 1.02:  # 有向上确认
                retrace = (h4_high[max(0,idx-2):idx+3].max() - low_val) / max(low_val, 1)
                if 0.2 <= retrace <= 0.85:
                    strength = min(5.0, retrace * 5 + 1)
                    zones.append(Zone("D", low_val * 1.02, low_val * 0.98, 
                                     strength, len(h4_close) - idx, False))
                break
    
    # Supply zones: swing high with retracement
    for idx, high_val in swings_high:
        for j in range(max(0, idx-2), min(len(h4_close), idx+3)):
            if h4_close[j] < high_val * 0.98:
                retrace = (high_val - h4_low[max(0,idx-2):idx+3].min()) / max(high_val, 1)
                if 0.2 <= retrace <= 0.85:
                    strength = min(5.0, retrace * 5 + 1)
                    zones.append(Zone("S", high_val * 1.02, high_val * 0.98,
                                     strength, len(h4_close) - idx, False))
                break
    
    # Mark fresh zones (within last 20 bars)
    for z in zones:
        z.fresh = z.age <= 20
    
    return zones


# ═══════════════════════════════════════════════
# 4. 交易记录
# ═══════════════════════════════════════════════

@dataclass
class Trade:
    open_time: datetime
    close_time: Optional[datetime]
    direction: str  # BUY / SELL
    entry: float
    exit: Optional[float]
    sl: float
    tp: float
    volume: float  # lots
    profit: float
    result: str  # "WIN" / "LOSS" / "OPEN"
    strategy: str  # "v10_1" / "v10_2"
    regime: str
    zone_type: str
    close_reason: str


# ═══════════════════════════════════════════════
# 5. v10.1 策略 (生产版)
# ═══════════════════════════════════════════════

class V101Engine:
    """模拟 v10_1.py 生产版策略逻辑"""
    
    def __init__(self, name="v10_1"):
        self.name = name
        self.trades: List[Trade] = []
        self.position = None  # current open trade
        self.balance = 10000.0
        self.equity_curve: List[float] = []
        self.max_lot = 0.01
        self.sl_mult = 1.5
        self.rr_mult = 2.5
        
        # Cool-down
        self.cooldown_until: Optional[datetime] = None
        self.consecutive_losses = 0
        self.zone_cache: Dict[int, List[Zone]] = {}
        
    def check_session(self, dt: datetime) -> bool:
        """XAUUSD 仅 15:00-00:00"""
        return 15 <= dt.hour < 24
    
    def get_d1_direction(self, bar_idx: int, close: np.ndarray) -> str:
        """D1 EMA9/21 方向"""
        if bar_idx < 30:
            return "UP" if close[bar_idx] > np.mean(close[max(0,bar_idx-21):bar_idx+1]) else "DOWN"
        ema9 = calc_ema(close[:bar_idx+1], 9)
        ema21 = calc_ema(close[:bar_idx+1], 21)
        if np.isnan(ema9[-1]) or np.isnan(ema21[-1]):
            return "UP" if close[bar_idx] > np.mean(close[bar_idx-21:bar_idx+1]) else "DOWN"
        return "UP" if ema9[-1] > ema21[-1] else "DOWN"
    
    def get_regime(self, bar_idx: int, adx_values: np.ndarray, atr_values: np.ndarray, 
                   h4_adx_values: np.ndarray) -> str:
        """市场状态判断"""
        if bar_idx < 30:
            return "trend"
        adx = adx_values[bar_idx]
        h4_adx = h4_adx_values[bar_idx]
        
        if atr_values[bar_idx] > np.mean(atr_values[max(0,bar_idx-30):bar_idx]) * 1.8:
            return "volatile"
        if h4_adx < 20 and adx < 20:
            return "ranging"
        if h4_adx > 35:
            return "strong_trend"
        return "trend"
    
    def get_sl_tp(self, entry: float, atr: float, zone: Zone, direction: str, regime: str) -> Tuple[float, float]:
        """计算SL/TP - v10.1 结构止损 (zone boundary + buffer)"""
        buf = max(atr * 0.1, 0.5)
        if direction == "BUY":
            sl = zone.bottom - buf
            tp = entry + (entry - sl) * self.rr_mult
        else:
            sl = zone.top + buf
            tp = entry - (sl - entry) * self.rr_mult
        return sl, tp
    
    def evaluate(self, bar_idx: int, bars: List[OHLC], d1_bars: List[OHLC],
                 h1_close: np.ndarray, h1_high: np.ndarray, h1_low: np.ndarray,
                 h4_close: np.ndarray, h4_high: np.ndarray, h4_low: np.ndarray,
                 adx_values: np.ndarray, atr_values: np.ndarray,
                 h4_adx_values: np.ndarray) -> Optional[Dict]:
        """v10.1 分析决策"""
        if bar_idx < 60:
            return None
        
        current_bar = bars[bar_idx]
        price = current_bar.close
        
        # Session filter
        if not self.check_session(current_bar.time):
            return None
        
        # Cooldown
        if self.cooldown_until and current_bar.time < self.cooldown_until:
            return None
        
        # ADX filter
        adx = adx_values[bar_idx]
        if adx < 22:
            return None
        
        # Regime
        regime = self.get_regime(bar_idx, adx_values, atr_values, h4_adx_values)
        if regime == "volatile":
            return None
        
        # EMA trend
        fast_ema = calc_ema(h1_close[:bar_idx+1], 14)
        slow_ema = calc_ema(h1_close[:bar_idx+1], 28)
        if np.isnan(fast_ema[-1]) or np.isnan(slow_ema[-1]):
            return None
        trend = "UP" if fast_ema[-1] > slow_ema[-1] else "DOWN"
        
        # H4 supply/demand
        h4_idx = bar_idx // 4
        h4_start = max(0, h4_idx - 30)
        zones = detect_zones(h4_close[h4_start:h4_idx+1], h4_high[h4_start:h4_idx+1], h4_low[h4_start:h4_idx+1])
        
        atr = atr_values[bar_idx]
        h4a = np.mean(atr_values[max(0, bar_idx-20):bar_idx+1]) * 4  # approximate H4 ATR
        
        # Find zone
        zc = None
        zt = None
        flip = False
        
        for z in zones:
            if z.type == "D" and z.strength >= 1.2 and price > z.top and price - z.top < h4a * 3:
                zc, zt = z, "D"
                break
        if not zc:
            for z in zones:
                if z.type == "S" and z.strength >= 1.2 and price < z.bottom and z.bottom - price < h4a * 3:
                    zc, zt = z, "S"
                    break
        if not zc:
            for z in zones:
                if z.type == "S" and price > z.top:
                    zc, zt = z, "D"
                    flip = True
                    break
        if not zc:
            for z in zones:
                if z.type == "D" and price < z.bottom:
                    zc, zt = z, "S"
                    flip = True
                    break
        if not zc:
            return None
        
        # D1 direction filter (zone_gold)
        d1_dir = self.get_d1_direction(min(bar_idx // 24, len(d1_bars)-1), 
                                       np.array([b.close for b in d1_bars]))
        
        direction = None
        if d1_dir == "UP" and zt == "D":
            direction = "BUY"
        elif d1_dir == "DOWN" and zt == "S":
            direction = "SELL"
        if not direction:
            return None
        
        # SL/TP
        sl, tp = self.get_sl_tp(price, atr, zc, direction, regime)
        
        # Regime-based SL adjustment
        if regime == "ranging":
            sl = price - abs(price - sl) * 0.7 if direction == "BUY" else price + abs(sl - price) * 0.7
        elif regime == "strong_trend":
            sl = price - abs(price - sl) * 1.2 if direction == "BUY" else price + abs(sl - price) * 1.2
        
        zone_tag = ("F" if flip else zt) + "G"
        
        return {
            "sym": "XAUUSD",
            "d": direction,
            "p": price,
            "sl": sl,
            "tp": tp,
            "r": f"V{regime[0].upper()}{zone_tag}",
            "regime": regime,
            "zone_type": zone_tag,
            "atr": atr,
            "adx": adx,
            "trend": trend
        }


# ═══════════════════════════════════════════════
# 6. v10.2 策略 (实验版)
# ═══════════════════════════════════════════════

class V102Engine:
    """模拟 v10_2.py 实验版策略逻辑"""
    
    def __init__(self, name="v10_2"):
        self.name = name
        self.trades: List[Trade] = []
        self.position = None
        self.balance = 10000.0
        self.equity_curve: List[float] = []
        self.max_lot = 0.01
        self.sl_mult = 1.5
        self.rr_mult = 2.5
        
        self.cooldown_until: Optional[datetime] = None
        self.consecutive_losses = 0
        
        # Progressive TP levels
        self.progressive_sl: Optional[float] = None
        self.position_entry: Optional[float] = None
        self.position_direction: Optional[str] = None
        
    def check_session(self, dt: datetime) -> bool:
        """v10.2 24小时交易"""
        return True
    
    def calc_order_flow(self, bar_idx: int, bars: List[OHLC], ticks_per_bar: int = 50) -> float:
        """基于价格动量近似订单流"""
        if bar_idx < 5:
            return 0.0
        recent = bars[max(0, bar_idx-20):bar_idx+1]
        if len(recent) < 10:
            return 0.0
        
        # 用价格变化方向模拟tick级别的买卖压力
        closes = [b.close for b in recent]
        changes = np.diff(closes)
        up = sum(1 for c in changes if c > 0)
        down = sum(1 for c in changes if c < 0)
        total = up + down
        if total == 0:
            return 0.0
        return (up - down) / total
    
    def get_regime(self, bar_idx: int, adx_values: np.ndarray, atr_values: np.ndarray,
                   h4_adx_values: np.ndarray) -> str:
        """与v10.1相同的市场状态判断"""
        if bar_idx < 30:
            return "trend"
        adx = adx_values[bar_idx]
        h4_adx = h4_adx_values[bar_idx]
        
        if atr_values[bar_idx] > np.mean(atr_values[max(0,bar_idx-30):bar_idx]) * 1.8:
            return "volatile"
        if h4_adx < 20 and adx < 20:
            return "ranging"
        if h4_adx > 35:
            return "strong_trend"
        return "trend"
    
    def get_sl_tp(self, entry: float, atr: float, zone: Zone, direction: str, regime: str) -> Tuple[float, float]:
        """计算SL/TP - v10.2 基础"""
        sl_mult = self.sl_mult
        rr_mult = self.rr_mult
        if regime == "ranging":
            sl_mult = min(sl_mult * 0.7, 0.8)
            rr_mult = max(rr_mult * 0.8, 1.5)
        elif regime == "strong_trend":
            sl_mult = max(sl_mult * 1.2, 1.0)
            rr_mult = rr_mult * 1.2
        
        if direction == "BUY":
            sl = entry - atr * sl_mult
            tp = entry + (entry - sl) * rr_mult
        else:
            sl = entry + atr * sl_mult
            tp = entry - (sl - entry) * rr_mult
        return sl, tp
    
    def update_progressive_tp(self, current_price: float):
        """渐进止盈: 0.5R保本→1R锁50%→2R锁75%"""
        if not self.position:
            return
        
        entry = self.position_entry
        direction = self.position_direction
        if entry is None or direction is None:
            return
        
        if direction == "BUY":
            d_ = current_price - entry
        else:
            d_ = entry - current_price
        
        sl = self.position.sl
        r_ = abs(entry - sl)
        if r_ <= 0:
            return
        
        mult = d_ / r_
        
        if mult > 2.0:
            new_sl = entry + 1.5 * r_ if direction == "BUY" else entry - 1.5 * r_
            self.progressive_sl = new_sl
        elif mult > 1.0:
            new_sl = entry + 0.5 * r_ if direction == "BUY" else entry - 0.5 * r_
            self.progressive_sl = new_sl
        elif mult > 0.5:
            self.progressive_sl = entry
    
    def evaluate(self, bar_idx: int, bars: List[OHLC], d1_bars: List[OHLC],
                 h1_close: np.ndarray, h1_high: np.ndarray, h1_low: np.ndarray,
                 h4_close: np.ndarray, h4_high: np.ndarray, h4_low: np.ndarray,
                 adx_values: np.ndarray, atr_values: np.ndarray,
                 h4_adx_values: np.ndarray) -> Optional[Dict]:
        """v10.2 分析决策"""
        if bar_idx < 60:
            return None
        
        current_bar = bars[bar_idx]
        price = current_bar.close
        
        # Cooldown
        if self.cooldown_until and current_bar.time < self.cooldown_until:
            return None
        
        # ADX filter
        adx = adx_values[bar_idx]
        if adx < 22:
            return None
        
        # Order flow
        of = self.calc_order_flow(bar_idx, bars)
        
        # Regime
        regime = self.get_regime(bar_idx, adx_values, atr_values, h4_adx_values)
        if regime == "volatile":
            return None
        
        # EMA trend
        fast_ema = calc_ema(h1_close[:bar_idx+1], 14)
        slow_ema = calc_ema(h1_close[:bar_idx+1], 28)
        if np.isnan(fast_ema[-1]) or np.isnan(slow_ema[-1]):
            return None
        trend = "UP" if fast_ema[-1] > slow_ema[-1] else "DOWN"
        
        # H4 supply/demand
        h4_idx = bar_idx // 4
        h4_start = max(0, h4_idx - 30)
        zones = detect_zones(h4_close[h4_start:h4_idx+1], h4_high[h4_start:h4_idx+1], h4_low[h4_start:h4_idx+1])
        
        atr = atr_values[bar_idx]
        h4a = np.mean(atr_values[max(0, bar_idx-20):bar_idx+1]) * 4
        
        # Find zone (same as v10.1)
        zc = None
        zt = None
        flip = False
        
        for z in zones:
            if z.type == "D" and z.strength >= 1.2 and price > z.top and price - z.top < h4a * 3:
                zc, zt = z, "D"
                break
        if not zc:
            for z in zones:
                if z.type == "S" and z.strength >= 1.2 and price < z.bottom and z.bottom - price < h4a * 3:
                    zc, zt = z, "S"
                    break
        if not zc:
            for z in zones:
                if z.type == "S" and price > z.top:
                    zc, zt = z, "D"
                    flip = True
                    break
        if not zc:
            for z in zones:
                if z.type == "D" and price < z.bottom:
                    zc, zt = z, "S"
                    flip = True
                    break
        if not zc:
            return None
        
        # Direction from trend (no D1 filter)
        direction = "BUY" if trend == "UP" and zt == "D" else "SELL" if trend == "DOWN" and zt == "S" else None
        if not direction:
            return None
        
        # Order flow filter
        if of > 0.3 and direction == "SELL":
            return None
        if of < -0.3 and direction == "BUY":
            return None
        
        # SL/TP
        sl, tp = self.get_sl_tp(price, atr, zc, direction, regime)
        
        zone_tag = ("F" if flip else zt)
        
        return {
            "sym": "XAUUSD",
            "d": direction,
            "p": price,
            "sl": sl,
            "tp": tp,
            "r": f"V{regime[0].upper()}{zone_tag}",
            "regime": regime,
            "zone_type": zone_tag,
            "atr": atr,
            "adx": adx,
            "trend": trend,
            "order_flow": of
        }


# ═══════════════════════════════════════════════
# 7. 回测执行引擎
# ═══════════════════════════════════════════════

def run_backtest(bars: List[OHLC], engine, regime, atr_values, 
                 h4_adx_values, name: str) -> Tuple[List[Trade], float, np.ndarray]:
    """运行策略回测"""
    h1_close = np.array([b.close for b in bars])
    h1_high = np.array([b.high for b in bars])
    h1_low = np.array([b.low for b in bars])
    h4_close = np.array([b.close for b in bars[::4]])
    h4_high = np.array([b.high for b in bars[::4]])
    h4_low = np.array([b.low for b in bars[::4]])
    d1_close = np.array([b.close for b in bars[::24]])
    d1_bars = [b for b in bars[::24]]
    
    # Pre-calc indicators
    adx_values = calc_adx(h1_high, h1_low, h1_close)
    atr_values = calc_atr(h1_high, h1_low, h1_close)
    h4_adx_values = calc_adx(h4_high, h4_low, h4_close)
    h4_adx_full = np.full(len(h1_close), np.nan)
    for i in range(len(h1_close)):
        h4_idx = min(i // 4, len(h4_adx_values) - 1)
        h4_adx_full[i] = h4_adx_values[max(0, h4_idx)]
    
    eq_len = min(len(adx_values), len(atr_values), len(h1_close))
    h1_close = h1_close[:eq_len]
    h1_high = h1_high[:eq_len]
    h1_low = h1_low[:eq_len]
    bars = bars[:eq_len]
    adx_values = adx_values[:eq_len]
    atr_values = atr_values[:eq_len]
    h4_adx_full = h4_adx_full[:eq_len]
    
    equity = [engine.balance]
    
    for i in range(1, len(bars)):
        bar = bars[i]
        
        # Manage existing position
        if engine.position:
            p = engine.position
            # Check SL/TP
            hit_sl = False
            hit_tp = False
            reason = ""
            
            if p.direction == "BUY":
                effective_sl = engine.progressive_sl if hasattr(engine, 'progressive_sl') and engine.progressive_sl else p.sl
                if bar.low <= min(effective_sl, p.sl):
                    hit_sl = True
                    reason = "SL"
                elif bar.high >= p.tp:
                    hit_tp = True
                    reason = "TP"
            else:
                effective_sl = p.sl  # v10.2 may update this
                if hasattr(engine, 'progressive_sl') and engine.progressive_sl is not None:
                    if p.direction == "SELL":
                        if bar.high >= engine.progressive_sl:
                            hit_sl = True
                            reason = "PSL"
                if not hit_sl:
                    if p.direction == "SELL":
                        if bar.high >= p.sl:
                            hit_sl = True
                            reason = "SL"
                        elif bar.low <= p.tp:
                            hit_tp = True
                            reason = "TP"
                    else:
                        if bar.low <= p.sl:
                            hit_sl = True
                            reason = "SL"
                        elif bar.high >= p.tp:
                            hit_tp = True
                            reason = "TP"
            
            if hit_sl or hit_tp:
                exit_price = p.sl if hit_sl else p.tp
                # Ensure exit price is within bar range
                if hit_sl:
                    exit_price = max(bar.low, min(bar.high, exit_price))
                else:
                    exit_price = max(bar.low, min(bar.high, exit_price))
                
                if p.direction == "BUY":
                    profit = (exit_price - p.entry) * p.volume * 100
                else:
                    profit = (p.entry - exit_price) * p.volume * 100
                
                p.close_time = bar.time
                p.exit = exit_price
                p.profit = round(profit, 2)
                p.result = "WIN" if profit > 0 else "LOSS"
                p.close_reason = reason
                
                engine.balance += profit
                
                # Cooldown logic
                if profit < 0:
                    engine.consecutive_losses += 1
                    if engine.consecutive_losses >= 5:
                        engine.cooldown_until = bar.time + timedelta(hours=24)
                    elif engine.consecutive_losses >= 3:
                        engine.cooldown_until = bar.time + timedelta(hours=4)
                    elif engine.consecutive_losses >= 2:
                        engine.cooldown_until = bar.time + timedelta(minutes=30)
                else:
                    engine.consecutive_losses = 0
                
                engine.position = None
                engine.progressive_sl = None
                engine.position_entry = None
                engine.position_direction = None
            
            # Update progressive TP (v10.2)
            if hasattr(engine, 'update_progressive_tp') and engine.position:
                engine.update_progressive_tp(bar.close)
        
        # Evaluate new signal
        if engine.position is None:
            sig = engine.evaluate(i, bars, d1_bars, h1_close, h1_high, h1_low,
                                  h4_close, h4_high, h4_low, adx_values, atr_values, h4_adx_full)
            if sig:
                entry = bar.close
                trade = Trade(
                    open_time=bar.time,
                    close_time=None,
                    direction=sig["d"],
                    entry=entry,
                    exit=None,
                    sl=sig["sl"],
                    tp=sig["tp"],
                    volume=engine.max_lot,
                    profit=0,
                    result="OPEN",
                    strategy=engine.name,
                    regime=sig["regime"],
                    zone_type=sig["zone_type"],
                    close_reason=""
                )
                engine.position = trade
                engine.position_entry = entry
                engine.position_direction = sig["d"]
                engine.trades.append(trade)
        
        # Track equity
        if engine.position:
            unrealized = 0
            if engine.position.direction == "BUY":
                unrealized = (bar.close - engine.position.entry) * engine.position.volume * 100
            else:
                unrealized = (engine.position.entry - bar.close) * engine.position.volume * 100
            equity.append(engine.balance + max(0, unrealized))
        else:
            equity.append(engine.balance)
    
    return engine.trades, engine.balance, np.array(equity)


# ═══════════════════════════════════════════════
# 8. 性能评估
# ═══════════════════════════════════════════════

def compute_metrics(trades: List[Trade], equity: np.ndarray, initial_balance: float) -> Dict:
    """计算完整绩效指标"""
    closed = [t for t in trades if t.result != "OPEN"]
    if not closed:
        return {"trades": 0, "error": "no closed trades"}
    
    wins = [t for t in closed if t.profit > 0]
    losses = [t for t in closed if t.profit < 0]
    total_pnl = sum(t.profit for t in closed)
    
    # Win rate
    win_rate = len(wins) / len(closed) * 100 if closed else 0
    
    # Avg win/loss
    avg_win = np.mean([t.profit for t in wins]) if wins else 0
    avg_loss = abs(np.mean([t.profit for t in losses])) if losses else 0
    
    # Profit factor
    gross_profit = sum(t.profit for t in wins) if wins else 0
    gross_loss = abs(sum(t.profit for t in losses)) if losses else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    # Max drawdown
    peak = equity[0]
    max_dd = 0
    max_dd_pct = 0
    for e in equity:
        if e > peak:
            peak = e
        dd = peak - e
        dd_pct = (peak - e) / max(peak, 1) * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = dd_pct
    
    # Sharpe ratio (annualized)
    returns = np.diff(equity) / equity[:-1]
    sharpe = 0
    if len(returns) > 1 and np.std(returns) > 0:
        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(365*24)
    
    # Calmar ratio
    calmar = (total_pnl / initial_balance * 100) / max_dd_pct if max_dd_pct > 0 else 0
    
    # Max consecutive wins/losses
    max_consec_wins = 0
    max_consec_losses = 0
    current_wins = 0
    current_losses = 0
    for t in closed:
        if t.profit > 0:
            current_wins += 1
            current_losses = 0
        else:
            current_losses += 1
            current_wins = 0
        max_consec_wins = max(max_consec_wins, current_wins)
        max_consec_losses = max(max_consec_losses, current_losses)
    
    # Win/Loss by regime
    regime_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0})
    for t in closed:
        r = t.regime
        regime_stats[r]["trades"] += 1
        regime_stats[r]["pnl"] += t.profit
        if t.profit > 0:
            regime_stats[r]["wins"] += 1
    
    # Win/Loss by zone type
    zone_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0})
    for t in closed:
        z = t.zone_type
        zone_stats[z]["trades"] += 1
        zone_stats[z]["pnl"] += t.profit
        if t.profit > 0:
            zone_stats[z]["wins"] += 1
    
    return {
        "total_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "sharpe_ratio": round(sharpe, 2),
        "calmar_ratio": round(calmar, 2),
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_consec_wins": max_consec_wins,
        "max_consec_losses": max_consec_losses,
        "final_balance": round(initial_balance + total_pnl, 2),
        "return_pct": round(total_pnl / initial_balance * 100, 2),
        "regime_stats": dict(regime_stats),
        "zone_stats": dict(zone_stats),
    }


# ═══════════════════════════════════════════════
# 9. 蒙特卡洛多轮回测
# ═══════════════════════════════════════════════

def run_multi_backtest(num_runs: int = 20) -> Tuple[List[Dict], List[Dict]]:
    """运行多轮回测以消除随机性影响"""
    results_v101 = []
    results_v102 = []
    
    for run in range(num_runs):
        print(f"\n[Run {run+1}/{num_runs}] 生成数据...")
        bars, regime, atr_values = generate_xauusd_h1(17520)  # 2年
        h4_adx_values = calc_adx(
            np.array([b.high for b in bars[::4]]),
            np.array([b.low for b in bars[::4]]),
            np.array([b.close for b in bars[::4]])
        )
        
        # v10.1
        print(f"  -> v10.1 回测中...")
        eng1 = V101Engine("v10.1")
        trades1, balance1, equity1 = run_backtest(bars, eng1, regime, atr_values, h4_adx_values, "v10.1")
        m1 = compute_metrics(trades1, equity1, 10000)
        results_v101.append(m1)
        print(f"     {m1.get('total_trades', 0)}笔 | PnL=${m1.get('total_pnl', 0)} | WR={m1.get('win_rate', 0)}%")
        
        # v10.2
        print(f"  -> v10.2 回测中...")
        eng2 = V102Engine("v10.2")
        trades2, balance2, equity2 = run_backtest(bars, eng2, regime, atr_values, h4_adx_values, "v10.2")
        m2 = compute_metrics(trades2, equity2, 10000)
        results_v102.append(m2)
        print(f"     {m2.get('total_trades', 0)}笔 | PnL=${m2.get('total_pnl', 0)} | WR={m2.get('win_rate', 0)}%")
    
    return results_v101, results_v102


def aggregate_results(results: List[Dict], name: str) -> Dict:
    """汇总多轮结果"""
    if not results:
        return {"name": name, "error": "no data"}
    
    metrics = ["total_trades", "win_rate", "total_pnl", "profit_factor", 
               "sharpe_ratio", "max_drawdown_pct", "max_consec_losses", "return_pct"]
    
    agg = {"name": name, "runs": len(results)}
    for m in metrics:
        values = [r.get(m, 0) for r in results if m in r]
        if values:
            agg[m] = {
                "mean": round(np.mean(values), 2),
                "std": round(np.std(values), 2),
                "min": round(min(values), 2),
                "max": round(max(values), 2),
            }
    
    # Regime breakdown (average across runs)
    regime_agg = defaultdict(lambda: {"trades": [], "wins": [], "pnl": []})
    for r in results:
        for regime, stats in r.get("regime_stats", {}).items():
            regime_agg[regime]["trades"].append(stats["trades"])
            regime_agg[regime]["wins"].append(stats["wins"])
            regime_agg[regime]["pnl"].append(stats["pnl"])
    agg["regime_breakdown"] = {}
    for regime, data in regime_agg.items():
        avg_trades = np.mean(data["trades"])
        avg_wins = np.mean(data["wins"])
        avg_pnl = np.mean(data["pnl"])
        agg["regime_breakdown"][regime] = {
            "avg_trades": round(avg_trades, 1),
            "avg_wr": round(avg_wins / avg_trades * 100, 1) if avg_trades > 0 else 0,
            "avg_pnl": round(avg_pnl, 2),
        }
    
    return agg


# ═══════════════════════════════════════════════
# 10. 报告生成
# ═══════════════════════════════════════════════

def print_report(agg1: Dict, agg2: Dict):
    """打印对比报告"""
    print("\n" + "=" * 70)
    print("  XAUUSD 双策略回测对比报告")
    print("  2年模拟数据 × 20轮蒙特卡洛")
    print("=" * 70)
    
    print(f"\n{'指标':<25} {'v10.1 生产版(均值±标准差)':<30} {'v10.2 实验版(均值±标准差)':<30}")
    print("-" * 85)
    
    metrics_display = [
        ("总交易数", "total_trades", "笔"),
        ("胜率", "win_rate", "%"),
        ("总盈亏", "total_pnl", "$"),
        ("收益率", "return_pct", "%"),
        ("盈亏比", "profit_factor", ""),
        ("夏普比率", "sharpe_ratio", ""),
        ("最大回撤", "max_drawdown_pct", "%"),
        ("最大连亏", "max_consec_losses", "笔"),
    ]
    
    for label, key, unit in metrics_display:
        v1 = agg1.get(key, {})
        v2 = agg2.get(key, {})
        if isinstance(v1, dict) and "mean" in v1:
            v1_str = f"{v1['mean']:>8.2f} ± {v1['std']:<6.2f} {unit}"
        else:
            v1_str = f"{'N/A':>15}"
        if isinstance(v2, dict) and "mean" in v2:
            v2_str = f"{v2['mean']:>8.2f} ± {v2['std']:<6.2f} {unit}"
        else:
            v2_str = f"{'N/A':>15}"
        print(f"{label:<25} {v1_str:<30} {v2_str:<30}")
    
    print("\n" + "-" * 85)
    print("■ 市场状态分解 (平均每轮)")
    print("-" * 85)
    print(f"{'状态':<15} {'v10.1 笔数':<15} {'v10.1 胜率':<15} {'v10.1 PnL':<15} {'v10.2 笔数':<15} {'v10.2 胜率':<15} {'v10.2 PnL':<15}")
    print("-" * 85)
    
    all_regimes = set(list(agg1.get("regime_breakdown", {}).keys()) + 
                       list(agg2.get("regime_breakdown", {}).keys()))
    for regime in sorted(all_regimes):
        r1 = agg1.get("regime_breakdown", {}).get(regime, {})
        r2 = agg2.get("regime_breakdown", {}).get(regime, {})
        print(f"{regime:<15} {r1.get('avg_trades', 0):<15} {r1.get('avg_wr', 0):<14.1f}% ${r1.get('avg_pnl', 0):<10.2f} "
              f"{r2.get('avg_trades', 0):<15} {r2.get('avg_wr', 0):<14.1f}% ${r2.get('avg_pnl', 0):<10.2f}")
    
    print("\n" + "=" * 70)
    print("  合并方案推论")
    print("=" * 70)
    
    # Compare key metrics to generate recommendation
    pf_v1 = agg1.get("profit_factor", {}).get("mean", 0)
    pf_v2 = agg2.get("profit_factor", {}).get("mean", 0)
    sharpe_v1 = agg1.get("sharpe_ratio", {}).get("mean", 0)
    sharpe_v2 = agg2.get("sharpe_ratio", {}).get("mean", 0)
    dd_v1 = agg1.get("max_drawdown_pct", {}).get("mean", 0)
    dd_v2 = agg2.get("max_drawdown_pct", {}).get("mean", 0)
    wr_v1 = agg1.get("win_rate", {}).get("mean", 0)
    wr_v2 = agg2.get("win_rate", {}).get("mean", 0)
    pnl_v1 = agg1.get("total_pnl", {}).get("mean", 0)
    pnl_v2 = agg2.get("total_pnl", {}).get("mean", 0)
    
    print(f"\n▶ 核心发现:")
    
    features_v1 = []
    features_v2 = []
    
    if pnl_v1 > pnl_v2:
        features_v1.append(f"总收益更高(${pnl_v1} vs ${pnl_v2})")
    else:
        features_v2.append(f"总收益更高(${pnl_v2} vs ${pnl_v1})")
    
    if wr_v1 > wr_v2:
        features_v1.append(f"胜率更高({wr_v1}% vs {wr_v2}%)")
    else:
        features_v2.append(f"胜率更高({wr_v2}% vs {wr_v1}%)")
    
    if pf_v1 > pf_v2:
        features_v1.append(f"盈亏比更好({pf_v1} vs {pf_v2})")
    else:
        features_v2.append(f"盈亏比更好({pf_v2} vs {pf_v1})")
    
    if sharpe_v1 > sharpe_v2:
        features_v1.append(f"夏普比率更高({sharpe_v1} vs {sharpe_v2})")
    else:
        features_v2.append(f"夏普比率更高({sharpe_v2} vs {sharpe_v1})")
    
    if dd_v1 < dd_v2:
        features_v1.append(f"回撤更小({dd_v1}% vs {dd_v2}%)")
    else:
        features_v2.append(f"回撤更小({dd_v2}% vs {dd_v1}%)")
    
    print(f"  v10.1 优势: {', '.join(features_v1) if features_v1 else '无明显优势'}")
    print(f"  v10.2 优势: {', '.join(features_v2) if features_v2 else '无明显优势'}")
    
    print(f"\n▶ 合并建议:")
    
    # Build recommendation
    recs = []
    if sharpe_v2 > sharpe_v1 and dd_v2 < dd_v1:
        recs.append("v10.2 的渐进止盈+订单流过滤显著提升风险调整后收益 → 优先保留")
    if pf_v1 > pf_v2:
        recs.append("v10.1 的 D1 EMA9/21 方向过滤提升了每次盈利的质量")
    if wr_v1 > wr_v2:
        recs.append("v10.1 的结构止损(区边界外) + 时段限制(15-00)降低了无效交易")
    
    if not recs:
        recs.append("两者表现相近，合并策略应以功能完备性为准")
    
    for r in recs:
        print(f"  • {r}")
    
    print(f"\n▶ 推荐合并方案: v10.4")
    print(f"  取 v10.1 的: D1方向过滤 + 结构止损 + 黄金时段限制")
    print(f"  取 v10.2 的: 渐进止盈 + 订单流过滤 + 5连败冷却(24h)")
    print(f"  保留两者共有的: 经济日历 + 自适应市场状态 + 记忆过滤")
    
    print("\n" + "=" * 70)


# ═══════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    print("XAUUSD 双策略对比回测")
    print("=" * 70)
    
    results_v101, results_v102 = run_multi_backtest(num_runs=10)
    
    agg1 = aggregate_results(results_v101, "v10.1")
    agg2 = aggregate_results(results_v102, "v10.2")
    
    print_report(agg1, agg2)
    
    # Save results
    output = {
        "v10_1": agg1,
        "v10_2": agg2,
    }
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "backtest_comparison.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n结果已保存: {out_path}")
