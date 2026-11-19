# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r"E:\GoldstrategyEngine")
import _night_fam4_m30_exit as fam4
import _rd_mom_veto_gate as mv

sym = "BTCUSD"
ev, ctx = fam4.build(sym)
r1 = fam4.replay(ev, ctx, "P4")
r2 = mv.replay_p4_with_i0(ev, ctx)
diffs = [(a, b) for a, b in zip(r1, r2) if not (a[1] == b[1] and a[2] == b[2] and abs(a[3] - b[3]) < 1e-9)]
print("n_diff:", len(diffs))
for a, b in diffs[:5]:
    print("orig:", a, "copy:", b)
