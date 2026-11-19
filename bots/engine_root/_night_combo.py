# -*- coding: utf-8 -*-
# 族5 组合层: M30趋势腿P0(SLM3.0) × 日内腿全时段 组合模拟 + Kelly/vol-target 仓位缩放
# 数据只读 data/tf_cache/*.npz; 趋势腿几何 = _tf_m30.py replay 口径, 日内腿 = _intra_tfsweep.py 几何(00-24, close口径)
# 12个月 = 全史最后12个月; 1%风险/笔固定仓位 + 分数Kelly/vol-target缩放 + 熔断对照
import json, os, time
import numpy as np
import numpy.lib.stride_tricks as st
import pandas as pd

ROOT = r"E:/GoldstrategyEngine"
CACHE = os.path.join(ROOT, "data", "tf_cache")
OUT = os.path.join(ROOT, "data", "night_rd_combo.json")
T_END = 1790427600
T_START = T_END - 12 * 30 * 86400  # 2025-08 左右
CAP0 = 1.0
SLIP = 0.095          # P95 滑点档
CAP = 3              # 每品种每日最多3单
DAYSTOP = 0.10       # 日亏10%熔断
LOOK_AHEAD = 42
FILL_WINDOW = 4
SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]

print(f"[start] {time.strftime('%H:%M:%S')} T_START={T_START}")

def load(sym, tf):
    a = np.load(f"{CACHE}/{sym}_{tf}.npz")
    return dict(t=a["t"].astype(np.int64), h=a["h"].astype(np.float64),
                l=a["l"].astype(np.float64), c=a["c"].astype(np.float64))

def atr_wilder(h, l, c, p=14):
    n = len(c)
    tr = np.empty(n); tr[0] = h[0] - l[0]
    if n > 1:
        tr[1:] = np.maximum(h[1:] - l[1:],
                            np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    out = np.zeros(n)
    if n <= p:
        return out
    out[p] = tr[1:p + 1].mean()
    for i in range(p + 1, n):
        out[i] = (out[i - 1] * (p - 1) + tr[i]) / p
    return out

def atr_last(h, l, c, i0, i1):
    """当日已完結H1区间的因果 ATR14 (对齐 _intra_tfsweep: 区间末尾 ATR)"""
    seg = slice(max(0, i0), i1)
    if i1 - max(0, i0) < 15:
        return None
    return atr_wilder(h[seg], l[seg], c[seg])[-1]

def build_trend_fills():
    """趋势腿 M30 P0 SLM=3.0: 全史 fills (ts, sym, side, R, ts_exit), 过滤 T_START 起"""
    fills = []
    for sym in SYMS:
        d1 = load(sym, "D1"); m = load(sym, "M30")
        hh, ll, cc, tt = m["h"], m["l"], m["c"], m["t"]
        hi = st.sliding_window_view(hh, 20).max(axis=1)[:-19]
        lo = st.sliding_window_view(ll, 20).min(axis=1)[:-19]
        atr = atr_wilder(hh, ll, cc)
        d1t, d1c = d1["t"], d1["c"]
        d1t_comp = d1t + 86400
        t0_i = int(np.searchsorted(tt, T_START))
        hi_n = len(hi)  # 比 M30 少19根
        # 事件循环 (只扫 T_START 起), 但 D1闸/Donchian/ATR 均因果计算
        for i in range(max(21, t0_i - 1), min(len(tt) - 1, hi_n)):
            ts = int(tt[i])
            if ts < T_START:
                continue
            ok = d1t + 86400 <= ts
            idx = np.where(ok)[0]
            if len(idx) == 0 or idx[-1] < 1:
                continue
            j = int(idx[-1])
            g = 1 if d1c[j] > d1c[j - 1] else 0
            a = atr[i]
            if not a > 0:
                continue
            hi_i = hi[i]; lo_i = lo[i]
            if not (hi_i > 0 and lo_i > 0):
                continue
            side, trig = 0, 0.0
            if g == 1 and cc[i] < hi_i * 1.003:
                side, trig = 1, float(hi_i * 1.003)
            elif g == 0 and cc[i] > lo_i / 1.003:
                side, trig = -1, float(lo_i / 1.003)
            else:
                continue
            # 当期4根成交判定 (spec 铁律2: 事件bar之后的4根, _tf_m30.py 口径)
            j0 = i + 1
            if j0 >= len(tt) or j0 + FILL_WINDOW > len(tt):
                continue
            seg_h = hh[j0:j0 + FILL_WINDOW]; seg_l = ll[j0:j0 + FILL_WINDOW]
            if side == 1:
                f = np.where(seg_h >= trig)[0]
            else:
                f = np.where(seg_l <= trig)[0]
            if len(f) == 0:
                continue
            fidx = int(f[0])
            fill_ts = int(tt[j0 + fidx])
            if fill_ts < T_START:
                continue
            a2 = atr[j0 + fidx]
            if not a2 > 0:
                continue
            sl = trig - 3.0 * a2 if side == 1 else trig + 3.0 * a2
            r0 = abs(trig - sl)
            if r0 <= 0:
                continue
            tp = trig + 2 * r0 if side == 1 else trig - 2 * r0
            # 前向42根自成交bar起 (close口径超时计R)
            end = min(j0 + fidx + LOOK_AHEAD, len(tt))
            if end - (j0 + fidx) < 2:
                continue
            hseg = hh[j0 + fidx:end]; lseg = ll[j0 + fidx:end]; cseg = cc[j0 + fidx:end]
            tseg = tt[j0 + fidx:end]
            R = None; exit_ts = None
            for k in range(len(hseg)):
                hhk, llk = hseg[k], lseg[k]
                if side == 1:
                    if llk <= sl:
                        R, exit_ts = -1.0, int(tseg[k]); break
                    if hhk >= tp:
                        R, exit_ts = 2.0, int(tseg[k]); break
                else:
                    if hhk >= sl:
                        R, exit_ts = -1.0, int(tseg[k]); break
                    if llk <= tp:
                        R, exit_ts = 2.0, int(tseg[k]); break
            if R is None:
                R = (cseg[-1] - trig) / r0 if side == 1 else (trig - cseg[-1]) / r0
                exit_ts = int(tseg[-1])
            fills.append(dict(ts=fill_ts, sym=sym, side=side, R=float(R), te=exit_ts))
    fills.sort(key=lambda x: x["ts"])
    Rs = np.array([f["R"] for f in fills])
    print(f"[trend] fills={len(fills)} exp_R={Rs.mean():+.4f} wr={(Rs>0).mean():.4f}")
    return fills

def build_intra_fills():
    """日内腿 全时段(00-24) close口径: 对齐 _intra_tfsweep.py 几何"""
    fills = []
    for sym in SYMS:
        d1 = load(sym, "D1"); h1 = load(sym, "H1")
        t1, hh, ll, cc = h1["t"], h1["h"], h1["l"], h1["c"]
        d1t, d1h, d1l, d1c = d1["t"], d1["h"], d1["l"], d1["c"]
        for i in range(1, len(d1t) - 1):
            dts = int(d1t[i])
            if dts < T_START or d1c[i - 1] <= 0:
                continue
            pdh, pdl = float(d1h[i - 1]), float(d1l[i - 1])
            mid = (pdh + pdl) / 2.0
            i0 = int(np.searchsorted(t1, dts, side="left"))
            i1 = int(np.searchsorted(t1, dts + 86400, side="left"))
            i1 = min(i1, len(t1) - 1)
            if i1 <= i0:
                continue
            a = atr_last(hh, ll, cc, i0, i1)
            if a is None or a < 1e-6:
                continue
            risk = 0.75 * a
            # 全时段: 成交窗口 = 全天 i0..i1 (超时24根只限定退出, 不限制当日可成交)
            for side, trig in [("S", pdh * 1.002), ("B", pdl * 0.998)]:
                d = -1 if side == "S" else 1
                sl = trig - d * risk
                fk = None
                for k in range(i0, i1 + 1):
                    if (hh[k] >= trig) if d < 0 else (ll[k] <= trig):
                        fk = k; break
                if fk is None:
                    continue
                ts_fill = int(t1[fk])
                if ts_fill < T_START:
                    continue
                R = None
                for k in range(fk, min(fk + 24, i1 + 1)):
                    hit_sl = (hh[k] >= sl) if d < 0 else (ll[k] <= sl)
                    if hit_sl:
                        R = -1.0; break
                    hit_tp = (cc[k] <= mid) if d < 0 else (cc[k] >= mid)
                    if hit_tp:
                        R = abs(mid - trig) / risk; break
                if R is None:
                    kk = min(fk + 24 - 1, i1)
                    R = max(min(d * (cc[kk] - trig) / risk, abs(mid - trig) / risk), -1.0)
                R = float(R) - SLIP  # 扣P95滑点
                fills.append(dict(ts=ts_fill, sym=sym, side=1 if side == "B" else -1, R=R))
    fills.sort(key=lambda x: x["ts"])
    Rs = np.array([f["R"] for f in fills])
    print(f"[intra] fills={len(fills)} exp_R(net)={Rs.mean():+.4f} wr={(Rs>0).mean():.4f}")
    return fills

def run_equity(fills, mode, scale_fn):
    """mode: combo(双腿合并) / trend-only. 逐笔按时间序, 仓位=1%风险×scale_fn, 日熔断."""
    rows = []
    evs = []
    for f in fills:
        evs.append((f["ts"], "in"))
        if f.get("te"):
            evs.append((f["te"], "out", f["R"]))
    evs.sort(key=lambda x: x[0])
    pend = []  # 未离场趋势单 (side, trig, r0, ts_entry)
    cap_by_sym = {}   # sym -> 当日笔数
    day = None; day_start_eq = 1.0; halted = False; day_fills = 0
    eq = CAP0
    eq_at_fill = {}
    fill_ts_list, R_list = [], []
    pend_exit = {}
    # 逐笔时间序
    pending = {}  # ts -> list of (f, eq_at_fill)
    for ts, *rest in evs:
        if day is None or ts // 86400 != day:
            day = ts // 86400
            day_start_eq = eq
            halted = False
            cap_by_sym = {}
            day_fills = 0
        if halted:
            continue
        if rest and rest[0] == "in":
            f = rest[1]
            n_sym = cap_by_sym.get(f["sym"], 0)
            if f.get("te") is not None and n_sym >= CAP:
                continue  # 趋势单被日闸卡掉 (与日内单共享每品种3单闸)
            npos = len(pend)
            if npos > 0 and f.get("te") is None:
                continue  # 日内单在趋势持仓期间不开 (同日分母, 保守)
            if f.get("te") is not None:
                cap_by_sym[f["sym"]] = n_sym + 1
            s = scale_fn(len(pend))
            eqf = eq
            pend.append([f, eqf * s])
            pending.setdefault(ts, []).append(f)
        elif rest and rest[0] == "out":
            R = rest[1]
            f = next((p[0] for p in pend if p[0] is not None and abs(p[0]["ts"]) >= 0), None)
            # 找最早未结算的趋势单
            if pend:
                p, w = pend.pop(0)
                eq *= (1.0 + w * R)
                fill_ts_list.append(p["ts"]); R_list.append(R)
            d = (eq - day_start_eq) / day_start_eq
            if d <= -DAYSTOP:
                halted = True
                # 熔断: 持仓按末根close结算 (日内单 R 已含close; 趋势单保守计 -0.5R)
                for p, w in pend:
                    eq *= (1.0 + w * (-0.5 if p.get("te") is not None else p["R"]))
                pend.clear()
    eqs = np.array([CAP0] + [float(f"{eq}") for _ in [0]])
    # 重建曲线 (重算一遍保留逐笔权益)
    return eq

def run_portfolio(fills, scale_fn, tag):
    """逐笔合并回放 (单账户, 1%风险基准). 返回净值统计."""
    evs = []
    for f in fills:
        evs.append((f["ts"], f, "in"))
        if f.get("te"):
            evs.append((f["te"], None, "out", f["R"]))
    evs.sort(key=lambda x: x[0])
    pend = []
    cap_by_sym, day, day_start, halted = {}, None, 1.0, False
    eq = 1.0
    curve_ts, curve_eq = [T_START], [1.0]
    R_list, ts_list = [], []
    for item in evs:
        ts, f, typ = item[0], item[1], item[2]
        if typ == "in":
            nd = ts // 86400
            if nd != day:
                day, day_start, halted, cap_by_sym = nd, eq, False, {}
            if halted:
                continue
            if f.get("te") is not None and cap_by_sym.get(f["sym"], 0) >= CAP:
                continue
            if pend and f.get("te") is None:
                continue
            if f.get("te") is not None:
                cap_by_sym[f["sym"]] = cap_by_sym.get(f["sym"], 0) + 1
            s = scale_fn(len(pend))
            pend.append((f, s))
            eq_new = eq  # 填充时点权益 (入场不加资金)
        else:
            R = item[3]
            if not pend:
                continue
            f, s = pend.pop(0)
            eq *= (1.0 + 0.01 * s * R)
            ts_list.append(f["ts"]); R_list.append(R)
            curve_ts.append(ts); curve_eq.append(eq)
            if (eq - day_start) / day_start <= -DAYSTOP:
                halted = True
                for ff, ss in pend:
                    eq *= (1.0 + 0.01 * ss * (-0.5 if ff.get("te") is not None else ff["R"]))
                pend.clear()
                curve_ts.append(ts); curve_eq.append(eq)
                day_start = eq
    ts_arr = np.array(curve_ts); eq_arr = np.array(curve_eq)
    rets = np.diff(eq_arr) / eq_arr[:-1]
    daily_r = rets  # 笔级近似
    ann = eq_arr[-1] ** (365 * 86400 / (ts_arr[-1] - ts_arr[0])) - 1
    sharpe = (daily_r.mean() / daily_r.std()) * np.sqrt(365) if len(daily_r) > 2 and daily_r.std() > 0 else 0.0
    # 最大回撤 (峰值→谷底)
    pk = np.maximum.accumulate(eq_arr)
    mdd = float(((eq_arr - pk) / pk).min())
    out = dict(tag=tag, end_eq=round(float(eq_arr[-1]), 4), ret_pct=round((float(eq_arr[-1]) - 1) * 100, 2),
               ann_ret=round(ann * 100, 1), sharpe=round(float(sharpe), 2), mdd=round(mdd * 100, 2),
               n_fills=len(R_list), wr=round(float(np.mean(np.array(R_list) > 0)), 3) if R_list else None)
    return out

def vol_target_scale(rets_hist, target_ann_vol, n_conc):
    """等权组合波动率目标化仓位系数 (对固定1%基准的乘数). rets_hist: 12m 已发生的笔收益."""
    if len(rets_hist) < 30 or rets_hist.std() == 0:
        return 1.0
    ann_v = rets_hist.std() * np.sqrt(365)
    return float(np.clip(target_ann_v / max(ann_v, 1e-6), 0.25, 2.0))

def main():
    t0 = time.time()
    trend = build_trend_fills()
    intra = build_intra_fills()
    combo_fills = sorted(trend + intra, key=lambda x: x["ts"])
    Rs_t = np.array([f["R"] for f in trend]); Rs_i = np.array([f["R"] for f in intra])

    # ── 1) 1% 风险固定仓位: 双腿组合 vs 仅趋势腿 ──
    r_combo = run_portfolio(combo_fills, lambda n: 1.0, "combo_1pct")
    r_trend = run_portfolio(trend, lambda n: 1.0, "trend_only_1pct")
    if not Rs_t:
        print("[!] 趋势腿 fills 为空 — 跳过 Kelly/voltgt")
    # ── 2) Kelly 分数对照 (按趋势腿P0统计) ──
    if len(Rs_t) > 0:
        def kelly_scale(b, w, f_kelly):
            if b + w <= 0:
                return 0.0
            return f_kelly * w / b
        b = float(Rs_t[Rs_t > 0].mean()) if (Rs_t > 0).any() else 0.0
        w = float((Rs_t < 0).mean())
        kelly = w - w / max(2.0, b) if b > 0 else 0.0  # 盈亏比不对称, b=均盈R, w=SL概率
        k_full = max(kelly, 0.0)
        sc_25, sc_50 = 0.25 * k_full, 0.5 * k_full
        sc_25 = max(sc_25, 0.05)  # 下限防归零
    else:
        k_full, sc_25, sc_50 = 0.0, 0.0, 0.0

    def s_25(n): return sc_25
    def s_50(n): return sc_50
    r_k25 = run_portfolio(combo_fills, s_25, "kelly_25")
    r_k50 = run_portfolio(combo_fills, s_50, "kelly_50")

    # ── 3) 波动率目标化对照 (年化 20%, 基于组合12m笔收益重标定) ──
    combo_ret_series = [0.01 * f["R"] for f in combo_fills]
    vt = vol_target_scale(np.array(combo_ret_series), 0.20, 1)
    r_vt = run_portfolio(combo_fills, lambda n: vt, f"voltgt_{round(vt,2)}")

    result = {
        "family": "combo",
        "notes": "12m=全史最后12个月; 1%风险/笔固定仓位; 双腿共享每品种≤3单/日闸, 趋势单优先; 日亏10%熔断; "
                 "Kelly按趋势腿P0(b=2R,w=SL概率)公式; vol-target年化20%基于组合笔收益重标定",
        "trend_stats": {"n": len(Rs_t), "exp_R": round(float(Rs_t.mean()), 4), "wr": round(float((Rs_t > 0).mean()), 4)},
        "intra_stats": {"n": len(Rs_i), "exp_R_net": round(float(Rs_i.mean()), 4), "wr": round(float((Rs_i > 0).mean()), 4)},
        "kelly_full": round(k_full, 3), "sc_25": round(sc_25, 3), "sc_50": round(sc_50, 3), "voltgt": round(vt, 3),
        "combo_1pct": r_combo,
        "trend_only_1pct": r_trend,
        "kelly_25": r_k25,
        "kelly_50": r_k50,
        "voltgt": r_vt,
        "runtime_s": round(time.time() - t0, 1),
    }
    with open(OUT, "w", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False, indent=1)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    print(f"[done] {time.strftime('%H:%M:%S')} rt={time.time()-t0:.1f}s")

if __name__ == "__main__":
    main()
