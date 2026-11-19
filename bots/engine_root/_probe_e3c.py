import csv
P = "data/live24_trades.csv"
rows = list(csv.reader(open(P, encoding="utf-8-sig")))
data = [r for r in rows[1:]]
def g(r,i): return r[i] if i < len(r) else ""
def ts(r): return g(r,0)
# The task's two cited all-loss batch windows:
# W1: 11-13 13:00 BJT coin family -> task says "币系 4 腿". In CSV near 12:00-13:15 BJT coins: LNKUSD,LTCUSD,CHCUSD,GBPUSD...
# W2: 11-13 16:01 BJT JPY/CAD 3 腿 -> near 16:00 BJT: USDZAR(16:00),SWI20(16:16),CHFJPY(16:45)...
# To confirm "all loss", pull pnl of the legs that actually CLOSE within ~6h of each open.
# Build open->close pnl map by symbol+dir+ticket on 11-13
opens={}
for r in data:
    if ts(r).startswith("2026-11-13") and g(r,1)=="OPEN":
        opens.setdefault(g(r,2),[]).append(r)
print("=== 11-13 coin-family opens (币系 USD-quoted) with same-day close pnl ===")
COINS={"AVXUSD","DOGEUSD","SOLUSD","UNIUSD","LNKUSD","LTCUSD","BTCUSD","ETHUSD","BNBUSD","XLMUSD","XRPUSD","POLUSD","CHCUSD"}
for s in sorted(openers if False else opens.keys()):
    pass
for r in data:
    pass
# For W1: 4 legs opened ~12:00-13:15 BJT among coins. Identify: LNKUSD(12:00),LTCUSD(12:00),CHCUSD(13:15),GBPUSD? no.
# Task text: "11-13 13:00 BJT 币系 4 腿". The 13:00 bucket = EURAUD(13:00) is fx. Coin 4 legs around 12:00-13:15: LNK,LTC,CHC + one more.
# Just dump close pnl for each coin opened 11:30-13:15:
print("--- coin opens 11:30-13:15 BJT and their close pnl ---")
cmap={}
for r in data:
    if g(r,1)=="CLOSE" and ts(r)[:10]=="2026-11-13":
        t=g(r,2)
        try: pnl=float(g(r,9))
        except: pnl=float("nan")
        if t not in cmap: cmap[t]=[]
        cmap[t].append((ts(r),pnl))
for r in data:
    if ts(r).startswith("2026-11-13") and g(r,1)=="OPEN" and g(r,2) in COINS and "11:30"<=ts(r)[11:16]<="13:15":
        t=g(r,2)
        print(f"{ts(r)[11:16]} {t:9s} dir={g(r,3)} -> closes: {cmap.get(t)}")
print("\n--- JPY/CAD-family opens 15:45-17:00 BJT and close pnl ---")
JC={"USDJPY","CADJPY","EURJPY","AUDJPY","CHFJPY","USDZAR","EURCAD","USDCAD","GBPJPY","CHFZAR"}
for r in data:
    if ts(r).startswith("2026-11-13") and g(r,1)=="OPEN" and g(r,2) in JC and "15:45"<=ts(r)[11:16]<="17:00":
        t=g(r,2)
        print(f"{ts(r)[11:16]} {t:9s} dir={g(r,3)} -> closes: {cmap.get(t)}")
