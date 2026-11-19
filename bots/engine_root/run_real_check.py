"""真实 MT5 路径冒烟测试 (real walk-forward 闸门)

用途: 在用户 MT5 终端在线时, 一键验证 continuous_evolution_v2 的
      real walk-forward 路径确实能拉到真实行情并产生真实交易统计。
      - MT5 未连接 → 打印 SKIP 并退出 0 (不报错, 可在任意环境安全运行)
      - MT5 已连接 → 实跑少量策略×全品种真实回测, 断言交易数 > 0,
        并打印每品种真实 ADX 区间 / 胜率 / best_fitness, 写确认到
        data/continuous_evolution/real_check.json

退出码: 0=通过或跳过, 1=真路径产出 0 交易 (FAIL, 需排查)
"""
import os, sys, json, time
import numpy as np
import continuous_evolution_v2 as ce

EVOLVE_DIR = ce.EVOLVE_DIR
OUT = os.path.join(EVOLVE_DIR, "real_check.json")


def _real_dl_cache(engine):
    cache = {}
    if engine.mode == 'real' and ce._DL is not None and engine.mt5 is not None:
        for sym in ce.SYMBOL_CONFIG:
            try:
                cache[sym] = ce._DL.boost_from_raw(sym, 0.0, None, True, engine.mt5)
            except Exception:
                cache[sym] = None
    return cache


def main():
    print("=" * 64)
    print("  真实 MT5 walk-forward 冒烟测试")
    print("=" * 64)

    if not ce.ensure_mt5():
        print("  ⚠ MT5 终端未连接/未登录 → SKIP (本环境无需真跑)")
        print("  ℹ 在用户机器(MT5在线)运行此脚本即可验证真实路径。")
        return 0

    engine = ce.BacktestEngine()
    assert engine.mode == 'real', f"engine.mode={engine.mode} (应为 real)"
    print(f"  ✅ MT5 已连接, 回测模式: {engine.mode}")

    # DL 盘感缓存(真实)
    dl_cache = _real_dl_cache(engine)

    pool = ce.StrategyPool()
    sample_strats = pool.strategies[:5]   # 取 5 条策略做快速验证

    per_sym = {}
    all_trades = []
    for sym in ce.SYMBOL_CONFIG:
        hist, spread = engine._load_history(sym)
        if hist is None:
            per_sym[sym] = {"trades": 0, "note": "history None"}
            continue
        close, high, low = hist
        adx = ce._adx(high, low, close)
        adx_valid = adx[60:]
        sym_t = []
        for s in sample_strats:
            sym_t.extend(engine.run_walkforward(s, sym, dl_cache.get(sym)))
        wins = sum(1 for t in sym_t if t['pnl'] > 0)
        per_sym[sym] = {
            "trades": len(sym_t),
            "win_rate": round(wins / max(len(sym_t), 1), 3),
            "adx_min": round(float(np.nanmin(adx_valid)), 1),
            "adx_max": round(float(np.nanmax(adx_valid)), 1),
            "adx_mean": round(float(np.nanmean(adx_valid)), 1),
            "spread": round(float(spread), 3),
        }
        all_trades.extend(sym_t)
        print(f"  {sym:7s} | trades:{len(sym_t):>3d} | 胜率:{per_sym[sym]['win_rate']:.1%} "
              f"| ADX:{per_sym[sym]['adx_mean']:.0f}({per_sym[sym]['adx_min']:.0f}~{per_sym[sym]['adx_max']:.0f})")

    total = len(all_trades)
    print(f"\n  真实总交易数: {total}")
    if total == 0:
        print("  ❌ FAIL: 真实路径未产生任何交易 (数据链路或入场过滤有问题)")
        out = {"verdict": "FAIL", "total_trades": 0, "per_symbol": per_sym,
               "checked_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        with open(OUT, 'w') as f:
            json.dump(out, f, indent=2)
        return 1

    # 双裁判统计验证
    tc_hits = [t for t in all_trades if t.get('predicted_bias') and ce.TC_CONSENSUS.get(t['symbol'])]
    dl_hits = [t for t in all_trades if t.get('dl_dir')]
    # 小轮真实进化(2轮) 确认端到端
    out_evo = ce.run_continuous_evolution(max_rounds=2, force_synthetic=False)
    best = None
    if out_evo is not None:
        _, p2, _ = out_evo
        best = max(p2.strategies, key=lambda s: s['fitness']) if p2.strategies else None

    verdict = {
        "verdict": "PASS",
        "mode": engine.mode,
        "total_trades": total,
        "per_symbol": per_sym,
        "tc_labeled": len(tc_hits),
        "dl_labeled": len(dl_hits),
        "evolution_best_fitness": round(best['fitness'], 3) if best else None,
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(OUT, 'w') as f:
        json.dump(verdict, f, indent=2, default=str)
    print(f"  ✅ PASS: 真实 walk-forward 链路正常 (best_fitness="
          f"{verdict['evolution_best_fitness']})")
    print(f"  📁 确认已写: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
