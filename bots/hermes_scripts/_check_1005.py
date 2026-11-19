# -*- coding: utf-8 -*-
"""10:05 节点核验: ①今日研判文件出现?候选源已切今日? ②KSMUSD 进化点进五验队列没丢?
只读, 不动交易."""
import json, os, datetime

D = r"E:\GoldstrategyEngine\data"

def mtime(p):
    return datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%m-%d %H:%M") if os.path.exists(p) else "(不存在)"

print("=== 1. 今日研判 daily_advisory_20261008.json ===")
today_adv = D + r"\daily_advisory_20261008.json"
if os.path.exists(today_adv):
    d = json.load(open(today_adv, encoding="utf-8"))
    secs = d.get("sections") or []
    n = sum(len(s.get("items", [])) for s in secs)
    print("  mtime:", mtime(today_adv), "| items:", n, "| sections:", [s.get("session") for s in secs])
else:
    print("  尚不存在(节点 09:31 引用的可能是别处生成, 查下方)")
    # 找所有 1008 相关研判
    import glob
    for p in glob.glob(D + r"\daily_advisory_20261008*"):
        print("  找到:", p, mtime(p))

print("\n=== 2. 候选管道当前 advisory_source(今日源 or 回退昨夜?) ===")
cc = json.load(open(D + r"\discretion_candidates.json", encoding="utf-8"))
print("  advisory_source:", cc.get("advisory_source"))
print("  ts:", datetime.datetime.fromtimestamp(cc.get("ts", 0)).strftime("%m-%d %H:%M"), "| candidates:", len(cc.get("candidates", [])), "| watch:", len(cc.get("watch", [])))
print("  stale_note:", str(cc.get("stale_note"))[:80])

print("\n=== 3. KSMUSD 进化点是否进五验/研发队列 ===")
for fn in ("rd_or_review_24h.json", "rd_ledger_24h.json", "evolution_queue.json", "rd_pending.json"):
    p = D + "\\" + fn
    if os.path.exists(p):
        txt = open(p, encoding="utf-8", errors="ignore").read()
        hit = [ln.strip()[:120] for ln in txt.splitlines() if "KSM" in ln]
        if hit:
            print(f"  {fn}: KSMUSD 命中 {len(hit)} 行, 首条: {hit[0]}")
        else:
            print(f"  {fn}: 无 KSMUSD")
    else:
        print(f"  {fn}: (不存在)")

print("\n=== 4. 账户实读快照(0持仓0挂单是否仍成立) ===")
for fn in ("equity_pending_state.json", "crypto_pending_state.json"):
    p = D + "\\" + fn
    if os.path.exists(p):
        s = json.load(open(p, encoding="utf-8"))
        print(f"  {fn}: open_positions={s.get('open_positions') or s.get('open')} pending={s.get('pending') or s.get('pending_orders')}")
