# -*- coding: utf-8 -*-
"""
OTAS策略回测验证脚本
"""
import numpy as np
import pandas as pd
import sys
sys.path.insert(0, 'E:/GoldstrategyEngine')

from otas_strategy import gen_otas, backtest_otas

def create_test_data(seed=42, n=2000):
    """创建多样化测试数据"""
    np.random.seed(seed)
    closes = [100.0]
    for i in range(1, n):
        # 模拟趋势+波动率聚类
        trend = 0.01 * np.sin(i * 0.005)
        vol = 0.3 + 0.15 * np.sin(i * 0.01) * np.abs(np.random.randn())
        noise = np.random.randn() * vol * 0.01
        closes.append(closes[-1] * (1 + trend + noise))
    closes = np.array(closes)
    opens = closes + np.random.randn(n) * 0.001
    highs = np.maximum(closes, opens) + np.abs(np.random.randn(n)) * 0.003
    lows = np.minimum(closes, opens) - np.abs(np.random.randn(n)) * 0.003
    times = np.arange(n) * 3600
    return pd.DataFrame({'open': opens, 'high': highs, 'low': lows, 'close': closes, 'time': times})

print('=' * 70)
print('OTAS 一次一单策略 - 回测验证')
print('=' * 70)

# 测试多个种子
seeds = [42, 123, 456, 789, 1024]
results = []

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
    
    result = backtest_otas(h1, h4, d1, initial_equity=10000.0, pip_usd=10.0)
    results.append(result)
    status = '✅' if result['total_pnl'] > 0 else '❌'
    print(f'Seed {seed}: {status} 交易{result["trades"]}笔, 胜率{result["win_rate"]:.1f}%, 盈亏${result["total_pnl"]:.2f}, PF:{result["profit_factor"]:.2f}')

# 汇总
print(f'\n汇总结果:')
avg_pnl = np.mean([r['total_pnl'] for r in results])
avg_wr = np.mean([r['win_rate'] for r in results])
avg_trades = np.mean([r['trades'] for r in results])
avg_pf = np.mean([r['profit_factor'] for r in results if r['profit_factor'] != float('inf') and r['profit_factor'] < 100])
profitable_count = sum(1 for r in results if r['total_pnl'] > 0)

print(f'  平均盈亏: ${avg_pnl:.2f}')
print(f'  平均胜率: {avg_wr:.1f}%')
print(f'  平均交易: {avg_trades:.1f}笔')
print(f'  平均PF: {avg_pf:.2f}')
print(f'  盈利比例: {profitable_count}/{len(results)} ({profitable_count/len(results)*100:.0f}%)')

print(f'\n结论: {"✅ OTAS策略稳定盈利" if avg_pnl > 0 and profitable_count > len(results)/2 else "❌ OTAS策略不稳定"}')
print('=' * 70)
