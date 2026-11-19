import csv
from collections import Counter
P = "data/live24_trades.csv"
rows = list(csv.reader(open(P, encoding="utf-8-sig")))
data = [r for r in rows[1:]]
def g(r,i): return r[i] if i < len(r) else ""
# The task evidence: 11-13 13:00 BJT coin 4-leg + 16:01 BJT JPY/CAD 3-leg all-loss.
# Find all OPENs on 11-13 grouped by 15-min bucket, list symbols+dir
print("=== 11-13 all OPEN, bucketed (BJT) ===")
for r in data:
    t=g(r,0)
    if "2026-11-13" in t and g(r,1)=="OPEN":
        print(f"{t[11:16]} {g(r,2):9s} dir={g(r,3):>2} adx={g(r,10):>6} {g(r,11)[:28]}")
