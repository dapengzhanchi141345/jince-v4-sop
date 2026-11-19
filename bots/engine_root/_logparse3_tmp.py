import re, json

logpath = "E:/GoldstrategyEngine/data/logs/live_loop_main.log"

# (a) full last drift entry
last_drift = None
with open(logpath, encoding="utf-8", errors="replace") as f:
    for line in f:
        if "漂移监控" in line:
            last_drift = line.strip()
# extract JSON inside
m = re.search(r'(\{.*\})', last_drift) if last_drift else None
print("=== LAST DRIFT FULL ===")
if m:
    try:
        d = json.loads(m.group(1))
        print(json.dumps(d, ensure_ascii=False, indent=2))
    except Exception as e:
        print("parse err", e, last_drift[:400])
else:
    print(last_drift[:400] if last_drift else "NONE")

print()
# (b) recent bridge decisions for strong-edge symbols: XAUUSD BTCUSD ETHUSD GBPJPY USDJPY
targets = ["XAUUSD","BTCUSD","ETHUSD","GBPJPY","USDJPY","GBPUSD","EURUSD"]
with open(logpath, encoding="utf-8", errors="replace") as f:
    lines = f.readlines()
recent = lines[-6000:]
print("=== RECENT (last 6000 lines) bridge decisions for evolved symbols ===")
for s in targets:
    decisions = []
    for ln in recent:
        if s in ln and ("同源桥接" in ln or "VETO" in ln or "SKIP" in ln or "开仓" in ln or "持有" in ln or "→" in ln):
            # shorten
            s2 = ln.strip().replace("\n"," ")
            if len(s2)>180: s2=s2[:180]+"..."
            decisions.append(s2)
    print("\n--- {} ({} recent decision-lines) ---".format(s, len(decisions)))
    for d in decisions[:12]:
        print("  ", d)
