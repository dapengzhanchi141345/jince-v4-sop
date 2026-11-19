# -*- coding: utf-8 -*-
"""
MultiStrategyCoordinator V1.0
多策略协同引擎 — 融合OTAS+PASD+DIV+TREND+MR+BO

核心设计理念:
1. 分层决策: 品种层 → 策略层 → 信号层 → 执行层
2. 策略协同: 多策略共振提高置信度
3. 动态权重: 根据实盘表现自动调整策略权重
4. 风险总控: 总仓位不超过账户净值X%
"""

import numpy as np
import pandas as pd
import json
import os
import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

# ═══════════════════════════════════════════════════════════════
# 配置常量
# ═══════════════════════════════════════════════════════════════

@dataclass
class StrategyConfig:
    """策略配置"""
    name: str
    weight: float = 1.0           # 策略权重 (初始1.0)
    min_confidence: float = 0.5   # 最低置信度
    max_positions: int = 1        # 最大持仓数
    risk_pct: float = 0.02        # 单笔风险占比

@dataclass
class Signal:
    """标准化信号"""
    symbol: str
    side: int                    # 1=买入, -1=卖出
    entry: float
    sl: float
    tp: float
    confidence: float            # 0-1, 置信度
    strategies: List[str] = field(default_factory=list)  # 触发策略
    timestamp: float = 0.0
    bar: int = 0

@dataclass
class Position:
    """持仓记录"""
    symbol: str
    side: int
    entry: float
    sl: float
    tp: float
    lot: float
    strategy: str
    open_time: float
    pnl: float = 0.0

@dataclass
class Performance:
    """策略表现追踪"""
    name: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    weight: float = 1.0
    last_update: float = 0.0

# ═══════════════════════════════════════════════════════════════
# 多策略协同引擎
# ═══════════════════════════════════════════════════════════════

class MultiStrategyCoordinator:
    """
    多策略协同引擎
    
    核心功能:
    1. 多策略信号生成与融合
    2. 共振检测与置信度计算
    3. 动态权重调整
    4. 风险总控
    5. 表现追踪与进化
    """
    
    def __init__(self, 
                 keep_symbols: List[str],
                 initial_equity: float = 10000.0,
                 max_risk_pct: float = 0.05,
                 resonance_threshold: float = 0.6,
                 weight_decay: float = 0.95):
        """
        初始化协同引擎
        
        Args:
            keep_symbols: KEEP品种列表
            initial_equity: 初始净值
            max_risk_pct: 最大总风险占比
            resonance_threshold: 共振阈值 (≥2策略同向)
            weight_decay: 权重衰减因子
        """
        self.keep_symbols = keep_symbols
        self.initial_equity = initial_equity
        self.equity = initial_equity
        self.max_risk_pct = max_risk_pct
        self.resonance_threshold = resonance_threshold
        self.weight_decay = weight_decay
        
        # 策略配置
        self.strategy_configs = {
            # [2026-08-31 V4修复] 补入高信号量策略 SDP/ICT/VP
            # 实测(真实MT5·1000根H1): SDP≈536 / ICT≈351 / VP≈35 信号,
            # 而原配置6策略(OTAS仅4·TREND仅2)信号极度稀缺 → 长期"无有效信号"不开单
            # [2026-08-31 质量优先进化] 风控额度稀缺(新闻闸HIGH→单笔0.75%风险,
            # 日上限3% ⇒ 每天仅约4单额度), 而信号供给过剩(单品种≈200个协调信号).
            # 此时"提门槛"是纯收益: 额度恒定, 只让最强信号去竞争这4个名额。
            'SDP':  StrategyConfig('SDP',  weight=0.9,  min_confidence=0.62),
            'ICT':  StrategyConfig('ICT',  weight=0.9,  min_confidence=0.62),
            'VP':   StrategyConfig('VP',   weight=0.7,  min_confidence=0.60),
            'OTAS': StrategyConfig('OTAS', weight=1.0, min_confidence=0.58),
            'PASD': StrategyConfig('PASD', weight=1.0, min_confidence=0.58),
            'DIV': StrategyConfig('DIV', weight=1.0, min_confidence=0.58),
            'TREND': StrategyConfig('TREND', weight=1.0, min_confidence=0.58),
            'MR': StrategyConfig('MR', weight=1.0, min_confidence=0.58),
            'BO': StrategyConfig('BO', weight=0.5, min_confidence=0.65),  # BO信号多，降权+更高门槛
        }
        
        # 表现追踪
        self.performances = {name: Performance(name) for name in self.strategy_configs}
        
        # 当前持仓
        self.positions: Dict[str, Position] = {}
        
        # 交易历史
        self.trade_history: List[Dict] = []
        
        # 信号缓存
        self.signal_cache: Dict[str, List[Signal]] = {}
        
        # 特征工程缓存
        self.feature_cache: Dict[str, Dict] = {}
        
        # 进化日志
        self.evolution_log: List[Dict] = []
        
        print(f"[Coordinator] 初始化完成")
        print(f"  KEEP品种: {len(keep_symbols)} 个")
        print(f"  策略数: {len(self.strategy_configs)} 个")
        print(f"  初始净值: ${initial_equity:.2f}")
    
    def generate_signals(self, 
                         symbol: str,
                         h1: pd.DataFrame,
                         h4: pd.DataFrame,
                         d1: pd.DataFrame,
                         cfg: dict) -> List[Signal]:
        """
        生成多策略融合信号
        
        流程:
        1. 各策略独立生成信号
        2. 信号标准化 (置信度计算)
        3. 共振检测
        4. 权重调整
        """
        signals = []

        # 0. 数据长度校验 (V4集成: 数据不足时直接返回空, 避免指标计算越界)
        MIN_BARS = 250
        try:
            if h1 is None or len(h1) < MIN_BARS:
                return []
            if h4 is None or len(h4) < 60:
                return []
            if d1 is None or len(d1) < 30:
                return []
        except Exception:
            return []

        # 1. 各策略独立生成信号 (V4优先, 回退V1)
        try:
            from advanced_strategies_v4 import STRATEGY_REGISTRY as REG_V4
        except Exception:
            from advanced_strategies import STRATEGY_REGISTRY as REG_V4

        for name, gen in REG_V4.items():
            if name not in self.strategy_configs:
                continue
            
            config = self.strategy_configs[name]
            if config.weight <= 0:
                continue
            
            try:
                raw_sigs = gen(h1, h4, d1, cfg)
                for sig in raw_sigs:
                    # 标准化信号
                    signal = self._normalize_signal(
                        symbol, sig, name, config.weight
                    )
                    if signal and signal.confidence >= config.min_confidence:
                        signals.append(signal)
            except Exception as e:
                print(f"[Coordinator] {name} 策略报错: {e}")
        
        # 2. 共振检测
        resonant = self._detect_resonance(signals)
        
        # 3. 返回融合信号
        return resonant
    
    def _normalize_signal(self, 
                          symbol: str,
                          raw_sig: dict,
                          strategy: str,
                          weight: float) -> Optional[Signal]:
        """标准化信号，计算置信度"""
        try:
            side = raw_sig.get('side', 0)
            entry = raw_sig.get('entry', 0)
            sl = raw_sig.get('sl', 0)
            tp = raw_sig.get('tp', 0)
            bar = raw_sig.get('bar', 0)
            
            if side not in [1, -1] or entry <= 0 or sl <= 0 or tp <= 0:
                return None
            
            # 计算置信度
            confidence = self._calc_confidence(raw_sig, strategy, weight)
            
            return Signal(
                symbol=symbol,
                side=side,
                entry=entry,
                sl=sl,
                tp=tp,
                confidence=confidence,
                strategies=[strategy],
                timestamp=time.time(),
                bar=bar
            )
        except Exception as e:
            return None
    
    def _calc_confidence(self, raw_sig: dict, strategy: str, weight: float) -> float:
        """计算信号置信度 (0-1)"""
        base_confidence = 0.5  # 基础置信度
        
        # 策略权重加成
        confidence = base_confidence * weight
        
        # 根据策略特性调整
        if strategy == 'OTAS':
            # 一次一单策略，强趋势过滤，置信度较高
            adx = raw_sig.get('adx', 0)
            if adx >= 30:
                confidence += 0.2
            elif adx >= 25:
                confidence += 0.1
        elif strategy == 'PASD':
            # 供需共振策略
            resonance = raw_sig.get('mf_resonance', 0)
            confidence += resonance * 0.3
        elif strategy == 'DIV':
            # 均值回归策略
            confidence += 0.1
        elif strategy == 'TREND':
            # 趋势跟踪
            confidence += 0.1
        elif strategy == 'MR':
            # 均值回归
            confidence += 0.05
        elif strategy == 'BO':
            # 突破策略，信号多，降低置信度
            confidence *= 0.7
        
        return min(confidence, 1.0)
    
    def _detect_resonance(self, signals: List[Signal]) -> List[Signal]:
        """共振检测 — 多策略同向信号提升置信度"""
        if not signals:
            return signals
        
        # 按品种+方向分组
        groups = defaultdict(list)
        for sig in signals:
            key = (sig.symbol, sig.side)
            groups[key].append(sig)
        
        # 共振提升
        resonant_signals = []
        for key, sigs in groups.items():
            if len(sigs) >= 2:
                # 共振！提升置信度
                for sig in sigs:
                    sig.confidence = min(sig.confidence + 0.2, 1.0)
                    # 合并策略列表
                    all_strategies = set()
                    for s in sigs:
                        all_strategies.update(s.strategies)
                    sig.strategies = list(all_strategies)
            resonant_signals.extend(sigs)
        
        return resonant_signals
    
    def select_best_signal(self, signals: List[Signal]) -> Optional[Signal]:
        """选择最佳信号 (考虑仓位和风险)"""
        if not signals:
            return None
        
        # 按置信度排序
        signals.sort(key=lambda s: s.confidence, reverse=True)
        
        # 筛选: 不与现有持仓冲突
        for sig in signals:
            if sig.symbol in self.positions:
                continue  # 已有持仓，跳过
            if sig.symbol not in self.keep_symbols:
                continue  # 非KEEP品种，跳过
            return sig
        
        return None
    
    def calculate_position_size(self, signal: Signal) -> float:
        """计算仓位大小 (基于风险百分比)"""
        risk_per_trade = self.equity * self.max_risk_pct
        risk_per_unit = abs(signal.entry - signal.sl)
        
        if risk_per_unit <= 0:
            return 0.1  # 默认0.1手
        
        lot = risk_per_trade / (risk_per_unit * 100)  # 简化计算
        lot = max(0.01, min(lot, 1.0))  # 限制在0.01-1.0手
        
        return round(lot, 2)
    
    def update_performance(self, trade: Dict):
        """更新策略表现"""
        strategy = trade.get('strategy', '')
        if strategy not in self.performances:
            return
        
        perf = self.performances[strategy]
        perf.trades += 1
        
        if trade.get('result') == 'win':
            perf.wins += 1
        else:
            perf.losses += 1
        
        perf.total_pnl += trade.get('pnl', 0)
        
        if perf.trades > 0:
            perf.win_rate = perf.wins / perf.trades * 100
        
        # 计算PF
        wins_pnl = sum(t['pnl'] for t in self.trade_history 
                      if t.get('strategy') == strategy and t.get('result') == 'win')
        losses_pnl = abs(sum(t['pnl'] for t in self.trade_history 
                       if t.get('strategy') == strategy and t.get('result') == 'loss'))
        perf.profit_factor = wins_pnl / losses_pnl if losses_pnl > 0 else float('inf')
        
        perf.last_update = time.time()
        
        # 动态权重调整
        self._adjust_weight(strategy, perf)
    
    def _adjust_weight(self, strategy: str, perf: Performance):
        """根据表现调整策略权重"""
        if perf.trades < 5:
            return  # 样本不足，不调整
        
        # 基于PF和胜率调整
        target_pf = 1.5
        target_wr = 45.0
        
        pf_ratio = perf.profit_factor / target_pf if target_pf > 0 else 1.0
        wr_ratio = perf.win_rate / target_wr if target_wr > 0 else 1.0
        
        # 综合评分
        score = (pf_ratio * 0.6 + wr_ratio * 0.4)
        score = max(0.3, min(score, 2.0))  # 限制在0.3-2.0
        
        # 更新权重
        config = self.strategy_configs.get(strategy)
        if config:
            # 指数移动平均
            config.weight = config.weight * self.weight_decay + score * (1 - self.weight_decay)
            config.weight = max(0.3, min(config.weight, 2.0))
            
            # 记录进化日志
            self.evolution_log.append({
                'timestamp': time.time(),
                'strategy': strategy,
                'weight_old': config.weight / (1 - self.weight_decay) if self.weight_decay < 1 else config.weight,
                'weight_new': config.weight,
                'pf': perf.profit_factor,
                'wr': perf.win_rate,
                'trades': perf.trades
            })
    
    def get_status_report(self) -> Dict:
        """获取状态报告"""
        report = {
            'equity': self.equity,
            'initial_equity': self.initial_equity,
            'return_pct': (self.equity - self.initial_equity) / self.initial_equity * 100,
            'positions': len(self.positions),
            'strategies': {},
            'evolution_count': len(self.evolution_log)
        }
        
        for name, perf in self.performances.items():
            report['strategies'][name] = {
                'weight': self.strategy_configs[name].weight,
                'trades': perf.trades,
                'win_rate': perf.win_rate,
                'profit_factor': perf.profit_factor,
                'total_pnl': perf.total_pnl
            }
        
        return report


# ═══════════════════════════════════════════════════════════════
# 进化优化引擎
# ═══════════════════════════════════════════════════════════════

class EvolutionEngine:
    """
    进化优化引擎
    
    功能:
    1. 参数自动调优
    2. 策略权重进化
    3. 品种适配优化
    4. 市况适应
    """
    
    def __init__(self, coordinator: MultiStrategyCoordinator):
        self.coordinator = coordinator
        self.generation = 0
        self.best_params = {}
        
    def optimize_params(self, symbol: str, h1: pd.DataFrame, h4: pd.DataFrame, d1: pd.DataFrame):
        """优化策略参数"""
        # TODO: 实现参数优化
        pass
    
    def evolve(self):
        """进化一步"""
        self.generation += 1
        print(f"[Evolution] Generation {self.generation} completed")


# ═══════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("多策略协同引擎 V1.0 自检")
    print("=" * 70)
    
    # 模拟KEEP列表
    keep_symbols = ['XAUUSD', 'XAGUSD', 'BTCUSD', 'ETHUSD', 'EURUSD', 'GBPUSD']
    
    # 初始化
    coordinator = MultiStrategyCoordinator(
        keep_symbols=keep_symbols,
        initial_equity=10000.0,
        max_risk_pct=0.05,
        resonance_threshold=0.6
    )
    
    print(f"\n[OK] 协同引擎初始化完成")
    print(f"  策略数: {len(coordinator.strategy_configs)}")
    print(f"  KEEP品种: {len(keep_symbols)}")
    
    # 模拟生成信号
    np.random.seed(42)
    n = 500
    closes = np.cumsum(np.random.randn(n) * 0.5) + 100
    opens = closes + np.random.randn(n) * 0.1
    highs = np.maximum(closes, opens) + np.abs(np.random.randn(n)) * 0.3
    lows = np.minimum(closes, opens) - np.abs(np.random.randn(n)) * 0.3
    times = np.arange(n) * 3600
    
    h1 = pd.DataFrame({'open': opens, 'high': highs, 'low': lows, 'close': closes, 'time': times})
    h4 = h1.iloc[::4].copy()
    d1 = h1.iloc[::20].copy()
    
    cfg = {'pip': 0.01, 'lot': 0.1}
    
    # 测试各策略
    from advanced_strategies import STRATEGY_REGISTRY
    
    print(f"\n各策略信号测试:")
    for name in ['OTAS', 'PASD', 'DIV', 'TREND', 'MR', 'BO']:
        gen = STRATEGY_REGISTRY.get(name)
        if gen:
            try:
                sigs = gen(h1, h4, d1, cfg)
                print(f"  {name}: {len(sigs)} 信号")
            except Exception as e:
                print(f"  {name}: 错误 - {e}")
    
    # 生成协同信号
    print(f"\n协同信号生成测试:")
    signals = coordinator.generate_signals('XAUUSD', h1, h4, d1, cfg)
    print(f"  生成信号: {len(signals)} 个")
    
    if signals:
        best = coordinator.select_best_signal(signals)
        if best:
            lot = coordinator.calculate_position_size(best)
            print(f"  最佳信号: {best.symbol} {'BUY' if best.side==1 else 'SELL'} @ {best.entry:.2f}")
            print(f"  置信度: {best.confidence:.2f}")
            print(f"  推荐仓位: {lot}手")
    
    # 状态报告
    print(f"\n协同引擎状态:")
    report = coordinator.get_status_report()
    print(f"  净值: ${report['equity']:.2f}")
    print(f"  收益: {report['return_pct']:+.2f}%")
    print(f"  持仓: {report['positions']}")
    
    for name, st in report['strategies'].items():
        print(f"  {name}: 权重={st['weight']:.2f} 交易={st['trades']} PF={st['profit_factor']:.2f}")
    
    print("\n" + "=" * 70)
    print("✅ 多策略协同引擎自检完成")
    print("=" * 70)
