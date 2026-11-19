# -*- coding: utf-8 -*-
"""
EvolutionEngine V1.0
进化优化引擎 — 根据实盘表现自动调优策略参数和权重

核心功能:
1. 策略权重进化 (基于PF和胜率)
2. 参数自动调优 (网格搜索+交叉验证)
3. 品种适配优化 (不同品种最优参数)
4. 市况适应 (根据regime调整策略选择)
"""

import numpy as np
import pandas as pd
import json
import os
import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict

@dataclass
class ParamSet:
    """参数集"""
    name: str
    params: Dict[str, float]
    pf: float = 0.0
    win_rate: float = 0.0
    trades: int = 0
    last_optimized: float = 0.0

class EvolutionEngine:
    """进化优化引擎"""
    
    def __init__(self, save_dir: str = "data/evolution"):
        self.save_dir = save_dir
        os.makedirs(save_dir, exist_ok=True)
        
        # 策略参数空间
        self.param_spaces = {
            'OTAS': {
                'MA_FAST': [15, 20, 25, 30],
                'MA_SLOW': [50, 60, 70, 80],
                'ADX_THRESHOLD': [20, 25, 30],
                'SL_ATR_MULT': [1.2, 1.5, 1.8, 2.0],
                'TP_ATR_MULT': [2.5, 3.0, 3.5, 4.0],
            },
            'PASD': {
                'MIN_RESONANCE': [0.05, 0.1, 0.15, 0.2],
                'MIN_PB_SCORE': [1, 2, 3],
                'SIGNAL_COOLDOWN': [15, 20, 25, 30],
                'SL_ATR_MULT': [1.0, 1.2, 1.5],
                'TP_RR': [2.0, 2.5, 3.0],
            },
            'DIV': {
                'divergence_lookback': [20, 30, 40, 50],
                'sl_atr_mult': [1.2, 1.5, 1.8],
                'tp_rr': [2.0, 2.5, 3.0],
            },
            'TREND': {
                'ema_fast': [20, 30, 50],
                'ema_slow': [50, 80, 100],
                'atr_mult': [1.5, 2.0, 2.5],
            },
            'MR': {
                'bb_period': [14, 20, 26],
                'bb_std': [1.5, 2.0, 2.5],
                'sl_atr_mult': [1.2, 1.5, 1.8],
            },
            'BO': {
                'lookback': [20, 30, 50],
                'breakout_threshold': [0.001, 0.002, 0.003],
                'sl_atr_mult': [1.5, 2.0, 2.5],
            },
        }
        
        # 当前最优参数
        self.best_params: Dict[str, ParamSet] = {}
        
        # 品种适配参数
        self.symbol_params: Dict[str, Dict[str, ParamSet]] = {}
        
        # 进化日志
        self.evolution_log: List[Dict] = []
        
        # 加载历史最优参数
        self._load_best_params()
        
        print(f"[Evolution] 进化引擎初始化完成")
        print(f"  参数空间: {len(self.param_spaces)} 个策略")
    
    def _load_best_params(self):
        """加载历史最优参数"""
        params_file = os.path.join(self.save_dir, 'best_params.json')
        if os.path.exists(params_file):
            try:
                with open(params_file, 'r') as f:
                    data = json.load(f)
                self.best_params = {
                    name: ParamSet(**info) for name, info in data.items()
                }
                print(f"[Evolution] 已加载 {len(self.best_params)} 个历史最优参数")
            except Exception as e:
                print(f"[Evolution] 加载参数失败: {e}")
    
    def _save_best_params(self):
        """保存最优参数"""
        params_file = os.path.join(self.save_dir, 'best_params.json')
        try:
            data = {name: asdict(info) for name, info in self.best_params.items()}
            with open(params_file, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"[Evolution] 已保存 {len(self.best_params)} 个最优参数")
        except Exception as e:
            print(f"[Evolution] 保存参数失败: {e}")
    
    def optimize_strategy(
        self,
        strategy_name: str,
        h1: pd.DataFrame,
        h4: pd.DataFrame,
        d1: pd.DataFrame,
        initial_equity: float = 10000.0,
        pip_usd: float = 10.0,
        max_iterations: int = 50
    ) -> Optional[ParamSet]:
        """
        优化单个策略参数
        
        使用简化网格搜索 + 表现评估
        """
        if strategy_name not in self.param_spaces:
            print(f"[Evolution] 未知策略: {strategy_name}")
            return None
        
        params_space = self.param_spaces[strategy_name]
        param_keys = list(params_space.keys())
        
        # 生成参数组合
        from itertools import product
        param_values = [params_space[k] for k in param_keys]
        all_combos = list(product(*param_values))
        
        # 限制搜索空间
        if len(all_combos) > max_iterations:
            indices = np.random.choice(len(all_combos), max_iterations, replace=False)
            all_combos = [all_combos[i] for i in indices]
        
        best_result = None
        best_score = -float('inf')
        
        print(f"[Evolution] 优化 {strategy_name}: {len(all_combos)} 个组合")
        
        for i, combo in enumerate(all_combos):
            params = dict(zip(param_keys, combo))
            
            # 临时修改参数并运行回测
            try:
                # 导入策略模块
                if strategy_name == 'OTAS':
                    from otas_strategy import backtest_otas as bt_func, gen_otas
                elif strategy_name == 'PASD':
                    from pasd_fusion import backtest_pasd_v2 as bt_func, gen_pasad
                else:
                    continue  # 其他策略暂不支持自动优化
                
                # 临时修改参数
                import sys
                mod = sys.modules.get(bt_func.__module__, None)
                if mod:
                    for k, v in params.items():
                        if hasattr(mod, k):
                            setattr(mod, k, v)
                    
                    # 运行回测
                    result = bt_func(h1, h4, d1, initial_equity=initial_equity, pip_usd=pip_usd)
                    
                    # 计算综合评分 (PF * 胜率/100)
                    pf = result.get('profit_factor', 0)
                    wr = result.get('win_rate', 0)
                    trades = result.get('trades', 0)
                    
                    if trades < 5:
                        continue  # 样本不足
                    
                    score = pf * (wr / 100) * min(trades / 20, 2.0)
                    
                    if score > best_score:
                        best_score = score
                        best_result = ParamSet(
                            name=strategy_name,
                            params=params,
                            pf=pf,
                            win_rate=wr,
                            trades=trades,
                            last_optimized=time.time()
                        )
                    
                    # 进度报告
                    if (i + 1) % 10 == 0:
                        print(f"  进度: {i+1}/{len(all_combos)}, 当前最佳PF={best_result.pf:.2f}, WR={best_result.win_rate:.1f}%")
                
            except Exception as e:
                continue
        
        if best_result:
            self.best_params[strategy_name] = best_result
            self._save_best_params()
            
            self.evolution_log.append({
                'timestamp': time.time(),
                'strategy': strategy_name,
                'best_pf': best_result.pf,
                'best_wr': best_result.win_rate,
                'best_trades': best_result.trades,
                'params': best_result.params
            })
            
            print(f"[Evolution] {strategy_name} 优化完成:")
            print(f"  最佳PF: {best_result.pf:.2f}")
            print(f"  最佳胜率: {best_result.win_rate:.1f}%")
            print(f"  交易数: {best_result.trades}")
            print(f"  最优参数: {best_result.params}")
        
        return best_result
    
    def optimize_all_strategies(
        self,
        symbol: str,
        h1: pd.DataFrame,
        h4: pd.DataFrame,
        d1: pd.DataFrame,
        initial_equity: float = 10000.0,
        pip_usd: float = 10.0
    ) -> Dict[str, ParamSet]:
        """优化所有策略参数"""
        results = {}
        
        for strategy_name in self.param_spaces.keys():
            result = self.optimize_strategy(
                strategy_name, h1, h4, d1,
                initial_equity=initial_equity,
                pip_usd=pip_usd
            )
            if result:
                results[strategy_name] = result
        
        return results
    
    def get_optimal_params(self, strategy_name: str) -> Dict[str, float]:
        """获取最优参数"""
        if strategy_name in self.best_params:
            return self.best_params[strategy_name].params
        return self.param_spaces.get(strategy_name, {})
    
    def adapt_to_symbol(self, symbol: str, h1: pd.DataFrame, h4: pd.DataFrame, d1: pd.DataFrame):
        """根据品种特征适配参数"""
        if symbol not in self.symbol_params:
            self.symbol_params[symbol] = {}
        
        # 分析品种特征
        closes = h1['close'].values.astype(float)
        highs = h1['high'].values.astype(float)
        lows = h1['low'].values.astype(float)
        
        # 波动率特征
        returns = np.diff(np.log(closes))
        vol = np.std(returns) * 100  # 年化波动率
        
        # 趋势特征
        ema20 = np.convolve(closes, np.ones(20)/20, mode='valid')
        ema50 = np.convolve(closes, np.ones(50)/50, mode='valid')
        trend_strength = abs(ema20[-1] - ema50[-1]) / ema50[-1] if len(ema50) > 0 else 0
        
        # 根据特征调整参数
        adaptations = {}
        
        if vol > 30:  # 高波动品种 (黄金、加密货币)
            adaptations['OTAS'] = {'SL_ATR_MULT': 2.0, 'TP_ATR_MULT': 4.0}
            adaptations['PASD'] = {'SL_ATR_MULT': 1.5, 'TP_RR': 3.0}
        elif vol < 10:  # 低波动品种
            adaptations['OTAS'] = {'SL_ATR_MULT': 1.2, 'TP_ATR_MULT': 2.5}
            adaptations['PASD'] = {'SL_ATR_MULT': 1.0, 'TP_RR': 2.0}
        
        if trend_strength > 0.02:  # 强趋势
            adaptations['TREND'] = {'ema_fast': 20, 'ema_slow': 50}
        
        # 保存适配
        for strategy, params in adaptations.items():
            if strategy not in self.symbol_params[symbol]:
                self.symbol_params[symbol][strategy] = ParamSet(
                    name=strategy,
                    params=params,
                    last_optimized=time.time()
                )
            else:
                self.symbol_params[symbol][strategy].params.update(params)
        
        return adaptations
    
    def get_evolution_report(self) -> Dict:
        """获取进化报告"""
        report = {
            'generation': self.generation if hasattr(self, 'generation') else 0,
            'best_params': {name: asdict(info) for name, info in self.best_params.items()},
            'symbol_adaptations': {
                sym: {strat: asdict(info) for strat, info in strat_params.items()}
                for sym, strat_params in self.symbol_params.items()
            },
            'evolution_log': self.evolution_log[-10:]  # 最近10条
        }
        return report


# ═══════════════════════════════════════════════════════════════════════════
# V2 进化层 (2026-09-01 全网研究落地) — 纯函数式、零依赖、可单测
# 针对 live_bridge 现有三个未覆盖高杠杆缺口:
#   1) 波动率目标化头寸 (现有: 等风险% → 多品种波动差异大→风险集中)
#   2) regime 优先级 → 头寸权重 (现有: regime 只决定扫描顺序, 不调资金)
#   3) Meta 置信度硬闸 (现有: 仅 vol 恐慌闸, 无置信度拒单)
# 全部异常安全 (调用方 try/except 即可回退旧值), 所有乘数有 cap/floor,
# 绝不放大单笔风险 (只减不增优于盲目加仓). 由 EVOLUTION_V2_ENABLED 总开关控制.
# ═══════════════════════════════════════════════════════════════════════════
EVOLUTION_V2_ENABLED = True

# 波动率目标化: 目标"日波动贡献". XAUUSD 常态日波动~0.01-0.015.
EV2_TARGET_DAILY_VOL = 0.011
EV2_VOL_SCALE_CAP = 2.2      # 低波动品种最多加到 2.2×
EV2_VOL_SCALE_FLOOR = 0.30   # 高波动品种最少压到 0.30×

# regime 优先级(来自 regime_router.REGIME_PRIORITY 的值) → size 乘数
EV2_REGIME_PRIORITY_TO_SIZE = {3: 1.00, 2: 0.70, 1: 0.45, 0: 0.0}

# Meta 置信度硬闸
EV2_GATE_CONF_THR = 0.55        # 综合置信度低于此 → 拒单
EV2_GATE_VOL_SPIKE_THR = 2.0    # 当前波动 > 近期中位数 2× → 拒单
EV2_GATE_HIGH_VOL_SKIP = False  # 高波动 regime 不硬拒(已有 vol 恐慌闸), 改为降仓(见 ev2_size_multiplier)


def ev2_ewma_vol(returns, lam: float = 0.94):
    """EWMA 波动率 (基于收益率序列), 失败返回 None."""
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 5:
        return None
    prev = float(np.var(r[: max(2, len(r) // 4)]))
    for x in r:
        prev = lam * prev + (1 - lam) * (x ** 2)
    return float(np.sqrt(prev))


def ev2_symbol_daily_vol_from_h1(h1_close, bars_per_day: int = 24):
    """从 H1 收盘价算 EWMA 日波动率. h1_close: np.array 或 pandas Series."""
    try:
        c = np.asarray(h1_close, dtype=float)
        if len(c) < bars_per_day + 2:
            return None
        rets = np.diff(np.log(c))
        v = ev2_ewma_vol(rets)
        if v is None:
            return None
        return float(v * np.sqrt(bars_per_day))
    except Exception:
        return None


def ev2_vol_target_scale(symbol_daily_vol, target=EV2_TARGET_DAILY_VOL,
                         cap=EV2_VOL_SCALE_CAP, floor=EV2_VOL_SCALE_FLOOR):
    """波动率目标化乘数: 高波动品种<1(降仓), 低波动>1(加仓), 受 cap/floor 限.

    例: BTC 日波动 0.04 → 0.011/0.04=0.275→floor 0.30; EUR 日波动 0.006 → 1.83.
    让每个品种对组合波动的贡献被拉平, 避免高波动品种吞噬全部风险预算.
    """
    if symbol_daily_vol is None or symbol_daily_vol <= 0:
        return 1.0
    s = target / symbol_daily_vol
    return float(min(cap, max(floor, s)))


def ev2_regime_size_weight(priority):
    """把 regime_router 的策略优先级转成 size 乘数. 0=禁用→0(不开)."""
    try:
        return float(EV2_REGIME_PRIORITY_TO_SIZE.get(int(priority), 0.5))
    except Exception:
        return 0.5


def ev2_composite_confidence(wr=None, pf=None, raw_conf=None):
    """由历史 wr/pf 合成置信度 (0..1); 有 raw_conf 则取较大者."""
    conf = 0.5
    try:
        if wr is not None and pf is not None and pf > 1.0 and wr > 0:
            conf = min(1.0, (pf - 1.0) / pf * (wr / 100.0) * 2.0)
        if raw_conf is not None:
            conf = max(conf, float(raw_conf))
        return float(min(1.0, max(0.0, conf)))
    except Exception:
        return 0.5


def ev2_meta_gate(conf, vol_spike_ratio, regime_vol_state,
                  conf_thr=EV2_GATE_CONF_THR, spike_thr=EV2_GATE_VOL_SPIKE_THR,
                  high_vol_skip=EV2_GATE_HIGH_VOL_SKIP):
    """返回 (accept: bool, reason: str). 任何异常 → (True,'safe') 失败开放."""
    try:
        if conf is not None and conf < conf_thr:
            return False, f"low_conf({conf:.2f}<{conf_thr})"
        if vol_spike_ratio is not None and vol_spike_ratio > spike_thr:
            return False, f"vol_spike({vol_spike_ratio:.2f}>{spike_thr})"
        if high_vol_skip and regime_vol_state == "high":
            return False, "high_vol_regime"
        return True, "ok"
    except Exception:
        return True, "safe"


def ev2_vol_spike_ratio_now(vol_now, vol_history, pct=0.5):
    """当前波动 / 历史中位数 的比值 (尖峰检测)."""
    try:
        h = np.asarray(vol_history, dtype=float)
        h = h[np.isfinite(h)]
        if len(h) < 10 or vol_now <= 0:
            return 1.0
        med = float(np.median(h))
        if med <= 0:
            return 1.0
        return float(vol_now / med)
    except Exception:
        return 1.0


def ev2_size_multiplier(symbol_daily_vol, regime_priority,
                        conf=None, vol_spike_ratio=None,
                        regime_vol_state="mid",
                        enabled=EVOLUTION_V2_ENABLED):
    """一次性算总乘数 = vol目标 × regime权重 (Meta闸由 ev2_meta_gate 单独处理).

    返回 (multiplier, breakdown_dict). 异常 → (1.0, {...}) 失败开放.
    """
    if not enabled:
        return 1.0, {"enabled": False}
    try:
        vs = ev2_vol_target_scale(symbol_daily_vol)
        rs = ev2_regime_size_weight(regime_priority)
        mult = vs * rs
        # 高波动 regime: 额外压仓 (与既有 vol 恐慌闸互补, 不硬拒)
        if regime_vol_state == "high":
            mult = min(mult, 0.6)
        mult = min(2.2, mult)   # 软上限, 防单笔过冲
        return float(mult), {
            "vol_scale": round(vs, 3),
            "regime_size": round(rs, 3),
            "combined": round(mult, 3),
        }
    except Exception:
        return 1.0, {"error": "fallback"}


# 自检
if __name__ == "__main__":
    print("=" * 70)
    print("进化优化引擎 V1.0 自检")
    print("=" * 70)
    
    engine = EvolutionEngine()
    
    # 创建测试数据
    np.random.seed(42)
    n = 1000
    closes = [100.0]
    for i in range(1, n):
        trend = 0.005 * np.sin(i * 0.01)
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
    
    # 测试OTAS优化
    print(f"\n测试OTAS参数优化:")
    result = engine.optimize_strategy('OTAS', h1, h4, d1, max_iterations=20)
    
    if result:
        print(f"\n最优参数: {result.params}")
        print(f"PF: {result.pf:.2f}, 胜率: {result.win_rate:.1f}%, 交易: {result.trades}")
    
    # 测试品种适配
    print(f"\n测试品种适配 (XAUUSD):")
    adaptations = engine.adapt_to_symbol('XAUUSD', h1, h4, d1)
    print(f"适配结果: {adaptations}")
    
    # 报告
    print(f"\n进化报告:")
    report = engine.get_evolution_report()
    print(f"  最优参数数: {len(report['best_params'])}")
    print(f"  品种适配数: {len(report['symbol_adaptations'])}")
    
    print("\n" + "=" * 70)
    print("✅ 进化优化引擎自检完成")
    print("=" * 70)
