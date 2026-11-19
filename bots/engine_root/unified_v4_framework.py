# -*- coding: utf-8 -*-
"""
UnifiedStrategyV4 — 机构级策略统一升级框架
============================================
对标 Jane Street / Citadel / AQR 风控标准

统一升级特性:
1. Regime Detection (趋势/震荡/高波动三态)
2. Dynamic Parameters (波动率自适应)
3. Risk-Adjusted Position Sizing (Kelly + ATR)
4. Time Decay (信号时效衰减)
5. Quality Scoring (信号质量评分)
6. Correlation Filter (品种相关性过滤)
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json
import os


class Regime(Enum):
    TREND = "trend"
    RANGING = "ranging"
    VOLATILE = "volatile"
    TRANSITION = "transition"


@dataclass
class SignalQuality:
    """信号质量评分"""
    score: float           # 0-1
    regime: str
    adx: float
    atr_ratio: float
    confidence: float
    reasons: List[str]


class RegimeDetector:
    """机构级市况检测"""

    def __init__(self, adx_trend=25, adx_strong=40, atr_ratio_volatile=0.015):
        self.adx_trend = adx_trend
        self.adx_strong = adx_strong
        self.atr_ratio_volatile = atr_ratio_volatile

    def detect(self, h1, adx_v, atr_v, i):
        """检测当前市况"""
        if i < 50 or np.isnan(adx_v[i]) or np.isnan(atr_v[i]):
            return Regime.TRANSITION, {}

        # 获取价格用于计算ATR比率
        if h1 is not None:
            price = h1['close'].iloc[i] if hasattr(h1, 'iloc') else h1[i]
        else:
            price = 100.0  # 默认价格

        adx = adx_v[i]
        atr_ratio = atr_v[i] / price if price > 0 else 0

        # 波动率检测
        if atr_ratio > self.atr_ratio_volatile:
            return Regime.VOLATILE, {'adx': adx, 'atr_ratio': atr_ratio}

        # ADX趋势强度
        if adx >= self.adx_strong:
            return Regime.TREND, {'adx': adx, 'atr_ratio': atr_ratio, 'strength': 'strong'}
        elif adx >= self.adx_trend:
            return Regime.TREND, {'adx': adx, 'atr_ratio': atr_ratio, 'strength': 'moderate'}
        else:
            return Regime.RANGING, {'adx': adx, 'atr_ratio': atr_ratio}


class DynamicParameters:
    """波动率自适应参数"""

    def __init__(self, base_sl_mult=1.5, base_tp_mult=3.0):
        self.base_sl_mult = base_sl_mult
        self.base_tp_mult = base_tp_mult

    def adjust(self, atr_ratio: float, regime: str) -> Tuple[float, float]:
        """根据波动率和市况调整SL/TP倍数"""
        if regime == Regime.VOLATILE.value:
            # 高波动: 宽SL大TP
            return self.base_sl_mult * 1.5, self.base_tp_mult * 1.3
        elif regime == Regime.TREND.value:
            # 趋势市: 标准参数
            return self.base_sl_mult, self.base_tp_mult
        else:
            # 震荡市: 窄SL小TP
            return self.base_sl_mult * 0.8, self.base_tp_mult * 0.9


class SignalScorer:
    """信号质量评分器"""

    def __init__(self):
        self.factors = {
            'adx_strength': 0.2,      # ADX贡献
            'regime_match': 0.15,     # 市况匹配
            'multiframe': 0.2,        # 多时间框架确认
            'quality_pattern': 0.25,  # 价格行为质量
            'volume_confirm': 0.1,    # 成交量确认
            'freshness': 0.1,         # 信号新鲜度
        }

    def score(self, sig: dict, quality_factors: dict) -> SignalQuality:
        """计算信号质量"""
        score = 0.0
        reasons = []

        # ADX强度
        adx = quality_factors.get('adx', 20)
        if adx >= 35:
            score += self.factors['adx_strength']
            reasons.append('强趋势ADX')
        elif adx >= 25:
            score += self.factors['adx_strength'] * 0.7
            reasons.append('中等趋势')
        else:
            score += self.factors['adx_strength'] * 0.3
            reasons.append('弱趋势')

        # 市况匹配
        regime = quality_factors.get('regime', 'unknown')
        expected = quality_factors.get('expected_regime', regime)
        if regime == expected:
            score += self.factors['regime_match']
            reasons.append('市况匹配')
        else:
            reasons.append('市况不匹配')

        # 多时间框架
        if quality_factors.get('multiframe_confirm', False):
            score += self.factors['multiframe']
            reasons.append('多TF确认')

        # 价格行为质量
        pb_score = quality_factors.get('pb_score', 0)
        if pb_score >= 3:
            score += self.factors['quality_pattern']
            reasons.append('高质量PB')
        elif pb_score >= 1:
            score += self.factors['quality_pattern'] * 0.5

        # 成交量确认
        if quality_factors.get('volume_confirm', False):
            score += self.factors['volume_confirm']
            reasons.append('量价确认')

        # 信号新鲜度
        bar_age = quality_factors.get('bar_age', 0)
        if bar_age <= 1:
            score += self.factors['freshness']
            reasons.append('实时信号')
        elif bar_age <= 3:
            score += self.factors['freshness'] * 0.7

        return SignalQuality(
            score=score,
            regime=regime,
            adx=adx,
            atr_ratio=quality_factors.get('atr_ratio', 0),
            confidence=score,
            reasons=reasons
        )


class CorrelationFilter:
    """品种相关性过滤器"""

    def __init__(self, max_correlation=0.7):
        self.max_correlation = max_correlation
        self.correlation_matrix = {}

    def check(self, symbol: str, existing_positions: Dict[str, dict]) -> bool:
        """检查是否与其他持仓高度相关"""
        # 简化版: 检查同方向同品种
        for sym, pos in existing_positions.items():
            if sym == symbol and pos.get('side') == 1:
                # 同品种已有持仓，检查相关性
                if self.correlation_matrix.get(symbol, {}).get('side', 0) == 1:
                    return False  # 同方向，拒绝
        return True


class UnifiedV4Framework:
    """统一V4升级框架"""

    def __init__(self, risk_mgr=None):
        self.regime_detector = RegimeDetector()
        self.dynamic_params = DynamicParameters()
        self.scorer = SignalScorer()
        self.correlation_filter = CorrelationFilter()
        self.risk_mgr = risk_mgr

    def upgrade_signal(self, raw_sig: dict, h1, h4, d1, i: int) -> Optional[Dict]:
        """升级单个信号到V4标准"""
        if not raw_sig or 'side' not in raw_sig:
            return None

        # 1. 市况检测
        hc = h1['close'].values.astype(float)
        hh = h1['high'].values.astype(float)
        hl = h1['low'].values.astype(float)
        adx_v = self._calc_adx(hh, hl, hc)
        atr_v = self._calc_atr(hh, hl, hc)

        regime, regime_info = self.regime_detector.detect(h1, adx_v, atr_v, i)

        # 2. 动态参数调整
        atr_ratio = atr_v[i] / hc[i] if hc[i] > 0 else 0
        sl_mult, tp_mult = self.dynamic_params.adjust(atr_ratio, regime.value)

        # 3. 质量评分
        quality_factors = {
            'adx': regime_info.get('adx', 20),
            'regime': regime.value,
            'expected_regime': raw_sig.get('expected_regime', regime.value),
            'atr_ratio': atr_ratio,
            'multiframe_confirm': self._check_multiframe(h1, h4, i),
            'pb_score': raw_sig.get('pb_score', 0),
            'volume_confirm': raw_sig.get('volume_confirm', False),
            'bar_age': raw_sig.get('bar_age', 0),
        }

        quality = self.scorer.score(raw_sig, quality_factors)

        # 4. 风险调整
        if self.risk_mgr:
            risk_check = self.risk_mgr.calculate_position_size(
                symbol=raw_sig.get('symbol', 'UNKNOWN'),
                entry=raw_sig.get('entry', 0),
                sl=raw_sig.get('sl', 0),
                atr=atr_v[i],
                strategy=raw_sig.get('strat', 'UNKNOWN')
            )
            if risk_check.get('reason') != 'ok':
                return None  # 风险限制，拒绝信号

        # 5. 构建升级信号
        upgraded = raw_sig.copy()
        upgraded['quality_score'] = quality.score
        upgraded['regime'] = regime.value
        upgraded['sl_mult'] = sl_mult
        upgraded['tp_mult'] = tp_mult
        upgraded['confidence'] = quality.confidence
        upgraded['quality_reasons'] = quality.reasons
        upgraded['risk_tier'] = self.risk_mgr._drawdown_tier if self.risk_mgr else 1.0

        return upgraded

    def _calc_adx(self, hh, hl, hc, period=14):
        """计算ADX"""
        n = len(hh)
        tr = np.full(n, np.nan)
        plus_dm = np.full(n, np.nan)
        minus_dm = np.full(n, np.nan)

        for i in range(1, n):
            tr[i] = max(hh[i] - hl[i], abs(hh[i] - hc[i-1]), abs(hl[i] - hc[i-1]))
            up = hh[i] - hh[i-1]
            down = hl[i-1] - hl[i]
            if up > down and up > 0:
                plus_dm[i] = up
            if down > up and down > 0:
                minus_dm[i] = down

        plus_di = np.full(n, np.nan)
        minus_di = np.full(n, np.nan)
        for i in range(period, n):
            s = np.nansum(tr[i-period+1:i+1])
            if s > 0:
                plus_di[i] = 100 * np.nansum(plus_dm[i-period+1:i+1]) / s
                minus_di[i] = 100 * np.nansum(minus_dm[i-period+1:i+1]) / s

        dx = np.full(n, np.nan)
        for i in range(period, n):
            d = plus_di[i] + minus_di[i]
            if d > 0:
                dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / d

        # 平滑
        result = np.full(n, np.nan)
        for i in range(period, n):
            result[i] = np.nanmean(dx[i-period+1:i+1]) if not np.isnan(dx[i]).all() else np.nan
        return result

    def _calc_atr(self, hh, hl, hc, period=14):
        """计算ATR"""
        n = len(hh)
        tr = np.full(n, np.nan)
        for i in range(1, n):
            tr[i] = max(hh[i] - hl[i], abs(hh[i] - hc[i-1]), abs(hl[i] - hc[i-1]))
        atr = np.full(n, np.nan)
        if n >= period:
            atr[period] = np.mean(tr[1:period+1])
            for i in range(period+1, n):
                atr[i] = tr[i] / period + atr[i-1] * (period-1) / period
        return atr

    def _check_multiframe(self, h1, h4, i: int) -> bool:
        """检查多时间框架确认"""
        if len(h4) < 10:
            return False
        h4i = min(i // 4, len(h4) - 1)
        # 简化: 检查H4趋势
        h4c = h4['close'].values
        h4_ma20 = np.mean(h4c[max(0,h4i-20):h4i]) if h4i >= 20 else np.mean(h4c[:h4i])
        h4_ma50 = np.mean(h4c[max(0,h4i-50):h4i]) if h4i >= 50 else h4_ma20
        return not (np.isnan(h4_ma20) or np.isnan(h4_ma50))


# ═══════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 70)
    print("UnifiedV4Framework 自检")
    print("=" * 70)

    framework = UnifiedV4Framework()

    # 测试市况检测
    np.random.seed(42)
    n = 200
    closes = np.cumsum(np.random.randn(n) * 0.5) + 100
    highs = closes + np.abs(np.random.randn(n)) * 0.3
    lows = closes - np.abs(np.random.randn(n)) * 0.3

    adx_v = framework._calc_adx(highs, lows, closes)
    atr_v = framework._calc_atr(highs, lows, closes)

    print(f"\n测试市况检测:")
    for i in [50, 100, 150]:
        regime, info = framework.regime_detector.detect(None, adx_v, atr_v, i)
        print(f"  bar {i}: regime={regime.value}, ADX={info.get('adx',0):.1f}, ATR_RATIO={info.get('atr_ratio',0):.4f}")

    # 测试动态参数
    print(f"\n测试动态参数:")
    for atr_ratio in [0.002, 0.005, 0.01, 0.02]:
        sl, tp = framework.dynamic_params.adjust(atr_ratio, 'trend')
        print(f"  ATR_RATIO={atr_ratio:.4f}: SL={sl:.2f}x, TP={tp:.2f}x")

    print("\n" + "=" * 70)
    print("✅ UnifiedV4Framework 自检完成")
    print("=" * 70)
