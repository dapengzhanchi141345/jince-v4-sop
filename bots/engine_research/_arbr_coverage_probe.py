import csv, collections
for sym in ["EURUSD","GBPUSD","USDJPY","AUDUSD","XAUUSD","XAGUSD","USDCAD"]:
    p = f"E:/GoldstrategyEngine/data/{sym}_H1.csv"
    days = collections.Counter(); first=last=None; n=0
    with open(p, encoding='utf-8') as f:
        rdr = csv.reader(f); next(rdr)
        for row in rdr:
            if len(row) < 5: continue
            t = row[0][:10]; days[t]+=1
            if first is None: first=t
            last=t; n+=1
    d8 = sum(v==8 for v in days.values())
    print(f"{sym}: {first} -> {last} | bars={n} days={len(days)} days_with_8_asian_bars={d8} max_bars/day={max(days.values())}")
