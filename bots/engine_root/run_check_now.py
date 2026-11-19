"""真实MT5 50轮进化现状确认 (post-merge) - 干净脚本, 避免heredoc转义问题"""
import time, continuous_evolution_v2 as ce

assert ce.ensure_mt5(), "MT5 not connected"
t0 = time.time()
results, pool, memory = ce.run_continuous_evolution(max_rounds=50)
dt = time.time() - t0

hist = pool.fitness_history
print("=== REAL 50R (post-merge, current state) ===")
print("elapsed %.1fs | last5 survivors %s | min %d" % (
    dt, [h['pool_size'] for h in hist[-5:]], min(h['pool_size'] for h in hist)))

best = max(pool.strategies, key=lambda s: s['fitness'])
p = best['params']
def _sf(x):
    return ("%.3f" % x) if isinstance(x, (int, float)) else str(x)
print("BEST %s | fitness=%s | tc=%s | dl=%s" % (
    best['name'], _sf(best['fitness']), best.get('tc_consistency'), best.get('dl_consistency')))
print("params:", {k: round(v, 3) if isinstance(v, float) else v for k, v in p.items()})
inb = all(ce.PARAM_BOUNDS[k][0] <= p[k] <= ce.PARAM_BOUNDS[k][1]
          for k in ce.PARAM_BOUNDS if k in p)
print("params_in_bounds:", inb, "| sl>=0.5:", p['sl_multiplier'] >= 0.5)

eng = ce.BacktestEngine()
tot = 0
print("--- per-symbol REAL trades (best) ---")
for sym in ce.SYMBOL_CONFIG:
    tr = eng.run_walkforward(best, sym, None)
    tot += len(tr)
    print("  %-8s %d" % (sym, len(tr)))
print("TOTAL best real trades:", tot)
