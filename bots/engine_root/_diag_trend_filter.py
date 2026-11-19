import json
from collections import defaultdict

P = r"E:\GoldstrategyEngine\data\continuous_evolution\trade_journal.jsonl"
fills = {}
closes = []
for line in open(P, encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    try:
        r = json.loads(line)
    except Exception:
        continue
    if r.get("type") == "FILL":
        fills[r["ticket"]] = r
    elif r.get("type") == "CLOSE":
        closes.append(r)


def pnl_of(c):
    for k in ("pnl", "profit", "realized_pnl", "close_pnl"):
        if isinstance(c.get(k), (int, float)):
            return float(c[k])
    f = fills.get(c.get("ticket"))
    if f and isinstance(c.get("price"), (int, float)) and isinstance(f.get("price"), (int, float)):
        d = 1 if str(f.get("direction", "")).upper() == "BUY" else -1
        return d * (float(c["price"]) - float(f["price"]))
    return None


# pair close -> fill adx
rows = []
for c in closes:
    f = fills.get(c.get("ticket"))
    if not f:
        continue
    p = pnl_of(c)
    if p is None:
        continue
    rows.append((f.get("adx"), f.get("symbol"), p, c.get("ts", "")))


def bucket_stats(label, subset):
    if not subset:
        print(f"{label}: n=0")
        return
    n = len(subset)
    gw = sum(p for _, _, p, _ in subset if p > 0)
    gl = -sum(p for _, _, p, _ in subset if p < 0)
    w = sum(1 for _, _, p, _ in subset if p > 0)
    pf = gw / gl if gl > 0 else None
    aw = gw / w if w else 0
    los = n - w
    al = gl / los if los else 0
    wl = aw / abs(al) if al else None
    print(f"{label}: n={n} WR={round(w/n,2)} PF={round(pf,2) if pf else None} W/L={round(wl,2) if wl else None} net={round(gw-gl,1)}")


print("全月按开仓 ADX 分层 (FILL.adx):")
allsince = [r for r in rows]  # 全量已含历史
bucket_stats("ADX<20 (震荡)", [r for r in allsince if (r[0] or 0) < 20])
bucket_stats("ADX 20-30", [r for r in allsince if 20 <= (r[0] or 0) < 30])
bucket_stats("ADX 30-45", [r for r in allsince if 30 <= (r[0] or 0) < 45])
bucket_stats("ADX>=45 (强趋势)", [r for r in allsince if (r[0] or 0) >= 45])
bucket_stats("全量", allsince)

# 仅看部署后(9-01起)
post = [r for r in allsince if r[3] >= "2026-09-01T00:00"]
print("\n部署后(9-01起)按 ADX 分层:")
bucket_stats("ADX<20", [r for r in post if (r[0] or 0) < 20])
bucket_stats("ADX>=20", [r for r in post if (r[0] or 0) >= 20])
bucket_stats("全量", post)
