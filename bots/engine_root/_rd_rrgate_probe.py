import os, json, datetime, collections
import numpy as np
DATA = "E:/GoldstrategyEngine/data"
import importlib.util, sys
# load the verify script as module without running main
src = open("E:/GoldstrategyEngine/_rd_rrgate_verify.py", encoding="utf-8").read()
g = {"__file__": "E:/GoldstrategyEngine/_rd_rrgate_verify.py", "__name__": "_rdx"}
mod_src = src.replace('if __name__ == "__main__":\n    main()', '')
exec(compile(mod_src, "_rdx", "exec"), g)
load_h1 = g["load_h1"]
refl = json.load(open(DATA + "/advisory_reflection.json", encoding="utf-8"))
recs = [r for r in refl["records"] if r[4] >= 0.7 and r[3] in ("LONG", "SHORT")]
hist = {}
for f in sorted(os.listdir(DATA + "/advisory/history")):
    dd = json.load(open(DATA + "/advisory/history/" + f, encoding="utf-8"))
    for sec in dd.get("sections", []):
        for it in sec.get("items", []):
            if it.get("status") != "ok" or not it.get("direction"):
                continue
            key = (it["sym"], it.get("beijing_date") or f.replace(".json", ""), sec.get("session"))
            hist[key] = it
cnt = collections.Counter()
per_sym = collections.Counter()
for r in recs:
    key = (r[0], r[1], r[2])
    it = hist.get(key)
    sym = r[0]
    cn = {"JPN225": "JP225", "GER40": "DE30"}.get(sym, sym)
    if not os.path.exists("%s/%s_H1.csv" % (DATA, cn)):
        cnt["no_csv"] += 1; continue
    d2 = load_h1(sym)
    pos = int(np.searchsorted(d2["times"], float(it["ts"]), side="right"))
    if pos >= len(d2["h"]):
        cnt["ts_out"] += 1; per_sym[sym] -= 1
    else:
        cnt["ok"] += 1; per_sym[sym] += 1
print(cnt)
print("per_sym ok-ts:", dict(per_sym))
# ts range vs data ranges
d2 = load_h1("EURUSD")
print("EURUSD data:", d2["ts"][0], "->", d2["ts"][-1])
d3 = load_h1("JPN225")
print("JPN225 data:", d3["ts"][0], "->", d3["ts"][-1])
print("event ts sample:", datetime.datetime.fromtimestamp(1791122455), "(utc+8 wall?)")
