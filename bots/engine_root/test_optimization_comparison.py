# -*- coding: utf-8 -*-
"""
策略优化对比回测 — V1.0 vs V2.0/V3.0
=======================================
对比测试各策略升级前后的回测表现
"""

import numpy as np
import pandas as pd
import sys
import os

# 添加路径
sys.path.insert(0, 'E:/GoldstrategyEngine')

from otas_strategy import gen_otas as gen_otas_v1, backtest_otas as backtest_otas_v1
from otas_strategy_v2 import gen_otas as gen_otas_v2, backtest_otas_v2
from pasd_fusion_v3 import gen_pasd as gen_pasd_v3, backtest_pasd_v3
from advanced_strategies import gen_sdp, gen_trend, gen_breakout, gen_divergence


def generate_test_data(seed=42, n_bars=1000):
    """生成测试数据"""
    np.random.seed(seed)
    n = n_bars
    closes = [100.0]
    for i in range(1, n):
        trend = 0.02 * np.sin(i * 0.01)
        noise = np.random.randn() * 0.3
        closes.append(closes[-1] * (1 + trend + noise * 0.01))
    closes = np.array(closes)
    opens = closes + np.random.randn(n) * 0.05
    highs = np.maximum(closes, opens) + np.abs(np.random.randn(n)) * 0.2
    lows = np.minimum(closes, opens) - np.abs(np.random.randn(n)) * 0.2
    times = np.arange(n) * 3600

    h1 = pd.DataFrame({'open': opens, 'high': highs, 'low': lows, 'close': closes, 'time': times})
    h4 = pd.DataFrame({'open': opens[::4], 'high': highs[::4], 'low': lows[::4], 'close': closes[::4], 'time': times[::4]})
    d1 = pd.DataFrame({'open': opens[::20], 'high': highs[::20], 'low': lows[::20], 'close': closes[::20], 'time': times[::20]})

    return h1, h4, d1


def run_comparison(h1, h4, d1, cfg):
    """运行对比测试"""
    print("=" * 80)
    print("策略优化对比回测报告")
    print("=" * 80)

    results = {}

    # ── OTAS V1.0 vs V2.0 ──
    print("\n【OTAS 一次一单策略】")
    print("-" * 60)

    sigs_v1 = gen_otas_v1(h1, h4, d1, cfg)
    result_v1 = backtest_otas_v1(h1, h4, d1, initial_equity=10000.0, pip_usd=10.0)

    sigs_v2 = gen_otas_v2(h1, h4, d1, cfg)
    result_v2 = backtest_otas_v2(h1, h4, d1, initial_equity=10000.0, pip_usd=10.0)

    # 统一键名
    pf_v1 = result_v1.get('profit_factor', 0)
    pf_v2 = result_v2.get('profit_factor', 0)
    pnl_v1 = result_v1.get('total_pnl', 0)
    pnl_v2 = result_v2.get('total_pnl', 0)
    wr_v1 = result_v1.get('win_rate', 0)
    wr_v2 = result_v2.get('win_rate', 0)

    print(f"V1.0 | 信号: {result_v1['signals']:3d} | 交易: {result_v1['trades']:3d} | 胜率: {wr_v1:5.1f}% | PF: {pf_v1:5.2f} | 盈亏: ${pnl_v1:8.2f}")
    print(f"V2.0 | 信号: {result_v2['signals']:3d} | 交易: {result_v2['trades']:3d} | 胜率: {wr_v2:5.1f}% | PF: {pf_v2:5.2f} | 盈亏: ${pnl_v2:8.2f}")
    print(f"改进 | 信号: {result_v2['signals']-result_v1['signals']:+3d} | 交易: {result_v2['trades']-result_v1['trades']:+3d} | 胜率: {wr_v2-wr_v1:+5.1f}% | PF: {pf_v2-pf_v1:+5.2f} | 盈亏: ${pnl_v2-pnl_v1:+8.2f}")

    results['OTAS'] = {'v1': result_v1, 'v2': result_v2}

    # ── PASD V2.0 vs V3.0 ──
    print("\n【PASD 价格行为+供需融合策略】")
    print("-" * 60)

    try:
        from pasd_fusion import backtest_pasd_v2
        sigs_v2_orig = __import__('pasd_fusion', fromlist=['gen_pasd']).gen_pasd(h1, h4, d1, cfg)
        result_v2_orig = backtest_pasd_v2(h1, h4, d1, initial_equity=10000.0, pip_usd=10.0)

        sigs_v3 = gen_pasd_v3(h1, h4, d1, cfg)
        result_v3 = backtest_pasd_v3(h1, h4, d1, initial_equity=10000.0, pip_usd=10.0)

        print(f"V2.0 | 信号: {result_v2_orig['signals']:3d} | 交易: {result_v2_orig['trades']:3d} | 胜率: {result_v2_orig['win_rate']:5.1f}% | PF: {result_v2_orig.get('profit_factor', 0):5.2f} | 盈亏: ${result_v2_orig['total_pnl']:8.2f}")
        print(f"V3.0 | 信号: {result_v3['signals']:3d} | 交易: {result_v3['trades']:3d} | 胜率: {result_v3['win_rate']:5.1f}% | PF: {result_v3['profit_factor']:5.2f} | 盈亏: ${result_v3['total_pnl']:8.2f}")
        print(f"改进 | 信号: {result_v3['signals']-result_v2_orig['signals']:+3d} | 交易: {result_v3['trades']-result_v2_orig['trades']:+3d} | 胜率: {result_v3['win_rate']-result_v2_orig['win_rate']:+5.1f}% | PF: {result_v3['profit_factor']-result_v2_orig.get('profit_factor', 0):+5.2f} | 盈亏: ${result_v3['total_pnl']-result_v2_orig['total_pnl']:+8.2f}")

        results['PASD'] = {'v2': result_v2_orig, 'v3': result_v3}
    except Exception as e:
        print(f"PASD V3.0测试失败: {e}")

    # ── 其他策略基准 ──
    print("\n【其他策略基准回测】")
    print("-" * 60)

    for name, gen_func in [('SDP', gen_sdp), ('TREND', gen_trend), ('BO', gen_breakout), ('DIV', gen_divergence)]:
        try:
            sigs = gen_func(h1, h4, d1, cfg)
            print(f"{name:8s} | 信号数: {len(sigs):4d}")
        except Exception as e:
            print(f"{name:8s} | 错误: {e}")

    return results


if __name__ == "__main__":
    cfg = {'pip': 0.01, 'lot': 0.1, 'adx_min': 20, 'sl_mult': 1.5, 'rr_mult': 3.0}

    # 多种子测试
    all_results = {}
    for seed in [42, 123, 456, 789, 1024]:
        print(f"\n{'='*80}")
        print(f"种子: {seed}")
        print('='*80)

        h1, h4, d1 = generate_test_data(seed=seed)
        results = run_comparison(h1, h4, d1, cfg)
        all_results[seed] = results

    # 汇总报告
    print("\n" + "=" * 80)
    print("汇总对比报告 (5个种子平均)")
    print("=" * 80)

    print("\n【OTAS 平均表现】")
    print(f"{'种子':<8} {'版本':<6} {'信号':<6} {'交易':<6} {'胜率':<8} {'PF':<8} {'盈亏':<10}")
    print("-" * 60)
    for seed, results in all_results.items():
        if 'OTAS' in results:
            v1 = results['OTAS']['v1']
            v2 = results['OTAS']['v2']
            print(f"{seed:<8} V1.0 {v1['signals']:<6} {v1['trades']:<6} {v1.get('win_rate',0):<8.1f} {v1.get('profit_factor',0):<8.2f} ${v1.get('total_pnl',0):<9.2f}")
            print(f"{seed:<8} V2.0 {v2['signals']:<6} {v2['trades']:<6} {v2.get('win_rate',0):<8.1f} {v2.get('profit_factor',0):<8.2f} ${v2.get('total_pnl',0):<9.2f}")

    print("\n" + "=" * 80)
    print("✅ 策略优化对比回测完成")
    print("=" * 80)
