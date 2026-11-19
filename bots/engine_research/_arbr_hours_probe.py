import csv, collections
def probe(sym, days=5):
    p = f"E:/GoldstrategyEngine/data/{sym}_H1.csv"
    data = collections.defaultdict(dict)
    with open(p, encoding='utf-8') as f:
        rdr = csv.reader(f); next(rdr)
        for row in rdr:
            if len(row) < 5: continue
            d = row[0][:10]; h = int(row[0][11:13])
            data[d][h] = row[4]
    ds = sorted(data)
    print(f"== {sym} total days={len(ds)}")
    for d in [ds[0], ds[len(ds)//2], ds[-1]]:
        hrs = sorted(data[d])
        print(f"  {d}: hours={hrs} closes={[round(float(data[d][h]),5) for h in hrs]}")
probe("EURUSD")
probe("XAUUSD")
