# run_executor_demo.py — 金刚卫 + 审度司 执行链演示
"""
演示 "研究 → 信号 → 风控" 全闭环的前半段:
  1. 加载已进化出的最佳策略 (evolution_state.json)
  2. 对每个品种用最佳策略生成实时信号提案 (方向/手数/SL/TP)
  3. 送审度司 (risk_auditor) 审计, 输出 PASS / VETO / SKIP 结论

安全: auto_confirm=False + LIVE_TRADING_ENABLED=False → 绝不调用 order_send。
仅展示执行链的"决策大脑"部分, 真下单需单独明确授权。
"""
import json
import os
import continuous_evolution_v2 as ce
from guardian_executor import GuardianExecutor, LIVE_TRADING_ENABLED


def main():
    assert ce.ensure_mt5(), "MT5 NOT CONNECTED"

    # 1. 加载已进化的最佳策略
    state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'data', 'continuous_evolution', 'evolution_state.json')
    st = json.load(open(state_path, encoding='utf-8'))
    best_params = st.get('best_params') or st['best_strategy']['params']
    best = {'name': 'Evolved_Best', 'params': best_params,
            'fitness': st.get('best_fitness', 0)}

    # 2. 金刚卫 (人工确认模式)
    gex = GuardianExecutor(auto_confirm=False)
    assert gex.connect(), "MT5 connect failed"

    print("=== 金刚卫 信号生成 + 审度司审计 (人工确认模式, 不真下单) ===")
    print(f"策略: {best['name']} | fitness={best['fitness']:.3f}")
    print("参数: " + ", ".join(
        f"{k}={round(v, 3) if isinstance(v, float) else v}"
        for k, v in best_params.items()))
    print(f"风控: 单笔≤{gex.auditor.max_rpt*100:.1f}% | 日累计≤{gex.auditor.max_dr*100:.1f}%")
    print("-" * 72)

    total_pass = total_veto = total_skip = 0
    for sym in ce.SYMBOL_CONFIG:
        prop, why = gex.build_signal(best, sym)
        res = gex.audit_and_execute(prop)
        d = res['decision']
        if d == 'SKIP':
            total_skip += 1
            print(f"  {sym:8s} SKIP   | {why}")
        elif d == 'PASS':
            total_pass += 1
            p = res['proposal']
            print(f"  {sym:8s} PASS   | {p['direction']:4s} lot={p['lot']:.2f} "
                  f"entry={p['entry']:.3f} sl={p['sl']:.3f} tp={p['tp']:.3f} "
                  f"| {res['note']}")
        else:
            total_veto += 1
            print(f"  {sym:8s} VETO   | {why} | {res['reasons']}")

    print("-" * 72)
    print(f"审度司日风险已用: {gex.auditor.daily_risk_used()*100:.2f}% "
          f"| PASS={total_pass} VETO={total_veto} SKIP={total_skip}")
    print(f"LIVE_TRADING_ENABLED = {LIVE_TRADING_ENABLED} "
          f"(False → 任何模式均不真下单)")


if __name__ == '__main__':
    main()
