import json
path = r"E:/GoldstrategyEngine/data/logs/live_loop_main.log"
rows = []
with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        if '漂移监控-告警' not in line:
            continue
        i = line.find('{'); j = line.rfind('}')
        if i < 0 or j < 0:
            continue
        try:
            obj = json.loads(line[i:j+1])
        except Exception:
            continue
        b = obj.get('baseline', {}); l = obj.get('live', {})
        rows.append((obj.get('timestamp',''), obj.get('status'),
                     b.get('pf'), b.get('win_rate'), b.get('trade_count'),
                     l.get('pf'), l.get('win_rate'), l.get('trade_count')))
print("total drift entries:", len(rows))
print("FIRST:", rows[0])
print("LAST 14:")
for r in rows[-14:]:
    print(r)
prev = None; trans = []
for r in rows:
    if r[1] != prev:
        trans.append(r); prev = r[1]
print("TRANSITIONS (status changes):", len(trans))
for r in trans:
    print(r)
# how many RED vs GREEN
from collections import Counter
c = Counter(r[1] for r in rows)
print("STATUS COUNTS:", dict(c))
