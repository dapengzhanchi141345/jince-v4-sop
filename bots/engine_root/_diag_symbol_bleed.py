import json, os
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


def analyze(since):
    sym = defaultdict(lambda: {"pnls": [], "gw": 0.0, "gl": 0.0, "w": 0, "n": 0})
    for c in closes:
        ts = c.get("ts", "")
        if ts < since:
            continue
        p = pnl_of(c)
        if p is None:
            continue
        s = c.get("symbol", "?")
        d = sym[s]
        d["pnls"].append(p)
        d["n"] += 1
        if p > 0:
            d["gw"] += p
            d["w"] += 1
        else:
            d["gl"] += -p
    rows = []
    for s, d in sym.items():
        n = d["n"]
        if n == 0:
            continue
        pf = (d["gw"] / d["gl"]) if d["gl"] > 0 else None
        rows.append((s, n, d["w"], round(d["w"] / n, 2),
                     round(pf, 2) if pf is not None else None,
                     round(d["gw"], 1), round(d["gl"], 1)))
    return rows


def show(title, rows, topn=12, worst=True):
    print(f"\n=== {title} (n={sum(r[1] for r in rows)}) ===")
    rows_sorted = sorted(rows, key=lambda r: (r[5] - r[6]))  # net pnl asc
    pick = rows_sorted[:topn] if worst else rows_sorted[-topn:][::-1]
    print(f"{'SYM':10} {'n':>4} {'win':>4} {'WR':>5} {'PF':>6} {'grossW':>8} {'grossL':>8} {'NET':>8}")
    for s, n, w, wr, pf, gw, gl in pick:
        print(f"{s:10} {n:>4} {w:>4} {wr:>5} {str(pf):>6} {gw:>8} {gl:>8} {gw-gl:>8.1f}")


for since, label in [("2026-08-01T00:00", "全月 (8月至今)"),
                     ("2026-09-01T00:00", "部署后 (9-01起, 含V3)")]:
    rows = analyze(since)
    print(f"\n########## {label} ##########")
    show("最亏品种 TOP", rows, 12, worst=True)
    show("最赚品种 TOP", rows, 8, worst=False)
    tot_w = sum(r[2] for r in rows)
    tot_n = sum(r[1] for r in rows)
    tot_gw = sum(r[5] for r in rows)
    tot_gl = sum(r[6] for r in rows)
    pf = tot_gw / tot_gl if tot_gl else None
    print(f"--- 合计: n={tot_n} WR={round(tot_w/tot_n,3)} PF={round(pf,3) if pf else None} net={round(tot_gw-tot_gl,1)} ---")
