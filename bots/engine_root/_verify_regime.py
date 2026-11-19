# -*- coding: utf-8 -*-
"""
_verify_regime.py — regime 过滤(Hurst + MACD面积背驰)作为日内挂单层质量闸 有效性回测
==============================================================================
- 数据: MT5 只读 (Demo), BTCUSD/ETHUSD/SOLUSD/XRPUSD, H4 全史 2600 根
- 事件: H4 布林带(20,2) 上下轨触及 (high>=upper / low<=lower), 简化日内挂单事件
- 过滤条件 (均用事件当根之前 60 根窗口, 严格前向, 当根不参与):
    H_trend : 前60根 hurst(close60, 60) >= 0.618
    H_mrev  : 前60根 hurst <= 0.382
    DIV     : 前60根 macd_area_divergence(close60).divergent == True
    DIV_TREN: DIV 且 H_trend  (顺轨单: 上轨触及→看多 fwd2, 下轨触及→看空 fwd2)
- 对照: 同事件同分母
    B_base : 盲目反做 (上轨→fwd2 看空, 下轨→fwd2 看多)
    B_trend: 盲目顺做 (上轨→fwd2 看多, 下轨→fwd2 看空)
- 指标: fwd2 = close[t+2]/close[t] 方向; 胜率 = 方向命中比例 (平局剔除, 分母=有向事件数)
- 显著性: 双样本二项比例 z 检验 (pooled SE); 单边 p 检验 "过滤组胜率高于对照"
- 产出: data/skills_verify_regime.json
"""
import os, sys, json, math
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "multi_agent", "trading"))

import MetaTrader5 as mt5
import structure_fusion as sf

SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"]
N_H4 = 2600
WIN = 60          # 过滤条件窗口 (当根之前 60 根)
FWD = 2           # fwd2 H4 close
H_TREND, H_MREV = 0.618, 0.382

ACCOUNT_ID = 60137964
SERVER = "TradeMaxGlobal-Demo"
PASSWORD = ""


def fetch(sym):
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, N_H4)
    if rates is None or len(rates) < 200:
        raise RuntimeError(f"{sym} 取数失败: {len(rates) if rates is not None else 0}")
    df = rates
    return {"o": df["open"], "h": df["high"], "l": df["low"], "c": df["close"]}


def boll_touch(h, l, c, n=20, k=2.0):
    up = np.full_like(c, np.nan); lo = np.full_like(c, np.nan)
    for i in range(n, len(c)):
        w = c[i - n + 1:i + 1]
        m = w.mean(); sd = w.std(ddof=0)
        up[i] = m + k * sd
        lo[i] = m - k * sd
    touch_hi = np.zeros(len(c), bool)
    touch_lo = np.zeros(len(c), bool)
    touch_hi[n:] = h[n:] >= up[n:]
    touch_lo[n:] = l[n:] <= lo[n:]
    return touch_hi, touch_lo, up, lo


def hurst60(close_w):
    return _hurst_rs(close_w)


def _hurst_rs(close_w, min_obs=30):
    """60根窗口 R/S Hurst: 2^k lag 序列 (2,4,8,16,32), 逐 lag 全窗口 R/S,
    log-log 线性拟合取斜率; 样本不足/拟合退化回退 0.5. 与 sf.hurst 算法同构
    (sf.hurst 因近2000根截断+lag数下限, 60根窗口永远退化为0.5, 故此处按
    窗口语义重实现, 保持 R/S 口径一致)."""
    r = np.diff(np.log(np.asarray(close_w, float) + 1e-12))
    n = len(r)
    if n < min_obs:
        return 0.5
    lags = [float(2 ** k) for k in range(1, 6)]
    lags = [L for L in lags if L < n]
    if len(lags) < 4:
        return 0.5
    sds, rs_by_lag = [], []
    for L in lags:
        Li = int(L)
        vals = []
        for start in range(0, n - Li, Li):
            seg = r[start:start + Li]
            dev = np.cumsum(seg - seg.mean())
            R = dev.max() - dev.min()
            S = seg.std()
            if S > 0:
                vals.append(R / S)
        if vals:
            sds.append(L)
            rs_by_lag.append(np.mean(vals))
    if len(sds) < 4:
        return 0.5
    slope = np.polyfit(np.log(sds), np.log(rs_by_lag), 1)[0]
    return float(max(0.0, min(1.0, slope)))


def div60(close_w):
    return sf.macd_area_divergence(close_w, rate=0.9)


def binom_ztest(n1, w1, n2, w2):
    """双样本二项比例 z 检验, 返回 (delta(pp), two-sided p). w=命中数."""
    if n1 == 0 or n2 == 0:
        return 0.0, 1.0
    p1, p2 = w1 / n1, w2 / n2
    ppool = (w1 + w2) / (n1 + n2)
    se = math.sqrt(ppool * (1 - ppool) * (1.0 / n1 + 1.0 / n2))
    if se == 0:
        return 0.0, 1.0
    z = (p1 - p2) / se
    delta = (p1 - p2) * 100
    p = 2 * (1 - _norm_cdf(abs(z)))
    return delta, p, z


def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def main():
    print("[setup] MT5 初始化 ...")
    if not (mt5.initialize() and mt5.login(ACCOUNT_ID, password=PASSWORD, server=SERVER)):
        print(f"[!] MT5 登录失败: {mt5.last_error()}")
        sys.exit(1)
    print("[OK] MT5 已登录")

    per_sym = {}
    # 每个符号逐事件收集 (t, side=+1/±1, fwd2_close, H, div, side_blind)
    events = []
    for sym in SYMS:
        try:
            d = fetch(sym)
        except Exception as e:
            print(f"[!] {sym} 取数失败: {e}, 跳过")
            continue
        c = d["c"]; h = d["h"]; l = d["l"]
        touch_hi, touch_lo, up, lo = boll_touch(h, l, c)
        for t in range(WIN + 1, len(c) - FWD - 1):
            if not (touch_hi[t] or touch_lo[t]):
                continue
            side = 1 if touch_hi[t] else -1   # 上轨触及=+1, 下轨=-1
            close60 = c[t - WIN:t]
            Hv = hurst60(close60)
            dv = div60(close60)["divergent"]
            fwd2 = c[t + FWD] / c[t]
            events.append({
                "sym": sym, "t": t, "side": side,
                "fwd2_up": fwd2 > 1.0, "fwd2_dn": fwd2 < 1.0,
                "H": Hv, "div": bool(dv),
            })
        print(f"[OK] {sym}: {len(c)} 根, 事件累计 {len(events)}")
    mt5.shutdown()

    evs = np.array([e["side"] for e in events], dtype=int)
    fwd_up = np.array([e["fwd2_up"] for e in events])
    fwd_dn = np.array([e["fwd2_dn"] for e in events])
    Hv = np.array([e["H"] for e in events])
    dv = np.array([e["div"] for e in events])
    n_all = len(events)
    print(f"[OK] 全事件 n={n_all} (上轨 {int((evs==1).sum())} / 下轨 {int((evs==-1).sum())})")

    def wr(side_idx, direction="align"):
        """side_idx: bool 数组 (事件子集); direction='align' 顺轨 / 'counter' 反轨."""
        s = evs[side_idx]
        if direction == "align":
            hit = (s == 1) & fwd_up[side_idx] | (s == -1) & fwd_dn[side_idx]
        else:
            hit = (s == 1) & fwd_dn[side_idx] | (s == -1) & fwd_up[side_idx]
        # 平局 (fwd2==close[t]) 剔除: 该事件既未 up 也未 dn
        decided = fwd_up[side_idx] | fwd_dn[side_idx]
        n = int(decided.sum())
        w = int(hit[decided].sum())
        return n, w

    def stat(name, mask, direction):
        n, w = wr(mask, direction)
        base_n, base_w = wr(np.ones(n_all, bool), "counter")
        base_wr = base_w / base_n if base_n else float("nan")
        if n == 0:
            return {"name": name, "n": 0, "wr": None, "wr_comparator": round(base_wr, 4),
                    "delta": None, "p": None, "z": None}
        wr_ = w / n
        delta, p, z = binom_ztest(n, w, base_n, base_w)
        return {"name": name, "n": n, "wr": round(wr_, 4), "wr_comparator": round(base_wr, 4),
                "delta": round(delta, 4), "p": round(p, 4), "z": round(z, 4),
                "w": w, "n_comparator": base_n, "w_comparator": base_w}

    h_trend = Hv >= H_TREND
    h_mrev = Hv <= H_MREV
    combo = dv & h_trend

    base_mask = np.ones(n_all, bool)
    base = stat("盲反做(全事件基线)", base_mask, "counter")
    s1 = stat("盲顺做(全事件)", base_mask, "align")
    s2 = stat("DIV单独-顺轨", dv, "align")
    s3 = stat("H_trend单独-顺轨", h_trend, "align")
    s4 = stat("DIV+trendH叠加-顺轨", combo, "align")
    s5 = stat("DIV+反轨对照", dv, "counter")

    def verdict(s, lo=0.0):
        # s['delta'] 相对盲反做基线 (顺做 vs 反做, 同分母)
        if s.get("n", 0) == 0:
            return "样本不足"
        z = s.get("z")
        if z is None:
            return "无显著性"
        if s["delta"] > 0 and z >= 1.96:
            return "有效(显著高于盲反做)"
        if s["delta"] > 0:
            return "不显著(倾向正向)"
        if s["delta"] < 0 and z <= -1.96:
            return "反向(显著低于盲反做)"
        return "不显著"

    verdicts = []
    for s in [s2, s3, s4]:
        v = verdict(s)
        verdicts.append({
            "组件": s["name"],
            "判级": v,
            "数字": f"n={s['n']}, wr={s.get('wr')} vs 基线{base['wr_comparator']}, "
                    f"delta={s.get('delta')}pp, p={s.get('p')}"
        })

    # 建议: 哪个叠加最强且显著正向才建议接否决门
    best = s4
    if s4.get("n", 0) >= 30 and s4.get("delta") is not None and s4["delta"] > 0 and s4.get("z", 0) >= 1.96:
        advice = "接进intra层做否决门"
    elif s4.get("delta") is not None and s4["delta"] > 0:
        advice = "保留(不显著, 暂不否决门化, 继续观察)"
    else:
        advice = "不动"

    out = {
        "事件数": n_all,
        "盲反做基线": base,
        "盲顺做": s1,
        "各过滤边际": [s2, s3, s4, s5],
        "结论": verdicts,
        "建议": advice,
        "note": "同分母对照=全事件盲反做基线; fwd2 H4 close 方向; p=双样本二项z检验(双侧); "
                "各符号事件已混合, side=轨触方向; 平局( fwd2==open )剔除。",
    }

    out_path = os.path.join(ROOT, "data", "skills_verify_regime.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[OK] 写出 {out_path}")

    # ---- 短输出 ----
    print("\n=== 结果 ===")
    print(f"事件总数: {n_all}")
    print(f"基线盲反做: n={base['n']}, wr={base.get('wr')}")
    for s in [s1, s2, s3, s4, s5]:
        wrs = f"{s.get('wr')}" if s.get('wr') is not None else "-"
        dlt = f"{s.get('delta')}" if s.get('delta') is not None else "-"
        pv = f"{s.get('p')}" if s.get('p') is not None else "-"
        print(f"  {s['name']:>18s}: n={s.get('n', 0):<4d} wr={wrs:<6s} delta={dlt:<8s} p={pv}")
    for v in verdicts:
        print(f"  判级: {v['组件']} → {v['判级']} ({v['数字']})")
    print(f"建议: {advice}")
    if best.get("n", 0):
        print(f"best_filter_delta(DIV+trendH vs 基线盲反做): {best['delta']}pp")


if __name__ == "__main__":
    main()
