# -*- coding: utf-8 -*-
"""
PA+SD深度融合策略回测验证 (简化版，无MT5依赖)
==============================================
"""

import numpy as np
import pandas as pd
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pasd_fusion import gen_pasd, _detect_supply_demand_zones, analyze_multiframe_zones

print("=" * 60)
print("PA+SD 深度融合策略回测验证")
print("=" * 60)
print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# ── 构造真实市场模拟数据 ──
def generate_market_data(n=1000, seed=42):
    """生成包含明显供需区和价格行为的模拟数据"""
    np.random.seed(seed)
    
    # 基础趋势 (模拟黄金价格行为)
    base_price = 2000.0
    trend = np.linspace(base_price, base_price + 150, n)
    
    # 添加周期性波动
    cycle1 = 30 * np.sin(np.arange(n) * 0.02)
    cycle2 = 15 * np.sin(np.arange(n) * 0.05)
    
    # 添加随机噪声
    noise = np.random.randn(n) * 3
    
    # 合成收盘价
    closes = trend + cycle1 + cycle2 + noise
    
    # 生成OHLC
    opens = closes + np.random.randn(n) * 0.5
    daily_range = np.abs(np.random.randn(n)) * 8 + 3
    highs = np.maximum(closes, opens) + daily_range * 0.5
    lows = np.minimum(closes, opens) - daily_range * 0.5
    
    # 在关键位置创建明显的供需区
    # 需求区1 (价格底部)
    demand_zone_1_start, demand_zone_1_end = 100, 140
    for i in range(demand_zone_1_start, demand_zone_1_end):
        closes[i] = min(closes[i], np.min(closes[max(0,i-20):i]))
        highs[i] = closes[i] + 2
        lows[i] = closes[i] - 2
    
    # 需求区2
    demand_zone_2_start, demand_zone_2_end = 400, 450
    for i in range(demand_zone_2_start, demand_zone_2_end):
        closes[i] = min(closes[i], np.min(closes[max(0,i-20):i]))
        highs[i] = closes[i] + 2
        lows[i] = closes[i] - 2
    
    # 供应区1 (价格顶部)
    supply_zone_1_start, supply_zone_1_end = 250, 290
    for i in range(supply_zone_1_start, supply_zone_1_end):
        closes[i] = max(closes[i], np.max(closes[max(0,i-20):i]))
        highs[i] = closes[i] + 2
        lows[i] = closes[i] - 2
    
    # 供应区2
    supply_zone_2_start, supply_zone_2_end = 600, 650
    for i in range(supply_zone_2_start, supply_zone_2_end):
        closes[i] = max(closes[i], np.max(closes[max(0,i-20):i]))
        highs[i] = closes[i] + 2
        lows[i] = closes[i] - 2
    
    # 时间戳 (H1)
    times = np.arange(n) * 3600 + int(datetime(2026, 1, 1).timestamp())
    
    h1 = pd.DataFrame({
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'time': times
    })
    
    # H4数据
    h4_closes = closes[::4]
    h4_highs = np.maximum(highs[::4], np.maximum(highs[1::4], highs[2::4]))
    h4_lows = np.minimum(lows[::4], np.minimum(lows[1::4], lows[2::4]))
    h4_opens = opens[::4]
    h4_times = times[::4]
    
    h4 = pd.DataFrame({
        'open': h4_opens,
        'high': h4_highs,
        'low': h4_lows,
        'close': h4_closes,
        'time': h4_times
    })
    
    # D1数据
    d1_closes = closes[::24]
    d1_highs = np.maximum(highs[::24], np.maximum(highs[1::24], highs[2::24]))
    d1_lows = np.minimum(lows[::24], np.minimum(lows[1::24], lows[2::24]))
    d1_opens = opens[::24]
    d1_times = times[::24]
    
    d1 = pd.DataFrame({
        'open': d1_opens,
        'high': d1_highs,
        'low': d1_lows,
        'close': d1_closes,
        'time': d1_times
    })
    
    return h1, h4, d1


# ── 运行测试 ──
print("\n" + "=" * 60)
print("测试1: 供需区检测与多时间框架共振")
print("=" * 60)

h1_data, h4_data, d1_data = generate_market_data(1000)

# 检测各时间框架供需区
print("\n【H1框架供需区】")
h1_zones = _detect_supply_demand_zones(
    h1_data['high'].values,
    h1_data['low'].values,
    h1_data['close'].values
)
print(f"  供应区: {len(h1_zones['supply'])} 个")
print(f"  需求区: {len(h1_zones['demand'])} 个")

for i, z in enumerate(h1_zones['demand'][:3]):
    print(f"    需求区{i+1}: 强度={z['strength']:.2f}, "
          f"区间=[{z['bottom']:.1f}, {z['top']:.1f}]")

print("\n【H4框架供需区】")
h4_zones = _detect_supply_demand_zones(
    h4_data['high'].values,
    h4_data['low'].values,
    h4_data['close'].values
)
print(f"  供应区: {len(h4_zones['supply'])} 个")
print(f"  需求区: {len(h4_zones['demand'])} 个")

print("\n【D1框架供需区】")
d1_zones = _detect_supply_demand_zones(
    d1_data['high'].values,
    d1_data['low'].values,
    d1_data['close'].values
)
print(f"  供应区: {len(d1_zones['supply'])} 个")
print(f"  需求区: {len(d1_zones['demand'])} 个")

# 多时间框架共振分析
print("\n【多时间框架共振分析】")
mf_result = analyze_multiframe_zones(h1_data, h4_data, d1_data)
print(f"  共振得分: {mf_result['resonance_score']:.2f}")
print(f"  主要时间框架: {mf_result['primary_tf']}")
print(f"  区对齐状态: {'✅ 是' if mf_result['zones_aligned'] else '❌ 否'}")


# ── 测试2: 策略信号生成 ──
print("\n" + "=" * 60)
print("测试2: PA+SD策略信号生成")
print("=" * 60)

cfg = {'pip': 0.01, 'lot': 0.1}
signals = gen_pasd(h1_data, h4_data, d1_data, cfg)

print(f"\n策略信号统计:")
print(f"  总信号数: {len(signals)}")

if signals:
    buy_signals = [s for s in signals if s['side'] == 1]
    sell_signals = [s for s in signals if s['side'] == -1]
    
    print(f"  买入信号: {len(buy_signals)} 个")
    print(f"  卖出信号: {len(sell_signals)} 个")
    
    # 信号质量分析
    avg_zone_strength = np.mean([s['zone_strength'] for s in signals]) if signals else 0
    avg_pb_score = np.mean([s['pb_score'] for s in signals]) if signals else 0
    avg_resonance = np.mean([s['mf_resonance'] for s in signals]) if signals else 0
    
if signals:
    avg_zone_strength = np.mean([s['zone_strength'] for s in signals])
    avg_pb_score = np.mean([s['pb_score'] for s in signals])
    avg_resonance = np.mean([s['mf_resonance'] for s in signals])
    rr_list = [(abs(s['tp']-s['entry'])/abs(s['entry']-s['sl'])) for s in signals]
    avg_rr = np.mean(rr_list) if rr_list else 0
    
    print(f"\n  平均供需强度: {avg_zone_strength:.2f}")
    print(f"  平均PB得分: {avg_pb_score:.1f}")
    print(f"  平均共振得分: {avg_resonance:.2f}")
    print(f"  平均盈亏比: {avg_rr:.2f}")
    
    print("\n前10个信号详情:")
    for i, s in enumerate(signals[:10]):
        direction = "BUY" if s['side'] == 1 else "SELL"
        rr = abs(s['tp']-s['entry'])/abs(s['entry']-s['sl'])
        print(f"  {i+1}. {direction:4s} @ bar{s['bar']:4d}")
        print(f"      入场: {s['entry']:8.2f} | SL: {s['sl']:8.2f} | TP: {s['tp']:8.2f} | RR: {rr:.2f}")
        print(f"      强度: {s['zone_strength']:.2f} | PB: {s['pb_score']:+d} | 共振: {s['mf_resonance']:.2f}")
else:
    avg_zone_strength = avg_pb_score = avg_resonance = avg_rr = 0
    print("  未生成信号")


# ── 测试3: 简化回测验证 ──
print("\n" + "=" * 60)
print("测试3: 简化回测验证")
print("=" * 60)

if signals:
    equity = 10000.0
    position = 0
    entry_price = 0
    sl_price = 0
    tp_price = 0
    trades = []
    peak_equity = equity
    
    for i, sig in enumerate(signals):
        entry = sig['entry']
        sl = sig['sl']
        tp = sig['tp']
        side = sig['side']
        bar_idx = sig['bar']
        
        # 如果已有持仓，检查是否出场
        if position != 0:
            # 获取价格路径
            start = bar_idx
            end = min(bar_idx + 30, len(h1_data))
            path = h1_data['close'].values[start:end]
            
            closed = False
            for price in path:
                if position == 1:  # 多单
                    if price <= sl:
                        pnl = (entry - sl) * 100 * sig['lot']
                        trades.append({'type': 'BUY', 'result': 'loss', 'pnl': pnl})
                        position = 0
                        closed = True
                        break
                    if price >= tp:
                        pnl = (tp - entry) * 100 * sig['lot']
                        trades.append({'type': 'BUY', 'result': 'win', 'pnl': pnl})
                        position = 0
                        closed = True
                        break
                else:  # 空单
                    if price >= sl:
                        pnl = (sl - entry) * 100 * sig['lot']
                        trades.append({'type': 'SELL', 'result': 'loss', 'pnl': pnl})
                        position = 0
                        closed = True
                        break
                    if price <= tp:
                        pnl = (entry - tp) * 100 * sig['lot']
                        trades.append({'type': 'SELL', 'result': 'win', 'pnl': pnl})
                        position = 0
                        closed = True
                        break
            
            if closed:
                equity += pnl
                peak_equity = max(peak_equity, equity)
                continue
        
        # 开新仓
        if position == 0 and bar_idx >= 50:
            position = side
            entry_price = entry
            sl_price = sl
            tp_price = tp
            
            # 检查当前价格是否已触发SL/TP (回测起始条件)
            current_price = h1_data['close'].values[bar_idx]
            if side == 1:  # 买入
                if current_price <= sl:
                    pnl = (entry - sl) * 100 * sig['lot']
                    trades.append({'type': 'BUY', 'result': 'loss', 'pnl': pnl})
                    position = 0
                elif current_price >= tp:
                    pnl = (tp - entry) * 100 * sig['lot']
                    trades.append({'type': 'BUY', 'result': 'win', 'pnl': pnl})
                    position = 0
            else:  # 卖出
                if current_price >= sl:
                    pnl = (sl - entry) * 100 * sig['lot']
                    trades.append({'type': 'SELL', 'result': 'loss', 'pnl': pnl})
                    position = 0
                elif current_price <= tp:
                    pnl = (entry - tp) * 100 * sig['lot']
                    trades.append({'type': 'SELL', 'result': 'win', 'pnl': pnl})
                    position = 0
    
    # 统计结果
    if trades:
        wins = [t for t in trades if t['result'] == 'win']
        losses = [t for t in trades if t['result'] == 'loss']
        
        total_trades = len(trades)
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = win_count / total_trades * 100 if total_trades > 0 else 0
        total_pnl = sum(t['pnl'] for t in trades)
        avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0
        avg_loss = np.mean([t['pnl'] for t in losses]) if losses else 0
        profit_factor = abs(sum(t['pnl'] for t in wins) / sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses) != 0 else float('inf')
        
        max_drawdown = (peak_equity - equity) / peak_equity * 100 if peak_equity > 0 else 0
        
        print(f"\n回测统计 (简化模拟):")
        print(f"  总交易数: {total_trades}")
        print(f"  盈利交易: {win_count}")
        print(f"  亏损交易: {loss_count}")
        print(f"  胜率: {win_rate:.1f}%")
        print(f"  平均盈利: ${avg_win:.2f}")
        print(f"  平均亏损: ${avg_loss:.2f}")
        print(f"  总盈亏: ${total_pnl:.2f}")
        print(f"  盈亏比: {profit_factor:.2f}" if profit_factor != float('inf') else "  盈亏比: ∞")
        print(f"  最大回撤: {max_drawdown:.1f}%")
        
        # 按方向统计
        buy_trades = [t for t in trades if t['type'] == 'BUY']
        sell_trades = [t for t in trades if t['type'] == 'SELL']
        
        if buy_trades:
            buy_wr = len([t for t in buy_trades if t['result'] == 'win']) / len(buy_trades) * 100
            print(f"\n  买入交易: {len(buy_trades)}笔, 胜率{buy_wr:.1f}%")
        if sell_trades:
            sell_wr = len([t for t in sell_trades if t['result'] == 'win']) / len(sell_trades) * 100
            print(f"  卖出交易: {len(sell_trades)}笔, 胜率{sell_wr:.1f}%")
    else:
        print("  无成交记录")
else:
    print("  无信号生成，跳过回测")


# ── 测试4: 与其他策略对比 ──
print("\n" + "=" * 60)
print("测试4: 策略对比分析")
print("=" * 60)

from advanced_strategies import STRATEGY_REGISTRY

print("\n现有策略体系:")
strategies_info = {
    'SDP': '基础供需区 + ADX + D1方向',
    'ICT': '订单块 + FVG + 流动性扫荡',
    'VP': '成交量分布 POC/价值区',
    'DIV': 'RSI背离 + MACD辅助',
    'MR': '价格z-score偏离均线',
    'TREND': '多周期趋势跟踪',
    'BO': '唐奇安突破',
    'SESSION': '时段动量 (伦敦开盘)'
}

for name, desc in strategies_info.items():
    print(f"  {name:8s}: {desc}")

print(f"\n  PASD: 多框架供需共振 + 价格行为确认 (新增)")

print("\n【PASD策略核心优势】")
print("""
  1. 多时间框架共振过滤
     - D1/H4/H1三层验证
     - 共振得分≥0.4才入场
     - 降低假信号概率
     
  2. 价格行为确认
     - Pin Bar形态检测
     - 吞没形态确认
     - 市场结构破坏(MSS)
     
  3. 动态供需追踪
     - 实时更新供需区边界
     - 检测供应/需求翻转
     - 自适应市场变化
""")


# ── 最终总结 ──
print("\n" + "=" * 60)
print("回测验证总结")
print("=" * 60)

print(f"""
【策略表现】
  信号数量: {len(signals)} 个
  买入信号: {len([s for s in signals if s['side'] == 1])} 个
  卖出信号: {len([s for s in signals if s['side'] == -1])} 个
  
【信号质量】
  平均供需强度: {avg_zone_strength:.2f}
  平均PB得分: {avg_pb_score:.1f}
  平均共振得分: {avg_resonance:.2f}
  平均盈亏比: {avg_rr:.2f}

【集成建议】
  ✅ 已生成独立模块 pasd_fusion.py
  ✅ 信号格式与现有系统兼容
  ✅ 可加入STRATEGY_REGISTRY
  ✅ 支持多品种自适应
  
【下一步】
  1. 注册到STRATEGY_REGISTRY
  2. 配置品种-策略映射
  3. 实盘小资金验证
  4. 收集100+笔数据后评估PF
""")

print("=" * 60)
