"""A.T.E. 一键学习+进化 (真实 MT5 环境)
阶段1: 用真实历史训练盘感神经网络 (IntuitionNet)
阶段2: 用真实回测驱动达尔文进化 (盘感DL + TC 双裁判)
全部基于用户本机 MT5 终端的真实行情, 不跑任何合成假数据。
"""
import time, os
import MetaTrader5 as mt5
import deep_learning_optimizer as m
import continuous_evolution_v2 as ce

t0 = time.time()
SYMS = ['XAUUSD', 'BTCUSD', 'ETHUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'GBPJPY', 'AUDUSD']

print("=" * 70, flush=True)
print("  A.T.E. 自主学习 + 进化  (真实 MT5 环境)", flush=True)
print("=" * 70, flush=True)

# ── 阶段1: 训练真盘感模型 ──
print(f"\n[阶段1] 训练盘感神经网络 (真MT5历史, 8品种) ...", flush=True)
opt = m.DLOptimizer()
opt.train_on_mt5(SYMS, epochs=10)
print(f"  模型: {m.MODEL_PATH}  大小: {os.path.getsize(m.MODEL_PATH)} bytes", flush=True)

# ── 阶段2: 生产进化 (real 模式 + 真DL) ──
print(f"\n[阶段2] 达尔文进化 (real回测 + 真盘感DL + TC双裁判) ...", flush=True)
out = ce.run_continuous_evolution(max_rounds=50)
if out is None:
    print("  进化跳过: MT5 不可用", flush=True)
else:
    results, pool, mem = out
    best = max(pool.strategies, key=lambda s: s['fitness'])
    print(f"  进化完成: 存活 {len(pool.strategies)} 策略", flush=True)
    print(f"  最佳策略: {best['name']} | fitness={best['fitness']:.2f} | "
          f"TC一致性={best.get('tc_consistency')} | DL一致性={best.get('dl_consistency')}", flush=True)
    print(f"  TC总经验: {mem.patterns['total_experiences']} 条", flush=True)

if mt5.terminal_info() is not None:
    mt5.shutdown()
print(f"\n✅ 总耗时 {time.time()-t0:.1f}s", flush=True)
