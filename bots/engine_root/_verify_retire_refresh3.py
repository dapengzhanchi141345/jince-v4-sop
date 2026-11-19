
import sys, os, json
sys.path.insert(0, r"E:\GoldstrategyEngine")
import MetaTrader5 as mt5, edge_tracker
DATA = r"E:\GoldstrategyEngine\data"
mt5.initialize()
ok = True
for i in range(3):
    edge_tracker.refresh(mt5=mt5, days=30)
    e = json.load(open(os.path.join(DATA,"edge_tracker.json"), encoding="utf-8"))
    r = e["symbols"]["XAUUSD"]["gate_flags"].get("retired") is True
    ok = ok and r
    print("第%d轮 refresh 后 gate_flags.retired=%s scale=%s" % (i+1, r, e["symbols"]["XAUUSD"]["gate_flags"].get("scale")))
mt5.shutdown()
print("-> @chief 22:00 复读判据 retired===True:", "命中(连3轮不抹)" if ok else "未命中")
