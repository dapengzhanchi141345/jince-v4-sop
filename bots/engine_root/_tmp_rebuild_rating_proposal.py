# -*- coding: utf-8 -*-
# 临时脚本: 验活评级修复 + 重建 alpha_rating.json + 重跑 advisory_to_order 提案
import sys, json, time
sys.path.insert(0, "E:/GoldstrategyEngine")
from multi_agent.research import alpha_researcher as ar
print("N_D_MIN =", ar.N_D_MIN)
print("alpha_rating(0.2,1) =", ar.alpha_rating(0.2, 1), "(应为 C 小样本)")
print("alpha_rating(0.2,7) =", ar.alpha_rating(0.2, 7), "(应为 D 实盘差)")
print("alpha_rating(1.6,20) =", ar.alpha_rating(1.6, 20), "(应为 A)")

# 重建 alpha_rating.json (读 edge_tracker, 走新评级函数)
et = json.load(open("E:/GoldstrategyEngine/data/edge_tracker.json", encoding="utf-8"))
rs = ar.build_ratings(et)
out = {"ts": int(time.time()), "ratings": rs}
json.dump(out, open("E:/GoldstrategyEngine/data/alpha_rating.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
nD = sum(1 for v in rs.values() if v.get("rating") == "D")
nC = sum(1 for v in rs.values() if v.get("rating") == "C")
print(f"评级重建: {len(rs)} 品种 D={nD} C={nC}")
flipped = [s for s, v in rs.items() if v.get("rating") == "C" and v.get("reason") == "insufficient_samples_small_pf"]
print(f"D级 n<5 已转C(小样本观察): {sorted(flipped)}")

# 重跑 advisory_to_order 提案 (用新评级)
sys.path.insert(0, "E:/GoldstrategyEngine/multi_agent/trading")
import advisory_to_order as a2o
from datetime import datetime
ev = "UNKNOWN"
ep = "E:/GoldstrategyEngine/data/event_risk.json"
try:
    ev = str(json.load(open(ep, encoding="utf-8")).get("level", "UNKNOWN"))
except Exception:
    pass
res = a2o.build("20261012", datetime.now(), rs, ev)
json.dump(res, open("E:/GoldstrategyEngine/data/pending_orders_proposal.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"提案重生成: {res['n_proposals']} 项, 放行 {res['n_proceed']}, killzone={res['killzone']}, event={ev}")
for p in res["proposals"]:
    if p["proceed"]:
        print(f"  PROCEED {p['sym']:8} {p['direction']:5} entry={p['entry']} sl={p['sl']} tp={p['tp']} lots={p['lots']} leg={p['leg']}")
# entry==tp 检查 (bug 已修, 应无)
bad = [p["sym"] for p in res["proposals"] if p["sym"].endswith("USD") is False and p.get("entry") == p.get("tp") and p.get("entry") is not None]
print(f"entry==tp 仍异常的外汇/股指条数: {len(bad)} {bad[:5]}")
