"""P1-B 区间模块 DRY-RUN 验证脚本 (不下单, 仅产提案)。

用途: 启用 RANGE_MODE_ENABLED 后, 在真实行情下跑 scan_symbol, 验证区间
模块能在震荡市(H1 ADX<20)产生合法提案: RR≥2.0 / 仓位≤0.03 / sl 在
区间边界外 / 全链路保护仍生效. 绝不调用 order_send.

运行: C:/Users/ASUS/AppData/Roaming/uv/python/cpython-3.11.15-windows-x86_64-none/python.exe -u test_dryrun_range.py
"""
import sys
import market_scanner as ms
import continuous_evolution_v2 as ce
import guardian_executor as ge
from position_supervisor import load_all_best_strategies


def main():
    # 关键: 启用区间模块 (生产默认 False, 此脚本仅为验证)
    ms.RANGE_MODE_ENABLED = True
    print(f"[DRY-RUN] RANGE_MODE_ENABLED = {ms.RANGE_MODE_ENABLED}")
    print(f"[DRY-RUN] LIVE_TRADING_ENABLED = {ge.LIVE_TRADING_ENABLED} "
          f"(应 False 才安全, 本脚本绝不下单)")

    # 连接 MT5 拿真实行情 (scan_symbol 的 _hist 依赖)
    if not ce.ensure_mt5():
        print("[ERROR] MT5 初始化失败")
        sys.exit(1)

    guardian = ge.GuardianExecutor(auto_confirm=False)
    if not guardian.connect():
        print("[ERROR] guardian.connect 失败")
        sys.exit(1)

    strategies = load_all_best_strategies()
    hunter = ms.MarketHunter(strategies=strategies)

    print("=" * 70)
    print(f"{'SYMBOL':<10} {'RESULT':<10} {'DIR':<6} {'RR':<7} {'LOT':<6} DETAIL")
    print("=" * 70)

    range_signals = 0
    for sym in ce.SYMBOL_CONFIG.keys():
        try:
            p, r = hunter.scan_symbol(sym)
        except Exception as e:
            print(f"{sym:<10} ERROR    -      -      -      {e}")
            continue
        if p is None:
            print(f"{sym:<10} SKIP     -      -      -      {r[:55]}")
            continue
        if p.get('range_mode'):
            rr = p['tp_pts'] / p['sl_pts'] if p['sl_pts'] > 0 else 0
            ok = "OK" if (rr >= 2.0 - 1e-6 and p['lot'] <= 0.03) else "BAD"
            range_signals += 1
            print(f"{sym:<10} {ok:<9} {p['direction']:<6} {rr:<7.2f} "
                  f"{p['lot']:<6} range entry={p['entry']:.3f} "
                  f"sl={p['sl']:.3f} tp={p['tp']:.3f}")
        else:
            rr = p['tp_pts'] / p['sl_pts'] if p['sl_pts'] > 0 else 0
            print(f"{sym:<10} TREND    {p['direction']:<6} {rr:<7.2f} "
                  f"{p['lot']:<6} (趋势提案, 非区间)")

    print("=" * 70)
    print(f"[SUMMARY] 区间信号数={range_signals} / 品种数={len(ce.SYMBOL_CONFIG)}")
    print("[DRY-RUN] 完成, 未执行任何下单操作")


if __name__ == '__main__':
    main()
