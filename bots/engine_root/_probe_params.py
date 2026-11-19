import json, os
p = json.load(open("data/practice_params_all_symbols.json", encoding="utf-8"))
want = ["XAUUSD","EURUSD","BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD","KSMUSD"]
print("top-level type:", type(p).__name__, "n keys:", len(p) if isinstance(p,dict) else "n/a")
if isinstance(p, dict):
    print("sample keys:", list(p.keys())[:15])
    for s in want:
        print(f"{s:8s} ->", p.get(s, "<ABSENT>"))
