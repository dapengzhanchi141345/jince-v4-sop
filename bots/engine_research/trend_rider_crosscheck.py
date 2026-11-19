# -*- coding: utf-8 -*-
"""
落码一致性对拍: tools/trend_rider_v1.py  vs  research/trend_riding_optimize.py
=============================================================================
目的: 防"研究一套、实盘另一套"。同入场、同 bar 序列下, 模块 TrendRider 的
      realized_r 必须与回测 sim_wide 的返回值逐笔一致(容差 1e-9)。
覆盖: 8品种 × 全部入场点 × 两组参数(宽游程 / 金字塔), 统计不一致笔数。
"""
import os, sys
sys.path.insert(0, r"E:/GoldstrategyEngine")
sys.path.insert(0, r"E:/GoldstrategyEngine/research")
sys.path.insert(0, r"E:/GoldstrategyEngine/tools")

import trend_riding_optimize as B
from trend_rider_v1 import TrendRider

EMA = 150
TRAIL = "SW72"


def sim_via_module(h1, atr, e, dirn, pyramid):
    """用落码模块重演回测 sim_wide 的时序, 返回 net R。"""
    a0 = atr[e]
    if a0 <= 1e-8:
        return None
    rider = TrendRider(h1[e][3], dirn, a0, pyramid=pyramid, entry_bar=h1[e])
    last = min(e + B.MAX_BARS, len(h1) - 1)
    for j in range(e + 1, last + 1):
        act = rider.update(h1[j], atr[j] if atr[j] > 0 else a0)
        if act == "CLOSE":
            return rider.realized_r
    rider.force_close()
    return rider.realized_r


def main():
    total = 0; mism = 0; maxdiff = 0.0
    worst = None
    for sym in B.SYMS:
        h1 = B.load_h1(sym); d1 = B.load_d1(sym)
        if h1 is None or d1 is None or len(h1) < 200 or len(d1) < EMA:
            continue
        atr = B.atr_arr(h1)
        d1e = B.ema_arr([b[3] for b in d1], EMA)
        ents = B.gen_trend_entries(h1, atr, d1, d1e)
        s_tot = 0; s_mis = 0
        for (e, d) in ents:
            for pyr in (False, True):
                rb = B.sim_wide(h1, atr, e, d, TRAIL, pyr)
                rm = sim_via_module(h1, atr, e, d, pyr)
                if rb is None or rm is None:
                    continue
                s_tot += 1; total += 1
                diff = abs(rb - rm)
                if diff > maxdiff:
                    maxdiff = diff; worst = (sym, e, d, pyr, rb, rm)
                if diff > 1e-9:
                    s_mis += 1; mism += 1
        print("  %-7s 笔数=%5d 不一致=%4d" % (sym, s_tot, s_mis))
    print("\n对拍总计: %d 笔  不一致 %d 笔  最大绝对差=%.12g" % (total, mism, maxdiff))
    if worst:
        print("最大差样本: sym=%s e=%d dirn=%d pyr=%s 回测=%.6f 模块=%.6f" % worst)
    print("VERDICT:", "PASS 研究与落码完全一致" if mism == 0 else "FAIL 存在偏差, 禁止上线")
    return 0 if mism == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
