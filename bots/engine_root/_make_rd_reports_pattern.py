import json
base = json.load(open("E:/GoldstrategyEngine/data/pattern_gate.json", encoding="utf-8"))
fa = base["faceA_intra"]; fb = base["faceB_m30_slm3"]
# 假设1: 日内腿2R变体+形态否决门 (faceA) — 几何≠已验证日内腿(目标前日中值/24根超时), 且净口径仍负
rep1 = {
  "hypo": "日内腿2R变体+K线形态否决门 (faceA, 非已验证几何)",
  "baseline": {"n": fa["baseline"]["n"], "exp_R": fa["baseline"]["exp_R"],
                "note": "TP=2R固定+无超时变体, 尾部不封顶; 已验证日内腿几何(前日中值目标/24根超时)全史-0.15R, 两者不可比"},
  "candidate": {"n": fa["gated"]["n"], "exp_R": fa["gated"]["exp_R"],
                 "wf3": fa["gated"]["wf3"], "per_sym": fa["gated"]["per_sym"],
                 "sym_pass": fa["对称自检"]["pass"], "same_denom": True, "close_basis": True,
                 "note": "形态否决门 Δ=+0.022R(优势闸不过), 扣0.5R滑点后-0.366仍负, per_sym全null(脚本bug), 对称自检4/6不过"},
  "slip_R": 0.5}
json.dump(rep1, open("E:/GoldstrategyEngine/data/rd_report_faceA.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
# 假设2: M30格+K线形态否决门 (faceB) — 几何已复证基线+0.104, 但门无增量
rep2 = {
  "hypo": "M30_SLM3.0+K线形态否决门 (faceB)",
  "baseline": {"n": fb["baseline"]["n"], "exp_R": fb["baseline"]["exp_R"],
                "note": "独立复证+0.104基线, 对称自检pass, wf3三段全正, 6/6品种正 — M30毛edge第二次独立复证"},
  "candidate": {"n": fb["gated"]["n"], "exp_R": fb["gated"]["exp_R"],
                 "wf3": [fb["gated"]["wf3"][str(k)] for k in (1,2,3)], "per_sym": fb["gated"]["per_sym"],
                 "sym_pass": fb["gated"]["symmetric_pass"], "same_denom": True, "close_basis": True,
                 "note": "形态门Δ=+0.0027R≈0(优势闸不过), 扣0.5R滑点后-0.393仍负"},
  "slip_R": 0.5}
json.dump(rep2, open("E:/GoldstrategyEngine/data/rd_report_faceB.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("two reports written")
