
import json, os, time
base = r"E:\GoldstrategyEngine\data"
# 1) training_history.json 结构
th_p = os.path.join(base, "training_history.json")
if os.path.exists(th_p):
    th = json.load(open(th_p, encoding="utf-8"))
    print("training_history:", type(th).__name__)
    if isinstance(th, dict):
        print("  keys:", list(th.keys())[:10])
        for k in list(th.keys())[:3]:
            v = th[k]
            print("   ", k, "->", type(v).__name__, (len(v) if isinstance(v,(list,dict)) else v))
    elif isinstance(th, list):
        print("  len:", len(th))
        if th: print("  sample:", json.dumps(th[0], ensure_ascii=False)[:300])
# 2) MT5 连得上吗 + 能否 history_deals_get
try:
    import MetaTrader5 as mt5
    ok = mt5.initialize()
    print("MT5 initialize:", ok)
    if ok:
        acc = mt5.account_info()
        print("account:", acc.login if acc else None, "equity:", getattr(acc,'equity',None) if acc else None)
        deals = mt5.history_deals_get(time.time()-30*86400, time.time())
        print("history_deals 30d:", len(deals) if deals else 0)
        if deals:
            d = deals[0]
            print("deal fields sample:", [f for f in d._asdict().keys()][:40])
            mt5.shutdown()
except Exception as e:
    print("MT5 probe fail:", repr(e))
