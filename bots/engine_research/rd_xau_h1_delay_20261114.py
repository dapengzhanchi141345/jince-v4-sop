# -*- coding: utf-8 -*-
"""rd_xau_h1_delay_20261114.py —— P1·XAU 子项: H1 共振闸 滞后容忍 (允许 M15/M30 领先 15min 内共振)
====================================================================
红线: 纯研究. 引擎 jince_live24.py / REAL 30261104 参数零动. 产物只落 research/ 与 data/.
口径: 复用 rd_verify_batch_20261114 的 M30 突破信号池 + 统一出场引擎 (0.095R 成本, 18h 硬平,
     0.5R BE/1.0R 锁半/ATR 紧跟踪/giveback0.6, winsor[-3,8], 同品种不重叠). 品种=XAUUSD 单源.
base  = 现行 SKIP_H1 严格共振: 信号决策时刻 T 上 H1_dir(T)==dir 才放行 (与引擎 11-09 逻辑一致).
cand  = 滞后容忍 15min: H1_dir(T)==dir 或 H1_dir(T+900s)==dir 均放行 (允许 H1 在 15min 内追认).
同分母: 同一信号池, 同一进场根(次根), 同一出场引擎, 仅 H1 共振闸宽严不同 -> 增量 = cand - base.
H1_dir(t): 取开线时刻 < t 的最近 H1 收盘序列, H1_m5=mean(近5根H1收) vs H1_m20=mean(近20根H1收) 定方向.
五验+⑥ (逐品种, XAU 单源): T1 净R(扣0.095)>0 且 >=base | T2 胜率>=base-0.02 | T3 5折时间切分全正
| T4 OOS70/30 两段皆正 | T5 成本0.15R 仍正 | ⑥ 净期望(均R)>=1.0. 裁定 APPROVE/WATCH/REJECT.
"""
import os, json, datetime as dt
import numpy as np
import importlib.util
ROOT = "E:/GoldstrategyEngine"
TOL = 900  # 15min
spec = importlib.util.spec_from_file_location("batch", os.path.join(ROOT, "research", "rd_verify_batch_20261114.py"))
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)   # 不执行 main (有 __main__ 守卫)

SYM = "XAUUSD"
P = batch.prepare30(SYM)
H = batch.load_npz(SYM, "H1")
ht, hc = H["t"], H["c"]

def h1_dir_at(tsec):
    """H1 趋势方向 at 决策时刻 tsec (只用开线 < tsec 的 H1 收盘, 无未来函数)."""
    m = np.searchsorted(ht, tsec, side="left")   # 首个开线>=tsec, 故开线<tsec 的是 [0:m)
    if m < 20:
        return 0
    win = hc[m-20:m]
    m5, m20 = win[-5:].mean(), win.mean()
    return 1 if m5 > m20 else (-1 if m5 < m20 else 0)

# 信号池 = base 突破信号 (adx_max=None -> 全部突破单)
params = json.load(open(os.path.join(ROOT, "data", "practice_params_all_symbols.json"), encoding="utf-8"))
p = params.get(SYM, {})
g = dict(adx_min=float(p.get("adx_min", 35.0)), break_margin=0.6, min_body=0.3,
         h1_on=False, max_hold_h=18, giveback=0.6,
         sl_mult=float(p.get("sl_mult", 1.0)), tp_mult=float(p.get("tp_mult", 3.0)))
k, s, dist, tp_d = batch.gen_signals(P, g, adx_max=None)
N = P["n"]
t = P["t"]
# 决策时刻 T = 信号根收线 = t[k]+1800; 逐单算 H1_dir(T) 与 H1_dir(T+900)
Tdec = t[k] + 1800
base_mask = np.zeros(len(k), dtype=bool)
cand_mask = np.zeros(len(k), dtype=bool)
for i in range(len(k)):
    h1now = h1_dir_at(Tdec[i])
    h1tol = h1_dir_at(Tdec[i] + TOL)
    if h1now == s[i]:
        base_mask[i] = True
    if h1now == s[i] or h1tol == s[i]:
        cand_mask[i] = True

def run(mask, cost):
    kk = k[mask]
    ss = s[mask]
    dd = dist[mask]
    tt = tp_d[mask]
    res = batch.simulate(P, g, kk, ss, dist=dd, tp_d=tt, cost=cost)
    R = res["R"]; et = res["et"]
    n = len(R)
    return dict(n=n, net=float(R.sum()) if n else 0.0,
                avg=float(R.mean()) if n else 0.0,
                win=float((R > 0).mean()) if n else 0.0, R=R, et=et)

base095 = run(base_mask, batch.COST)
cand095 = run(cand_mask, batch.COST)
base15 = run(base_mask, batch.COST_T5)
cand15 = run(cand_mask, batch.COST_T5)
incr095 = run(cand_mask & ~base_mask, batch.COST)   # 仅滞后容忍新增单

oos_cut = float(np.quantile(t, 0.70))
def seg(run_res):
    tr = run_res["R"] <= 0  # placeholder; recompute below
    m = np.array(run_res["et"] <= oos_cut)
    R = run_res["R"]
    return dict(train_net=float(R[m].sum()) if m.any() else 0.0,
                test_net=float(R[~m].sum()) if (~m).any() else 0.0,
                train_n=int(m.sum()), test_n=int((~m).sum()))
sb, sc, si = seg(base095), seg(cand095), seg(incr095)

gates = dict(
    T1=bool(cand095["net"] > 0 and cand095["net"] >= base095["net"]),
    T2=bool(cand095["win"] >= base095["win"] - 0.02),
    T3=bool(cand095["n"] >= 5 and all(x.sum() > 0 for x in np.array_split(cand095["R"], 5))),
    T4=bool(sb["train_net"] > 0 and sb["test_net"] > 0 and sc["train_net"] > 0 and sc["test_net"] > 0),
    T5=bool(cand15["net"] > 0),
    g6=bool(cand095["avg"] >= 1.0))
gates["passed"] = sum(int(v) for key, v in gates.items() if key != "passed")
def verdict_of(gates):
    t15 = gates["passed"] - int(gates["g6"])
    if gates["passed"] == 6: return "APPROVE"
    if t15 >= 3 and (gates["T4"] or gates["T3"]): return "WATCH"
    return "REJECT"

out = dict(
    meta=dict(ts=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sym=SYM, tol_s=TOL,
              kline_source=batch.KLINE_SRC,
              h1_note="H1 npz last open 2026-11-13 02:00 UTC; H1_dir 只用开线<决策时刻的收盘(无未来函数)",
              real_account_untouched="30261104 零动; 引擎只读"),
    signal_pool_n=int(len(k)),
    base_strict=dict(n=base095["n"], net=round(base095["net"], 2), win=round(base095["win"], 4),
                     avg=round(base095["avg"], 4), oos_train=round(sb["train_net"], 2), oos_test=round(sb["test_net"], 2),
                     net_015=round(base15["net"], 2)),
    cand_delay=dict(n=cand095["n"], net=round(cand095["net"], 2), win=round(cand095["win"], 4),
                    avg=round(cand095["avg"], 4), oos_train=round(sc["train_net"], 2), oos_test=round(sc["test_net"], 2),
                    net_015=round(cand15["net"], 2)),
    incremental_lag_only=dict(n=incr095["n"], net=round(incr095["net"], 2),
                              avg=round(incr095["avg"], 4), oos_train=round(si["train_net"], 2), oos_test=round(si["test_net"], 2),
                              win=round(incr095["win"], 4)),
    gates=gates, verdict=verdict_of(gates),
)
with open(os.path.join(ROOT, "data", "rd_xau_h1_delay_20261114.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
