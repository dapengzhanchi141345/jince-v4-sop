import csv, os
P = "data/live24_trades.csv"
rows = list(csv.reader(open(P, encoding="utf-8-sig")))
hdr = [h.strip() for h in rows[0]]
data = rows[1:]
def ts(r): return r[0]
# events present
from collections import Counter
print("events:", Counter(r[1] for r in data))
print("symbols sample:", Counter(r[2] for r in data).most_common(20))
# focus window 11-13 12:00 - 17:30 BJT
print("\n=== 2026-11-13 11:30 - 18:00 BJT rows ===")
for r in data:
    t = ts(r)
    if "2026-11-13" in t and "11:30" <= t[11:16] <= "18:00":
        print(f"{t} {r[1]:5s} {r[2]:8s} dir={r[3]:>2} adx={r[10]:>6} pnl={r[9]:>8}  {r[11][:40]}")
