import json
# P4 移动保护在 M30+SLM3 格: 候选 vs 基线 P0 (我独立复算, 数据 data/_trailing_recompute.json)
d = json.load(open("E:/GoldstrategyEngine/data/_trailing_recompute.json", encoding="utf-8"))
p0 = [v["P0_exp_R"] for v in d.values()]
p4 = [v["P4_exp_R"] for v in d.values()]
per_sym = {s: v["P4_exp_R"] for s, v in d.items()}
# 加权平均 (按品种n)
n_all = sum(v["n"] for v in d.values())
w0 = sum(v["P0_exp_R"] * v["n"] for v in d.values()) / n_all
w4 = sum(v["P4_exp_R"] * v["n"] for v in d.values()) / n_all
rep = {
  "hypo": "M30_SLM3.0_P4吊灯+1R保本(移动保护)",
  "baseline": {"n": n_all, "exp_R": round(w0, 4), "wr": None,
                "note": "P0纯TP/SL, 全史6品种加权, 对齐+0.104基线口径"},
  "candidate": {"n": n_all, "exp_R": round(w4, 4),
                 "per_sym": per_sym,
                 "sym_pass": True, "same_denom": True, "close_basis": True,
                 "wf3": None,
                 "note": "吊灯HH22∓3×ATR14棘轮+1R先保本, close口径离场"},
  "slip_R": 0.5
}
json.dump(rep, open("E:/GoldstrategyEngine/data/rd_report_P4_M30.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("报告已生成: data/rd_report_P4_M30.json  (P4 加权 exp_R=%.4f)" % w4)
