import csv, collections
p = "E:/GoldstrategyEngine/data/XAUUSD_H1.csv"
cnt = collections.Counter()
sample = collections.defaultdict(list)
with open(p, encoding='utf-8') as f:
    rdr = csv.reader(f); next(rdr)
    for row in rdr:
        if len(row) < 5: continue
        d = row[0][:10]; h = int(row[0][11:13])
        cnt[h] += 1
        if len(sample[h]) < 3: sample[h].append(d)
print("hour bar counts (XAUUSD):")
for h in range(24):
    print(f"  {h:02d}h: {cnt[h]} bars  e.g. {sample.get(h,[])}")
# dense days with hours 1-7
data = collections.defaultdict(set)
with open(p, encoding='utf-8') as f:
    rdr = csv.reader(f); next(rdr)
    for row in rdr:
        if len(row) < 5: continue
        data[row[0][:10]].add(int(row[0][11:13]))
dense = [d for d, s in data.items() if all(h in s for h in range(1,8))]
dense.sort()
print(f"dense(asia7: 01-07h) days={len(dense)} range {dense[0] if dense else None} -> {dense[-1] if dense else None}")
