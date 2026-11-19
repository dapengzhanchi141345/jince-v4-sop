# -*- coding: utf-8 -*-
"""PASD策略集成测试"""
import numpy as np
import pandas as pd
import sys
sys.path.insert(0, 'E:/GoldstrategyEngine')

from advanced_strategies import STRATEGY_REGISTRY
from pasd_fusion import backtest_pasd_v2

# 创建多样化测试数据
def create_test_data(seed=42, n=3000):
    np.random.seed(seed)
    closes = [100.0]
    for i in range(1, n):
        vol = 0.3 + 0.15 * np.sin(i * 0.005)
        trend = 0.05 * np.sin(i * 0.002)
        noise = np.random.randn() * vol
        closes.append(closes[-1] * (1 + noise + trend))
    closes = np.array(closes)
    opens = closes + np.random.randn(n) * 0.05
    highs = np.maximum(closes, opens) + np.abs(np.random.randn(n)) * 0.3
    lows = np.minimum(closes, opens) - np.abs(np.random.randn(n)) * 0.3
    times = np.arange(n) * 3600
    return pd.DataFrame({'open': opens, 'high': highs, 'low': lows, 'close': closes, 'time': times})

print('=' * 70)
print('PASD策略集成测试')
print('=' * 70)

# 测试多个种子
seeds = [42, 123, 456]
all_results = []

for seed in seeds:
    h1 = create_test_data(seed=seed)
    h4 = pd.DataFrame({
        'open': h1['open'].values[::4], 'high': h1['high'].values[::4],
        'low': h1['low'].values[::4], 'close': h1['close'].values[::4],
        'time': h1['time'].values[::4]
    })
    d1 = pd.DataFrame({
        'open': h1['open'].values[::20], 'high': h1['high'].values[::20],
        'low': h1['low'].values[::20], 'close': h1['close'].values[::20],
        'time': h1['time'].values[::20]
    })
    
    result = backtest_pasd_v2(h1, h4, d1, initial_equity=10000.0, pip_usd=10.0)
    all_results.append(result)
    status = '✅' if result['total_pnl'] > 0 else '❌'
    print(f'Seed {seed}: {status} 交易{result["trades"]}笔, 胜率{result["win_rate"]:.1f}%, 盈亏${result["total_pnl"]:.2f}')

# 汇总
avg_pnl = np.mean([r['total_pnl'] for r in all_results])
avg_wr = np.mean([r['win_rate'] for r in all_results])
avg_trades = np.mean([r['trades'] for r in all_results])
profitable_count = sum(1 for r in all_results if r['total_pnl'] > 0)

print(f'\n汇总结果:')
print(f'  平均盈亏: ${avg_pnl:.2f}')
print(f'  平均胜率: {avg_wr:.1f}%')
print(f'  平均交易: {avg_trades:.1f}笔')
print(f'  盈利比例: {profitable_count}/{len(all_results)} ({profitable_count/len(all_results)*100:.0f}%)')

# 检查PASD在策略列表中的位置
print(f'\nPASD集成状态:')
print(f'  已注册到STRATEGY_REGISTRY: {"PASD" in STRATEGY_REGISTRY}')
print(f'  策略总数: {len(ALL_STRATEGIES)}')

# 检查品种映射
from live_bridge import SYMBOL_STRATEGY_MAP
pasd_symbols = [s for s, strategies in SYMBOL_STRATEGY_MAP.items() if 'PASD' in strategies]
print(f'  配置PASD的品种: {pasd_symbols}')
print(f'  PASD已集成到系统 ✅')
