import json, datetime, glob, os
D = r"E:\GoldstrategyEngine\data"
print("=== discussion_log 里 KSMUSD 进化点落盘了吗 ===")
LOG = D + r"\discussion_log.jsonl"
hits = []
for line in open(LOG, encoding="utf-8", errors="ignore"):
    if "KSM" in line:
        try:
            rec = json.loads(line)
            ts = rec.get("ts")
            hits.append((str(ts), str(rec.get("node")), rec.get("actor",""), (str(rec.get("content"))+str(rec.get("note"))+str(rec.get("msg")))[:120]))
        except: pass
print("KSM 相关记录", len(hits), "条, 末3条:")
for h in hits[-3:]: print("  ", h[0], h[1], h[2], "|", h[3][:100])
print("\n=== rd_ledger_24h.json 顶层结构(看五验队列长啥样) ===")
rl = json.load(open(D + r"\rd_ledger_24h.json", encoding="utf-8"))
print("keys:", list(rl.keys())[:12])
if "batch" in rl: print("batch:", json.dumps(rl["batch"], ensure_ascii=False)[:300])
if "pending" in rl: print("pending:", json.dumps(rl["pending"], ensure_ascii=False)[:300])
