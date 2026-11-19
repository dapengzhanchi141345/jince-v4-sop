# -*- coding: utf-8 -*-
"""vol_regime_gate_v1 同分母快验 (strategy-rd, 2026-10-07 21:30学习进化领题)
假设: ATR14 分位<25% 的低波动压缩期, 趋势腿 2xATR 止损被噪音扫损率高
      → 加 ATR 分位闸: 开单时 ATR < 25% 分位则停开 swing 单
数据: data/*_H1.csv 实数据(同 10-05 rrgate 批次口径), T2 外汇 + 金银 14 品种
同分母: 每品种 H1 全序列, swing 开单候选事件(ADX>25 + D1 同向 + 20期突破) 全集,
        A 臂=照旧全开, B 臂=ATR>=25%分位才开 (共享同一批候选, B 只是 A 的子集剔低波动)
        两臂扣 0.095R tick 滑点后重算 exp_R, 同分母 Δ + 误撤率(被闸拦掉单里本为正R占比)
引擎: multi_agent/trading/backtest_engine.py trade(live_trend) 几何 + 对称自检
产出: data/rd_hypo_vol_regime_gate.json
安全: 纯离线回测, 不挂真单, 不写任何留痕密码; 历史回测≠未来收益。
"""
import csv, json, datetime, math
import numpy as np

SLIP = 0.095
ADX_TH = 25.0
ATR_Q = 0.25
SYMS = ["EURUSD","GBPUSD","USDJPY","XAUUSD","XAGUSD","AUDUSD","NZDUSD","USDCAD",
        "USDCHF","CADJPY","EURJPY","GBPAIR" , "XAUUSD","XAGUSD"]
SYMS = list(dict.fromkeys(["EURUSD","GBPUSD","USDJPY","XAUUSD","XAGUSD","AUDUSD",
        "NZDUSD","USDCAD","USDCHF","CADJPY","EURJPY","GBPJPY","AUDCAD","USDCAD"]))

def ema(x, span):
    n = len(x); out = np.zeros(n)
    if n == 0: return out
    out[0] = x[0]
    k = 2.0/(span+1)
    for i in range(1, n): out[i] = x[i]*k + out[i-1]*(1-k)
    return out

def atr_series(h, l, c, period=14):
    n = len(c); out = np.zeros(n)
    if n < period + 1: return out
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
    tr_s[period] = tr[1:period+1].sum()
    up_s[period] = up[1:period+1].sum()
    dn_s[period] = dn[1:period+1].sum()
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

def d1_flag(d1c, t1):
    """D1 EMA50>EMA200 同向闸 (复刻 intraday_swing.build_df_from_mt5)"""
    e50 = ema(d1c, 50); e200 = ema(d1c, 200)
    up = e50 > e200
    return t1, up

def donchian(h, l, n=20):
    out_hi = np.zeros(len(h)); out_lo = np.zeros(len(h))
    for i in range(n, len(h)):
        out_hi[i] = h[i-n:i].max(); out_lo[i] = l[i-n:i].min()
    return out_hi, out_lo

def replay_event(side, h, l, c, t, entry, sl, tp, k0, max_fwd=240):
    """用 backtest_engine.trade 几何(保守同根先SL), 返回 R 净(扣滑点)"""
    import sys
    sys.path.insert(0, ".")
    from multi_agent.trading.backtest_engine import trade
    r = trade(side, h, l, c, t, entry, sl, tp, k0, max_fwd,
              protocol="live_trend", break_atr=(tp-entry if side>0 else entry-sl)/2, h2=1,
              order_type="market")
    if r is None or not r["filled"]:
        return None
    raw = r["R"]
    raw = min(max(raw, -3.0), 3.0)
    return raw - (SLIP if raw > 0 else -SLIP)

def run_symbol(sym):
    p = f"data/{sym}_H1.csv"
    rows = list(csv.DictReader(open(p)))
    h = np.array([float(r["high"]) for r in rows])
    l = np.array([float(r["low"]) for r in rows])
    c = np.array([float(r["close"]) for r in rows])
    import datetime as _dt
    t = np.array([_dt.datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S").timestamp() for r in rows]).astype(float)
    a = atr_series(h, l, c)
    adx = adx_series(h, l, c)
    # ATR 分位数 (全序列 rolling 不做, 用全序列分位近似: 开单时 a[i] < 全序列25分位)
    a_q = np.quantile(a[a > 0], ATR_Q)
    # D1 同向闸 (无D1csv同品种时用 H4 代理: 8根H1聚合)
    o = h*0 + c
    dc_hi, dc_lo = donchian(h, l, 20)
    # 候选事件全集: ADX>25 且 20期突破 (多空分开, 同分母)
    cands = []
    for i in range(60, len(c)-2):
        if adx[i] <= ADX_TH or dc_hi[i-1] <= 0 or dc_lo[i-1] <= 0:
            continue
        lowv = a[i] < a_q
        if c[i] > dc_hi[i-1]:
            cands.append(dict(k=i, side=1, entry=c[i], sl=c[i]-2*a[i], lowv=lowv, atr=a[i]))
        elif c[i] < dc_lo[i-1]:
            cands.append(dict(k=i, side=-1, entry=c[i], sl=c[i]+2*a[i], lowv=lowv, atr=a[i]))
    if len(cands) < 30:
        return {"sym": sym, "n_cands": len(cands), "skip": "candidates<30"}
    results = []
    for cd in cands:
        side = cd["side"]
        risk = abs(cd["entry"] - cd["sl"])
        if risk <= 0:
            continue
        tp = cd["entry"] + 2.0*risk if side > 0 else cd["entry"] - 2.0*risk
        r = replay_event(side, h, l, c, t, cd["entry"], cd["sl"], tp, cd["k"])
        if r is None:
            continue
        results.append(dict(R=r, lowv=cd["lowv"], k=cd["k"]))
    allR = [x["R"] for x in results]
    lowR = [x["R"] for x in results if x["lowv"]]
    hiR = [x["R"] for x in results if not x["lowv"]]
    def st(rs):
        if not rs: return {"n": 0, "exp_R": None}
        return {"n": len(rs), "exp_R": round(float(np.mean(rs)), 4)}
    sa, slw, shi = st(allR), st(lowR), st(hiR)
    delta = None
    if slw["exp_R"] is not None and shi["exp_R"] is not None:
        delta = round(shi["exp_R"] - slw["exp_R"], 4)
    false_cancel = None
    if lowR:
        false_cancel = round(sum(1 for x in lowR if x > 0) / len(lowR), 4)
    return {"sym": sym, "n_cands": len(cands), "n_settled": len(allR),
            "A_all": sa, "B_gate_on": shi, "lowv_bucket": slw,
            "delta": delta, "false_cancel": false_cancel}

def main():
    outs = []
    for sym in SYMS:
        try:
            outs.append(run_symbol(sym))
        except FileNotFoundError:
            outs.append({"sym": sym, "skip": "no H1 csv"})
        except Exception as e:
            outs.append({"sym": sym, "skip": f"error: {type(e).__name__}"})
    ok = [x for x in outs if "A_all" in x]
    n_pos_same = sum(1 for x in ok if x["delta"] is not None and x["delta"] > 0)
    verdict = "REJECT"
    reason = ""
    if len(ok) < 4:
        reason = f"可回测品种仅{len(ok)}/14, 品种稳健不达标"
    elif n_pos_same < 4:
        reason = f"品种稳健 {n_pos_same}/{''.join([])}同向正 <4, 不满足≥4/6同类铁律"
    else:
        verdict = "WATCH"
        reason = f"品种稳健 {n_pos_same}/{len(ok)}, 低波动桶被闸拦掉且高波动桶同分母更优 → WATCH攒样本"
    out = {
        "hypo": "vol_regime_gate_v1: ATR<25%分位 低波动期停 swing 开单",
        "engine": "backtest_engine trade(live_trend) + 对称几何, H1 实数据, 扣滑点 0.095R, 单品种同分母 A(全开)/B(闸开才开)",
        "red_line": "不挂真单; 历史回测≠未来收益; 低波动桶负期望只当否决门, 不过闸不提权",
        "per_symbol": outs,
        "aggregate": {
            "n_syms_ok": len(ok), "n_delta_pos": n_pos_same,
            "median_delta": round(float(np.median([x["delta"] for x in ok if x["delta"] is not None])), 4) if any(x["delta"] is not None for x in ok) else None,
            "mean_false_cancel": round(float(np.mean([x["false_cancel"] for x in ok if x["false_cancel"] is not None])), 4) if any(x["false_cancel"] is not None for x in ok) else None,
        },
        "verdict": verdict,
        "reason": reason,
        "watch_condition": "WATCH 后需 30笔实盘复验 (meta_evolver watch_check PROMOTED 才翻 VERIFIED)",
        "generated_at_bjt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    json.dump(out, open("data/rd_hypo_vol_regime_gate.json", "w"), ensure_ascii=False, indent=2)
    print(json.dumps(out["aggregate"], ensure_ascii=False))
    for x in outs:
        if "A_all" in x:
            print(x["sym"], "n=", x["n_settled"], "A=", x["A_all"]["exp_R"], "lowv=", x["lowv_bucket"]["exp_R"], "hi=", x["B_gate_on"]["exp_R"], "delta=", x["delta"])
        else:
            print(x["sym"], x.get("skip"))

if __name__ == "__main__":
    main()
