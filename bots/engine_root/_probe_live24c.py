import csv, os
from collections import Counter
P = "data/live24_trades.csv"
rows = list(csv.reader(open(P, encoding="utf-8-sig")))
data = [r for r in rows[1:]]
def g(r,i): return r[i] if i < len(r) else ""
# 11-13 window BJT
print("=== 2026-11-13 11:00-18:30 BJT (all events, open/close only) ===")
for r in data:
    t=g(r,0)
    if "2026-11-13" in t and "11:00" <= t[11:16] <= "18:30" and g(r,1) in ("OPEN","CLOSE","MAXHOLD硬平","B0_EXIT","LOSECUT斩亏"):
        print(f"{t} {g(r,1):10s} {g(r,2):8s} dir={g(r,3):>2} adx={g(r,10):>6} pnl={g(r,9):>8}  {g(r,11)[:45]}")
print("\n=== OPEN events on 11-13 12:30-17:30 BJT (batch evidence) ===")
for r in data:
    t=g(r,0)
    if "2026-11-13" in t and "12:30" <= t[11:16] <= "17:30" and g(r,1)=="OPEN":
        print(f"{t} {g(r,2):8s} dir={g(r,3):>2} entry={g(r,5)} adx={g(r,10)}")
print("\n=== 11-11 19:30-22:30 BJT SKIP_H1 ===")
for r in data:
    t=g(r,0)
    if "2026-11-11" in t and "19:30" <= t[11:16] <= "22:30" and "H1" in g(r,1):
        print(f"{t} {g(r,1):12s} {g(r,2):8s} dir={g(r,3):>2} {g(r,11)[:50]}")
