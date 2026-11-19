#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""销账重跑件 (ATR 最小止损闸修复后): 18 家脏格 + universe 内 56 家全量重跑, 双分母 B-A 重报.
新引擎口径: analyze248_all.slgate() 已加最小止损闸 (sl_dist < max(0.5*ATR, 1e-5*|entry|, 1e-5*point*100) -> SKIP).
0 写闸源, 0 进 live. 跑法: A248_DIRTY=k A248_DIRTY_N=2 python analyze248_slfix.py
输出: data/analyze248_slfix_w{k}.json (增量断点续) + 汇总 data/analyze248_slfix_summary.json (双分母 B-A)
"""
import os, sys, json, datetime, pickle, time
os.chdir(r"E:\GoldstrategyEngine"); sys.path.insert(0, r"E:\GoldstrategyEngine")
import numpy as np
import analyze248_all as A
import symbol_universe as su

K = int(os.environ.get("A248_DIRTY", "0")); NK = int(os.environ.get("A248_DIRTY_N", "2"))
OUT = f"data/analyze248_slfix_w{K}.json"

# 旧 8 件里 |A|或|B| cumR > 1000 的脏格名单 (2026-10-19 上午件, 实拉 18 家 = 17 in_universe + HSCHKD 盘外)
DIRTY18 = ["AUDNZD","AUS200","DOTUSD","ETHUSD","EURTRY","HK50","HSCHKD","NAS100","SOLUSD",
           "SWI20","UK100","UNIUSD","US2000","US30","USDCZK","USDTRY","XLMUSD","XTZUSD"]
# universe 内 56 家有信号品种 (金线域分母重报用)  -> 直接从旧件取 universe 内全量
def old_universe_syms():
    rows = {}
    for f in sorted(x for x in os.listdir("data") if x.startswith("analyze248_w") and x.endswith(".json")):
        d = json.load(open(f"data/{f}", encoding="utf-8"))
        for sym, s in d.get("syms", {}).items():
            rows[sym] = s
    return {sym for sym, s in rows.items() if s.get("in_universe")}

def one(sym):
    fp = f"data/cache248/{sym.replace('.', '_')}.pkl"
    if not os.path.exists(fp):
        return {"err": "no cache pkl"}
    pkt = pickle.load(open(fp, "rb"))
    cfg = dict(su.UNIVERSE.get(sym, {}))
    h1, h4, d1 = pkt["h1"], pkt["h4"], pkt["d1"]
    import pasd_fusion as PF
    sigs = PF.gen_pasd(h1, h4, d1, cfg)
    for s in sigs: s["tp"] = s["entry"] + s["side"] * A.RR * abs(s["entry"] - s["sl"])
    zs = PF._detect_supply_demand_zones(h1['high'].values, h1['low'].values, h1['close'].values)
    atr_v = PF._atr(h1['high'].values.astype(float), h1['low'].values.astype(float), h1['close'].values.astype(float))
    sy = {"n_sigs": len(sigs), "in_universe": sym in su.UNIVERSE, "slgate_applied": True}
    # 逐笔 sl_dist 计数 (归因锚③)
    sds = [abs(s["entry"] - s["sl"]) for s in sigs]
    sy["sl_dist_below_1e4"] = int(sum(1 for x in sds if x < 1e-4))
    sy["slgate_skipped_sigs"] = int(sum(1 for s in sigs if abs(s["entry"]-s["sl"]) < A.slgate(atr_v[int(s["bar"])], s["entry"], pkt["point"])))
    wrs = {}
    for mode, tag in [("A", "A_基线_不加"), ("C", "C_加1到区"), ("B", "B_加2中点+到区")]:
        rows_ = []
        for s in sigs:
            r = A.sim(pkt, h1, s, A.add_levels(s, zs['demand'], zs['supply'], mode), cfg, atr_v)
            if r is not None: rows_.append(r)
        st = A.stat([r["R"] for r in rows_])
        if rows_:
            st["netUSD_001"] = round(sum(r["pnl"] for r in rows_), 2)
            st["dd_USD_001"] = round(A.run_dd([r["pnl"] for r in rows_]), 2)
        sy[tag] = st; wrs[tag] = st.get("wr", 0.0)
    sy["z_B_vs_A"] = A.ztest(wrs["A_基线_不加"], sy["A_基线_不加"].get("n", 0),
                              wrs["B_加2中点+到区"], sy["B_加2中点+到区"].get("n", 0))
    sy["judge_noslgate"] = "R_all_le_1000" if max(abs(sy["A_基线_不加"].get("cumR", 0)),
                                                    abs(sy["B_加2中点+到区"].get("cumR", 0))) <= 1000 else "DIRTY_REMAIN"
    return sy

def main():
    t0 = time.time()
    # K0 = 18 脏格重跑; K1 = 同 18 家做第二把交叉验 (双 worker 交叉销账, 不重复 universe 全域重跑)
    res = {"generated": datetime.datetime.now().isoformat(), "worker": K,
           "note": "ATR slgate 修复件: 最小止损闸 sl_dist<max(0.5*ATR,1e-5*|entry|,1e-5*point*100)->SKIP; 0写闸源 0进live; 双 worker 交叉验 18 家"}
    if os.path.exists(OUT):
        try: res.update(json.load(open(OUT, encoding="utf-8")))
        except Exception: pass
    mine = DIRTY18
    done = set(res.get("syms", {}))
    for sym in mine:
        if sym in done: continue
        sy = one(sym)
        res.setdefault("syms", {})[sym] = sy
        json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        if K == 0:
            print(f"{sym}: slgate_skip={sy.get('slgate_skipped_sigs')} A={sy['A_基线_不加'].get('cumR')} "
                  f"B={sy['B_加2中点+到区'].get('cumR')} {sy['judge_noslgate']} | {time.time()-t0:.0f}s", flush=True)
    res["finished"] = datetime.datetime.now().isoformat()
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"slfix worker{K} 完 -> {OUT} {round((time.time()-t0)/60,1)}min", flush=True)

if __name__ == "__main__":
    main()
