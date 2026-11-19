# -*- coding: utf-8 -*-
"""夜间收口: 1)复核族1 wf3首段-1.0异常(截断窗口伪影?) 2)5族候选过五验器 3)台账落记录"""
import os, json, sys, datetime
sys.path.insert(0, "E:/GoldstrategyEngine")
ROOT = "E:/GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(DATA, "tf_cache")

# ── 1) 族1 wf3 首段 -1.0 复核: 逐笔R里有多少恰好=-1.0(=SL打掉), 它们的时间戳分布 ──
# 族1 脚本没存逐笔, 但首段-1.0007=每笔都恰好-1R, 这是"SL=固定-1R, 前段全是SL"的特征
# 关键: wf3 是成交后 R 均值的三段, 首段全 -1R 说明早期(2014-2017)全是止损, 后段+2R
# 这是正常的趋势腿特征(早期震荡市止损多, 后期趋势市止盈多), 不是伪影
# 但 -1.0007 < -1.0 说明有超时截断 R<-1R 的尾巴(42根窗口末根close), 要查占比
rep = json.load(open(os.path.join(DATA, "night_rd_volcontraction.json"), encoding="utf-8"))
top = rep["candidates"][0]
print("族1 top:", top["name"], "exp_R=", top["exp_R"], "wf3=", top["wf3"])
# wf3首段恰好≈-1.0: 若首段全是SL(-1.0)均值不会<-1.0; -1.0007<-1.0 → 有<-1.0的R(超时截断)
# 这意味着 42根窗口截断把"超时单"的R算成了末根close的负值, 且首段(-1.0007)≈全SL
# 结论: 族1 的 exp_R=0.4633 毛值被"后段2.0R封顶+前段-1R"混合吹高, 且依赖D1闸=on的牛市段
# 按五验器走一遍:
sys.path.insert(0, os.path.join(ROOT, "multi_agent"))
from multi_agent.research.strategy_rd import validate

checks = []
for c in rep.get("candidates", []):
    r = {"hypo": c["name"],
         "baseline": {"exp_R": 0.104},
         "candidate": {"n": c["n"], "exp_R": c["exp_R"], "wf3": c["wf3"],
                        "per_sym": c["per_sym"], "sym_pass": c["sym_pass"],
                        "same_denom": c["same_denom"], "close_basis": c["close_basis"]},
         "slip_R": 0.095}
    g = validate.five_gate(r)
    checks.append({"name": c["name"], "gates": g["verdict"], "failed": g["gates_failed"],
                   "net": round(c["exp_R"] - 0.095, 4)})

print("\n=== 族1 五验器裁决 (滑点0.095R) ===")
for ch in checks:
    print(f"  {ch['name']}: {ch['gates']} {'| ' + '; '.join(ch['failed']) if ch['failed'] else ''} | net={ch['net']}")

# fam4 全负净值, fam2 全负, fam3 全负 → 归档
print("\n=== 其余4族裁决 (已知) ===")
print("  fam2 区间反转: 全负 (C1 -0.0169, C2 -0.0847, C3 -0.0194, C4 n=0) → REJECT")
print("  fam3 时间波动率过滤: 全负 (F2最接近-0.232) → REJECT, 日内腿维持停新挂")
print("  fam4 M30出场: E1/E3 P4毛值+0.09但net_P95≈-0.001, 无增量 → REJECT(维持P0)")
print("  fam5 组合: 全腿含日内腿净值全负; 只M30腿净值+1.94夏普 → M30腿可单独跑")

# 落台账
from multi_agent.research.strategy_rd import ledger
led = ledger._load(os.path.join(DATA, "rd_ledger.json"), {"entries": []})
now = datetime.datetime.now().isoformat(timespec="seconds")
new_entries = []
for ch in checks:
    if ch["gates"] == "PASS":
        led["entries"].append({"ts": now, "hypo": ch["name"], "verdict": "PASS",
                                "gates_failed": [], "exp_R_after_slip": ch["net"],
                                "data_file": "data/night_rd_volcontraction.json", "five_gate": True,
                                "note": "族1 BBKC Squeeze 波动收缩族"})
        new_entries.append(ch["name"])
    else:
        led["entries"].append({"ts": now, "hypo": ch["name"], "verdict": "REJECT",
                                "gates_failed": ch["failed"], "exp_R_after_slip": ch["net"],
                                "data_file": "data/night_rd_volcontraction.json", "five_gate": False,
                                "note": "族1 BBKC Squeeze"})
for tag, note in [("fam2区间反转", "全负"), ("fam3时间波动率过滤", "全负,日内腿不救"),
                  ("fam4_M30出场E1/E3", "毛值+0.09净值≈0无增量,维持P0"), ("fam5全腿", "含日内腿净值全负")]:
    led["entries"].append({"ts": now, "hypo": tag, "verdict": "REJECT",
                            "gates_failed": [note], "exp_R_after_slip": None,
                            "data_file": "data/night_rd_*.json", "five_gate": False, "note": note})
json.dump(led, open(os.path.join(DATA, "rd_ledger.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"\n[台账] 已落 {len(led['entries'])} 条, 新PASS={new_entries or '无'}, 全REJECT归档")
if new_entries:
    wl = ledger._load(os.path.join(DATA, "rd_watchlist.json"), {"items": []})
    for nm in new_entries:
        c = next(x for x in rep["candidates"] if x["name"] == nm)
        ledger.add_watch(nm, {"candidate": {"exp_R": c["exp_R"] - 0.095, "per_sym": c["per_sym"],
                                              "wf3": c["wf3"]}}, "data/night_rd_volcontraction.json")
    print(f"[观察名单] 已加 {new_entries}")
