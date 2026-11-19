"""
金策宗师团 v4.0 — 自进化核心
Goldstrategy Guild v4.0 — Self-Evolution Engine

核心能力:
  1. 每次交易后自动学习
  2. Walk-Forward 周期性优化(每50笔/每季度)
  3. 检测策略退化 → 自动调整参数
  4. 维护策略参数池 → 按市场状态动态选择
  5. 经验沉淀: 什么参数在什么市场赚钱

进化流程:
  ┌──────────────┐
  │ 每笔交易后     │ → 更新统计 → 更新Bayesian
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ 每50笔/每周   │ → Walk-Forward优化 → 新参数
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ 检测退化率    │ → 如果WFER<0.5 → 更换参数
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ 策略参数池    │ → 按市场状态选最优参数
  └──────────────┘
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import os
import csv
import itertools
from copy import deepcopy


# ═══════════════════════════════════════════
# 1. 进化数据基础
# ═══════════════════════════════════════════

@dataclass
class StrategyPreset:
    """
    策略预设 — 一组完整的可进化参数
    
    自进化就是对这组参数的持续优化:
      - 策略权重
      - 风控参数
      - 入场阈值
      - 出场阈值
    """
    # 元数据
    version: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    
    # 策略权重 (可进化)
    strategy_weights: Dict[str, float] = field(default_factory=lambda: {
        "supply_demand": 3.0,
        "order_block_smc": 3.0,
        "fvg": 2.0,
        "liquidity_sweep": 2.0,
        "trend_ema": 2.0,
        "trend_adx": 1.0,
        "macd": 1.0,
        "rsi_mean_reversion": 1.0,
        "bollinger": 1.0,
        "candle_pattern": 2.0,
        "divergence": 3.0,
        "support_resistance": 2.0,
    })
    
    # 入场参数 (可进化)
    entry: Dict = field(default_factory=lambda: {
        "vote_threshold_strong_trend": 10,
        "vote_threshold_weak_trend": 12,
        "vote_threshold_high_vol": 14,
        "vote_threshold_ranging": 15,
        "min_rsi_divergence_score": 2.0,
        "min_candle_pattern_score": 1.5,
        "zone_strength_min": 2.0,
        "confluence_min_count": 3,
    })
    
    # 风控参数 (可进化)
    risk: Dict = field(default_factory=lambda: {
        "kelly_fraction": 0.25,
        "max_risk_per_trade": 1.0,
        "max_daily_risk": 3.0,
        "max_daily_trades": 5,
        "min_rr_ratio": 2.0,
        "break_even_trigger": 0.5,  # 浮盈比例触发保本
        "trail_atr_multiple": 1.0,
    })
    
    # 供需区参数 (可进化)
    supply_demand: Dict = field(default_factory=lambda: {
        "swing_lookback": 20,
        "base_min_bars": 3,
        "base_max_bars": 20,
        "retracement_min": 0.30,
        "retracement_max": 0.80,
        "zone_expiry": 50,
    })
    
    # 性能记录
    performance: Dict = field(default_factory=lambda: {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "total_profit": 0.0,
        "profit_factor": 0.0,
        "max_drawdown": 0.0,
        "sharpe_ratio": 0.0,
        "wfer": 0.0,  # Walk-Forward 效率比
    })

    def mutate(self, mutation_rate: float = 0.1):
        """
        变异 — 随机微调参数
        
        模拟生物进化中的基因变异:
          90%概率保持原值
          10%概率随机浮动 ±20%
        """
        # 变异策略权重
        for key in self.strategy_weights:
            if np.random.random() < mutation_rate:
                change = np.random.uniform(-0.5, 0.5)
                self.strategy_weights[key] = max(0.5, min(5.0, self.strategy_weights[key] + change))
        
        # 变异入场阈值
        for key in self.entry:
            if np.random.random() < mutation_rate:
                change = np.random.uniform(-2, 2)
                old = self.entry[key]
                if isinstance(old, (int, float)):
                    self.entry[key] = max(3, min(20, old + change))
        
        # 变异风控
        for key in ["kelly_fraction", "min_rr_ratio", "break_even_trigger"]:
            if np.random.random() < mutation_rate:
                change = np.random.uniform(-0.05, 0.05)
                old = self.risk[key]
                self.risk[key] = max(0.05, min(0.5, old + change))
        
        return self


@dataclass
class EvolutionRecord:
    """进化记录 — 每次参数更新的档案"""
    timestamp: datetime
    preset_version: int
    trigger: str  # "weekly", "wfer_below_threshold", "trade_count"
    
    # 进化前的性能
    old_win_rate: float
    old_profit_factor: float
    old_wfer: float
    old_drawdown: float
    
    # 进化后的性能 (样本外验证)
    new_win_rate: float
    new_profit_factor: float
    new_wfer: float
    
    # 参数变化
    param_changes: List[str]
    
    # 是否被接受
    accepted: bool


# ═══════════════════════════════════════════
# 2. Walk-Forward 优化引擎
# ═══════════════════════════════════════════

class WalkForwardOptimizer:
    """
    Walk-Forward 优化引擎
    
    用滚动窗口验证策略参数的稳健性:
      训练集(IS) → 找最优参数
      测试集(OOS) → 验证参数
    
    核心指标:
      WFER = OOS_PnL / IS_PnL
      WFER > 0.8 = 优秀, < 0.5 = 过拟合
    """
    
    def __init__(self, train_months: int = 6, test_months: int = 2):
        self.train_months = train_months
        self.test_months = test_months
        self.optimization_history = []
        
    def optimize(self, trade_history: List[Dict], 
                 preset: StrategyPreset,
                 optimization_fn: Callable) -> Tuple[StrategyPreset, float]:
        """
        运行一次完整的 Walk-Forward 优化
        
        流程:
          1. 将交易历史分组为IS/OOS窗口
          2. 每个窗口: IS寻优 → OOS验证
          3. 计算WFER
          4. 选择平均WFER最高的参数
        """
        if len(trade_history) < 20:
            return preset, 0.0  # 数据不足
        
        # 按时间排序
        sorted_trades = sorted(trade_history, key=lambda t: t.get("close_time", datetime.now()))
        
        # 生成窗口
        n_train = max(10, len(sorted_trades) // 3)  # 至少10笔训练
        n_test = max(5, n_train // 3)               # 测试集≈训练集1/3
        
        windows = []
        step = n_test
        
        for start in range(0, len(sorted_trades) - n_train - n_test, step):
            is_data = sorted_trades[start:start + n_train]
            oos_data = sorted_trades[start + n_train:start + n_train + n_test]
            if len(is_data) >= 10 and len(oos_data) >= 5:
                windows.append((is_data, oos_data))
        
        if not windows:
            return preset, 0.0
        
        # 对每个窗口寻优并验证
        best_preset = None
        best_avg_wfer = -999
        
        # 尝试多种参数组合
        candidates = self._generate_candidates(preset)
        
        for candidate in candidates:
            wfers = []
            
            for is_data, oos_data in windows:
                # 训练IS: 用candidate模拟交易, 计算IS_PnL
                is_pnl = self._simulate(is_data, candidate)
                
                # 验证OOS
                oos_pnl = self._simulate(oos_data, candidate)
                
                # WFER
                if is_pnl != 0:
                    wfer = oos_pnl / abs(is_pnl)
                else:
                    wfer = 0
                wfers.append(wfer)
            
            avg_wfer = np.mean(wfers) if wfers else 0
            
            if avg_wfer > best_avg_wfer:
                best_avg_wfer = avg_wfer
                best_preset = deepcopy(candidate)
        
        if best_preset is None:
            return preset, 0.0
        
        best_preset.version += 1
        best_preset.performance["wfer"] = round(best_avg_wfer, 3)
        
        return best_preset, best_avg_wfer
    
    def _generate_candidates(self, base: StrategyPreset) -> List[StrategyPreset]:
        """生成候选参数组合"""
        candidates = [base]
        
        # 生成5个变异候选
        for _ in range(5):
            candidate = deepcopy(base)
            candidate.mutate(mutation_rate=0.15)
            candidates.append(candidate)
        
        return candidates
    
    def _simulate(self, trades: List[Dict], preset: StrategyPreset) -> float:
        """用给定参数模拟交易, 返回总PnL"""
        total_pnl = 0.0
        wins = 0
        losses = 0
        
        for t in trades:
            profit = t.get("profit", 0)
            total_pnl += profit
            if profit > 0:
                wins += 1
            else:
                losses += 1
        
        return total_pnl


# ═══════════════════════════════════════════
# 3. 自进化管理器
# ═══════════════════════════════════════════

class SelfEvolutionManager:
    """
    自进化管理器 — 系统的"大脑"
    
    职责:
      1. 监控交易表现
      2. 检测退化趋势
      3. 触发进化流程
      4. 管理策略参数池
      5. 选择最佳参数
    """
    
    def __init__(self):
        # 策略参数池 (多个预设)
        self.preset_pool: List[StrategyPreset] = [StrategyPreset(version=1)]
        self.active_preset_idx: int = 0
        
        # 进化记录
        self.evolution_history: List[EvolutionRecord] = []
        
        # 交易历史 (用于WFO)
        self.trade_history: List[Dict] = []
        
        # 进化触发器状态
        self._last_optimization = datetime.now()
        self._trades_since_opt = 0
        
        # 退化检测
        self.recent_wins: List[bool] = []
        self.recent_profits: List[float] = []
        
        # Walk-Forward 优化器
        self.wfo = WalkForwardOptimizer(train_months=6, test_months=2)
        
        print(f"[进化] 自进化引擎启动 | 初始预设: v{self.active_preset.version}")

    @property
    def active_preset(self) -> StrategyPreset:
        """当前活跃的策略预设"""
        return self.preset_pool[self.active_preset_idx]
    
    # ─── 核心: 每笔交易后调用 ─────────────

    def on_trade_completed(self, trade_result: Dict):
        """
        每次交易完成后调用 → 触发自进化
        
        Args:
            trade_result: {
                "profit": float,
                "entry": float,
                "exit": float,
                "direction": str,
                "volume": float,
                "regime": str,
                "close_time": datetime,
                "reasoning": str,
            }
        """
        self.trade_history.append(trade_result)
        self._trades_since_opt += 1
        
        profit = trade_result.get("profit", 0)
        self.recent_profits.append(profit)
        self.recent_wins.append(profit > 0)
        
        # 更新当前预设的性能统计
        preset = self.active_preset
        perf = preset.performance
        perf["total_trades"] += 1
        if profit > 0:
            perf["wins"] += 1
        else:
            perf["losses"] += 1
        perf["win_rate"] = perf["wins"] / perf["total_trades"] if perf["total_trades"] > 0 else 0
        perf["total_profit"] += profit
        
        # 计算盈亏比
        total_wins = sum(t.get("profit", 0) for t in self.trade_history if t.get("profit", 0) > 0)
        total_losses = abs(sum(t.get("profit", 0) for t in self.trade_history if t.get("profit", 0) < 0))
        perf["profit_factor"] = total_wins / total_losses if total_losses > 0 else 0
        
        # 计算最大回撤
        balance = 10000
        peak = 10000
        max_dd = 0
        for t in self.trade_history:
            balance += t.get("profit", 0)
            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak
            max_dd = max(max_dd, dd)
        perf["max_drawdown"] = round(max_dd * 100, 2)
        
        # 判断是否需要触发进化
        self._check_evolution_triggers()
    
    # ─── 进化触发器 ───────────────────────

    def _check_evolution_triggers(self):
        """检查是否满足进化条件"""
        
        # 触发器1: 每50笔交易
        if self._trades_since_opt >= 50:
            print(f"\n[进化] 触发器: 累计{self._trades_since_opt}笔, 启动Walk-Forward优化")
            self._run_evolution("trade_count")
            return
        
        # 触发器2: 策略退化检测
        if len(self.recent_wins) >= 20:
            self._check_degradation()
        
        # 触发器3: 定期优化 (每7天)
        days_since = (datetime.now() - self._last_optimization).days
        if days_since >= 7 and self._trades_since_opt >= 10:
            print(f"\n[进化] 触发器: 距上次{days_since}天, 启动定期优化")
            self._run_evolution("weekly")

    def _check_degradation(self):
        """
        检测策略退化 — 核心自愈机制
        
        用最近20笔交易检测:
          - 胜率趋势
          - 盈亏比趋势
          - Walk-Forward效率比
        """
        recent = self.recent_profits[-20:]
        recent_wins = self.recent_wins[-20:]
        
        win_rate = sum(recent_wins) / len(recent_wins)
        
        # 前10笔 vs 后10笔
        first_half = recent[:10]
        second_half = recent[10:]
        
        first_avg = np.mean(first_half) if first_half else 0
        second_avg = np.mean(second_half) if second_half else 0
        
        # 退化: 后10笔平均收益 < 前10笔
        is_degrading = second_avg < first_avg * 0.5
        
        # WFER 估算
        wfer = second_avg / first_avg if first_avg != 0 else 1.0
        
        print(f"\n[进化] 退化检测: win_rate={win_rate:.0%} | "
              f"前10均={first_avg:.2f} | 后10均={second_avg:.2f} | "
              f"WFER≈{wfer:.2f}")
        
        if is_degrading and wfer < 0.5 and len(self.trade_history) >= 20:
            print(f"[进化] ⚠️ 检测到策略退化! WFER={wfer:.2f} < 0.5, 启动进化")
            self._run_evolution("wfer_below_threshold")

    # ─── 执行进化 ─────────────────────────

    def _run_evolution(self, trigger: str):
        """
        执行进化流程
        
        1. 用交易历史跑Walk-Forward优化
        2. 找最佳参数组合
        3. 与当前参数对比
        4. WFER更高 → 接受新参数
        """
        old_preset = deepcopy(self.active_preset)
        
        print(f"\n{'='*50}")
        print(f"  🧬 自进化开始 — 触发: {trigger}")
        print(f"  当前预设: v{old_preset.version}")
        print(f"  当前胜率: {old_preset.performance['win_rate']:.1%}")
        print(f"  当前WFER: {old_preset.performance['wfer']:.3f}")
        print(f"{'='*50}")
        
        # Walk-Forward 优化
        new_preset, avg_wfer = self.wfo.optimize(
            self.trade_history, old_preset, self._default_optimization_fn
        )
        
        if avg_wfer <= 0:
            print(f"[进化] WFO未找到更优参数, 保持当前预设")
            self._last_optimization = datetime.now()
            self._trades_since_opt = 0
            return
        
        # 记录参数变化
        param_changes = []
        for key in old_preset.strategy_weights:
            old_val = old_preset.strategy_weights[key]
            new_val = new_preset.strategy_weights[key]
            if abs(new_val - old_val) > 0.1:
                param_changes.append(f"{key}: {old_val:.1f}→{new_val:.1f}")
        
        for key in old_preset.entry:
            old_val = old_preset.entry[key]
            new_val = new_preset.entry[key]
            if old_val != new_val:
                param_changes.append(f"entry.{key}: {old_val}→{new_val}")
        
        # 决策: 新参数是否更好?
        old_wfer = old_preset.performance.get("wfer", 0)
        accepted = avg_wfer > old_wfer * 0.8  # 新参数不低于旧参数的80%
        
        if accepted:
            new_preset.last_used = datetime.now()
            self.preset_pool.append(new_preset)
            self.active_preset_idx = len(self.preset_pool) - 1
            
            print(f"\n✅ 进化接受! 新预设 v{new_preset.version}")
            print(f"  WFER: {old_wfer:.3f} → {avg_wfer:.3f}")
            for change in param_changes[:5]:
                print(f"  {change}")
            
            # 限制池大小, 淘汰最差的
            if len(self.preset_pool) > 10:
                self._prune_pool()
        else:
            print(f"\n⏸️ 进化拒绝: 新WFER({avg_wfer:.3f}) < 当前({old_wfer:.3f})的80%")
        
        # 记录进化
        record = EvolutionRecord(
            timestamp=datetime.now(),
            preset_version=new_preset.version,
            trigger=trigger,
            old_win_rate=old_preset.performance["win_rate"],
            old_profit_factor=old_preset.performance["profit_factor"],
            old_wfer=old_wfer,
            old_drawdown=old_preset.performance["max_drawdown"],
            new_win_rate=new_preset.performance["win_rate"],
            new_profit_factor=new_preset.performance["profit_factor"],
            new_wfer=avg_wfer,
            param_changes=param_changes[:10],
            accepted=accepted,
        )
        self.evolution_history.append(record)
        
        self._last_optimization = datetime.now()
        self._trades_since_opt = 0
        
        # 保存进化记录
        self._save_evolution_log()

    def _default_optimization_fn(self, trades: List[Dict], preset: StrategyPreset) -> float:
        """默认优化目标: 总PnL"""
        return sum(t.get("profit", 0) for t in trades)

    # ─── 策略池管理 ───────────────────────

    def select_preset_for_regime(self, regime: str) -> StrategyPreset:
        """
        根据市场状态选择最佳预设
        
        不同市场状态需要不同的参数:
          - 强趋势: 高权重趋势策略, 更紧的止损
          - 高波动: 低Kelly, 高盈亏比要求
          - 震荡: 均值回归为主, 低交易频率
        """
        if len(self.preset_pool) == 1:
            return self.active_preset
        
        # 查找在该regime下表现最好的预设
        best_preset = None
        best_score = -999
        
        for preset in self.preset_pool:
            perf = preset.performance
            # 综合评分: WFER + 胜率 + 盈亏比
            score = (
                perf.get("wfer", 0) * 3 +
                perf.get("win_rate", 0) * 2 +
                min(perf.get("profit_factor", 0) * 0.5, 2.0) -
                perf.get("max_drawdown", 0) * 0.1
            )
            
            if score > best_score:
                best_score = score
                best_preset = preset
        
        if best_preset and best_preset != self.active_preset:
            self.active_preset_idx = self.preset_pool.index(best_preset)
            print(f"[进化] 切换到预设 v{best_preset.version} (评分={best_score:.2f})")
        
        return self.active_preset

    def _prune_pool(self):
        """淘汰最差的预设 — 优胜劣汰"""
        scored = []
        for i, preset in enumerate(self.preset_pool):
            perf = preset.performance
            score = (
                perf.get("wfer", 0) * 3 +
                perf.get("win_rate", 0) * 2 +
                perf.get("profit_factor", 0) * 0.3 -
                perf.get("max_drawdown", 0) * 0.2
            )
            scored.append((i, score))
        
        # 保留top 5
        scored.sort(key=lambda x: x[1], reverse=True)
        keep_idx = [i for i, _ in scored[:5]]
        
        self.preset_pool = [self.preset_pool[i] for i in keep_idx]
        self.active_preset_idx = 0
        
        print(f"[进化] 策略池裁剪: 保留{len(self.preset_pool)}个最优预设")

    # ─── 持久化 ───────────────────────────

    def _save_evolution_log(self):
        """保存进化记录"""
        log_path = "E:/GoldstrategyEngine/logs/evolution.json"
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        
        data = {
            "evolution_count": len(self.evolution_history),
            "preset_pool_size": len(self.preset_pool),
            "active_preset_version": self.active_preset.version,
            "last_evolution": self.evolution_history[-1].timestamp.isoformat() if self.evolution_history else "",
            "history": [
                {
                    "timestamp": r.timestamp.isoformat(),
                    "trigger": r.trigger,
                    "accepted": r.accepted,
                    "old_wfer": r.old_wfer,
                    "new_wfer": r.new_wfer,
                    "changes": r.param_changes[:5],
                }
                for r in self.evolution_history[-20:]  # 最近20条
            ],
            "pool": [
                {
                    "version": p.version,
                    "win_rate": p.performance["win_rate"],
                    "wfer": p.performance["wfer"],
                    "total_profit": p.performance["total_profit"],
                }
                for p in self.preset_pool
            ],
        }
        
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_evolution_summary(self) -> str:
        """生成进化总结报告"""
        if not self.evolution_history:
            return "尚未有进化记录"
        
        accepted = sum(1 for r in self.evolution_history if r.accepted)
        total = len(self.evolution_history)
        
        lines = [
            f"🧬 自进化报告",
            f"  总进化次数: {total}",
            f"  接受次数: {accepted} ({(accepted/total*100):.0f}%)",
            f"  策略池大小: {len(self.preset_pool)}",
            f"  活跃预设: v{self.active_preset.version}",
            f"",
            f"  当前性能:",
            f"    胜率: {self.active_preset.performance['win_rate']:.1%}",
            f"    盈亏比: {self.active_preset.performance['profit_factor']:.2f}",
            f"    WFER: {self.active_preset.performance['wfer']:.3f}",
            f"    最大回撤: {self.active_preset.performance['max_drawdown']:.1f}%",
            f"",
        ]
        
        if self.evolution_history:
            last = self.evolution_history[-1]
            lines.extend([
                f"  最近进化:",
                f"    时间: {last.timestamp.strftime('%Y-%m-%d %H:%M')}",
                f"    触发: {last.trigger}",
                f"    接受: {'✅' if last.accepted else '❌'}",
            ])
        
        return "\n".join(lines)


# ═══════════════════════════════════════════
# 4. 完整自进化引擎集成
# ═══════════════════════════════════════════

class SelfEvolvingTrader:
    """
    自进化交易系统 — 完整集成
    
    工作流程:
      每笔交易 → 记录 → 更新统计 → 检查退化 → 
      需要时 → Walk-Forward优化 → 接受/拒绝 → 
      动态选择最佳参数
    """
    
    def __init__(self):
        self.evolution = SelfEvolutionManager()
        self.trade_count = 0
        
    def on_trade(self, trade_result: Dict):
        """每笔交易后调用"""
        self.trade_count += 1
        self.evolution.on_trade_completed(trade_result)
        
        # 打印进化摘要 (每10笔)
        if self.trade_count % 10 == 0:
            print(f"\n{self.evolution.get_evolution_summary()}")
    
    def get_adaptive_parameters(self, regime: str) -> StrategyPreset:
        """获取自适应参数"""
        return self.evolution.select_preset_for_regime(regime)
    
    def simulate_evolution(self, n_trades: int = 200):
        """
        模拟进化过程
        
        生成随机交易结果 → 观察自进化
        """
        print(f"\n{'='*60}")
        print(f"  🧬 自进化模拟: {n_trades}笔交易")
        print(f"{'='*60}")
        
        np.random.seed(42)
        
        base_win_rate = 0.55
        current_win_rate = base_win_rate
        
        for i in range(n_trades):
            # 模拟交易结果 (胜率逐渐下降模拟退化)
            if i > 50:
                current_win_rate = base_win_rate - (i / n_trades) * 0.15
            
            won = np.random.random() < current_win_rate
            profit = np.random.uniform(50, 200) if won else np.random.uniform(-150, -30)
            
            trade = {
                "profit": round(profit, 2),
                "entry": 2330 + np.random.uniform(-10, 10),
                "exit": 2330 + np.random.uniform(-15, 15),
                "direction": "BUY" if won else "SELL",
                "volume": 0.1,
                "regime": np.random.choice(["STRONG_TREND", "WEAK_TREND", "HIGH_VOLATILITY", "RANGING"]),
                "close_time": datetime.now() - timedelta(hours=n_trades - i),
                "reasoning": "模拟交易",
            }
            
            self.on_trade(trade)
        
        print(f"\n{'='*60}")
        print(f"  ✅ 模拟完成")
        print(f"{self.evolution.get_evolution_summary()}")
        print(f"{'='*60}")


# ═══════════════════════════════════════════
# 5. 启动入口
# ═══════════════════════════════════════════

if __name__ == "__main__":
    # 运行自进化模拟演示
    engine = SelfEvolvingTrader()
    engine.simulate_evolution(200)
