import json, sys, os
sys.path.insert(0, "E:/GoldstrategyEngine")

# 主 JSON 缺失(脚本语法错未跑完) → 用子代理轮落盘的 candidates JSON
cands = json.load(open("E:/GoldstrategyEngine/data/night_rd_族2区间反转.json.candidates.json", encoding="utf-8"))
if isinstance(cands, dict):
    cands = cands.get("report", list(cands.values())[0])
print("族2 candidates:", len(cands))
best = max(cands, key=lambda r: (r["exp_R"] or -99))
print("最优:", best["name"], "exp_R=", best["exp_R"], "net_P95=", best.get("net_P95"))
rep = {
    "hypo": "族2区间反转最优:" + best["name"] + "(M30+H4, 区间反转几何, close口径)",
    "baseline": {"n": best["n"], "exp_R": 0.0, "wr": 0.5},
    "candidate": {
        "n": best["n"], "exp_R": best["exp_R"], "wr": best.get("wr", 0.5),
        "wf3": best.get("wf3", [None, None, None]),
        "per_sym": {k: v for k, v in best.get("per_sym", {}).items() if isinstance(v, (int, float))},
        "sym_pass": best.get("mirror_pass", False) and best.get("sym_pass", False),
        "same_denom": best.get("same_denom", False),
        "close_basis": best.get("close_basis", False),
    },
    "slip_R": 0.095,
}
json.dump(rep, open("E:/GoldstrategyEngine/data/rd_report_fam2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
from multi_agent.research.strategy_rd import validate, ledger
gates = validate.five_gate(rep)
print("族2 verdict:", gates["verdict"], "gates:", gates["gates_failed"], "net:", gates["exp_R_after_slip"])
if gates["verdict"] != "PASS":
    ledger.record(rep["hypo"], rep, "REJECT", gates["gates_failed"], data_file="data/rd_report_fam2.json")
    print("族2 REJECT 入台账")
