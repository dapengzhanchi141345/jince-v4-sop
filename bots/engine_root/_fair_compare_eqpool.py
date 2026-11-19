# -*- coding: utf-8 -*-
# 等点池否决门 公平对照 (同分母): 拆穿"选择效应", 定 放大/保留/回滚
# 旧口径=全事件盲目反做; 新口径=池内反做 + 孤点顺做(交给趋势层). 两者都在全部15051事件上算.
# 新口径相对旧口径的边际贡献 只来自 孤点事件(反做→顺做 翻转).
# 产出: data/eqpool_fair_compare.json
import sys, json
sys.path.insert(0, "E:/GoldstrategyEngine")
sys.path.insert(0, "E:/GoldstrategyEngine/multi_agent/trading")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import MetaTrader5 as mt5
import _accept_eqpool as m

mt5.initialize()
mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
all_evts = []
for sym in m.SYMS:
    d1 = m.pull_d1(sym, 5000)  # 全史口径与 main 的 b) 组一致 (days=5000)
    if d1 is None:
        print(f"[!] {sym} 无数据, 跳过")
        continue
    all_evts.append((sym, m.build_events(d1, fwd=2)))
mt5.shutdown()

evts = [e for _, grp in all_evts for e in grp]
n_all = len(evts)
pool = [e for e in evts if e["in_pool"]]
lone = [e for e in evts if e["lone"]]

def rev_win(e):   # 反做胜率 (扫多hi→做空对=fwd<close; 扫空lo→做多对=fwd>close)
    return e["fwd"] < e["close"] if e["side"] == "hi" else e["fwd"] > e["close"]

def tr_win(e):    # 顺做胜率 = 反做的补集
    return e["fwd"] > e["close"] if e["side"] == "hi" else e["fwd"] < e["close"]

# 旧策略: 全事件反做
wr_old = sum(rev_win(e) for e in evts) / n_all
# 新策略: 池内反做 + 孤点顺做 (同分母 n_all)
wr_new_fair = (sum(rev_win(e) for e in pool) + sum(tr_win(e) for e in lone)) / n_all

# 孤点子集内部: 反做 vs 顺做 (gate 边际贡献的真正来源)
lone_rev = sum(rev_win(e) for e in lone) / len(lone)
lone_tr  = sum(tr_win(e) for e in lone) / len(lone)
pool_rev = sum(rev_win(e) for e in pool) / len(pool)

import math
def z2p(w1, n1, w2, n2):
    p1, p2 = w1 / n1, w2 / n2
    pp = (w1 + w2) / (n1 + n2)
    se = math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
    z = (p2 - p1) / se if se else 0.0
    return z, 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))

z_ns, p_ns = z2p(wr_old * n_all, n_all, wr_new_fair * n_all, n_all)  # 新vs旧 同分母
z_lt, p_lt = z2p(lone_rev * len(lone), len(lone), lone_tr * len(lone), len(lone))  # 孤点 顺vs反

res = {
    "口径说明": "同分母公平对照: 新旧策略都在全部{n}事件上评估; 新策略=池内反做+孤点顺做",
    "n_all": n_all, "n_pool": len(pool), "n_lone": len(lone),
    "wr_old_all_reversal": round(wr_old, 4),
    "wr_new_fair": round(wr_new_fair, 4),
    "fair_delta": round(wr_new_fair - wr_old, 4),
    "fair_z": round(z_ns, 3), "fair_p": round(p_ns, 4),
    "lone_reversal_wr": round(lone_rev, 4),
    "lone_trend_wr": round(lone_tr, 4),
    "lone_z": round(z_lt, 3), "lone_p": round(p_lt, 4),
    "pool_reversal_wr": round(pool_rev, 4),
}
res["结论"] = ("放大" if (wr_new_fair - wr_old > 0.01 and p_ns < 0.05)
            else "回滚" if (wr_new_fair - wr_old < -0.01 and p_ns < 0.05)
            else "保留中性0.6待观察(边际贡献不显著或双向不占优)")
print(json.dumps(res, ensure_ascii=False, indent=1))
json.dump(res, open("E:/GoldstrategyEngine/data/eqpool_fair_compare.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("[OK] 已写 data/eqpool_fair_compare.json")
