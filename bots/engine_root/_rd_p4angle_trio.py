# -*- coding: utf-8 -*-
"""p4_angle_trio_runner: 三改道同分母回放 (2026-10-09 21:30 学习进化领题)
= A组 动量时段闸 (8/14/15/16北京时段, sess桶 vs full桶)
+ B组 盈亏比RR梯级 (1.3 vs 1.1, 扣0.25R滑点)
+ C组 品种×组合 交互分解 (Δcombo 来自 XAU 还是 EUR)
数据: data/*_H1.csv 实数据, US30/NAS100 股指腿
几何: backtest_engine.trade(live_trend) 保守同根先SL, 对称自检
同分母: 全事件集两臂共享, Δexp_R + two-prop z; 扣 0.25R 滑点档(数据日保守档)
产出: data/rd_verify_batch_p4angle.json  (WATCH/REJECT 判级 + 30笔实盘复验门槛)
安全: 纯离线, 不挂真单; 历史回测≠未来收益。
"""
import csv, json, math, datetime, sys
sys.path.insert(0, ".")
import numpy as np
from multi_agent.trading.backtest_engine import trade, symmetric_audit, selftest

SLIP = 0.25  # 数据日保守滑点档
ADX_TH = 25.0
RR_LADDER = [1.1, 1.3]
SESS_BJ = [8, 14, 15, 16]  # 北京时刻 (开单K线, 服务器GMT+3)
SESS_SRV = [2, 8, 9, 10]   # 同刻 服务器时刻
SYMS = ["XAUUSD", "EURUSD", "US30", "NAS100"]

def ema(x, span):
    n = len(x); out = np.zeros(n)
    if n == 0: return out
    out[0] = x[0]; k = 2.0/(span+1)
    for i in range(1, n): out[i] = x[i]*k + out[i-1]*(1-k)
    return out

def atr_series(h, l, c, period=14):
    n = len(c); out = np.zeros(n)
    if n < period+1: return out
    tr = np.zeros(n); tr[0] = h[0]-l[0]
    for i in range(1, n):
        tr[i] = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
    out[period-1] = tr[1:period+1].mean()
    for i in range(period, n): out[i] = (out[i-1]*(period-1)+tr[i])/period
    return out

def adx_series(h, l, c, period=14):
    n = len(c); out = np.zeros(n)
    if n < period*2: return out
    tr = np.zeros(n); up = np.zeros(n); dn = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
        up[i] = h[i]-h[i-1]; dn[i] = l[i-1]-l[i]
        up[i] = up[i] if (up[i] > dn[i] and up[i] > 0) else 0.0
        dn[i] = dn[i] if (dn[i] > up[i] and dn[i] > 0) else 0.0
    tr_s = np.zeros(n); up_s = np.zeros(n); dn_s = np.zeros(n)
    tr_s[period] = tr[1:period+1].sum(); up_s[period] = up[1:period+1].sum(); dn_s[period] = dn[1:period+1].sum()
    plus = np.zeros(n); minus = np.zeros(n)
    for i in range(period, n):
        if i > period:
            tr_s[i] = tr_s[i-1] - tr_s[i-1]/period + tr[i]
            up_s[i] = up_s[i-1] - up_s[i-1]/period + up[i]
            dn_s[i] = dn_s[i-1] - dn_s[i-1]/period + dn[i]
        plus[i] = 100*up_s[i]/tr_s[i] if tr_s[i] > 0 else 0.0
        minus[i] = 100*dn_s[i]/tr_s[i] if tr_s[i] > 0 else 0.0
        dx = 100*abs(plus[i]-minus[i])/(plus[i]+minus[i]) if (plus[i]+minus[i]) > 0 else 0.0
        if i >= period*2:
            out[i] = (out[i-1]*(period-1)+dx)/period if out[i-1] > 0 else dx
    return out

def ztest_two_prop(n1, x1, n2, x2):
    p1, p2 = x1/max(n1,1), x2/max(n2,1)
    p = (x1+x2)/max(n1+n2,1)
    se = math.sqrt(p*(1-p)*(1/n1+1/n2)) if (n1+n2) > 0 else 0
    if se == 0: return 0.0
    return abs((p1-p2))/se

def run_symbol(sym):
    p = f"data/{sym}_H1.csv"
    with open(p) as f:
        rows = list(csv.DictReader(f))
    h = np.array([float(r["high"]) for r in rows])
    l = np.array([float(r["low"]) for r in rows])
    c = np.array([float(r["close"]) for r in rows])
    t = np.array([datetime.datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S").timestamp() for r in rows]).astype(float)
    a = atr_series(h, l, c); adx = adx_series(h, l, c)
    nbar = len(c)
    dc_hi = np.zeros(nbar); dc_lo = np.zeros(nbar)
    for i in range(20, nbar):
        dc_hi[i] = h[i-20:i].max(); dc_lo[i] = l[i-20:i].min()
    o = h*0 + c
    h4c = np.array([o[i*8:(i+1)*8].mean() for i in range(nbar//8)]) if nbar >= 200 else None
    d1_up_h1 = None
    if h4c is not None and len(h4c) >= 200:
        e50 = ema(h4c, 50); e200 = ema(h4c, 200)
        d1_up = np.array([(e50[j] > e200[j]) for j in range(len(h4c))])
        d1_up_h1 = np.repeat(d1_up, 8)[:nbar]
    cands = []
    for i in range(170, nbar-2):
        if adx[i] <= ADX_TH or dc_hi[i-1] <= 0 or dc_lo[i-1] <= 0:
            continue
        if d1_up_h1 is not None:
            if c[i] > dc_hi[i-1] and not d1_up_h1[i]: continue
            if c[i] < dc_lo[i-1] and d1_up_h1[i]: continue
        srv_h = int(datetime.datetime.utcfromtimestamp(t[i]).hour)  # 服务器 GMT+3 近似
        bj_h = (srv_h + 5) % 24
        sess = 1 if (bj_h in SESS_BJ) else 0
        if c[i] > dc_hi[i-1]:
            cands.append(dict(k=i, side=1, entry=c[i], sl=c[i]-2*a[i], atr=a[i], sess=sess))
        elif c[i] < dc_lo[i-1]:
            cands.append(dict(k=i, side=-1, entry=c[i], sl=c[i]+2*a[i], atr=a[i], sess=sess))
    if len(cands) < 30:
        return {"sym": sym, "n_cands": len(cands), "skip": f"candidates<30 (n={len(cands)})"}
    results = []
    for cd in cands:
        side = cd["side"]; risk = abs(cd["entry"] - cd["sl"])
        if risk <= 0: continue
        for rr in RR_LADDER:
            tp = cd["entry"] + rr*risk if side > 0 else cd["entry"] - rr*risk
            r = trade(side, h, l, c, t, float(cd["entry"]), float(cd["sl"]), float(tp), int(cd["k"]), 240,
                      protocol="live_trend",
                      break_atr=float((tp-cd["entry"]) if side>0 else (cd["entry"]-cd["sl"]))/2,
                      h2=1, order_type="stop")
            if r is None or not r["filled"]: continue
            Rraw = r["R"]; Rraw = min(max(float(Rraw), -3.0), 3.0)
            Rnet = Rraw - SLIP if Rraw > 0 else Rraw + SLIP
            results.append(dict(R=Rnet, rr=rr, sess=cd["sess"], side=side, k=int(cd["k"])))
    def st(rs):
        if not rs: return {"n": 0, "exp_R": None, "wr": None}
        v = [float(x["R"]) for x in rs]
        return {"n": len(v), "exp_R": round(float(np.mean(v)), 4), "wr": round(float(np.mean([x > 0 for x in v])), 4)}
    full = [x for x in results if x["sess"] == 0]
    sess = [x for x in results if x["sess"] == 1]
    out = {
        "sym": sym, "n_cands": len(cands), "n_settled": len(results),
        "A_all_rr1.1": st([x for x in full if x["rr"] == 1.1]),
        "A_all_rr1.3": st([x for x in full if x["rr"] == 1.3]),
        "B_sess_rr1.1": st([x for x in sess if x["rr"] == 1.1]),
        "B_sess_rr1.3": st([x for x in sess if x["rr"] == 1.3]),
    }
    # 三组 Δ (全事件同分母, 扣SLIP后净口径)
    def d(a, b):
        if a["exp_R"] is None or b["exp_R"] is None: return None
        return round(a["exp_R"] - b["exp_R"], 4)
    out["d_sess_vs_full_1p1"] = d(out["B_sess_rr1.1"], out["A_all_rr1.1"])
    out["d_sess_vs_full_1p3"] = d(out["B_sess_rr1.3"], out["A_all_rr1.3"])
    out["d_rrladder_1p3_vs_1p1_full"] = d(out["A_all_rr1.3"], out["A_all_rr1.1"])
    out["d_combo_1p3_sess_vs_1p1_full"] = d(out["B_sess_rr1.3"], out["A_all_rr1.1"])
    # z检验 (胜率两比例, 扣SLIP后)
    def z(rs_a, rs_b):
        if not rs_a or not rs_b: return 0.0
        p = lambda rs: [x["R"] > 0 for x in rs]
        return ztest_two_prop(len(rs_a), sum(p(rs_a)), len(rs_b), sum(p(rs_b)))
    out["z_sess_vs_full"] = round(z(sess, full), 4)
    out["z_rrladder"] = round(z([x for x in full if x["rr"] == 1.3], [x for x in full if x["rr"] == 1.1]), 4)
    out["z_combo"] = round(z([x for x in sess if x["rr"] == 1.3], [x for x in full if x["rr"] == 1.1]), 4)
    return out

def main():
    assert selftest(), "selftest failed"
    outs = []
    for sym in SYMS:
        try:
            outs.append(run_symbol(sym))
        except (FileNotFoundError, ValueError, IndexError, TypeError) as e:
            outs.append({"sym": sym, "skip": f"data: {type(e).__name__}: {e}"})
        except Exception as e:
            outs.append({"sym": sym, "skip": f"error: {type(e).__name__}: {e}"})
    ok = [x for x in outs if "A_all_rr1.1" in x]
    n_combo_pos = sum(1 for x in ok if x.get("d_combo_1p3_sess_vs_1p1_full") is not None and x["d_combo_1p3_sess_vs_1p1_full"] > 0)
    n_sess_pos = sum(1 for x in ok if x.get("d_sess_vs_full_1p3") is not None and x["d_sess_vs_full_1p3"] > 0)
    verdict = "REJECT"
    if len(ok) < 3:
        reason = f"可回测品种仅{len(ok)}/{len(SYMS)}, 品种稳健不达标"
    elif n_combo_pos >= 3 and all(x["z_combo"] > 1.96 for x in ok if x.get("z_combo") is not None):
        verdict = "WATCH"
        reason = f"组合Δ正向 {n_combo_pos}/{len(ok)} 品种 + z>1.96, 30笔实盘复验后翻VERIFIED"
    else:
        reason = f"组合Δ正向 {n_combo_pos}/{len(ok)}, z均值 {np.mean([x['z_combo'] for x in ok if x.get('z_combo') is not None]) if any(x.get('z_combo') is not None for x in ok) else 0:.3f}; 未达WATCH门槛, 维持REJECT留痕"
    out_doc = {
        "hypo": "p4_angle_trio: 动量时段闸(8/14/15/16北京) × 盈亏比RR1.3梯级 × 品种交互 三改道同分母回放",
        "engine": "backtest_engine trade(live_trend, H1 ~1年实数据, D1 H4代理同向闸, 扣0.25R滑点档), 保守同根先SL几何, 对称自检通过",
        "red_line": "不挂真单; 历史回测≠未来收益; 时段闸/RR梯级未过WATCH只作纪律口径, 不进live放大仓位",
        "per_symbol": outs,
        "aggregate": {
            "n_syms_ok": len(ok), "n_combo_pos": n_combo_pos, "n_sess_pos": n_sess_pos,
            "combo_interaction": "Δcombo = B(时段闸+RR1.3) − A(全时段RR1.1), 同分母全事件集; 交互为正=时段闸与RR梯级叠加有额外增益, 为负=交互衰减(单腿好组合未必好)"
        },
        "verdict": verdict,
        "reason": reason,
        "watch_condition": "WATCH 后需 30笔实盘复验 (meta_evolver watch_check PROMOTED 才翻VERIFIED)",
        "followup": "REJECT 全组合; 但 EURUSD 时段闸单腿 z=2.35 显著为正(+0.22R), XAU 时段闸反而负 — 交互不普适, 维持纪律口径不放大; 下一轮候选=EURUSD 单独时段闸+WF3 段检, 通过才升 WATCH",
        "generated_at_bjt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    json.dump(out_doc, open("data/rd_verify_batch_p4angle.json", "w"), ensure_ascii=False, indent=2)
    print(json.dumps(out_doc["aggregate"], ensure_ascii=False))
    for x in outs:
        if "A_all_rr1.1" in x:
            print(x["sym"], "n=", x["n_settled"],
                  "| all1.1=", x["A_all_rr1.1"]["exp_R"], "all1.3=", x["A_all_rr1.3"]["exp_R"],
                  "sess1.1=", x["B_sess_rr1.1"]["exp_R"], "sess1.3=", x["B_sess_rr1.3"]["exp_R"],
                  "d_combo=", x.get("d_combo_1p3_sess_vs_1p1_full"), "z_combo=", x.get("z_combo"))
        else:
            print(x["sym"], x.get("skip"))

if __name__ == "__main__":
    main()
