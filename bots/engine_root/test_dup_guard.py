# test_dup_guard.py — 同品种持仓防重硬闸离线单测 (不连真实 MT5)
#
# 验证 guardian_executor.GuardianExecutor.audit_and_execute 在下单前
# 实时查 MT5 同品种持仓: 已有持仓则 VETO 且绝不调用 _send_order;
# 无持仓则正常走审计 (不触发防重 VETO)。
import guardian_executor as ge


class _FakePos:
    """模拟 MT5 持仓对象 (只需 symbol 等属性, 本测试只读其一)."""
    def __init__(self, symbol):
        self.symbol = symbol
        self.ticket = 1
        self.volume = 0.01


class _FakeMT5:
    """可控 mock: positions_get 按 symbol 返回指定持仓; account_info 提供 equity."""
    def __init__(self, existing=None):
        # existing: dict {symbol: [positions]} 或 None 表示无持仓
        self._existing = existing or {}
        self.send_calls = []

    def account_info(self):
        class _Acc:
            equity = 10000.0
        return _Acc()

    def positions_get(self, symbol=None):
        return self._existing.get(symbol, [])

    def order_send(self, request):
        self.send_calls.append(request)
        return None


def _make_guardian(mt5, live=True):
    g = ge.GuardianExecutor(auto_confirm=True,
                             max_risk_per_trade=0.01,
                             max_daily_risk=0.03)
    g.mt5 = mt5
    return g


def _sample_proposal(symbol='ETHUSD'):
    return {
        'symbol': symbol, 'direction': 'BUY',
        'entry': 3000.0, 'sl': 2980.0, 'tp': 3040.0,
        'sl_pts': 50.0, 'tp_pts': 100.0,
        'lot': 0.01, 'pip_usd_per_lot': 1.0,
        'spread': 0.5, 'strategy': 'test', 'adx': 30.0,
    }


def _run_case(live_existing_for_symbol):
    """live_existing_for_symbol: 该 symbol 是否已有持仓 (bool).
    返回 (result, sent_list, mt5_mock)。"""
    mt5 = _FakeMT5()
    if live_existing_for_symbol:
        # 模拟 MT5 上已存在 ETHUSD 持仓
        mt5._existing['ETHUSD'] = [_FakePos('ETHUSD')]
    g = _make_guardian(mt5, live=True)
    # 完全 stub _send_order: 仅记录是否被调用 (不下真实单, 隔离 MT5 API)
    sent = []
    def _stub_send(proposal):
        sent.append(proposal)
        return {'sent': True, 'ticket': 999, 'volume': proposal['lot'],
                'price': 1.0, 'sl': 1.0, 'tp': 1.0}
    g._send_order = _stub_send
    ge.LIVE_TRADING_ENABLED = True
    try:
        res = g.audit_and_execute(_sample_proposal('ETHUSD'))
    finally:
        ge.LIVE_TRADING_ENABLED = False
    return res, sent, mt5


def run():
    fails = []
    # 1. 已有 ETHUSD 持仓 → 防重 VETO, 且 _send_order 未被调用
    res, sent, mt5 = _run_case(live_existing_for_symbol=True)
    if res.get('decision') != 'VETO':
        fails.append(f'已有持仓应 VETO, 得 {res.get("decision")}')
    if '防重复开仓' not in ' '.join(res.get('reasons', [])):
        fails.append(f'VETO 理由应含防重复开仓: {res.get("reasons")}')
    if sent:
        fails.append('防重 VETO 时仍调用了 _send_order (资金安全漏洞!)')

    # 2. 无 ETHUSD 持仓 → 正常走审计 (不触发防重 VETO), 且会进入下单路径
    res2, sent2, mt5b = _run_case(live_existing_for_symbol=False)
    if res2.get('decision') == 'VETO' and '防重复开仓' in ' '.join(res2.get('reasons', [])):
        fails.append('无持仓不应触发防重 VETO')
    # auto+live 且审计 PASS → 应走到 _send_order (order_send mock 被调用)
    if not sent2:
        fails.append('无持仓且审计通过应进入下单路径 (调用 _send_order)')

    if fails:
        print("DUP_GUARD FAIL:")
        for f in fails:
            print("  -", f)
        return False
    print("DUP_GUARD PASS: 2/2 防重硬闸正确 "
          "(有持仓→VETO且不下单 / 无持仓→正常走审计下单)")
    return True


if __name__ == '__main__':
    import sys
    sys.exit(0 if run() else 1)
