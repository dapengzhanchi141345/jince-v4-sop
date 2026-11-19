import csv, os, datetime as dt
P = "data/live24_trades.csv"
rows = list(csv.reader(open(P, encoding="utf-8-sig")))
print("total rows:", len(rows))
print("HEADER:", rows[0])
print("row1:", rows[1])
print("row2:", rows[2])
# column count
print("ncols:", len(rows[0]))
# Find the time column index (guess by name)
hdr = [h.strip() for h in rows[0]]
for i,h in enumerate(hdr):
    print(i, repr(h))
