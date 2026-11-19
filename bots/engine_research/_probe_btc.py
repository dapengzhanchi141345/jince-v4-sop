import csv, datetime
from collections import Counter
rows=[]
with open("data/BTCUSD_H1.csv",encoding="utf-8") as f:
    r=csv.reader(f); next(r)
    for line in r:
        if len(line)<5: continue
        try: rows.append((datetime.datetime.strptime(line[0],"%Y-%m-%d %H:%M:%S"), float(line[4])))
        except: pass
print("total rows",len(rows))
gaps=Counter()
for a,b in zip(rows,rows[1:]):
    gaps[int((b[0]-a[0]).total_seconds())]+=1
print("gap(s) top:",gaps.most_common(6))
ts=Counter(t for t,_ in rows)
dups={t:c for t,c in ts.items() if c>1}
print("duplicate timestamps:",len(dups),"e.g.",list(dups.items())[:3])
print("range:",rows[0][0],"->",rows[-1][0])
