
import numpy as np, datetime as dt
z = np.load("E:/GoldstrategyEngine/data/tf_cache/XAUUSD_M30.npz")
t = z["t"]; print("XAUUSD_M30 rows", len(t), dt.datetime.utcfromtimestamp(int(t[0])), "->", dt.datetime.utcfromtimestamp(int(t[-1])))
z2 = np.load("E:/GoldstrategyEngine/data/tf_cache/XAUUSD_D1.npz")
print("XAUUSD_D1 rows", len(z2["t"]), dt.datetime.utcfromtimestamp(int(z2["t"][0])), "->", dt.datetime.utcfromtimestamp(int(z2["t"][-1])))
import json
p = json.load(open(r"E:/GoldstrategyEngine/data/practice_params_all_symbols.json", encoding="utf-8"))
print("params keys:", list(p.keys())[:12])
print("XAUUSD:", p.get("XAUUSD"))
