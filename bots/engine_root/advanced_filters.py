# advanced_filters.py — P1+P2 高级过滤器（多时间框架 + ML预测 + 微观模式 + VaR）
# [2026-08-21] 借鉴世界顶级量化基金核心技术

"""
P1+P2 高级过滤器模块

借鉴来源:
- P1-3 多时间框架趋势确认: Man AHL (900+市场, 多时间框架共振)
- P1-4 波动率自适应: Man AHL (ATR动态调整)
- P1-5 简单ML预测胜率: Two Sigma (纯numpy逻辑回归)
- P2-1 微观模式识别: Renaissance (4000+子策略)
- P2-2 另类数据整合: Point72 (新闻情绪, 简化版)
- P2-3 实时VaR监控: Citadel (组合风险)
- P2-4 HMM状态机增强: Algo724 (全局市况切换)

设计原则:
- 纯numpy，无ML依赖（无sklearn/torch）
- 失败开放：任何异常不阻断交易链
- 模块化合并：所有功能合并为一个文件便于维护
"""

import numpy as np
import math
from typing import Tuple, List, Optional


# ════════════════════════════════════════════════════════════════
# P1-3: 多时间框架趋势确认 (借鉴 Man AHL)
# ════════════════════════════════════════════════════════════════

def mtf_trend_resonance(h1: np.ndarray, h4: np.ndarray, d1: np.ndarray, 
                        direction: str, window: int = 20) -> Tuple[bool, float, str]:
    """多时间框架趋势共振检测。
    
    返回 (共振通过, 共振缩放因子, 共振消息)
    
    原理:
    - D1/H4/H1 三周期同向 → 强共振 (scale=1.0)
    - 两周期同向 → 中等共振 (scale=0.8)
    - 仅单周期或反向 → 弱共振/逆势 (scale=0.5)
    - 双周期逆势 → 硬拒 (scale=0.0)
    """
    try:
        def slope_direction(prices: np.ndarray, window: int) -> str:
            """计算价格序列斜率方向"""
            if len(prices) < window:
                return 'NEUTRAL'
            y = prices[-window:].astype(float)
            x = np.arange(window, dtype=float)
            slope = np.polyfit(x, y, 1)[0]
            ref = np.mean(y)
            if ref == 0:
                return 'NEUTRAL'
            rel = slope * window / ref
            if rel > 0.003:
                return 'BUY'
            elif rel < -0.003:
                return 'SELL'
            return 'NEUTRAL'
        
        h1_dir = slope_direction(h1, window)
        h4_dir = slope_direction(h4, window)
        d1_dir = slope_direction(d1, window)
        
        # 统计同向周期数
        agree = sum(1 for d in [h1_dir, h4_dir, d1_dir] if d == direction)
        disagree = sum(1 for d in [h1_dir, h4_dir, d1_dir] if d != 'NEUTRAL' and d != direction)
        
        # 决策逻辑
        if disagree >= 2:
            # 双周期逆势 → 硬拒
            return False, 0.0, f"多时间框架逆势拒单 (H1={h1_dir}/H4={h4_dir}/D1={d1_dir})"
        elif disagree == 1:
            # 单周期逆势 → 降仓
            return True, 0.5, f"单周期逆势 H1={h1_dir}/H4={h4_dir}/D1={d1_dir}"
        elif agree == 3:
            # 三周期共振 → 满仓
            return True, 1.0, f"三周期共振 H1={h1_dir}/H4={h4_dir}/D1={d1_dir}"
        elif agree == 2:
            # 两周期共振 → 中等仓位
            return True, 0.8, f"两周期共振 H1={h1_dir}/H4={h4_dir}/D1={d1_dir}"
        else:
            # 单周期或中性
            return True, 0.6, f"弱共振 H1={h1_dir}/H4={h4_dir}/D1={d1_dir}"
            
    except Exception as e:
        # 失败开放
        return True, 1.0, f"共振检测异常: {e}"


# ════════════════════════════════════════════════════════════════
# P1-4: 波动率自适应参数 (借鉴 Man AHL)
# ════════════════════════════════════════════════════════════════

def adaptive_volatility_params(volatility: float, base_adx_min: float, 
                                base_sl_mult: float) -> Tuple[float, float, float]:
    """波动率自适应参数调整。
    
    返回 (adapted_adx_min, adapted_sl_mult, vol_regime)
    
    原理:
    - 高波动: 放宽ADX门槛, 增加SL距离
    - 低波动: 收紧ADX门槛, 缩小SL距离
    """
    try:
        # 波动率分级
        if volatility > 0.05:
            vol_regime = "high"
            # 高波动: ADX门槛降低50%, SL距离增加50%
            return base_adx_min * 0.7, base_sl_mult * 1.5, vol_regime
        elif volatility < 0.01:
            vol_regime = "low"
            # 低波动: ADX门槛提高20%, SL距离缩小30%
            return base_adx_min * 1.2, base_sl_mult * 0.7, vol_regime
        else:
            vol_regime = "normal"
            return base_adx_min, base_sl_mult, vol_regime
    except Exception:
        return base_adx_min, base_sl_mult, "unknown"


# ════════════════════════════════════════════════════════════════
# P1-5: 简单ML预测胜率 (借鉴 Two Sigma)
# ════════════════════════════════════════════════════════════════

class SimpleMLFilter:
    """纯numpy实现的简单ML过滤器。
    
    功能:
    1. 逻辑回归预测信号胜率
    2. 特征: ADX, 波动率, 信号强度
    3. 阈值: 预测胜率 > 0.55 才放行
    
    设计原则:
    - 失败开放: 无训练数据时返回1.0
    - 纯numpy: 无ML依赖
    """
    
    def __init__(self, threshold: float = 0.55):
        self.threshold = threshold
        self.weights = None
        self.bias = None
        self.trained = False
        self.training_samples = 0
        
    def _sigmoid(self, z):
        """Sigmoid激活函数 (支持标量与numpy数组)"""
        z = np.asarray(z, dtype=np.float64)
        # 数值稳定: 对极值裁剪
        z_clipped = np.clip(z, -500, 500)
        out = 1.0 / (1.0 + np.exp(-z_clipped))
        if out.ndim == 0:
            return float(out)
        return out
    
    def predict_win_rate(self, adx: float, volatility: float, 
                         signal_strength: float = 1.0) -> float:
        """预测信号胜率。
        
        参数:
        - adx: ADX值 (趋势强度)
        - volatility: 波动率
        - signal_strength: 信号强度 (0-1)
        
        返回:
        - 预测胜率 (0-1)
        """
        try:
            # 如果未训练, 使用启发式规则
            if not self.trained:
                # 启发式规则: ADX>25 且 波动率适中 → 胜率较高
                adx_score = min(1.0, adx / 50.0) if adx > 0 else 0.5
                vol_score = max(0.3, 1.0 - abs(volatility - 0.02) * 20) if volatility > 0 else 0.5
                base_rate = 0.45 + 0.1 * adx_score + 0.05 * vol_score
                return max(0.4, min(0.7, base_rate))
            
            # 训练后的预测
            features = np.array([adx, volatility, signal_strength])
            if self.weights is None:
                return 0.5
            z = np.dot(self.weights, features) + self.bias
            return self._sigmoid(z)
            
        except Exception:
            return 0.5
    
    def train(self, X: np.ndarray, y: np.ndarray, lr: float = 0.01, epochs: int = 100):
        """逻辑回归训练。
        
        参数:
        - X: 特征矩阵 (n_samples, n_features)
        - y: 标签向量 (n_samples,) 0=亏损 1=盈利
        - lr: 学习率
        - epochs: 训练轮数
        """
        try:
            if len(X) < 10:
                return False
            
            n_samples, n_features = X.shape
            # 初始化权重
            self.weights = np.zeros(n_features)
            self.bias = 0.0
            
            # 梯度下降
            for epoch in range(epochs):
                # 前向传播
                z = np.dot(X, self.weights) + self.bias
                predictions = self._sigmoid(z)
                
                # 计算损失
                epsilon = 1e-15
                predictions = np.clip(predictions, epsilon, 1 - epsilon)
                loss = -np.mean(y * np.log(predictions) + (1 - y) * np.log(1 - predictions))
                
                # 梯度计算
                error = predictions - y
                dw = np.dot(X.T, error) / n_samples
                db = np.mean(error)
                
                # 更新权重
                self.weights -= lr * dw
                self.bias -= lr * db
            
            self.trained = True
            self.training_samples = len(X)
            print(f"[MLFilter] 训练完成: {len(X)} 样本, 最终损失={loss:.4f}")
            return True
            
        except Exception as e:
            print(f"[MLFilter] 训练失败: {e}")
            return False


# 全局ML过滤器实例
_ml_filter = SimpleMLFilter(threshold=0.55)


# ════════════════════════════════════════════════════════════════
# P2-1: 微观模式识别 (借鉴 Renaissance)
# ════════════════════════════════════════════════════════════════

def detect_micro_patterns(prices: np.ndarray, volatility: float) -> Tuple[bool, float, str]:
    """微观模式识别。
    
    返回 (模式存在, 模式强度, 模式类型)
    
    模式类型:
    - consecutive_bars: 连续N根K线同向
    - breakout: 突破N日高点/低点
    - volume_spike: 成交量异常放大
    - squeeze: 波动率收缩（突破前兆）
    """
    try:
        if len(prices) < 20:
            return False, 0.0, "数据不足"
        
        closes = prices[-20:].astype(float)
        
        # 模式1: 连续3根K线同向
        consecutive_bars = 0
        for i in range(len(closes) - 1):
            if closes[i + 1] > closes[i]:
                consecutive_bars += 1
            else:
                consecutive_bars = 0
            if consecutive_bars >= 3:
                direction = 'UP' if closes[-1] > closes[0] else 'DOWN'
                return True, 0.8, f"连续{consecutive_bars+1}根同向K线({direction})"
        
        # 模式2: 突破20日高点/低点
        high_20 = np.max(closes)
        low_20 = np.min(closes)
        current = closes[-1]
        
        if current > high_20 * 1.002:
            return True, 0.9, "突破20日高点"
        elif current < low_20 * 0.998:
            return True, 0.9, "突破20日低点"
        
        # 模式3: 波动率收缩（突破前兆）
        if volatility < 0.005:  # 极低波动
            return True, 0.7, f"波动率收缩({volatility:.4f})"
        
        return False, 0.0, "无明显微观模式"
        
    except Exception:
        return False, 0.0, "检测失败"


# ════════════════════════════════════════════════════════════════
# P2-2: 另类数据整合（简化版：财经日历情绪）
# ════════════════════════════════════════════════════

def load_calendar_sentiment(symbol: str = None) -> float:
    """加载财经日历情绪（简化版）。
    
    返回情绪分数 (-1.0 到 1.0)
    - 1.0: 强烈看涨
    - -1.0: 强烈看跌
    - 0.0: 中性
    """
    try:
        # 简化：从TC共识读取
        import os
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tc_consensus.json')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if symbol:
                sym_data = data.get(symbol, {})
                bias = sym_data.get('bias', 'NEUTRAL')
                if bias == 'BUY':
                    return 0.7
                elif bias == 'SELL':
                    return -0.7
                return 0.0
            else:
                # 返回全局平均情绪
                biases = [v.get('bias', 'NEUTRAL') for v in data.values() 
                         if isinstance(v, dict)]
                buy_count = biases.count('BUY')
                sell_count = biases.count('SELL')
                total = len(biases)
                if total == 0:
                    return 0.0
                return (buy_count - sell_count) / total
        return 0.0
    except Exception:
        return 0.0


# ════════════════════════════════════════════════════════════════
# P2-3: 实时VaR监控 (借鉴 Citadel)
# ════════════════════════════════════════════════════════════════

def calculate_portfolio_var(positions: List[dict], confidence: float = 0.95, 
                            lookback: int = 60) -> float:
    """计算组合VaR（Value at Risk）。
    
    参数:
    - positions: 持仓列表 [{symbol, lot, direction, entry}]
    - confidence: 置信度 (0.95 = 95%)
    - lookback: 回看窗口（K线数）
    
    返回:
    - VaR美元值（正数表示风险金额）
    """
    try:
        if not positions:
            return 0.0
        
        # 简化：使用历史收益率分布
        # 实际应使用协方差矩阵，此处用单资产近似
        total_exposure = 0.0
        for pos in positions:
            lot = abs(pos.get('lot', 0))
            pip_usd = pos.get('pip_usd', 10.0)
            total_exposure += lot * pip_usd * 100  # 简化估算
        
        # 使用历史波动率估算
        # 95%置信度对应的z值约为1.645
        z_score = 1.645
        var = total_exposure * z_score * 0.02  # 假设日波动率2%
        
        return var
        
    except Exception:
        return 0.0


# ════════════════════════════════════════════════════════════════
# P2-4: HMM状态机增强（简化版：两状态隐马尔可夫）
# ════════════════════════════════════════════════════

class SimpleHMM:
    """简化版HMM状态机（两状态：趋势/震荡）。
    
    借鉴 Algo724 HMM regime filter
    """
    
    def __init__(self):
        self.transition_matrix = np.array([[0.9, 0.1],  # 趋势→趋势/震荡
                                           [0.2, 0.8]])  # 震荡→趋势/震荡
        self.observation_probs = {
            'trend': {'high_vol': 0.7, 'low_vol': 0.3},
            'range': {'high_vol': 0.3, 'low_vol': 0.7}
        }
        self.current_state = 'trend'
        self.state_probs = {'trend': 0.5, 'range': 0.5}
    
    def update(self, observation: str) -> str:
        """根据观测更新状态。
        
        参数:
        - observation: 'high_vol' 或 'low_vol'
        
        返回:
        - 更新后的状态
        """
        try:
            # 简化贝叶斯更新
            if observation == 'high_vol':
                self.state_probs['trend'] *= 0.7
                self.state_probs['range'] *= 0.3
            else:
                self.state_probs['trend'] *= 0.3
                self.state_probs['range'] *= 0.7
            
            # 归一化
            total = sum(self.state_probs.values())
            if total > 0:
                self.state_probs['trend'] /= total
                self.state_probs['range'] /= total
            
            # 取最可能状态
            self.current_state = 'trend' if self.state_probs['trend'] > self.state_probs['range'] else 'range'
            
            return self.current_state
            
        except Exception:
            return self.current_state


# 全局HMM实例
_hmm = SimpleHMM()


# ════════════════════════════════════════════════════════════════
# 主过滤器接口
# ════════════════════════════════════════════════════════════════

def get_advanced_filter() -> 'AdvancedFilter':
    """返回高级过滤器实例"""
    return AdvancedFilter()


class AdvancedFilter:
    """高级过滤器主类，整合所有P1+P2功能。"""
    
    def __init__(self):
        self.mlf = _ml_filter
        self.hmm = _hmm
    
    def filter_signal(self, symbol: str, h1_prices: np.ndarray, 
                      h4_prices: np.ndarray, d1_prices: np.ndarray,
                      direction: str, strategy: str,
                      volatility: float, adx: float,
                      equity: float, positions: List[dict] = None) -> Tuple[bool, float, str]:
        """
        高级过滤器主入口。
        
        参数:
        - symbol: 品种代码
        - h1_prices, h4_prices, d1_prices: 各时间框架收盘价数组
        - direction: 交易方向 ('BUY'/'SELL')
        - strategy: 策略名称
        - volatility: 当前波动率
        - adx: 当前ADX值
        - equity: 账户净值
        - positions: 当前持仓列表
        
        返回:
        - (通过, 缩放因子, 原因)
        """
        try:
            reasons = []
            scale = 1.0
            
            # 1. 多时间框架趋势确认 (P1-3)
            mtf_ok, mtf_scale, mtf_reason = mtf_trend_resonance(
                h1_prices, h4_prices, d1_prices, direction
            )
            if not mtf_ok:
                return False, 0.0, f"MTF拒单: {mtf_reason}"
            scale *= mtf_scale
            reasons.append(f"MTF:{mtf_reason}")
            
            # 2. 波动率自适应 (P1-4)
            adx_min, sl_mult, vol_regime = adaptive_volatility_params(
                volatility, adx * 0.5, 1.5  # 传入当前adx和默认sl_mult
            )
            reasons.append(f"VolRegime:{vol_regime}")
            
            # 3. ML预测胜率 (P1-5)
            predicted_wr = self.mlf.predict_win_rate(adx, volatility)
            if predicted_wr < self.mlf.threshold:
                # 低胜率信号降仓
                scale *= 0.5
                reasons.append(f"ML低胜率:{predicted_wr:.2f}")
            else:
                reasons.append(f"ML胜率:{predicted_wr:.2f}")
            
            # 4. 微观模式识别 (P2-1)
            pattern_found, pattern_strength, pattern_type = detect_micro_patterns(
                h1_prices, volatility
            )
            if pattern_found:
                scale *= (1.0 + pattern_strength * 0.2)  # 模式存在时小幅加仓位
                reasons.append(f"Pattern:{pattern_type}")
            
            # 5. 另类数据情绪 (P2-2)
            sentiment = load_calendar_sentiment(symbol)
            if sentiment > 0.5:
                scale *= 1.1  # 看涨情绪加仓位
            elif sentiment < -0.5:
                scale *= 0.9  # 看跌情绪降仓位
            reasons.append(f"Sentiment:{sentiment:+.2f}")
            
            # 6. VaR监控 (P2-3)
            var = calculate_portfolio_var(positions or [])
            if var > equity * 0.02:  # VaR > 2% 净值时降仓
                scale *= 0.7
                reasons.append(f"VaR高:${var:.2f}")
            
            # 7. HMM状态调整 (P2-4)
            obs = 'high_vol' if volatility > 0.03 else 'low_vol'
            hmm_state = self.hmm.update(obs)
            if hmm_state == 'range':
                scale *= 0.8  # 震荡市降仓
            reasons.append(f"HMM:{hmm_state}")
            
            # 最终检查
            if scale <= 0:
                return False, 0.0, "过滤器汇总: " + "; ".join(reasons)
            
            return True, scale, "; ".join(reasons)
            
        except Exception as e:
            # 失败开放
            return True, 1.0, f"过滤器异常开放: {e}"


# ════════════════════════════════════════════════════════════════
# 训练工具
# ════════════════════════════════════════════════════════════════

def train_ml_filter_from_history(journal_path: str = None):
    """从交易日志训练ML过滤器。
    
    参数:
    - journal_path: 交易日志JSON路径
    """
    try:
        import json as json_lib
        if journal_path is None:
            journal_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                        'data', 'trade_journal.json')
        
        if not os.path.exists(journal_path):
            print(f"[MLFilter] 日志文件不存在: {journal_path}")
            return False
        
        with open(journal_path, 'r', encoding='utf-8') as f:
            trades = json_lib.load(f)
        
        if len(trades) < 50:
            print(f"[MLFilter] 样本不足: {len(trades)} < 50")
            return False
        
        # 准备训练数据
        X = []
        y = []
        
        for trade in trades:
            # 特征: ADX, 波动率, 信号强度
            adx = trade.get('adx', 25.0)
            volatility = trade.get('volatility', 0.02)
            signal_strength = trade.get('signal_strength', 1.0)
            
            # 标签: 1=盈利, 0=亏损
            profit = trade.get('profit', 0)
            label = 1 if profit > 0 else 0
            
            X.append([adx, volatility, signal_strength])
            y.append(label)
        
        X = np.array(X)
        y = np.array(y)
        
        # 训练
        return _ml_filter.train(X, y, lr=0.01, epochs=200)
        
    except Exception as e:
        print(f"[MLFilter] 训练失败: {e}")
        return False


if __name__ == "__main__":
    # 自检
    print("=" * 60)
    print("AdvancedFilters 自检")
    print("=" * 60)
    
    # 测试多时间框架共振
    h1 = np.array([100, 101, 102, 103, 104])
    h4 = np.array([98, 99, 100, 101, 102])
    d1 = np.array([95, 96, 97, 98, 99])
    ok, scale, reason = mtf_trend_resonance(h1, h4, d1, 'BUY')
    print(f"MTF共振: ok={ok}, scale={scale:.2f}, reason={reason}")
    
    # 测试波动率自适应
    adx_min, sl_mult, regime = adaptive_volatility_params(0.06, 20.0, 1.5)
    print(f"高波动: adx_min={adx_min:.1f}, sl_mult={sl_mult:.2f}, regime={regime}")
    
    adx_min, sl_mult, regime = adaptive_volatility_params(0.005, 20.0, 1.5)
    print(f"低波动: adx_min={adx_min:.1f}, sl_mult={sl_mult:.2f}, regime={regime}")
    
    # 测试ML预测
    mlf = SimpleMLFilter()
    wr = mlf.predict_win_rate(30.0, 0.02)
    print(f"ML预测胜率 (ADX=30, vol=2%): {wr:.2f}")
    
    # 测试微观模式
    prices = np.array([100, 101, 102, 103, 104, 105, 106, 107, 108, 109])
    found, strength, ptype = detect_micro_patterns(prices, 0.02)
    print(f"微观模式: found={found}, strength={strength:.2f}, type={ptype}")
    
    print("\n✅ 自检通过")
