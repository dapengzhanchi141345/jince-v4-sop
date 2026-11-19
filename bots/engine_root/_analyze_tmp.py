import json

with open("E:/GoldstrategyEngine/_mt5_out.json", encoding="utf-8") as f:
    mt5 = json.load(f)
with open("E:/GoldstrategyEngine/data/continuous_evolution/evolution_state.json", encoding="utf-8") as f:
    evo = json.load(f)

bps = evo.get("best_per_symbol", {})
# fitness lookup
fit = {s: (bps[s]["fitness"] if s in bps else None) for s in bps}
fit0 = {s: (bps[s].get("baseline") is not None) for s in bps}

EVOLVED = ["XAUUSD","BTCUSD","ETHUSD","EURUSD","GBPUSD","USDJPY","GBPJPY"]

positions = mt5["positions"]
acct = mt5["account"]

# categorize held positions
held_syms = [p["symbol"] for p in positions]
total_float = sum(p["profit"] for p in positions)

# how many held symbols are in evolution universe
held_in_universe = [s for s in held_syms if s in bps]
held_not_in_universe = [s for s in held_syms if s not in bps]

# count by fitness bucket among held (matched universe)
buckets = {"fit>0 and has baseline": [], "fit>0 no baseline": [], "fit==0": [], "not in universe": []}
for s in held_syms:
    if s not in bps:
        buckets["not in universe"].append(s)
    else:
        f = bps[s]["fitness"]
        if f == 0:
            buckets["fit==0"].append(s)
        else:
            if bps[s].get("baseline"):
                buckets["fit>0 and has baseline"].append(s)
            else:
                buckets["fit>0 no baseline"].append(s)

# evolved symbols held?
evolved_held = [s for s in EVOLVED if s in held_syms]
evolved_not_held = [s for s in EVOLVED if s not in held_syms]

# strong edge evolved (fitness high) - define strong as fitness>=40 or has baseline pf>=1.5
strong_evolved = []
for s in EVOLVED:
    b = bps.get(s)
    if not b: continue
    f = b["fitness"]
    base = b.get("baseline")
    pf = base["pf"] if base else None
    if f > 0 and (f >= 40 or (pf and pf >= 1.5)):
        strong_evolved.append((s, "fit={} pf={}".format(round(f,2), pf)))

print("=== ACCOUNT ===")
print("balance={} equity={} margin={} free={} ml={}".format(
    acct["balance"], acct["equity"], acct["margin"], acct["free_margin"], acct["margin_level"]))
print("trade_allowed={}".format(acct["trade_allowed"]))
print()
print("=== POSITIONS ===")
print("total held =", len(positions))
print("total floating P/L =", round(total_float,2))
print("held in evolution universe =", len(held_in_universe))
print("held NOT in universe =", len(held_not_in_universe))
print()
print("--- held fitness buckets ---")
for k,v in buckets.items():
    print("{}: {} ({})".format(k, len(v), ", ".join(sorted(set(v)))[:600]))
print()
print("=== EVOLVED 7 SYMBOLS ===")
print("held (any):", evolved_held)
print("NOT held:", evolved_not_held)
print("strong-edge evolved:", strong_evolved)
print()
print("=== DEALS 2D ===")
print("count=", mt5["deals_count_2d"], "net=", mt5["deals_net_2d"])
print("by symbol net:", json.dumps(mt5["deals_by_symbol_net"], ensure_ascii=False))
# evolved symbols in deals
for s in EVOLVED:
    if s in mt5["deals_by_symbol_net"]:
        print("  EVOLVED DEAL:", s, mt5["deals_by_symbol_net"][s])
