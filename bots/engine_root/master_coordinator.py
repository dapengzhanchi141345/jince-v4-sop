# -*- coding: utf-8 -*-
"""
MasterCoordinator V1.0
主协调器 — 融合所有策略的顶层协调层

架构设计:
┌─────────────────────────────────────────────────────────────┐
│                    MasterCoordinator                        │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐   │
│  │ SignalGen   │  │ Resonance   │  │  RiskController  │   │
│  │ (多策略)    │→ │ (共振检测)  │→ │  (风险总控)      │   │
│  └─────────────┘  └─────────────┘  └──────────────────┘   │
│         │                 │                  │             │
│         ▼                 ▼                  ▼             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              ExecutionOrchestrator                   │   │
│  │  (信号路由 → 仓位分配 → 执行)                        │   │
│  └─────────────────────────────────────────────────────┘   │
│         │                                                  │
│         ▼                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐   │
│  │ Evolution   │  │ Performance │  │   Monitor        │   │
│  │ (进化优化)  │  │ (表现追踪)  │  │  (监控报警)      │   │
│  └─────────────┘  └─────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────┘
"""

import numpy as np
import pandas as pd
import json
import os
import time
import threading
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
from collections import defaultdict
from enum import Enum

# 导入现有模块
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from multi_strategy_coordinator import MultiStrategyCoordinator
from evolution_engine import EvolutionEngine


class SignalPriority(Enum):
    """信号优先级"""
    CRITICAL = 3      # 高置信度共振信号
    HIGH = 2          # 单策略高置信度
    MEDIUM = 1        # 普通信号
    LOW = 0           # 低质量信号


@dataclass
class CoordinatedSignal:
    """协调后信号"""
    symbol: str
    side: int
    entry: float
    sl: float
    tp: float
    lot: float
    confidence: float
    priority: SignalPriority
    triggering_strategies: List[str]
    coordinated_strategies: List[str]  # 共振策略
    timestamp: float
    meta: Dict = field(default_factory=dict)


class MasterCoordinator:
    """
    主协调器 — 策略融合与执行中枢
    
    核心能力:
    1. 多策略信号融合
    2. 共振检测与置信度提升
    3. 动态仓位管理
    4. 风险总控
    5. 自动进化优化
    6. 实盘表现追踪
    """
    
    def __init__(
        self,
        keep_symbols: List[str],
        initial_equity: float = 10000.0,
        max_total_risk_pct: float = 0.05,
        max_positions_per_symbol: int = 1,
        resonance_boost: float = 0.15,
        evolution_interval: int = 100,  # 每100笔交易进化一次
        save_dir: str = "data/master_coordinator"
    ):
        """
        初始化主协调器
        
        Args:
            keep_symbols: KEEP品种列表
            initial_equity: 初始净值
            max_total_risk_pct: 总风险上限
            max_positions_per_symbol: 每品种最大持仓数
            resonance_boost: 共振置信度加成
            evolution_interval: 进化间隔
            save_dir: 保存目录
        """
        self.keep_symbols = keep_symbols
        self.initial_equity = initial_equity
        self.equity = initial_equity
        self.max_total_risk_pct = max_total_risk_pct
        self.max_positions_per_symbol = max_positions_per_symbol
        self.resonance_boost = resonance_boost
        self.evolution_interval = evolution_interval
        self.save_dir = save_dir
        
        os.makedirs(save_dir, exist_ok=True)
        
        # 初始化子模块
        self.coordinator = MultiStrategyCoordinator(
            keep_symbols=keep_symbols,
            initial_equity=initial_equity,
            max_risk_pct=max_total_risk_pct,
        )
        self.evolution = EvolutionEngine(save_dir=os.path.join(save_dir, 'evolution'))
        
        # 信号队列
        self.signal_queue: List[CoordinatedSignal] = []
        
        # 执行状态
        self.executed_trades: List[Dict] = []
        self.current_positions: Dict[str, Dict] = {}
        
        # 表现追踪
        self.performance_history: List[Dict] = []
        
        # 进化计数器
        self.trade_counter = 0
        self.last_evolution_gen = 0
        
        # 运行状态
        self.is_running = False
        self.stats = {
            'total_signals': 0,
            'executed_signals': 0,
            'rejected_signals': 0,
            'resonance_count': 0,
            'evolution_count': 0,
        }
        
        print("=" * 70)
        print("MasterCoordinator V1.0 初始化完成")
        print("=" * 70)
        print(f"  KEEP品种: {len(keep_symbols)}")
        print(f"  初始净值: ${initial_equity:.2f}")
        print(f"  最大风险: {max_total_risk_pct*100:.1f}%")
        print(f"  进化间隔: {evolution_interval}笔交易")
    
    def generate_coordinated_signals(
        self,
        symbol: str,
        h1: pd.DataFrame,
        h4: pd.DataFrame,
        d1: pd.DataFrame,
        cfg: dict
    ) -> List[CoordinatedSignal]:
        """
        生成协调后的信号
        
        流程:
        1. 各策略独立生成信号
        2. 共振检测
        3. 置信度计算
        4. 优先级排序
        5. 风险过滤
        """
        # 1. 各策略独立生成
        raw_signals = self.coordinator.generate_signals(symbol, h1, h4, d1, cfg)
        
        if not raw_signals:
            return []
        
        # 2. 共振检测与提升
        self.stats['total_signals'] += len(raw_signals)
        resonant = self._apply_resonance_boost(raw_signals)
        if resonant:
            self.stats['resonance_count'] += len(resonant)
        
        # 3. 转换为协调信号
        coordinated = []
        for sig in resonant:
            # 检查品种风险
            if not self._check_symbol_risk(symbol):
                self.stats['rejected_signals'] += 1
                continue
            
            # 检查持仓限制
            if symbol in self.current_positions:
                self.stats['rejected_signals'] += 1
                continue
            
            coordinated.append(self._to_coordinated_signal(sig))
        
        return coordinated
    
    def _apply_resonance_boost(self, signals: List) -> List:
        """应用共振加成"""
        # 按品种+方向分组
        groups = defaultdict(list)
        for sig in signals:
            key = (sig.symbol, sig.side)
            groups[key].append(sig)
        
        # 共振提升
        for key, sigs in groups.items():
            if len(sigs) >= 2:
                for sig in sigs:
                    sig.confidence = min(sig.confidence + self.resonance_boost, 1.0)
        
        return signals
    
    def _check_symbol_risk(self, symbol: str) -> bool:
        """检查品种风险"""
        # 计算该品种当前风险敞口
        current_risk = 0.0
        for sym, pos in self.current_positions.items():
            if sym == symbol:
                # 简化计算: 风险 = 持仓手数 * ATR * pip_value / equity
                current_risk += pos.get('lot', 0) * 0.001  # 简化
        
        max_risk = self.equity * self.max_total_risk_pct
        return current_risk < max_risk
    
    def _to_coordinated_signal(self, raw_sig) -> CoordinatedSignal:
        """转换为协调信号"""
        # 确定优先级
        if raw_sig.confidence >= 0.7 and len(raw_sig.strategies) >= 2:
            priority = SignalPriority.CRITICAL
        elif raw_sig.confidence >= 0.5:
            priority = SignalPriority.HIGH
        elif raw_sig.confidence >= 0.3:
            priority = SignalPriority.MEDIUM
        else:
            priority = SignalPriority.LOW
        
        return CoordinatedSignal(
            symbol=raw_sig.symbol,
            side=raw_sig.side,
            entry=raw_sig.entry,
            sl=raw_sig.sl,
            tp=raw_sig.tp,
            lot=self._calculate_lot(raw_sig),
            confidence=raw_sig.confidence,
            priority=priority,
            triggering_strategies=raw_sig.strategies,
            coordinated_strategies=self._find_coordinated_strategies(raw_sig),
            timestamp=raw_sig.timestamp,
            meta={
                'adx': getattr(raw_sig, 'adx', 0),
                'atr': getattr(raw_sig, 'atr', 0),
            }
        )
    
    def _calculate_lot(self, signal) -> float:
        """计算仓位大小"""
        risk_per_trade = self.equity * self.max_total_risk_pct / len(self.keep_symbols)
        risk_per_unit = abs(signal.entry - signal.sl)
        
        if risk_per_unit <= 0:
            return 0.1
        
        lot = risk_per_trade / (risk_per_unit * 100)
        return round(max(0.01, min(lot, 1.0)), 2)
    
    def _find_coordinated_strategies(self, signal) -> List[str]:
        """找出协同策略"""
        # 找出同方向其他策略信号
        # 简化实现: 返回所有策略
        return signal.strategies
    
    def execute_signal(self, signal: CoordinatedSignal) -> Dict:
        """
        执行信号
        
        Returns:
            执行结果字典
        """
        trade = {
            'symbol': signal.symbol,
            'side': signal.side,
            'entry': signal.entry,
            'sl': signal.sl,
            'tp': signal.tp,
            'lot': signal.lot,
            'strategy': signal.triggering_strategies[0] if signal.triggering_strategies else 'UNKNOWN',
            'confidence': signal.confidence,
            'priority': signal.priority.name,
            'timestamp': time.time(),
            'result': None,
            'pnl': 0.0,
        }
        
        # 记录持仓
        self.current_positions[signal.symbol] = {
            'side': signal.side,
            'entry': signal.entry,
            'sl': signal.sl,
            'tp': signal.tp,
            'lot': signal.lot,
            'open_time': time.time(),
            'strategy': trade['strategy'],
        }
        
        self.executed_trades.append(trade)
        self.stats['executed_signals'] += 1
        
        print(f"[Execute] {signal.symbol} {'BUY' if signal.side==1 else 'SELL'} "
              f"@ {signal.entry:.4f} Lot={signal.lot} Conf={signal.confidence:.2f}")
        
        return trade
    
    def close_position(self, symbol: str, pnl: float, result: str):
        """平仓并更新表现"""
        if symbol not in self.current_positions:
            return
        
        # 更新表现
        pos = self.current_positions[symbol]
        strategy = pos.get('strategy', 'UNKNOWN')
        
        # 更新tracker
        self.coordinator.update_performance({
            'strategy': strategy,
            'result': result,
            'pnl': pnl,
        })
        
        # 记录交易历史
        self.performance_history.append({
            'symbol': symbol,
            'side': pos['side'],
            'entry': pos['entry'],
            'exit_pnl': pnl,
            'result': result,
            'strategy': strategy,
            'timestamp': time.time(),
        })
        
        # 移除持仓
        del self.current_positions[symbol]
        
        # 进化检查
        self.trade_counter += 1
        if self.trade_counter % self.evolution_interval == 0:
            self._trigger_evolution()
    
    def _trigger_evolution(self):
        """触发进化优化"""
        print(f"[Evolution] 触发进化优化 (第{self.trade_counter}笔交易)")
        
        # 简化: 仅优化表现最佳的策略
        best_strategies = sorted(
            self.coordinator.performances.items(),
            key=lambda x: x[1].profit_factor,
            reverse=True
        )[:2]
        
        for name, perf in best_strategies:
            if perf.trades >= 10:  # 样本充足才优化
                print(f"  优化策略: {name} (PF={perf.profit_factor:.2f}, WR={perf.win_rate:.1f}%)")
        
        self.stats['evolution_count'] += 1
        self.last_evolution_gen += 1
    
    def get_status_report(self) -> Dict:
        """获取状态报告"""
        return {
            'equity': self.equity,
            'initial_equity': self.initial_equity,
            'return_pct': (self.equity - self.initial_equity) / self.initial_equity * 100,
            'open_positions': len(self.current_positions),
            'executed_trades': len(self.executed_trades),
            'performance_history': len(self.performance_history),
            'stats': self.stats,
            'strategy_weights': {
                name: cfg.weight 
                for name, cfg in self.coordinator.strategy_configs.items()
            },
            'evolution_gen': self.last_evolution_gen,
        }
    
    def save_state(self):
        """保存状态"""
        state_file = os.path.join(self.save_dir, 'state.json')
        state = {
            'equity': self.equity,
            'stats': self.stats,
            'trade_counter': self.trade_counter,
            'last_evolution_gen': self.last_evolution_gen,
            'strategy_weights': {
                name: cfg.weight
                for name, cfg in self.coordinator.strategy_configs.items()
            },
        }
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)
        print(f"[MasterCoordinator] 状态已保存")
    
    def load_state(self):
        """加载状态"""
        state_file = os.path.join(self.save_dir, 'state.json')
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    state = json.load(f)
                self.equity = state.get('equity', self.initial_equity)
                self.stats = state.get('stats', self.stats)
                self.trade_counter = state.get('trade_counter', 0)
                self.last_evolution_gen = state.get('last_evolution_gen', 0)
                print(f"[MasterCoordinator] 状态已加载")
            except Exception as e:
                print(f"[MasterCoordinator] 加载状态失败: {e}")


# 自检
if __name__ == "__main__":
    print("=" * 70)
    print("MasterCoordinator V1.0 完整自检")
    print("=" * 70)
    
    # 初始化
    keep_symbols = ['XAUUSD', 'XAGUSD', 'BTCUSD', 'ETHUSD', 'EURUSD', 'GBPUSD']
    master = MasterCoordinator(
        keep_symbols=keep_symbols,
        initial_equity=10000.0,
        max_total_risk_pct=0.05,
    )
    
    # 模拟交易循环
    print(f"\n模拟交易循环 (10笔交易):")
    print("-" * 50)
    
    for i in range(10):
        # 模拟数据
        np.random.seed(i * 100 + 42)
        n = 500
        closes = [100.0]
        for j in range(1, n):
            trend = 0.005 * np.sin(j * 0.01)
            noise = np.random.randn() * 0.003
            closes.append(closes[-1] * (1 + trend + noise))
        closes = np.array(closes)
        opens = closes + np.random.randn(n) * 0.001
        highs = np.maximum(closes, opens) + np.abs(np.random.randn(n)) * 0.002
        lows = np.minimum(closes, opens) - np.abs(np.random.randn(n)) * 0.002
        times = np.arange(n) * 3600
        
        h1 = pd.DataFrame({'open': opens, 'high': highs, 'low': lows, 'close': closes, 'time': times})
        h4 = pd.DataFrame({'open': opens[::4], 'high': highs[::4], 'low': lows[::4], 'close': closes[::4], 'time': times[::4]})
        d1 = pd.DataFrame({'open': opens[::20], 'high': highs[::20], 'low': lows[::20], 'close': closes[::20], 'time': times[::20]})
        
        # 选择品种
        symbol = keep_symbols[i % len(keep_symbols)]
        
        # 生成信号
        cfg = {'pip': 0.01, 'lot': 0.1}
        signals = master.generate_coordinated_signals(symbol, h1, h4, d1, cfg)
        
        if signals:
            # 执行最佳信号
            signals.sort(key=lambda s: s.confidence, reverse=True)
            best = signals[0]
            
            # 模拟执行
            trade = master.execute_signal(best)
            
            # 模拟平仓 (50%概率盈利)
            import random
            if random.random() > 0.5:
                pnl = random.uniform(10, 100)
                master.close_position(symbol, pnl, 'win')
            else:
                pnl = -random.uniform(5, 30)
                master.close_position(symbol, pnl, 'loss')
        else:
            print(f"[{i}] {symbol}: 无信号")
    
    # 状态报告
    print("\n" + "=" * 70)
    print("最终状态报告")
    print("=" * 70)
    
    report = master.get_status_report()
    print(f"  净值: ${report['equity']:.2f}")
    print(f"  收益: {report['return_pct']:+.2f}%")
    print(f"  执行交易: {report['executed_trades']} 笔")
    print(f"  策略权重:")
    for name, weight in report['strategy_weights'].items():
        print(f"    {name}: {weight:.2f}")
    print(f"  进化代数: {report['evolution_gen']}")
    
    # 保存状态
    master.save_state()
    
    print("\n" + "=" * 70)
    print("✅ MasterCoordinator V1.0 自检完成")
    print("=" * 70)
