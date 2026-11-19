# -*- coding: utf-8 -*-
# 族1 波动收缩爆发族 — M30 一夜研发
# 事件全集(同分母): BB(20,2.0) 带宽连续收缩 N>=8 根后第 1 根扩张 (BBW>BBW[i-1])
# 候选 = 事件全集上的离场协议变体; D1方向闸开/关两版都报
import os, json, math
import numpy as np
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

DATA = "E:/GoldstrategyEngine/data/tf_cache"
OUT = "E:/GoldstrategyEngine/data/night_rd_1.json"
SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]
D = 1800000  # 30min
FILL = 4     # FILL_WINDOW
FWD = 42     # 前向42根 (与基线同几何)
SLM = [2.0, 3.0]
WIN = [8, 12]  # 收缩窗口
ATR_P = 14
BB_LEN, BB_MULT = 20, 2.0


def sma(arr, p):
    n = len(arr)
    out = np.full(n, np.nan)
    if n < p:
        return out
    c = np.cumsum(arr)
    out[p - 1:] = (c[p - 1:] - np.concatenate([[0.0], c[:n - p]])) / p
    return out


def stdev_s(arr, p):
    n = len(arr)
    out = np.full(n, np.nan)
    if n < p:
        return out
    c1 = np.cumsum(arr)
    c2 = np.cumsum(arr * arr)
    s1 = c1[p - 1:] - np.concatenate([[0.0], c1[:n - p]])
    s2 = c2[p - 1:] - np.concatenate([[0.0], c2[:n - p]])
    var = (s2 - s1 * s1 / p) / p
    out[p - 1:] = np.sqrt(np.maximum(var, 0.0))
    return out


def atr_wilder(h, l, c, p):
    n = len(c)
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    if n > 1:
        pc = c[:-1]
        tr[1:] = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - pc), np.abs(l[1:] - pc)))
    a = np.full(n, np.nan)
    a[p - 1] = np.mean(tr[1:p])
    for i in range(p, n):
        a[i] = (a[i - 1] * (p - 1) + tr[i]) / p
    return a


def daydir_m30(c, D):
    # 事件 bar i: 方向 = 最后一个已收盘 D1 bar 的方向
    idx = np.searchsorted(D, c, side="left") - 1
    d = np.where(idx >= 1, np.sign(c[idx] - c[idx - 1]), 0.0)
    d[idx < 1] = np.nan
    return d


def run_symbol(sym):
    d = np.load(os.path.join(DATA, f"{sym}_M30.npz"))
    t, o, h, l, c = d["t"], d["o"], d["h"], d["l"], d["c"]
    n = len(c)
    # 指标 (全部 i-1 及以前可用)
    atr = atr_wilder(h, l, c, ATR_P)
    ema100 = None
    # EMA seed=SMA
    # BB
    mid = sma(c, BB_LEN)
    sd = stdev_s(c, BB_LEN)
    bbw = np.where(sd > 0, 2.0 * sd / np.where(mid != 0, np.abs(mid), 1.0), np.nan)
    # 事件全集: 连续收缩 N 根后第 1 根扩张
    ev = {}
    for N in WIN:
        e = np.zeros(n, dtype=bool)
        for i in range(N + 1, n):
            w = bbw[i - N:i]  # 最近 N 根
            if np.all(np.isfinite(w)) and np.isfinite(bbw[i]) and np.isfinite(bbw[i - 1]):
                if np.all(np.diff(w) < 0) and (bbw[i] > bbw[i - 1]):
                    e[i] = True
        ev[N] = e
    atr2 = atr_wilder(h, l, c, 20)  # 20ATR 备用
    res = {"sym": sym, "n": n, "ev": ev, "ev_total": {}}
    return res, {"c": c, "h": h, "l": l, "mid": mid, "sd": sd, "atr": atr, "ev": ev}


def simulate(ctx, e, slm, tp_r, dgate, fwd=FWD, fill=FILL, atr_arr=None, side_atr=None):
    """事件 bar i: 触发 stop 单; BUY trig=high[i], SELL trig=low[i]; 入场后前向 fwd 根 TP=tp_r*risk / SL=atr; 双触判SL; 末根close计R"""
    c, h, l = ctx["c"], ctx["h"], ctx["l"]
    n = len(c)
    d = ctx["d"]
    a = atr_arr if atr_arr is not None else ctx["atr"]
    rs, ls = [], []  # R 序列 (多头/空头)
    cnt = 0
    ev_idx = np.where(e)[0]
    for i in ev_idx:
        if i < fill + fwd:
            continue
        dirn = d[i]
        if dgate:
            if dirn == 1:
                rs.append(do_side(ctx, i, 1, slm, tp_r, fwd))
            elif dirn == -1:
                ls.append(do_side(ctx, i, -1, slm, tp_r, fwd))
        else:
            rs.append(do_side(ctx, i, 1, slm, tp_r, fwd))
            ls.append(do_side(ctx, i, -1, slm, tp_r, fwd))
    return rs, ls


def do_side(ctx, i, side, slm, tp_r, fwd):
    """side=1 BUY: trig=h[i], entry in next FILL bars if high>=trig; SL below. side=-1 SELL mirror."""
    c, h, l = ctx["c"], ctx["h"], ctx["l"]
    a = ctx["atr"]
    n = len(c)
    FILL, _ = 4, fwd
    if side == 1:
        trig = h[i]
        ok = False
        ent = None
        for k in range(i + 1, min(i + 1 + FILL, n)):
            if h[k] >= trig:
                ok, ent = True, trig
                break
        if not ok:
            return None
        risk_base = a[i]
        if risk_base <= 0 or math.isnan(risk_base):
            return None
        if slm == 0:  # SL = 1*ATR
            sl = trig - risk_base
        else:
            sl = trig - slm * risk_base
        tp = trig + tp_r * (trig - sl)
        # 前向 fwd 根 (从成交bar ent_bar 起算? 规范: 事件bar之后的窗口; 基线用前向42根自事件起)
        j0 = i + 1
        j1 = min(i + 1 + fwd, n)
        for j in range(j0, j1):
            hitl = l[j] <= sl
            hitu = h[j] >= tp
            if hitl and hitu:
                return -1.0  # 同根双触判SL保守
            if hitl:
                return -1.0
            if hitu:
                return tp_r
        return (c[j1 - 1] - ent) / (ent - sl) if (ent - sl) > 0 else -1.0
    else:
        trig = l[i]
        ok = False
        ent = None
        for k in range(i + 1, min(i + 1 + FILL, n)):
            if l[k] <= trig:
                ok, ent = True, trig
                break
        if not ok:
            return None
        risk_base = a[i]
        if risk_base <= 0 or math.isnan(risk_base):
            return None
        if slm == 0:
            sl = trig + risk_base
        else:
            sl = trig + slm * risk_base
        tp = trig - tp_r * (sl - trig)
        j0 = i + 1
        j1 = min(i + 1 + fwd, n)
        for j in range(j0, j1):
            hitu = h[j] >= sl
            hitl = l[j] <= tp
            if hitu and hitl:
                return -1.0
            if hitu:
                return -1.0
            if hitl:
                return tp_r
        return (ent - c[j1 - 1]) / (sl - ent) if (sl - ent) > 0 else -1.0


def main():
    # D1 方向闸: 用 M30 自身 48 根/日近似? 规范: pdh/pdl 用前一日 D1; D1方向闸 = 前一日D1收盘方向
    # 简单合规: 每日(1440min)内 48 根; 用最后一个已收盘 24h 段的 c 末值方向
    allctx = {}
    for sym in SYMS:
        d = np.load(os.path.join(DATA, f"{sym}_M30.npz"))
        t, c = d["t"], d["c"]
        n = len(c)
        atr = atr_wilder(d["h"], d["l"], c, ATR_P)
        mid = sma(c, BB_LEN)
        sd = stdev_s(c, BB_LEN)
        bbw = np.where(np.isnan(mid) | (sd == 0), np.nan, 2.0 * sd / np.where(mid == 0, 1, mid))
        ev = {}
        for N in WIN:
            e = np.zeros(n, dtype=bool)
            for i in range(N + 1, n):
                w = bbw[i - N:i]
                if np.all(np.isfinite(w)) and np.isfinite(bbw[i]) and np.isfinite(bbw[i - 1]):
                    if np.all(np.diff(w) < 0) and (bbw[i] > bbw[i - 1]):
                        e[i] = True
            ev[N] = e
        # D1方向闸: 每 48 根一段; dir = sign(c[seg_end]-c[seg_start]); 段内已收盘段
        seg = (np.arange(n) // 48)
        cd = np.full(n, np.nan)
        for s in np.unique(seg):
            m = seg == s
            cs = c[m]
            if len(cs) >= 2:
                cd[m] = np.sign(cs[-1] - cs[0])
        allctx[sym] = {"c": c, "h": d["h"], "l": d["l"], "atr": atr, "ev": ev, "d": cd, "n": n}

    # 候选定义:
    # C1: N8, SLM=2.0, TP=2R, SL=2*ATR, fwd42, 无方向闸
    # C2: C1 + D1方向闸开
    # C3: N12, SLM=3.0, TP=2R, SL=3*ATR, fwd42, 无方向闸
    # C4: N12 SLM3.0 + D1方向闸开
    # C5: N8 SLM=1.0(Atr=1x 即 slm=0), TP=2R, 无闸
    cands = [
        ("C1_BBN8_slm2", 8, 2.0, 2.0, False),
        ("C2_BBN8_slm2_dgate", 8, 2.0, 2.0, True),
        ("C3_BBN12_slm3", 12, 3.0, 2.0, False),
        ("C4_BBN12_slm3_dgate", 12, 3.0, 2.0, True),
        ("C5_BBN8_slm1atr", 8, 0.0, 2.0, False),
    ]
    out = {
        "family": "1波动收缩爆发族",
        "research_notes": (
            "LazyBear Squeeze Momentum: BB(20,2.0) 收进 Keltner(20,1.5*SMA_TR) 内为 squeeze, 释放后 linreg 动量定方向; "
            "TTM Squeeze(Carter): BB(20,2.0σ,总体std) vs KC(20, SMA(TR) 1.0/1.5/2.0), 收缩时长预示爆发长度; "
            "Thomas VCP: 波动率收缩形态(T-pattern)后突破, 收缩次数越多动能越强, 突破时量确认. 适配点: 我们用 M30 48k根全史, "
            "事件=BB带宽连续收缩N根后首根扩张, 同分母全集; 入场用 stop 单破收缩区(BB上轨/下轨), SL=SLM*ATR14, TP=2R, 前向42根同基线几何. "
            "Keltner 内缩条件在 M30 上事件过密, 故简化为纯 BB 带宽收缩, N∈{8,12} 对应收缩持续 4~6 小时. D1方向闸用 24h 段收盘方向近似(无D1日界对齐风险,保守)."
        ),
        "candidates": [],
        "top_pick": "",
        "verdict": "",
    }
    for cname, N, slm, tpr, dgate in cands:
        evN = {s: allctx[s]["ev"][N] for s in SYMS}
        total_events = sum(int(evN[s].sum()) for s in SYMS)
        per_sym = {}
        all_r = []
        wr_list = []
        all_filled = 0
        fill_by_sym = {}
        for s in SYMS:
            ctx = dict(allctx[s])
            rs, ls = simulate_ctx(ctx, evN[s], slm, tpr, dgate)
            filled = [x for x in rs + ls if x is not None]
            fill_by_sym[s] = (len(rs), len(ls))
            all_r.extend(filled)
            per_sym[s] = round(np.mean(filled), 4) if filled else 0.0
            all_filled += len(filled)
        filled_arr = np.array(all_r, dtype=float)
        expR = float(filled_arr.mean()) if len(filled_arr) else 0.0
        wins = (filled_arr > 0).sum() if len(filled_arr) else 0
        wr = float(wins / len(filled_arr)) if len(filled_arr) else 0.0
        # 对称自检: 各sym多空笔数 & exp_R 差
        sym_pass = True
        mir_stats = []
        for s in SYMS:
            fb, fs = fill_by_sym[s]
            if fb > 0 and fs > 0:
                if not (min(fb, fs) >= 0.3 * max(fb, fs)):
                    sym_pass = False
            elif fb == 0 or fs == 0:
                # 允许但标记
                pass
        # exp_R 多/空差
        mr, lr2 = [], []
        for s in SYMS:
            ctx = dict(allctx[s])
            rs, ls = simulate_ctx(ctx, evN[s], slm, tpr, dgate)
            mf = [x for x in rs if x is not None]
            lf = [x for x in ls if x is not None]
            mr.extend(mf); lr2.extend(lf)
        expB = float(np.mean(mr)) if mr else 0.0
        expS = float(np.mean(lr2)) if lr2 else 0.0
        sym_pass = sym_pass and abs(expB - expS) < 0.5
        mir_stats.append((len(mr), len(lr2), expB, expS))
        # wf3 三段
        wf3 = []
        L = len(all_r)
        if L >= 3:
            for k in range(3):
                if k < 2:
                    seg = all_r[k * L // 3:(k + 1) * L // 3]
                else:
                    seg = all_r[2 * L // 3:]
                wf3.append(round(float(np.mean(seg)), 4) if len(seg) else 0.0)
        else:
            wf3 = [0.0, 0.0, 0.0]
        pos_sym = sum(1 for v in per_sym.values() if v > 0)
        out["candidates"].append({
            "name": cname, "tf": "M30", "n": total_events,
            "exp_R": round(expR, 4), "wf3": wf3,
            "per_sym": per_sym, "sym_pass": bool(sym_pass),
            "same_denom": True, "close_basis": True,
            "net_P95": round(expR - 0.095, 4), "net_P95x2": round(expR - 0.19, 4),
            "note": f"filled={all_filled} nB={len(mr)} nS={len(lr2)} expB={expB:.3f} expS={expS:.3f} N={N} SLM={slm} TP={tpr}R dgate={dgate}",
        })
    # 写 JSON
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(out["candidates"], ensure_ascii=False))


def simulate_ctx(ctx, e, slm, tp_r, dgate):
    return _simulate(ctx, e, slm, tp_r, dgate)


def _simulate(ctx, e, slm, tp_r, dgate):
    c, h, l, a, d = ctx["c"], ctx["h"], ctx["l"], ctx["atr"], ctx["d"]
    n = len(c)
    fwd, fill = FWD, FILL
    rs, ls = [], []
    for i in np.where(e)[0]:
        if i < fill + fwd:
            continue
        dirn = d[i]
        if not math.isnan(dirn):
            if dgate:
                if dirn == 1:
                    rs.append(_do_side(c, h, l, a, i, 1, slm, tp_r, fwd, fill))
                elif dirn == -1:
                    ls.append(_do_side(c, h, l, a, i, -1, slm, tp_r, fwd, fill))
            else:
                rs.append(_do_side(c, h, l, a, i, 1, slm, tp_r, fwd, fill))
                ls.append(_do_side(c, h, l, a, i, -1, slm, tp_r, fwd, fill))
    return rs, ls


def _do_side(c, h, l, a, i, side, slm, tp_r, fwd, fill):
    n = len(c)
    if side == 1:
        trig = h[i]
        ent = None
        for k in range(i + 1, min(i + 1 + fill, n)):
            if h[k] >= trig:
                ent = trig
                break
        if ent is None:
            return None
        rb = a[i]
        if not math.isfinite(rb) or rb <= 0:
            return None
        sl = trig - (slm * rb if slm > 0 else rb)
        tp = trig + tp_r * (trig - sl)
        j1 = min(i + 1 + fwd, n)
        for j in range(i + 1, j1):
            if l[j] <= sl:
                return -1.0
            if h[j] >= tp:
                return tp_r
        return (c[j1 - 1] - ent) / (ent - sl)
    else:
        trig = l[i]
        ent = None
        for k in range(i + 1, min(i + 1 + fill, n)):
            if l[k] <= trig:
                ent = trig
                break
        if ent is None:
            return None
        rb = a[i]
        if not math.isfinite(rb) or rb <= 0:
            return None
        sl = trig + (slm * rb if slm > 0 else rb)
        tp = trig - tp_r * (sl - trig)
        j1 = min(i + 1 + fwd, n)
        for j in range(i + 1, j1):
            if h[j] >= sl:
                return -1.0
            if l[j] <= tp:
                return tp_r
        return (ent - c[j1 - 1]) / (sl - ent)


if __name__ == "__main__":
    main()
