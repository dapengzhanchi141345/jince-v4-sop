# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r"E:\GoldstrategyEngine")
import _night_fam4_m30_exit as fam4
import _rd_mom_veto_gate as mv

# 原版 (ts,side,R) vs 副本 (i0,ts,side,R) -> 对齐比 ts/side/R
for sym in ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]:
    ev, ctx = fam4.build(sym)
    r1 = fam4.replay(ev, ctx, "P4")
    r2 = mv.replay_p4_with_i0(ev, ctx)
    same = len(r1) == len(r2) and all(
        a[0] == b[1] and a[1] == b[2] and abs(a[2] - b[3]) < 1e-9 for a, b in zip(r1, r2))
    print(sym, "n=", len(r1), "MATCH" if same else "MISMATCH!")
    if not same:
        for a, b in zip(r1, r2):
            if not (a[0] == b[1] and a[1] == b[2] and abs(a[2] - b[3]) < 1e-9):
                print("  diff:", a, "vs", b)
                break
        break
