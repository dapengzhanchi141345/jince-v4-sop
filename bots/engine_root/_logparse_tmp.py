import re

logpath = "E:/GoldstrategyEngine/data/logs/live_loop_main.log"

# tokens to probe
probes = {
    "drift/RED/GREEN": r"(drift|DRIFT|漂移|RED|GREEN)",
    "RF/probability": r"(RF|probabilit|\brf\b|贝叶斯|bayes)",
    "VETO/risk gate": r"(VETO|veto|风险闸|risk_gate|risk_veto)",
    "evolution/fitness/thr": r"(evolution|fitness|thr|MIN_EDGE|edge)",
    "GATE/guardian": r"(GATE|gate|护栏|guardian|EDGE_GATE)",
    "ADX/MTF/regime/flip": r"(ADX|MTF|regime|翻转|flip|H4|H1|D1)",
    "SupplyZone/OB/FVG/RR": r"(Supply Zone|OB|Order Block|FVG|RR Ratio|RR_ratio|RR\b)",
    "SKIP/no-trade": r"(SKIP|skip|NO_TRADE|no_trade|不开|过滤)",
    "order open/close": r"(OPEN|open_order|开仓|平仓|close|CLOSE|position)",
}

counts = {k:0 for k in probes}
samples = {k:[] for k in probes}

# also capture last timestamp lines
import time
t0 = time.time()

with open(logpath, encoding="utf-8", errors="replace") as f:
    for i, line in enumerate(f):
        # only process last ~1/3 to keep it fast but cover recent + some history
        pass

# Read all (8.8MB ok)
with open(logpath, encoding="utf-8", errors="replace") as f:
    for i, line in enumerate(f):
        for k, pat in probes.items():
            if re.search(pat, line):
                counts[k]+=1
                if len(samples[k])<4:
                    # truncate long line, strip newlines
                    s = line.strip().replace("\n"," ")
                    if len(s)>300:
                        s = s[:300]+"..."
                    samples[k].append((i, s))

for k in probes:
    print("### {} : count={}".format(k, counts[k]))
    for ln, s in samples[k]:
        print("  L{}: {}".format(ln, s))
    print()

print("=== TOP-LEVEL TIMESTAMP / loop markers (scan for recent) ===")
# find lines with date-like prefix
dtpat = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}")
recent = []
with open(logpath, encoding="utf-8", errors="replace") as f:
    for i, line in enumerate(f):
        if dtpat.search(line):
            recent.append((i, line.strip()[:200]))
# print last 15
for ln, s in recent[-15:]:
    print("L{}: {}".format(ln, s))
