# -*- coding: utf-8 -*-
"""PASD V2.0 完整回测验证"""

import numpy as np
import pandas as pd
import sys, os
from datetime import datetime

sys.path.insert(0, '.')
from pasd_fusion_v2 import gen_pasd, backtest_pasd_v2, _detect_trend

print("=" * 60)
print("PASD V2.0 回测验证")
print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# ── 生成多样化市场数据 ──
def generate_data(n=1500, seed=42):
    """生成包含趋势+震荡+反转的模拟数据"""
    np.random.seed(seed)
    t = np.arange(n)

    # 多趋势段: 涨→震荡→跌→涨
    segments = []
    pos = 0
    prices = [100.0]
    for i in range(n):
        if i < 300:
            # 上涨趋势
            prices.append(prices[-1] + np.random.randn() * 0.3 + 0.15)
        elif i < 600:
            # 震荡
            prices.append(prices[-1] + np.random.randn() * 0.4)
        elif i < 900:
            # 下跌趋势
            prices.append(prices[-1] + np.random.randn() * 0.3 - 0.12)
        elif i < 1200:
            # 震荡
            prices.append(prices[-1] + np.random.randn() * 0.35)
        else:
            # 上涨趋势
            prices.append(prices[-1] + np.random.randn() * 0.25 + 0.1)

    closes = np.array(prices[1:])
    opens = closes + np.random.randn(n) * 0.15
    highs = np.maximum(closes, opens) + np.abs(np.random.randn(n)) * 0.5
    lows = np.minimum(closes, opens) - np.abs(np.random.randn(n)) * 0.5
    times = np.arange(n) * 3600 + int(datetime(2026, 1, 1).timestamp())

    h1 = pd.DataFrame({'open': opens, 'high': highs, 'low': lows, 'close': closes, 'time': times})

    h4_c = closes[::4]; h4_h = np.maximum(highs[::4], np.maximum(highs[1::4], highs[2::4]))
    h4_l = np.minimum(lows[::4], np.minimum(lows[1::4], lows[2::4]))
    h4_o = opens[::4]
    h4 = pd.DataFrame({'open': h4_o, 'high': h4_h, 'low': h4_l, 'close': h4_c, 'time': times[::4]})

    d1_c = closes[::24]; d1_h = np.maximum(highs[::24], np.maximum(highs[1::24], highs[2::24]))
    d1_l = np.minimum(lows[::24], np.minimum(lows[1::24], lows[2::24]))
    d1_o = opens[::24]
    d1 = pd.DataFrame({'open': d1_o, 'high': d1_h, 'low': d1_l, 'close': d1_c, 'time': times[::24]})

    return h1, h4, d1


# ── 测试不同市场环境 ──
print("\n" + "=" * 60)
print("测试1: 多样化市场数据 (涨-震-跌-震-涨)")
print("=" * 60)

h1, h4, d1 = generate_data(1500)
cfg = {'pip': 0.01, 'lot': 0.1}

# 趋势分析
trend_h1 = _detect_trend(h1['close'].values)
trend_h4 = _detect_trend(h4['close'].values)
trend_d1 = _detect_trend(d1['close'].values)
print(f"\n趋势状态:")
print(f"  H1: {trend_h1['direction']} (强度={trend_h1['strength']:.4f})")
print(f"  H4: {trend_h4['direction']} (强度={trend_h4['strength']:.4f})")
print(f"  D1: {trend_d1['direction']} (强度={trend_d1['strength']:.4f})")

# 生成信号
signals = gen_pasd(h1, h4, d1, cfg)
print(f"\n策略信号: {len(signals)} 个")

if signals:
    buys = [s for s in signals if s['side'] == 1]
    sells = [s for s in signals if s['side'] == -1]
    print(f"  买入: {len(buys)} 个")
    print(f"  卖出: {len(sells)} 个")

    # 检查信号方向分布
    buy_trends = [s['trend'] for s in buys]
    sell_trends = [s['trend'] for s in sells]
    print(f"\n  买入信号趋势分布: {dict(zip(*np.unique(buy_trends, return_counts=True)))}")
    print(f"  卖出信号趋势分布: {dict(zip(*np.unique(sell_trends, return_counts=True)))}")

    # 信号质量
    avg_pb = np.mean([s['pb_score'] for s in signals])
    avg_mf = np.mean([s['mf_resonance'] for s in signals])
    print(f"\n  平均PB得分: {avg_pb:.1f} (V2.0阈值: ≥3)")
    print(f"  平均共振得分: {avg_mf:.2f} (V2.0阈值: ≥0.6)")

# ── 回测 ──
print("\n" + "=" * 60)
print("测试2: V2.0 回测验证")
print("=" * 60)

result = backtest_pasd_v2(h1, h4, d1, initial_equity=10000.0, pip_usd=10.0)
print(f"\n回测统计:")
print(f"  总信号数: {result['signals']}")
print(f"  总交易数: {result['trades']}")
print(f"  盈利交易: {result['wins']} 笔")
print(f"  亏损交易: {result['losses']} 笔")
print(f"  胜率: {result['win_rate']:.1f}%")
print(f"  总盈亏: ${result['total_pnl']:.2f}")
print(f"  平均盈利: ${result['avg_win']:.2f}")
print(f"  平均亏损: ${result['avg_loss']:.2f}")
print(f"  盈亏比: {result['profit_factor']:.2f}" if result['profit_factor'] != float('inf') else "  盈亏比: ∞")
print(f"  买入交易: {result['buy_trades']} 笔")
print(f"  卖出交易: {result['sell_trades']} 笔")


# ── 对比测试: V1.0 vs V2.0 ──
print("\n" + "=" * 60)
print("测试3: V1.0 vs V2.0 对比")
print("=" * 60)

# V1.0
sys.path.insert(0, '.')
try:
    from pasd_fusion import gen_pasd as gen_pasd_v1, backtest_pasd as backtest_pasd_v1
    result_v1 = backtest_pasd_v1(h1, h4, d1)
    print(f"\nV1.0 回测:")
    print(f"  信号: {result_v1.get('signals', 'N/A')}, 交易: {result_v1.get('trades', 'N/A')}")
    print(f"  胜率: {result_v1.get('win_rate', 'N/A')}, 盈亏: ${result_v1.get('pnl', 'N/A')}")
except Exception as e:
    print(f"\nV1.0 回测失败: {e}")

print(f"\nV2.0 回测:")
print(f"  信号: {result['signals']}, 交易: {result['trades']}")
print(f"  胜率: {result['win_rate']:.1f}%, 盈亏: ${result['total_pnl']:.2f}")

# ── 敏感性测试: 不同阈值组合 ──
print("\n" + "=" * 60)
print("测试4: 参数敏感性分析")
print("=" * 60)

import importlib
import pasd_fusion_v2 as pasd2

test_cases = [
    {'MIN_RESONANCE': 0.5, 'MIN_PB_SCORE': 2, 'SIGNAL_COOLDOWN_BARS': 20},
    {'MIN_RESONANCE': 0.6, 'MIN_PB_SCORE': 3, 'SIGNAL_COOLDOWN_BARS': 30},  # 当前
    {'MIN_RESONANCE': 0.7, 'MIN_PB_SCORE': 4, 'SIGNAL_COOLDOWN_BARS': 40},
    {'MIN_RESONANCE': 0.8, 'MIN_PB_SCORE': 5, 'SIGNAL_COOLDOWN_BARS': 50},
]

for i, params in enumerate(test_cases):
    # 临时修改参数
    orig_resonance = pasd2.MIN_RESONANCE
    orig_pb = pasd2.MIN_PB_SCORE
    orig_cd = pasd2.SIGNAL_COOLDOWN_BARS

    pasd2.MIN_RESONANCE = params['MIN_RESONANCE']
    pasd2.MIN_PB_SCORE = params['MIN_PB_SCORE']
    pasd2.SIGNAL_COOLDOWN_BARS = params['SIGNAL_COOLDOWN_BARS']

    # 重新生成信号 (注意: backtest调用gen_pasd，参数已修改)
    result = backtest_pasd_v2(h1, h4, d1, initial_equity=10000.0, pip_usd=10.0)

    print(f"\n  组合{i+1} (共振≥{params['MIN_RESONANCE']}, PB≥{params['MIN_PB_SCORE']}, 冷却{params['SIGNAL_COOLDOWN_BARS']}根):")
    print(f"    信号:{result['signals']} 交易:{result['trades']} 胜率:{result['win_rate']:.1f}% 盈亏:${result['total_pnl']:.2f}")

    # 恢复
    pasd2.MIN_RESONANCE = orig_resonance
    pasd2.MIN_PB_SCORE = orig_pb
    pasd2.SIGNAL_COOLDOWN_BARS = orig_cd


# ── 总结 ──
print("\n" + "=" * 60)
print("V2.0 优化总结")
print("=" * 60)
print(f"""
【V2.0 核心改进】
1. 趋势方向过滤 — 顺势开仓，逆势跳过
2. 信号冷却间隔 — 同方向≥30根K线，避免密集入场
3. 质量门槛提升 — 共振≥0.6 + PB≥3分
4. 止损优化 — SL=1.5×ATR (更宽，减少被扫)
5. 盈亏比提升 — TP=3×风险 (更大盈利空间)
6. 回测修正 — 检查高低点触发SL/TP

【预期效果】
- 胜率: 23.5% → 50%+
- 信号质量: 更精准，更少假信号
- 风险收益: 盈亏比提升
""")

print("=" * 60)
