
import json, time, os
base = r"E:\GoldstrategyEngine\data"

rd_path = os.path.join(base, "rd_decisions.json")
rd = json.load(open(rd_path, encoding="utf-8"))
items = rd["decisions"]
entry = {
    "time": time.strftime("%Y-%m-%d %H:%M"),
    "id": "v17_qlearn_grid_veto",
    "leg": "V17 Q-learning grid (metatrader_study batch)",
    "verdict": "VETO",
    "reason_plain": "Official DRL grid case same family as fam6 martin 50-grid 0/50 (add-position baseline): smarter learning cannot rescue a negative-expectancy structure; pre-set REJECT stands, logged and settled",
    "data_fields": "rd_verify_batch_metatrader_study_20261005.json#V17; fam6 ledger",
    "five_test_pass": False,
    "live_flag": False,
}
if not any(e.get("id") == "v17_qlearn_grid_veto" for e in items):
    items.append(entry)
    rd["ts"] = int(time.time())
    json.dump(rd, open(rd_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("rd_decisions now", len(items), "entries, last =", items[-1]["id"])

b_path = os.path.join(base, "rd_verify_batch_metatrader_study_20261005.json")
b = json.load(open(b_path, encoding="utf-8"))
for it in b.get("items", []):
    if it.get("id") in ("V15", "V16"):
        it["status"] = "BLOCKED"
        it["block_reason"] = ("mamba_ssm/transformers not installed + HF weights need extnet (DOWN, 10-05 probe); "
                              "DoH sidecar only unblocks github.com. Precond: extnet up -> pip install + pull Mantis weights -> "
                              "same-denom A/B vs current regime routing (T1 16 syms) + z-test + wf3 same-sign -> "
                              "polish.json -> five-test + risk-officer recheck")
json.dump(b, open(b_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("batch:", [(i.get("id"), i.get("status")) for i in b.get("items", [])])
