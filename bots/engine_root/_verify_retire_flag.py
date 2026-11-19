# -*- coding: utf-8 -*-
"""验证 XAU RETIRE 旗标经 30min 循环重建后是否被 merge 回 (L5 持久化销格) — 只读+refresh, 不碰开单闸"""
import os, sys, time, json
import MetaTrader5 as mt5
sys.path.insert(0, r"E:\GoldstrategyEngine")
import edge_tracker
import importlib

DATA = r"E:\GoldstrategyEngine\data"
def xau_gf():
    return json.load(open(os.path.join(DATA,"edge_tracker.json"),encoding="utf-8"))["symbols"]["XAUUSD"]["gate_flags"]

assert mt5.initialize(), "mt5 init failed"
edge_tracker.refresh(mt5=mt5, days=30); mt5.shutdown()
print("[round0] refresh 后 XAU gate_flags =", json.dumps(xau_gf(), ensure_ascii=False))

ok = True
for i in range(3):
    mt5.initialize()
    importlib.reload(edge_tracker)
    edge_tracker.refresh(mt5=mt5, days=30)
    mt5.shutdown()
    gf = xau_gf()
    r = gf.get("retired") is True
    ok = ok and r
    print("[round%d] retired=%s scale=%s reason=%r" % (i+1, gf.get("retired"), gf.get("scale"), str(gf.get("retired_reason",""))[:40]))
print("\n连跑3轮 retired 全在 ?", ok, " -> L4 22:00 判据 retired===True", "命中✅" if ok else "未命中❌")
