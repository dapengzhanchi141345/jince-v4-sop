# test_supervisor.py — 监军司决策引擎离线单测 (不连 MT5)
import MetaTrader5 as mt5
import position_supervisor as ps


class FakePos:
    def __init__(self, ticket, symbol, ptype, price_open, price_current,
                 sl, tp):
        self.ticket = ticket
        self.symbol = symbol
        self.type = ptype
        self.price_open = price_open
        self.price_current = price_current
        self.sl = sl
        self.tp = tp
        self.volume = 0.02


def _make_sup(bias, atr, adx):
    sup = ps.PositionSupervisor(dry_run=True, auto_confirm=False)
    sup.strategy = {'params': {'adx_min': 20}}
    sup.guardian.live_bias = lambda sym, strat: (bias, 'mock')
    sup.guardian.market_state = lambda sym: {'atr_now': atr, 'adx_now': adx}
    return sup


def run():
    BUY = mt5.POSITION_TYPE_BUY
    SELL = mt5.POSITION_TYPE_SELL
    fails = []

    # 1. 信号反向 (BUY 持仓 + SELL 研判) → CLOSE
    sup = _make_sup('SELL', 0.0010, 30.0)
    pos = FakePos(1, 'EURUSD', BUY, 1.1000, 1.1010, 1.0980, 1.1050)
    d = sup._evaluate(pos)
    if d.action != 'CLOSE':
        fails.append(f'反向应 CLOSE, 得 {d.action}')

    # 2. 同向且浮盈≥1ATR 未保本 → BREAKEVEN
    sup = _make_sup('BUY', 0.0010, 30.0)
    pos = FakePos(2, 'EURUSD', BUY, 1.1000, 1.1015, 1.0980, 1.1050)
    d = sup._evaluate(pos)
    if d.action != 'BREAKEVEN' or abs(d.new_sl - 1.1000) > 1e-6:
        fails.append(f'浮盈≥1ATR应 BREAKEVEN@entry, 得 {d.action}/{d.new_sl}')

    # 3. 同向且浮盈≥2ATR → TRAIL (且新 SL 收紧)
    sup = _make_sup('BUY', 0.0010, 30.0)
    pos = FakePos(3, 'EURUSD', BUY, 1.1000, 1.1030, 1.0980, 1.1050)
    d = sup._evaluate(pos)
    exp_sl = 1.1030 - 2.5 * 0.0010  # 1.1005 (2.5xATR 追踪距离, 2026-08-28 MQL5 XAU共识校准)
    if d.action != 'TRAIL' or abs(d.new_sl - exp_sl) > 1e-6:
        fails.append(f'浮盈≥2ATR应 TRAIL@{exp_sl:.5f}, 得 {d.action}/{d.new_sl}')

    # 4. 浮盈不足 → HOLD
    sup = _make_sup('BUY', 0.0010, 30.0)
    pos = FakePos(4, 'EURUSD', BUY, 1.1000, 1.1005, 1.0980, 1.1050)
    d = sup._evaluate(pos)
    if d.action != 'HOLD':
        fails.append(f'浮盈<1ATR应 HOLD, 得 {d.action}')

    # 5. ADX 崩溃且浮盈 → CLOSE
    sup = _make_sup('BUY', 0.0010, 10.0)  # adx_exit=18
    pos = FakePos(5, 'EURUSD', BUY, 1.1000, 1.1020, 1.0980, 1.1050)
    d = sup._evaluate(pos)
    if d.action != 'CLOSE':
        fails.append(f'ADX崩溃+浮盈应 CLOSE, 得 {d.action}')

    # 6. ADX 崩溃但浮亏 → HOLD (不在亏损时平)
    sup = _make_sup('BUY', 0.0010, 10.0)
    pos = FakePos(6, 'EURUSD', BUY, 1.1000, 1.0990, 1.0980, 1.1050)
    d = sup._evaluate(pos)
    if d.action != 'HOLD':
        fails.append(f'ADX崩溃+浮亏应 HOLD, 得 {d.action}')

    # 7. 已保本后不再重复 BREAKEVEN (SL 已在 entry)
    sup = _make_sup('BUY', 0.0010, 30.0)
    pos = FakePos(7, 'EURUSD', BUY, 1.1000, 1.1015, 1.1000, 1.1050)
    d = sup._evaluate(pos)
    if d.action == 'BREAKEVEN':
        fails.append('SL已在entry不应再 BREAKEVEN')
    if d.action not in ('TRAIL', 'HOLD'):
        fails.append(f'已保本应 TRAIL/HOLD, 得 {d.action}')

    if fails:
        print("SELFTEST FAIL:")
        for f in fails:
            print("  -", f)
        return False
    print("SELFTEST PASS: 7/7 决策路径正确 (CLOSE/BREAKEVEN/TRAIL/HOLD "
          "+ ADX崩溃/已保本边界)")
    return True


if __name__ == '__main__':
    run()
