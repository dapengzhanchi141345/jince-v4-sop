# -*- coding: utf-8 -*-
"""08:00 松闸首秀 + 07:51 点名 核验(只读, 不动交易配置)"""
import json, glob, os, datetime

D = r"E:\GoldstrategyEngine\data"

print("=== 1. chief 全链心跳源 ===")
for p in sorted(glob.glob(D + "/auto_cycle*") + glob.glob(D + "/heartbeat*") + glob.glob(D + "/chief*")):
    try:
        raw = open(p, encoding="utf-8", errors="ignore").read()
        print(p, "->", raw[:300].replace("\n", " | "))
    except Exception as e:
        print(p, "ERR", e)

print("\n=== 2. 自由裁量候选(松闸首秀 GO?) ===")
try:
    d = json.load(open(D + "/discretion_candidates.json", encoding="utf-8"))
    print("ts:", d.get("ts"), "| date:", d.get("date"))
    print("candidates:", json.dumps(d.get("candidates"), ensure_ascii=False)[:700])
    print("watch:", json.dumps(d.get("watch"), ensure_ascii=False)[:300])
    print("reason:", str(d.get("reason"))[:250])
    print("note:", str(d.get("note"))[:250])
except Exception as e:
    print("读不出:", e)

print("\n=== 3. 08:00 后 90min 内最新更新的数据文件 ===")
now = datetime.datetime.now().timestamp()
hits = []
for p in glob.glob(D + "/*.json"):
    try:
        if now - os.path.getmtime(p) < 5400:
            hits.append((datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%H:%M"), os.path.basename(p)))
    except Exception:
        pass
for t, p in sorted(hits)[-15:]:
    print(t, p)

print("\n=== 4. 风控冻结态(松闸是否仍在, 币系冻结) ===")
try:
    s = json.load(open(D + "/risk_freeze_state.json", encoding="utf-8"))
    print("level:", s.get("level"), "| policy.open_new_order:", s.get("policy", {}).get("open_new_order"))
    print("intraday_only:", s.get("intraday_only"), "| hold_max_hours:", s.get("hold_max_hours"), "| coin_freeze:", s.get("coin_freeze"))
    print("ts:", s.get("ts"))
except Exception as e:
    print("读不出:", e)

print("\n=== 5. 08:00 节点/研判 daily_advisory 是否已出(松闸后首个全链研判) ===")
for p in glob.glob(D + "/daily_advisory_*.json"):
    mt = datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%H:%M")
    print(mt, p)
