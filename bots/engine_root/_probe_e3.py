import csv, datetime as dt
from collections import Counter
P = "data/live24_trades.csv"
rows = list(csv.reader(open(P, encoding="utf-8-sig")))
data = [r for r in rows[1:]]
def g(r,i): return r[i] if i < len(r) else ""
# 1) coin opens 11-13 12:45-13:15 BJT
print("=== COIN opens 11-13 12:45-13:15 BJT ===")
COINS={"AVXUSD","DOGEUSD","SOLUSD","UNIUSD","LNKUSD","LTCUSD","BTCUSD","ETHUSD","BNBUSD","XLMUSD","XRPUSD","POLUSD"}
for r in data:
    t=g(r,0)
    if "2026-11-13" in t and "12:45"<=t[11:16]<="13:15" and g(r,1)=="OPEN" and g(r,2) in COINS:
        print(f"{t} {g(r,2):8s} dir={g(r,3)} adx={g(r,10)}")
# 2) JPY/CAD family 11-13 15:45-16:15 BJT (USDJPY/CADJPY/JPY/CAD legs)
print("\n=== JPY/CAD opens 11-13 15:45-16:15 BJT ===")
for r in data:
    t=g(r,0)
    if "2026-11-13" in t and "15:45"<=t[11:16]<="16:15" and g(r,1)=="OPEN" and ("JPY" in g(r,2) or "CAD" in g(r,2) or g(r,2) in ("USDZAR","CHFZAR")):
        print(f"{t} {g(r,2):8s} dir={g(r,3)} adx={g(r,10)}")
# 3) count SKIP_H1 for XAUUSD 11-11 19:45-21:51
print("\n=== XAUUSD SKIP_H1 11-11 19:45-21:51 BJT count ===")
c=0
for r in data:
    t=g(r,0)
    if "2026-11-11" in t and "19:45"<=t[11:16]<="21:51" and g(r,1)=="SKIP_H1" and g(r,2)=="XAUUSD":
        c+=1
print("XAUUSD SKIP_H1 count:", c)
# 4) date span of whole csv
allds=[g(r,0)[:10] for r in data if g(r,0)]
print("\ncsv date span:", min(allds), "->", max(allds), "rows", len(data))
# OPEN vs CLOSE per 30d
last30=[r for r in data if "2026-10-15"<=g(r,0)[:10]<="2026-11-14"]
print("last-30d rows:", len(last30), "OPEN:", sum(1 for r in last30 if g(r,1)=='OPEN'))
