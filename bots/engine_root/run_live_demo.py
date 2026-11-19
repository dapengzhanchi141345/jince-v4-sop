# run_live_demo.py — 金策宗师团 · 模拟账户实盘测试
"""
用户明确授权: 在 TradeMaxGlobal-Demo (模拟账户) 直接下单, 目的是增加经验。
配置:
  - LIVE_TRADING_ENABLED = True  (模拟账户授权, 真调 order_send)
  - auto_confirm = True         (用户要求直接下, 不等人点确认)
仍生效的约束 (金策宗师团铁律):
  - 审度司一票否决 (单笔≤1% / 日累计≤3% / 手数上限) 绝不绕过
  - 任何 VETO 的品种都不下单, 仅 PASS 才下
  - 下单后本脚本不主动平仓; 平仓/持仓管理为另一次受审度司审计的操作
"""
import json
import os
import continuous_evolution_v2 as ce
import guardian_executor as ge
from guardian_executor import GuardianExecutor

# ══ 模拟账户实盘总闸 (用户显式开启, 仅 TradeMaxGlobal-Demo) ══
ge.LIVE_TRADING_ENABLED = True


def main():
    assert ce.ensure_mt5(), "MT5 NOT CONNECTED"

    state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'data', 'continuous_evolution', 'evolution_state.json')
    st = json.load(open(state_path, encoding='utf-8'))
    best_params = st.get('best_params') or st['best_strategy']['params']
    best = {'name': 'Evolved_Best', 'params': best_params,
            'fitness': st.get('best_fitness', 0)}

    gex = GuardianExecutor(auto_confirm=True)
    assert gex.connect(), "MT5 connect failed"
    acc = gex.mt5.account_info()

    print("=== 金刚卫 模拟实盘 (TradeMaxGlobal-Demo) ===")
    print(f"策略: {best['name']} | fitness={best['fitness']:.3f}")
    print(f"账户: login={acc.login} server={acc.server} "
          f"balance={acc.balance:.2f} equity={acc.equity:.2f}")
    print(f"风控: 单笔≤{gex.auditor.max_rpt*100:.1f}% | 日累计≤{gex.auditor.max_dr*100:.1f}% "
          f"| 审度司 VETO 不可绕过")
    print(f"LIVE_TRADING_ENABLED = {ge.LIVE_TRADING_ENABLED} "
          f"(模拟账户用户授权开, 真调 order_send)")
    print("=" * 72)

    total_pass = total_veto = total_skip = total_sent = 0
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
            ord_info = res.get('order', {})
            if ord_info.get('sent'):
                total_sent += 1
                print(f"  {sym:8s} FILLED | {p['direction']:4s} lot={p['lot']:.2f} "
                      f"ticket={ord_info.get('ticket')} @ {ord_info.get('price')} "
                      f"| sl={ord_info.get('sl')} tp={ord_info.get('tp')}")
            else:
                print(f"  {sym:8s} PASS*  | {p['direction']:4s} lot={p['lot']:.2f} "
                      f"entry={p['entry']:.3f} sl={p['sl']:.3f} tp={p['tp']:.3f} "
                      f"| 下单失败: {ord_info}")
        else:
            total_veto += 1
            print(f"  {sym:8s} VETO   | {why} | {res['reasons']}")

    print("=" * 72)
    print(f"审度司日风险已用: {gex.auditor.daily_risk_used()*100:.2f}% "
          f"| PASS={total_pass} VETO={total_veto} SKIP={total_skip} "
          f"FILLED={total_sent}")
    print(f"LIVE_TRADING_ENABLED = {ge.LIVE_TRADING_ENABLED}")


if __name__ == '__main__':
    main()
