# -*- coding: utf-8 -*-
"""
V3 单元测试: 验证 position_supervisor 的「小止损大盈利」改造。
不连 MT5(纯逻辑/数值验证), mock guardian.market_state / live_bias。
"""
import numpy as np
import MetaTrader5 as mt5
import position_supervisor as ps


class FakeGuardian:
    def __init__(self, atr, adx, high, low, close, ii, bias):
        self._ms = {'atr_now': atr, 'adx_now': adx,
                    'high': high, 'low': low, 'close': close, 'i': ii}
        self._bias = bias

    def market_state(self, sym):
        return self._ms

    def live_bias(self, sym, strategy):
        return self._bias, 'test'


class FakePos:
    def __init__(self, symbol, ptype, open_, cur, sl, ticket=1, t=0):
        self.symbol = symbol
        self.type = ptype          # mt5.POSITION_TYPE_BUY / SELL
        self.price_open = open_
        self.price_current = cur
        self.sl = sl
        self.ticket = ticket
        self.time = t


def mk_arrays(n=40, lo_val=2000.0, hi_val=2050.0, cl_val=2030.0):
    low = np.full(n, lo_val, dtype=float)
    high = np.full(n, hi_val, dtype=float)
    close = np.full(n, cl_val, dtype=float)
    return high, low, close


PASS = 0
FAIL = 0


def check(name, dec, expect_action, expect_sl=None):
    global PASS, FAIL
    ok = (dec.action == expect_action)
    if expect_sl is not None and dec.new_sl is not None:
        ok = ok and abs(dec.new_sl - expect_sl) < 1e-6
    tag = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    extra = f" new_sl={dec.new_sl}" if dec.new_sl is not None else ""
    print(f"  [{tag}] {name}: action={dec.action} (expect {expect_action}){extra} :: {dec.reason[:60]}")


def main():
    ATR = 5.0           # XAUUSD 近似 ATR(美元)
    PIP = 0.01
    EARLY = ps.PositionSupervisor().early_be_mult * ATR      # V3.2: 0.2*5=1.0
    ACT = ps.PositionSupervisor().trail_activate_mult * ATR  # 1.5*5=7.5

    # 通用: 40根, ii=39
    sup = ps.PositionSupervisor(dry_run=True)
    sup.guardian = None  # 占位, 每场景单独设

    print(f"ATR={ATR} EARLY_BE阈值={EARLY} 激活阈值={ACT}")

    # ── 场景1: BUY 浮盈超早保本阈值, 原SL在下方 → 保本锁 ──
    h, l, c = mk_arrays(lo_val=1990, hi_val=2010, cl_val=2002)
    g = FakeGuardian(ATR, 30, h, l, c, 39, 'BUY')
    sup.guardian = g
    pos = FakePos('XAUUSD', mt5.POSITION_TYPE_BUY, 2000.0, 2002.5, 1997.0)
    d = sup._evaluate(pos)
    check("S1 BUY early-BE lock", d, 'BREAKEVEN', expect_sl=2000.0)

    # ── 场景2: BUY 已保本(SL=开仓价), 浮盈<激活 → HOLD(不回放) ──
    g = FakeGuardian(ATR, 30, h, l, c, 39, 'BUY')
    sup.guardian = g
    pos = FakePos('XAUUSD', mt5.POSITION_TYPE_BUY, 2000.0, 2002.5, 2000.0)
    d = sup._evaluate(pos)
    check("S2 BUY already-BE hold", d, 'HOLD')

    # ── 场景3: BUY 浮盈>激活, 20根低点抬高 → 吊灯追踪(锁利>开仓价) ──
    # 构造: 当前价2050, 窗口最低=2030 → raw=2030-12.5=2017.5 → stop=max(2000,2017.5)=2017.5
    h3, l3, c3 = mk_arrays(lo_val=2030.0, hi_val=2060.0, cl_val=2050.0)
    g = FakeGuardian(ATR, 35, h3, l3, c3, 39, 'BUY')
    sup.guardian = g
    pos = FakePos('XAUUSD', mt5.POSITION_TYPE_BUY, 2000.0, 2050.0, 2000.0)
    d = sup._evaluate(pos)
    check("S3 BUY chandelier trail", d, 'TRAIL', expect_sl=2017.5)

    # ── 场景4: BUY 浮亏 + 信号反向 → 风险平仓(小损≈0) ──
    g = FakeGuardian(ATR, 30, h, l, c, 39, 'SELL')
    sup.guardian = g
    pos = FakePos('XAUUSD', mt5.POSITION_TYPE_BUY, 2000.0, 1998.0, 1997.0)
    d = sup._evaluate(pos)
    check("S4 BUY loss+reverse close", d, 'CLOSE')

    # ── 场景5: BUY 微浮盈(<早保本阈值0.2×ATR=1.0) + 信号反向 → 不砍(等触及保本) ──
    # V3.2: 早保本阈值收紧到 0.2×ATR(=1.0 价位/100pip); 此处浮盈仅 0.5(<阈值)
    # → 尚未触发保本, 容忍反向, 不主动平仓(让利润奔跑至保本触发).
    g = FakeGuardian(ATR, 30, h, l, c, 39, 'SELL')
    sup.guardian = g
    pos = FakePos('XAUUSD', mt5.POSITION_TYPE_BUY, 2000.0, 2000.5, 1997.0)
    d = sup._evaluate(pos)
    check("S5 BUY sub-threshold no-clip", d, 'HOLD')

    # ── 场景6: BUY 浮亏 + ADX崩溃(<18) → 平仓 ──
    g = FakeGuardian(ATR, 10, h, l, c, 39, 'NEUTRAL')
    sup.guardian = g
    pos = FakePos('XAUUSD', mt5.POSITION_TYPE_BUY, 2000.0, 1998.0, 1997.0)
    d = sup._evaluate(pos)
    check("S6 BUY loss+ADX-collapse close", d, 'CLOSE')

    # ── 场景7: SELL 对称 早保本 ──
    g = FakeGuardian(ATR, 30, h, l, c, 39, 'SELL')
    sup.guardian = g
    pos = FakePos('XAUUSD', mt5.POSITION_TYPE_SELL, 2000.0, 1997.5, 2003.0)
    d = sup._evaluate(pos)
    check("S7 SELL early-BE lock", d, 'BREAKEVEN', expect_sl=2000.0)

    # ── 场景8: SELL 浮盈>激活, 20根高点压低 → 吊灯追踪(锁利<开仓价) ──
    # 当前价1950, 窗口最高=1970 → raw=1970+12.5=1982.5 → stop=min(2000,1982.5)=1982.5
    h8, l8, c8 = mk_arrays(lo_val=1940.0, hi_val=1970.0, cl_val=1950.0)
    g = FakeGuardian(ATR, 35, h8, l8, c8, 39, 'SELL')
    sup.guardian = g
    pos = FakePos('XAUUSD', mt5.POSITION_TYPE_SELL, 2000.0, 1950.0, 2000.0)
    d = sup._evaluate(pos)
    check("S8 SELL chandelier trail", d, 'TRAIL', expect_sl=1982.5)

    print(f"\n结果: PASS={PASS} FAIL={FAIL}")
    return FAIL == 0


if __name__ == "__main__":
    ok = main()
    print("ALL_OK" if ok else "HAS_FAILURE")
