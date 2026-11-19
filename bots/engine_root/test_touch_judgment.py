# -*- coding: utf-8 -*-
"""test_touch_judgment.py — 触价判定回归测试 (L5, 2026-11-02, 治 C 单复发)
目的: 用合成 K 线 (不依赖 MT5 终端) 实锤 backtest_engine.simulate_signal 的
  SL/TP 触价方向 + 赢单计数 不再有历史 bug:
  [历史 bug 2026-10-09 前] 空头 tp_hit 误写 lo[k] >= real_tp (判反):
    空头 TP 在入场价下方, 正确应是"low 下探到 real_tp"(lo<=real_tp);
    旧式 lo>=real_tp 在"价格向上(空头亏)"时恒真 -> 空头腿假胜 ~99.6% 虚高
    (TREND 8901 笔即此因), 全宇宙回测 wr 虚高, 01:30 验收枪连打回 rc=1.
  本测试 4 场景:
    1) 空头 + 上涨(不利) -> 必须判 SL 亏 (pnl<0), 不得假胜
    2) 空头 + 下跌(有利) -> 判 TP 赢 (pnl>0)
    3) 多头 + 下跌(不利) -> 判 SL 亏 (pnl<0)
    4) 多头 + 上涨(有利) -> 判 TP 赢 (pnl>0)
  任一不成立 = 触价口径复发, 直接 FAIL (防复发闸, 回测引擎每次发枪前可跑).
  运行: ATE/任意含 numpy+pandas 解释器, cwd=E:\\GoldstrategyEngine
"""
import sys, os
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_engine as E


def _df(opens):
    """由逐bar开盘价构造合成 H1 DataFrame (high=open+0.5, low=open-0.5)."""
    n = len(opens)
    o = [float(x) for x in opens]
    h = [x + 0.5 for x in o]
    l = [x - 0.5 for x in o]
    c = o[:]  # close=open (合成, 不影响 SL/TP high/low 判定)
    # MT5 契约: time 是 int64 unix 秒 (get_rates 产 pd.DataFrame(mt5_struct), time=int64).
    # 用 int64 才能模拟 //86400 出 int 天 (pandas Timestamp 会出 Timedelta64 -> swap 崩 ufunc).
    import numpy as _np
    t = _np.arange(n, dtype=_np.int64) * 3600 + 1767225600  # 1h 步长 unix 秒
    return pd.DataFrame({'time': t, 'open': o, 'high': h, 'low': l, 'close': c})


def _sim(df, side, entry, sl, tp, bar=0):
    sig = {'bar': bar, 'side': side, 'entry': entry, 'sl': sl, 'tp': tp, 'strat': 'REG'}
    return E.simulate_signal(df, sig, spread_pts=0, point=0.01,
                              swap_long=0.0, swap_short=0.0, lot=1.0,
                              pip=10.0, pip_usd=1.0)


def main():
    # 上涨市: 逐bar开盘 101 -> 113 (对空头不利, 对多头有利)
    up = _df([100, 101, 103, 105, 107, 109, 111, 113, 115, 117, 119, 121])
    # 下跌市: 逐bar开盘 99 -> 87 (对空头有利, 对多头不利)
    dn = _df([100, 99, 97, 95, 93, 91, 89, 87, 85, 83, 81, 79])

    cases = []
    # 1) 空头 + 上涨(不利): entry100 sl110 tp90 -> 应 SL 亏 (pnl<0)
    cases.append(('空头上涨->亏(SL)', _sim(up, -1, 100, 110, 90), -1))
    # 2) 空头 + 下跌(有利): entry100 sl110 tp90 -> 应 TP 赢 (pnl>0)
    cases.append(('空头下跌->赢(TP)', _sim(dn, -1, 100, 110, 90), +1))
    # 3) 多头 + 下跌(不利): entry100 sl90 tp110 -> 应 SL 亏 (pnl<0)
    cases.append(('多头下跌->亏(SL)', _sim(dn, +1, 100, 90, 110), -1))
    # 4) 多头 + 上涨(有利): entry100 sl90 tp110 -> 应 TP 赢 (pnl>0)
    cases.append(('多头上涨->赢(TP)', _sim(up, +1, 100, 90, 110), +1))

    ok = True
    print('触价判定回归测试 (合成数据, 无 MT5):')
    for name, pnl, want_sign in cases:
        if pnl is None:
            print('  [FAIL] %-18s -> None(数据不足?)' % name); ok = False; continue
        got = 1 if pnl > 0 else (-1 if pnl < 0 else 0)
        passed = (got == want_sign)
        ok = ok and passed
        print('  [%s] %-18s pnl=%+.3f 期望%s' %
              ('PASS' if passed else 'FAIL', name, pnl,
               '正(赢)' if want_sign > 0 else '负(亏)'))
    print('\n结论: %s' % ('触价口径正确, 空头腿无假胜虚高 (C单可放行)' if ok
                        else '触价口径异常, 虚高复发, 必须修'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
