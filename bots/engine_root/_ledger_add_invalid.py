import json, datetime
p = "E:/GoldstrategyEngine/data/rd_ledger.json"
led = json.load(open(p, encoding="utf-8"))
now = datetime.datetime.now().isoformat(timespec="seconds")
if not any(e["hypo"].startswith("M30出场协议族") for e in led["entries"]):
    led["entries"].append(dict(ts=now, hypo="M30出场协议族E1-E4+P4(代跑)", verdict="INVALID",
        gates_failed=["P4复现闸门自毁: 复现+0.0942 != 目标-0.813, 几何漂移, 整族作废"],
        exp_R_after_slip=None, data_file="data/night_rd_fam4_m30_exit.json", five_gate=False,
        note="5协议无一毛值超P0基线, 方向结论维持P0; 需按_tf_m30.py原版几何重测fam4"))
    json.dump(led, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("台账现有条目:", len(led["entries"]))
