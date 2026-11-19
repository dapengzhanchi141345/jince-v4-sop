import re

logpath = "E:/GoldstrategyEngine/data/logs/live_loop_main.log"

# 1) Last drift entry across whole log + all drift timestamps
drift_lines = []
evolved_hits = {s:0 for s in ["XAUUSD","BTCUSD","ETHUSD","EURUSD","GBPUSD","USDJPY","GBPJPY"]}
evolved_samples = {s:[] for s in evolved_hits}
bridge_mention_evolved = {s:0 for s in evolved_hits}

with open(logpath, encoding="utf-8", errors="replace") as f:
    for i, line in enumerate(f):
        if "漂移" in line or "drift" in line.lower():
            drift_lines.append((i, line.strip()[:240]))
        for s in evolved_hits:
            if s in line:
                evolved_hits[s]+=1
                if "同源桥接" in line or "VETO" in line or "SKIP" in line or "开仓" in line or "持有" in line:
                    bridge_mention_evolved[s]+=1
                if len(evolved_samples[s])<3:
                    evolved_samples[s].append((i, line.strip()[:200]))

print("=== DRIFT monitoring entries: total={} ===".format(len(drift_lines)))
if drift_lines:
    print("FIRST:", drift_lines[0][0], drift_lines[0][1])
    print("LAST :", drift_lines[-1][0], drift_lines[-1][1])
print()
print("=== EVOLVED 7 symbol hits in log ===")
for s in evolved_hits:
    print("{}: total_hits={} bridge_related={}".format(s, evolved_hits[s], bridge_mention_evolved[s]))
    for ln, sm in evolved_samples[s][:2]:
        print("    L{}: {}".format(ln, sm))
print()

# 2) Recent window: last 4000 lines, characterize loop decisions
print("=== RECENT WINDOW (last 4000 lines) ===")
with open(logpath, encoding="utf-8", errors="replace") as f:
    lines = f.readlines()
recent = lines[-4000:]
# count decision types
from collections import Counter
dec = Counter()
syms_recent = Counter()
for ln in recent:
    for tag in ["→ VETO","→ SKIP","→ 开仓","开仓","平仓","持有","交易轮次","漂移"]:
        if tag in ln:
            dec[tag]+=1
    for s in ["XAUUSD","BTCUSD","ETHUSD","GBPJPY","USDJPY","EURUSD","GBPUSD"]:
        if s in ln:
            syms_recent[s]+=1
print("decision tag counts:", dict(dec))
print("evolved symbol mentions in recent 4000 lines:", dict(syms_recent))
print()
# show any drift in recent
for ln in recent:
    if "漂移" in ln or "drift" in ln.lower():
        print("RECENT DRIFT:", ln.strip()[:200])
