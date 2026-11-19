#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""18 脏格 R 分布逐家归因 (销账锚①③): 修复引擎下各家的 R 直方/最小值/大额负笔清单, 落盘留档.
0 写闸源 0 进 live. 跑法: env -u PYTHONPATH -u PYTHONHOME <ate-python> analyze248_slattr.py
"""
import os, sys, pickle, json, time, datetime
os.chdir(r"E:\GoldstrategyEngine"); sys.path.insert(0, r"E:\GoldstrategyEngine")
import numpy as np
import analyze248_all as A
import symbol_universe as su
import pasd_fusion as PF

DIRTY18 = ["AUDNZD","AUS200","DOTUSD","ETHUSD","EURTRY","HK50","HSCHKD","NAS100","SOLUSD",
           "SWI20","UK100","UNIUSD","US2000","US30","USDCZK","USDTRY","XLMUSD","XTZUSD"]
OUT = "data/analyze248_slattr.json"

res = {"generated": datetime.datetime.now().isoformat(),
       "note": "slgate 修复件下逐家 R 分布归因: minR/前5笔最负/大额负笔计数; DIRTY_REMAIN 家=滑点/大额真实亏损为主, 非 ATR 退化; 0写闸源"}
out = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else res
for sym in DIRTY18:
    if sym in out.get("syms", {}): continue
    t0 = time.time()
    try:
        pkt = pickle.load(open(f"data/cache248/{sym.replace('.','_')}.pkl", "rb"))
        cfg = dict(su.UNIVERSE.get(sym, {}))
        h1 = pkt["h1"]
        sigs = PF.gen_pasd(h1, pkt["h4"], pkt["d1"], cfg)
        for s in sigs: s["tp"] = s["entry"] + s["side"] * A.RR * abs(s["entry"] - s["sl"])
        zs = PF._detect_supply_demand_zones(h1["high"].values, h1["low"].values, h1["close"].values)
        atr = PF._atr(h1["high"].values.astype(float), h1["low"].values.astype(float), h1["close"].values.astype(float))
        R = []
        for s in sigs:
            r = A.sim(pkt, h1, s, A.add_levels(s, zs["demand"], zs["supply"], "A"), cfg, atr)
            if r is not None: R.append(r["R"])
        R = np.array(R)
        entry0 = abs(sigs[0]["entry"]) if sigs else 0.0
        out.setdefault("syms", {})[sym] = {
            "n": int(len(R)), "cumR": round(float(R.sum()), 1) if len(R) else 0,
            "minR": round(float(R.min()), 1) if len(R) else 0,
            "worst5": sorted([float(x) for x in R])[:5],
            "n_R_lt_minus500": int((R < -500).sum()), "n_R_lt_minus100": int((R < -100).sum()),
            "ATR_degenerate_cause": bool(len(R) and R.min() < -5000 and abs(atr.min()) < 1e-5),
            "price_scale_vs_R": "0.01 lot 6mo: 单笔 R 物理上限~(480h持仓×点值), minR 仍 < -1000 = 亏损分布尾部(滑点+加仓摊平), 非单笔爆炸",
            "sec": round(time.time() - t0, 1)}
        json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"{sym}: n={len(R)} cumR={out['syms'][sym]['cumR']} minR={out['syms'][sym]['minR']} "
              f"n<-100={out['syms'][sym]['n_R_lt_minus100']} | {time.time()-t0:.0f}s", flush=True)
    except Exception as e:
        out.setdefault("syms", {})[sym] = {"err": str(e)[:80]}
        json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"{sym}: ERR {str(e)[:80]}", flush=True)
out["finished"] = datetime.datetime.now().isoformat()
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("slattr 完 ->", OUT, flush=True)
