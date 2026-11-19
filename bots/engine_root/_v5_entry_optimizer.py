"""
V5 进场点优化器 - 基于K线形态+动能判断
"""
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from datetime import datetime

class EntryOptimizerV5:
    """V5 进场点优化器"""
    
    def __init__(self):
        self.patterns = {
            'bullish_engulfing': self._is_bullish_engulfing,
            'bearish_engulfing': self._is_bearish_engulfing,
            'hammer': self._is_hammer,
            'shooting_star': self._is_shooting_star,
        }
    
    def analyze(self, symbol, timeframe=mt5.TIMEFRAME_H1):
        """综合分析 (自行拉MT5数据)"""
        candles = mt5.copy_rates_from_pos(symbol, timeframe, 0, 50)
        if candles is None or len(candles) < 20:
            return None
        return self.analyze_df(candles)

    def analyze_df(self, df):
        """综合分析 — 直接吃 pandas/numpy 结构 (open/high/low/close/tick_volume),
        避免 live_bridge 内重复拉取 MT5 (每品种省一次 IPC)。"""
        if df is None or len(df) < 20:
            return None
        # 兼容 pandas DataFrame 与 numpy recarray
        try:
            opens = df['open'].values if hasattr(df['open'], 'values') else df['open']
        except Exception:
            opens = df['open']
        try:
            highs = df['high'].values if hasattr(df['high'], 'values') else df['high']
        except Exception:
            highs = df['high']
        try:
            lows = df['low'].values if hasattr(df['low'], 'values') else df['low']
        except Exception:
            lows = df['low']
        try:
            closes = df['close'].values if hasattr(df['close'], 'values') else df['close']
        except Exception:
            closes = df['close']
        try:
            if 'tick_volume' in df.dtypes if hasattr(df, 'dtypes') else True:
                volumes = df['tick_volume'].values if hasattr(df['tick_volume'], 'values') else df['tick_volume']
        except Exception:
            volumes = df['tick_volume']
        closes = np.asarray(closes, dtype=float)
        opens = np.asarray(opens, dtype=float)
        highs = np.asarray(highs, dtype=float)
        lows = np.asarray(lows, dtype=float)
        volumes = np.asarray(volumes, dtype=float)

        # 1. 趋势判断
        trend = self._detect_trend(closes)
        
        # 2. 动能判断
        momentum = self._analyze_momentum(closes, volumes)
        
        # 3. 形态识别
        patterns = self._detect_patterns(opens, highs, lows, closes)
        
        # 4. 支撑阻力
        sr = self._find_support_resistance(highs, lows, closes)
        
        # 5. 综合评分
        score = self._calc_score(trend, momentum, patterns, sr)
        
        return {
            'symbol': '',
            'trend': trend,
            'momentum': momentum,
            'patterns': patterns,
            'support': sr.get('support', 0),
            'resistance': sr.get('resistance', 0),
            'score': score,
            'recommendation': self._get_recommendation(score, trend, momentum, patterns)
        }

    @staticmethod
    def direction_veto(analysis, direction):
        """V5 方向硬闸: 返回 (allow: bool, scale: float, reason: str)
        - 信号方向与 V5 趋势/形态冲突 → 拒单 (防逆势进场)
        - 同向且有形态确认 → 放行 + 小幅加分
        - V5 无结论 (NEUTRAL) → 放行不干预 (fail-open)
        [2026-09-04 修复] 新增趋势内反转形态拦截:
          BULLISH 趋势 + 看跌吞没/流星(高位反转) → 拒 BUY 防追高
          BEARISH 趋势 + 看涨吞没/锤子(低位反转) → 拒 SELL 防杀跌
        """
        if not analysis:
            return True, 1.0, "V5无数据(fail-open)"
        trend = analysis.get('trend', 'NEUTRAL')
        score = analysis.get('score', 0.0)
        patterns = analysis.get('patterns', [])
        rec = analysis.get('recommendation', 'NEUTRAL')

        if direction == 'BUY':
            # A. 强逆势 → 拒单
            if trend == 'BEARISH' and score <= -2:
                return False, 0.0, f"V5逆势(BEARISH score={score:.1f})"
            if trend == 'BEARISH' and 'bearish_engulfing' in patterns:
                return False, 0.0, "V5看跌吞没+下跌趋势"
            if trend == 'BEARISH' and 'shooting_star' in patterns:
                return False, 0.0, "V5流星线+下跌趋势(顺势看跌)"
            # B. [新增] 上涨趋势中出现高位反转形态 → 拒单防追高
            if trend == 'BULLISH':
                if 'bearish_engulfing' in patterns:
                    return False, 0.0, f"V5高位看跌吞没(上涨末端, score={score:.1f})"
                if 'shooting_star' in patterns and score <= 3:
                    return False, 0.0, f"V5流星线(上涨末端, score={score:.1f})"
            # C. 同向形态确认 → 加分
            if trend == 'BULLISH':
                if 'bullish_engulfing' in patterns or 'hammer' in patterns:
                    return True, 1.15, f"V5看涨形态确认({patterns})"
                return True, 1.05, f"V5上涨趋势 score={score:.1f}"
            return True, 1.0, f"V5中性(不干预) score={score:.1f}"
        else:  # SELL
            # A. 强逆势 → 拒单
            if trend == 'BULLISH' and score >= 2:
                return False, 0.0, f"V5逆势(BULLISH score={score:.1f})"
            if trend == 'BULLISH' and 'bullish_engulfing' in patterns:
                return False, 0.0, "V5看涨吞没+上涨趋势"
            if trend == 'BULLISH' and 'hammer' in patterns:
                return False, 0.0, "V5锤子线+上涨趋势(顺势看涨)"
            # B. [新增] 下跌趋势中出现低位反转形态 → 拒单防杀跌
            if trend == 'BEARISH':
                if 'bullish_engulfing' in patterns:
                    return False, 0.0, f"V5低位看涨吞没(下跌末端, score={score:.1f})"
                if 'hammer' in patterns and score >= -3:
                    return False, 0.0, f"V5锤子线(下跌末端, score={score:.1f})"
            # C. 同向形态确认 → 加分
            if trend == 'BEARISH':
                if 'bearish_engulfing' in patterns or 'shooting_star' in patterns:
                    return True, 1.15, f"V5看跌形态确认({patterns})"
                return True, 1.05, f"V5下跌趋势 score={score:.1f}"
            return True, 1.0, f"V5中性(不干预) score={score:.1f}"
        
        # 1. 趋势判断
        trend = self._detect_trend(closes)
        
        # 2. 动能判断
        momentum = self._analyze_momentum(closes, volumes)
        
        # 3. 形态识别
        patterns = self._detect_patterns(opens, highs, lows, closes)
        
        # 4. 支撑阻力
        sr = self._find_support_resistance(highs, lows, closes)
        
        # 5. 综合评分
        score = self._calc_score(trend, momentum, patterns, sr)
        
        return {
            'symbol': symbol,
            'trend': trend,
            'momentum': momentum,
            'patterns': patterns,
            'support': sr.get('support', 0),
            'resistance': sr.get('resistance', 0),
            'score': score,
            'recommendation': self._get_recommendation(score, trend, momentum, patterns)
        }
    
    def _detect_trend(self, closes):
        """趋势判断 [2026-09-04 修复: 真实EMA + 排除未收盘K线]
        原用 np.mean(最后20/50根) 近似"EMA" — 均值滞后且对最近权重错误;
        且 closes[-1] 是未收盘K线现价, 与EMA比较不稳定.
        改用标准 EMA20/EMA50 (ewm span), 用最近已收盘价 closes[-2].
        """
        if len(closes) < 25:
            return 'NEUTRAL'
        s = pd.Series(closes)
        ema20 = s.ewm(span=20, adjust=False).mean().iloc[-2]   # 排除未收盘K线
        ema50 = s.ewm(span=50, adjust=False).mean().iloc[-2]
        price = closes[-2]   # 最近已收盘价
        
        if price > ema20 > ema50:
            return 'BULLISH'
        elif price < ema20 < ema50:
            return 'BEARISH'
        return 'NEUTRAL'
    
    def _analyze_momentum(self, closes, volumes):
        """动能分析 [2026-09-04 修复: 排除未收盘K线 + 标准MACD EMA]
        原 RSI 用 len-1(未收盘K线)的裸均值, MACD 用 np.mean(近12/26根) 近似 —
        非标准且随盘中跳动. 现 RSI/MACD 均基于最近已收盘K线 closes[-2],
        MACD 用标准 EMA12-EMA26 (span 平滑).
        """
        if len(closes) < 30:
            return 'NEUTRAL'
        s = pd.Series(closes)
        # 用已收盘序列 (去掉最后一根未收盘K线)
        c = s.iloc[:-1]
        
        # RSI (Wilder 平滑近似: ewm alpha=1/14)
        delta = c.diff()
        gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = (100 - 100 / (1 + rs)).iloc[-1]
        if np.isnan(rsi):
            rsi = 50.0
        
        # MACD (标准 EMA12-26)
        ema12 = c.ewm(span=12, adjust=False).mean().iloc[-1]
        ema26 = c.ewm(span=26, adjust=False).mean().iloc[-1]
        macd = ema12 - ema26
        
        # 成交量: 最近已收盘K线 (倒数第2根) vs 之前均量
        avg_vol = np.mean(volumes[-22:-2]) if len(volumes) >= 22 else np.mean(volumes)
        vol_ratio = volumes[-2] / avg_vol if avg_vol > 0 else 1
        
        momentum = 'NEUTRAL'
        if rsi > 65:
            momentum = 'OVERBOUGHT'
        elif rsi > 55:
            momentum = 'BULLISH_MOMENTUM'
        elif rsi < 35:
            momentum = 'OVERSOLD'
        elif rsi < 45:
            momentum = 'BEARISH_MOMENTUM'
        
        return {
            'rsi': float(rsi),
            'macd': float(macd),
            'vol_ratio': float(vol_ratio),
            'signal': momentum
        }
    
    def _detect_patterns(self, opens, highs, lows, closes):
        """形态识别 [2026-09-04 修复: 只用已收盘K线]
        最后一根 H1 是当前进行中 K 线 — 锤子/流星等需完整影线才能判定,
        半成品K线会误报形态 (如刚开盘的十字被当锤子). 统一在
        len-2 (最近已收盘K线) 上识别吞没, len-2 上识别锤/流星.
        """
        patterns = []
        last_closed = len(closes) - 2  # 最近已收盘K线的索引
        
        # 看涨吞没 (需前一根: last_closed-1)
        if len(closes) >= 3:
            if self._is_bullish_engulfing(opens, closes, last_closed):
                patterns.append('bullish_engulfing')
        
        # 看跌吞没
        if len(closes) >= 3:
            if self._is_bearish_engulfing(opens, closes, last_closed):
                patterns.append('bearish_engulfing')
        
        # 锤子线 (最近已收盘K线)
        if last_closed >= 0:
            if self._is_hammer(opens, highs, lows, closes, last_closed):
                patterns.append('hammer')
        
        # 流星线
        if last_closed >= 0:
            if self._is_shooting_star(opens, highs, lows, closes, last_closed):
                patterns.append('shooting_star')
        
        return patterns
    
    def _is_bullish_engulfing(self, opens, closes, i):
        """看涨吞没"""
        if i < 1:
            return False
        prev = closes[i-1] - opens[i-1]
        curr = closes[i] - opens[i]
        return (closes[i] > opens[i-1] and 
                opens[i] < closes[i-1] and 
                curr > abs(prev) * 0.5)
    
    def _is_bearish_engulfing(self, opens, closes, i):
        """看跌吞没"""
        if i < 1:
            return False
        prev = closes[i-1] - opens[i-1]
        curr = closes[i] - opens[i]
        return (closes[i] < opens[i-1] and 
                opens[i] > closes[i-1] and 
                abs(curr) > abs(prev) * 0.5)
    
    def _is_hammer(self, opens, highs, lows, closes, i):
        """锤子线"""
        body = abs(closes[i] - opens[i])
        lower_wick = min(opens[i], closes[i]) - lows[i]
        upper_wick = highs[i] - max(opens[i], closes[i])
        return (lower_wick > body * 2 and 
                upper_wick < body * 0.5 and
                body / (highs[i] - lows[i]) < 0.3)
    
    def _is_shooting_star(self, opens, highs, lows, closes, i):
        """流星线"""
        body = abs(closes[i] - opens[i])
        upper_wick = highs[i] - max(opens[i], closes[i])
        lower_wick = min(opens[i], closes[i]) - lows[i]
        return (upper_wick > body * 2 and 
                lower_wick < body * 0.5 and
                body / (highs[i] - lows[i]) < 0.3)
    
    def _find_support_resistance(self, highs, lows, closes):
        """支撑阻力"""
        # 简单方法：最近的高点和低点
        support = np.min(lows[-20:]) if len(lows) >= 20 else np.min(lows)
        resistance = np.max(highs[-20:]) if len(highs) >= 20 else np.max(highs)
        return {'support': support, 'resistance': resistance}
    
    def _calc_score(self, trend, momentum, patterns, sr):
        """综合评分 [2026-09-04 修复: 形态按方向计分 + 缩量抑制]
        缺陷1: 原 score += len(patterns)*1.5 不分方向 — 看跌吞没在高位
              反被加分怂恿追BUY. 改为 bullish/hammer 加分, bearish/star 减分.
        缺陷2: 原只对 vol_ratio>1.5 放量加分, 缩量(<0.6)不抑制 — 缩量
              形态=假突破高发. 现缩量扣分抑制, 放量按趋势方向确认.
        """
        score = 0
        
        # 趋势得分
        if trend == 'BULLISH':
            score += 2
        elif trend == 'BEARISH':
            score -= 2
        
        # 动能得分
        if isinstance(momentum, dict):
            if momentum.get('rsi', 50) < 35:
                score += 1.0      # 超卖区: 潜在反转(仅配合同向形态)
            elif momentum.get('rsi', 50) > 65:
                score -= 1.0      # 超买区: 追高危险
            vr = momentum.get('vol_ratio', 1.0)
            if vr > 1.5:
                # 放量: 确认当前趋势方向 (趋势给分在 trend 项已体现, 这里顺势微加)
                score += 0.5 if trend != 'BEARISH' else -0.3
            elif vr < 0.6:
                # 缩量: 形态/突破可靠性差 → 抑制 (防缩量假突破)
                score -= 0.8
        
        # 形态得分 [修复: 按方向计分]
        for p in patterns:
            if p in ('bullish_engulfing', 'hammer'):
                score += 1.5       # 看涨形态 → 利多
            elif p in ('bearish_engulfing', 'shooting_star'):
                score -= 1.5       # 看跌形态 → 利空 (高位反转警告)
        
        return score
    
    def _get_recommendation(self, score, trend, momentum, patterns):
        """生成建议"""
        if score >= 4:
            return 'STRONG BUY'
        elif score >= 2:
            return 'BUY'
        elif score >= 0.5:
            return 'NEAR BUY'
        elif score >= -0.5:
            return 'NEUTRAL'
        elif score >= -2:
            return 'NEAR SELL'
        elif score >= -4:
            return 'SELL'
        else:
            return 'STRONG SELL'

# 测试
if __name__ == '__main__':
    if mt5.initialize():
        opt = EntryOptimizerV5()
        for symbol in ['XAUUSD', 'GBPUSD', 'BTCUSD']:
            result = opt.analyze(symbol)
            if result:
                print(f"\n{symbol}:")
                print(f"  趋势: {result['trend']}")
                print(f"  形态: {result['patterns']}")
                print(f"  评分: {result['score']:.1f}")
                print(f"  建议: {result['recommendation']}")
        mt5.shutdown()
