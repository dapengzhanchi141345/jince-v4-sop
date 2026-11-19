# _fill_baseline_s07.py — 钉回 Strategy_07 为 best, 并以其自身回测 trades 计算稳健 baseline
# 目的: 漂移监控的 live 成交(41笔)均为 Strategy_07 实盘, baseline 必须反映"当前实盘策略的
#       回测基线"才具备漂移意义。单次进化(20轮)误选出 Strategy_02 且基线来自单轮单品种噪声样本,
#       会导致"苹果对橘子"误报。故以 Strategy_07 多品种 walk-forward 回测聚合, 计算稳健 pf/win_rate。
# 仅读 MT5 历史回测 + 写 evolution_state.json, 绝不交易/开仓。
import os, json, datetime
import continuous_evolution_v2 as ce

assert ce.ensure_mt5(), "MT5 未连接 -> 无法跑真实回测基线"
engine = ce.BacktestEngine()

# Strategy_07 原始双铁律合规参数 (来自上一轮 30 轮进化验证 best)
s07 = {
    'id': 7, 'name': 'Strategy_07',
    'params': {
        'adx_min': 39,
        'position_size': 0.03,
        'risk_per_trade': 0.0162,
        'sl_multiplier': 2.5989,
        'tp_multiplier': 5.1979,
        'volatility_scalar': 0.9735,
        'momentum_filter': False,
    },
}
# 双铁律再夹一次, 确保合规 (RR>=2, pos in [0.01,0.03])
ce._ensure_rr(s07['params'])
ce._ensure_risk_cap(s07['params'])

# 多品种 walk-forward 回测聚合, 提升 baseline 稳健性
trades = []
for sym in ce.SYMBOL_CONFIG:
    try:
        t = engine.run_walkforward(s07, sym, None)
        if t:
            trades.extend(t)
            print(f"  [{sym}] trades={len(t)}")
    except Exception as e:
        print(f"  [{sym}] skip: {e}")
print(f"== 总回测 trades: {len(trades)}")

baseline = ce.compute_trades_baseline(trades)
print(f"== Strategy_07 baseline (pf/win_rate): {baseline}")

# 重写 evolution_state.json: best 钉回 Strategy_07 + 其真实 baseline
path = os.path.join(ce.EVOLVE_DIR, 'evolution_state.json')
with open(path, 'r', encoding='utf-8') as f:
    st = json.load(f)

st['best_strategy'] = {
    'name': 'Strategy_07',
    'fitness': 25.375,
    'params': {k: (round(v, 4) if isinstance(v, float) else v) for k, v in s07['params'].items()},
    'tc_consistency': None,
    'dl_consistency': None,
    'baseline': baseline,
}
st['updated_at'] = datetime.datetime.now().isoformat(timespec='seconds')
st['mode'] = 'real(MT5)'
st['baseline_filled_by'] = 'Strategy_07 multi-symbol walk-forward (drift-consistent)'

with open(path, 'w', encoding='utf-8') as f:
    json.dump(st, f, indent=2, default=str)
print(f"== 已钉回 Strategy_07 并写入 baseline: {baseline}")
print(f"== 双铁律校验: RR={s07['params']['tp_multiplier']/s07['params']['sl_multiplier']:.3f} "
      f"(>=2), pos={s07['params']['position_size']} (in [0.01,0.03])")
