import csv, collections
def probe(sym):
    p = f"E:/GoldstrategyEngine/data/{sym}_H1.csv"
    data = collections.defaultdict(dict)
    with open(p, encoding='utf-8') as f:
        rdr = csv.reader(f); next(rdr)
        for row in rdr:
            if len(row) < 5: continue
            d = row[0][:10]; h = int(row[0][11:13])
            data[d][h] = row
    dense = [d for d, hs in data.items() if all(h in hs for h in range(8))]
    dense.sort()
    if dense:
        print(f"{sym}: dense(asia8) days={len(dense)} range {dense[0]} -> {dense[-1]}")
    else:
        print(f"{sym}: dense(asia8) days=0")
for s in ["EURUSD","GBPUSD","USDJPY","AUDUSD","XAUUSD","XAGUSD"]:
    probe(s)
