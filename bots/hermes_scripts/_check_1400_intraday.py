# -*- coding: utf-8 -*-
"""14:00 松闸日内精选时段核验: extnet down 多久 / 候选管道今日源 / 日内 GO 进没进 / 币系 0 误放. 只读."""
import json, os, datetime

D = r"E:\GoldstrategyEngine\data"

print("=== 1. extnet 现状 + 挂了多久(network_probe_last) ===")
try:
    np_ = json.load(open(D + r"\network_probe_last.json", encoding="utf-8"))
    print("  ", json.dumps(np_, ensure_ascii=False)[:300])
except Exception as e:
    print("  读不出:", e)

print("\n=== 2. 候选管道(discretion_candidates 今日源?) ===")
try:
    cc = json.load(open(D + r"\discretion_candidates.json", encoding="utf-8"))
    print("  ts:", datetime.datetime.fromtimestamp(cc.get("ts", 0)).strftime("%m-%d %H:%M") if cc.get("ts") else cc.get("ts"),
          "| advisory_source:", cc.get("advisory_source"),
          "| candidates:", len(cc.get("candidates", [])), "| watch:", len(cc.get("watch", [])))
    for c in cc.get("candidates", [])[:5]:
        print("   [候选]", c.get("sym"), c.get("dir"), c.get("session"), c.get("setup"),
              "RR=", c.get("rr"), c.get("status"))
except Exception as e:
    print("  读不出:", e)

print("\n=== 3. 日内 swing/GO 候选进管道没 ===")
for fn in ("intraday_candidates.json", "intraday_go.json", "swing_intraday.json",
           "pending_orders_state.json", "equity_pending_state.json", "crypto_pending_state.json"):
    p = D + "\\" + fn
    if os.path.exists(p):
        mt = datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%m-%d %H:%M")
        try:
            d = json.load(open(p, encoding="utf-8"))
            print("  " + fn + " (mtime " + mt + "):", json.dumps(d, ensure_ascii=False)[:280])
        except Exception:
            print("  " + fn + " (mtime " + mt + "): 非json")
    else:
        print("  " + fn + " (不存在)")

print("\n=== 4. 风控冻结态(币系是否仍冻 / 日内开新单是否允许) ===")
try:
    rf = json.load(open(D + r"\risk_freeze_state.json", encoding="utf-8"))
    print("  level:", rf.get("level"), "| policy.open_new_order:", (rf.get("policy") or {}).get("open_new_order"),
          "| intraday_only:", rf.get("intraday_only"), "| hold_max_hours:", rf.get("hold_max_hours"),
          "| coin_freeze:", rf.get("coin_freeze"))
except Exception as e:
    print("  读不出:", e)

print("\n=== 5. 账户实读快照(挂单/持仓) ===")
for fn in ("equity_pending_state.json", "crypto_pending_state.json"):
    p = D + "\\" + fn
    if os.path.exists(p):
        s = json.load(open(p, encoding="utf-8"))
        print("  " + fn + ": open_positions=", s.get("open_positions") or s.get("open"),
              "| pending=", s.get("pending") or s.get("pending_orders"))
