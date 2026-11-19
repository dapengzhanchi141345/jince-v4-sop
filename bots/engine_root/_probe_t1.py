
import json, glob, os
base = r"E:\GoldstrategyEngine\data"
# 找 universe / T1 定义
for cand in ["symbol_universe.json","universe.json","t1_symbols.json"]:
    p = os.path.join(base, cand)
    if os.path.exists(p):
        d = json.load(open(p, encoding="utf-8"))
        print("FOUND", cand, "->", list(d.keys())[:8] if isinstance(d, dict) else ("list", len(d)))
# 从 crypto_pending 常量里取 T1（最权威）
import importlib
try:
    import sys; sys.path.insert(0, r"E:\GoldstrategyEngine")
    m = importlib.import_module("multi_agent.trading.crypto_pending")
    for attr in dir(m):
        if "T1" in attr or "UNIVERSE" in attr.upper() or "SYMBOLS" in attr.upper():
            v = getattr(m, attr)
            if isinstance(v, (list, tuple, set, dict)) and v:
                print(attr, "=", (list(v)[:20] if isinstance(v,(list,set,tuple)) else list(v.keys())[:20]))
except Exception as e:
    print("import fail:", e)
