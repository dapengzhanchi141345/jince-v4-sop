# -*- coding: utf-8 -*-
"""
Quick Evolution Demo - 快速进化演示
====================================
简单直接的进化演示，无需复杂依赖
"""

import sys
sys.path.insert(0, 'E:/GoldstrategyEngine')

import numpy as np
import pandas as pd
import json
import os
from datetime import datetime

def run_evolution_demo():
    """运行进化演示"""
    print('='*70)
    print('🚀 GoldstrategyEngine 主动进化演示')
    print('='*70)
    print()

    # 1. 加载策略
    print('[1/5] 加载V4策略...')
    from advanced_strategies_v4 import STRATEGY_REGISTRY_V4
    print(f'  ✅ 已加载 {len(STRATEGY_REGISTRY_V4)} 个策略')
    print()

    # 2. 生成测试数据
    print('[2/5] 生成测试数据 (多种市场模式)...')
    seeds = [42, 123, 456, 789, 1024]
    data_cache = {}
    for seed in seeds:
        np.random.seed(seed)
        n = 2000
        closes = [100.0]
        for i in range(1, n):
            trend = 0.01 * np.sin(i * 0.002) + 0.005 * np.random.randn()
            closes.append(closes[-1] * (1 + trend * 0.01))
        closes = np.array(closes)
        opens = closes + np.random.randn(n) * 0.05
        highs = np.maximum(closes, opens) + np.abs(np.random.randn(n)) * 0.2
        lows = np.minimum(closes, opens) - np.abs(np.random.randn(n)) * 0.2
        h1 = pd.DataFrame({'open': opens, 'high': highs, 'low': lows, 'close': closes})
        h4 = h1.iloc[::4].copy()
        d1 = h1.iloc[::20].copy()
        data_cache[seed] = (h1, h4, d1)
    print(f'  ✅ 生成 {len(seeds)} 组测试数据')
    print()

    # 3. 基准回测
    print('[3/5] 基准回测 (V4当前参数)...')
    cfg = {'pip': 0.01, 'lot': 0.1}
    baseline = {}
    for seed in seeds:
        h1, h4, d1 = data_cache[seed]
        seed_results = {}
        for name in ['SDP', 'ICT', 'BO', 'TREND']:
            try:
                sigs = STRATEGY_REGISTRY_V4[name](h1, h4, d1, cfg)
                seed_results[name] = len(sigs)
            except:
                seed_results[name] = 0
        baseline[seed] = seed_results

    # 计算平均值
    avg_baseline = {}
    for name in ['SDP', 'ICT', 'BO', 'TREND']:
        avg = np.mean([baseline[s].get(name, 0) for s in seeds])
        avg_baseline[name] = avg
        print(f'  {name}: {avg:.0f} 信号 (平均)')
    print()

    # 4. 参数优化
    print('[4/5] 参数优化 (简化版网格搜索)...')
    best_params = {}
    improved = {}

    for strategy in ['SDP', 'ICT', 'BO', 'TREND']:
        best_score = -999
        best_p = {}

        # 简化参数空间
        if strategy == 'SDP':
            param_grid = [
                {'adx_min': 15},
                {'adx_min': 20},
                {'adx_min': 25},
                {'sl_mult': 1.2},
                {'sl_mult': 1.5},
                {'sl_mult': 2.0},
            ]
        elif strategy == 'ICT':
            param_grid = [
                {'disp_threshold': 0.005},
                {'disp_threshold': 0.01},
                {'disp_threshold': 0.02},
            ]
        elif strategy == 'BO':
            param_grid = [
                {'lookback': 10},
                {'lookback': 15},
                {'lookback': 20},
                {'confirm_bars': 1},
                {'confirm_bars': 2},
            ]
        else:  # TREND
            param_grid = [
                {'ema_fast': 10},
                {'ema_fast': 20},
                {'ema_fast': 30},
                {'adx_min': 15},
                {'adx_min': 20},
            ]

        for params in param_grid:
            test_cfg = {**cfg, **params}
            total_sigs = 0
            for seed in seeds:
                h1, h4, d1 = data_cache[seed]
                try:
                    sigs = STRATEGY_REGISTRY_V4[strategy](h1, h4, d1, test_cfg)
                    total_sigs += len(sigs)
                except:
                    pass

            # 评分: 信号数量适中 (100-500) 且稳定
            if 100 <= total_sigs / len(seeds) <= 500:
                score = total_sigs / len(seeds)
            else:
                score = total_sigs / len(seeds) * 0.5  # 惩罚过于极端

            if score > best_score:
                best_score = score
                best_p = params

        best_params[strategy] = best_p
        baseline_count = avg_baseline[strategy]
        test_cfg = {**cfg, **best_p}
        improved_count = np.mean([
            len(STRATEGY_REGISTRY_V4[strategy](data_cache[s][0], data_cache[s][1], data_cache[s][2], test_cfg))
            for s in seeds
        ])
        improved[strategy] = {
            'baseline': baseline_count,
            'optimized': improved_count,
            'params': best_p,
            'change': improved_count - baseline_count,
        }
        print(f'  {strategy}: {baseline_count:.0f} → {improved_count:.0f} ({improved[strategy]["change"]:+.0f})')
        if best_p:
            print(f'    最优参数: {best_p}')

    print()

    # 5. 保存结果
    print('[5/5] 保存进化结果...')
    output_dir = 'E:/GoldstrategyEngine/evolution'
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    result = {
        'timestamp': timestamp,
        'baseline': avg_baseline,
        'improved': improved,
        'best_params': best_params,
    }

    filename = f'{output_dir}/evolution_{timestamp}.json'
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f'  ✅ 已保存: {filename}')
    print()

    # 总结
    print('='*70)
    print('🎉 进化完成')
    print('='*70)
    print()
    print('改进总结:')
    for strategy in ['SDP', 'ICT', 'BO', 'TREND']:
        imp = improved[strategy]
        status = '✅' if imp['change'] > 0 else '⚠️'
        print(f'  {status} {strategy}: {imp["baseline"]:.0f} → {imp["optimized"]:.0f} ({imp["change"]:+.0f})')

    print()
    print(f'📁 日志目录: {output_dir}/')
    print('='*70)

    return result


if __name__ == '__main__':
    result = run_evolution_demo()
    print()
    print('✅ 主动进化演示完成')
