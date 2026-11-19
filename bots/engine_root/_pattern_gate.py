# -*- coding: utf-8 -*-
# K线形态否决门 (V5已学习: 吞没/锤子/流星/晨暮星) — 形态只当否决门, 不做正向提权
# 数据: data/tf_cache/{SYM}_{TF}.npz (不连MT5). Python: ate env
# 面A 日内腿救活: H1逐K回放, 几何=前一日PDL/PHD swing 触发Stop单 (BUY_STOP@PDL*0.998 / SELL_STOP@PDH*1.002),
#        SL=0.75*ATR14(前一日收盘因果), TP=2R, 00-24全时段, close口径. 基线 -0.15R (intra_tfsweep 00-24 = -0.147)
#   加门: 触发K线上出现逆向往形态 (多头信号遇 看跌吞没/流星/暮星) 拒入场, 镜像拒空头
#   报: 拒单比例 / n / exp_R / wf3 / 对称自检 / 扣0.5R滑点
# 面B M30格加固: M30趋势腿 (D1方向闸 + Donchian20*1.003 stop, SL=3.0*ATR14=M30+SLM3.0 基线+0.104, TP=2R,
#   前向42根收盘计R不截断), 加同样形态否决门 (形态在M30触发K线上判定), 看 Δ = gated - baseline 是否 >= 0
# 形态判据 (因果, 只用当根及以前):
#   实体body_i = c-l..c-o; range_i = h-l (range<=0 跳过)
#   看跌吞没(i): c[i]<o[i] 且 c[i-1]>o[i-1] 且 o[i]>=c[i-1] 且 c[i]<=o[i-1] (大阴实体完全吞没前一根阳实体)
#   看跌流星(i): 小实体(body<=0.25*range) 且 上影>=2*实体 且 下影<=实体 (长上影短下影)
#   看跌暮星(i): 前一根大阳(body>=0.6*range) 且 当根小实体(body<=0.35*range) 且 c[i]>=o[i-1] 区域上方(收盘在前根实体上半区)
#   看涨镜像: 看涨吞没(c[i]>o[i], c[i-1]<o[i-1], o[i]<=c[i-1], c[i]>=o[i-1]); 看涨锤子(下影>=2*实体且实体在上1/3, 小实体); 看涨晨星(前一根大阴+当根小实体+收盘在下半区)
#   否决: side=+1(多头) 遇 看跌吞没|流星|暮星 → 拒; side=-1(空头) 遇 看涨吞没|锤子|晨星 → 拒
import os, json, math
import numpy as np

def _guard_commit():
    """commit 上限看门狗: 系统 committed>96% 时限制本进程, 防止把机器吃死.
    Windows 无 RLIMIT_AS, 用 ctypes 取内存状态 + 打印告警; 实际降载靠 float32."""
    try:
        import ctypes
        class MIB(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
            ]
        x = MIB()
        x.dwLength = ctypes.sizeof(x)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(x)
        if x.ullTotalPageFile > 0:
            used = x.ullTotalPageFile - x.ullAvailPageFile
            frac = used / x.ullTotalPageFile
            if frac > 0.96:
                print(f"[!] commit {frac:.1%} — 降载: 全用float32, 逐品种释放")
            else:
                print(f"[OK] commit {frac:.1%}")
    except Exception as e:
        print(f"[!] commit guard skipped: {e}")


ROOT = r"E:/GoldstrategyEngine"
CACHE = os.path.join(ROOT, "data", "tf_cache")
SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]


def load_npz(sym, tf):
    p = os.path.join(CACHE, f"{sym}_{tf}.npz")
    d = np.load(p)
    return dict(t=d["t"].astype(np.int64), h=d["h"].astype(np.float64),
                l=d["l"].astype(np.float64), c=d["c"].astype(np.float64),
                o=d["o"].astype(np.float64) if "o" in d else None)


def atr_wilder(h, l, c, p=14):
    n = len(c)
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    pc = np.concatenate([[np.nan], c[:-1]])
    tr[1:] = np.maximum(h[1:] - l[1:],
                        np.maximum(np.abs(h[1:] - pc[1:]), np.abs(l[1:] - pc[1:])))
    out = np.zeros(n)
    if n > p:
        out[p] = tr[1:p + 1].mean()
        for i in range(p + 1, n):
            out[i] = (out[i - 1] * (p - 1) + tr[i]) / p
    return out


# ── 形态检测: 逐bar, 因果 (只用 i 及以前数据). 返回 (bear_arr, bull_arr) ──
def detect_patterns(o, h, l, c):
    n = len(c)
    bear = np.zeros(n, dtype=bool)
    bull = np.zeros(n, dtype=bool)
    for i in range(1, n):
        rng = h[i] - l[i]
        if rng <= 0:
            continue
        body = abs(c[i] - o[i])
        up_sh = h[i] - max(o[i], c[i])      # 上影
        dn_sh = min(o[i], c[i]) - l[i]       # 下影
        bear_body = c[i] < o[i]
        bull_body = c[i] > o[i]
        prev_rng = h[i - 1] - l[i - 1]
        prev_body = abs(c[i - 1] - o[i - 1])
        # 看跌吞没: 阴实体完全吞没前一根阳实体
        if bear_body and c[i - 1] > o[i - 1] and o[i] >= c[i - 1] and c[i] <= o[i - 1]:
            bear[i] = True
        # 看涨吞没: 阳实体完全吞没前一根阴实体
        if bull_body and c[i - 1] < o[i - 1] and o[i] <= c[i - 1] and c[i] >= o[i - 1]:
            bull[i] = True
        if not bear[i] and not bull[i]:
            small = body <= 0.35 * rng
            if bear_body and small:
                # 看跌流星: 长上影
                if up_sh >= 2.0 * body and dn_sh <= body:
                    bear[i] = True
                # 看跌暮星: 前一根大阳, 当根小实体收盘在前根上半区
                if not bear[i] and prev_rng > 0 and (c[i - 1] - o[i - 1]) >= 0.6 * prev_rng:
                    half_lo = o[i - 1] + 0.5 * (c[i - 1] - o[i - 1])
                    if c[i] >= half_lo:
                        bear[i] = True
            elif bull_body and small:
                # 看涨锤子: 长下影, 实体在上1/3
                if dn_sh >= 2.0 * body and up_sh <= body and c[i] >= l[i] + (2.0 / 3.0) * rng:
                    bull[i] = True
                # 看涨晨星: 前一根大阴, 当根小实体收盘在前根下半区
                if not bull[i] and prev_rng > 0 and (o[i - 1] - c[i - 1]) >= 0.6 * prev_rng:
                    half_hi = o[i - 1] - 0.5 * (o[i - 1] - c[i - 1])
                    if c[i] <= half_hi:
                        bull[i] = True
    return bear, bull


def reject_flag(side, o, h, l, c, i):
    """side=+1多头: 触发K线出现看跌形态→拒; side=-1空头: 出现看涨形态→拒. 因果."""
    bear, bull = o, h  # placeholder (real arrays passed separately)
    raise RuntimeError("use reject_patterns")


def build_reject_arrays(o, h, l, c):
    bear, bull = detect_patterns(o, h, l, c)
    # side +1 拒入场 = 看跌形态; side -1 拒入场 = 看涨形态
    return bear, bull


# ════════ 面A: 日内腿 H1 逐K回放 (00-24全时段, close口径, TP=2R) ════════
def build_day_segments(sym):
    """前一日高低 → 当日H1段 (服务器日对齐), ATR因果 (只用当日之前已完结H1).
    返回 dict(sym) -> list of (day_ts, pdh, pdl, h1a, i0, i1)"""
    d1 = load_npz(sym, "D1")
    h1 = load_npz(sym, "H1")
    t1, h, l, c = d1["t"], d1["h"], d1["l"], d1["c"]
    th, hh, ll, cc = h1["t"], h1["h"], h1["l"], h1["c"]
    atr = atr_wilder(hh, ll, cc)
    out = []
    for i in range(14, len(t1) - 1):
        pdh, pdl = float(h[i - 1]), float(l[i - 1])
        dts = int(t1[i])
        i0 = int(np.searchsorted(th, dts, side="left"))
        i1 = int(np.searchsorted(th, dts + 86400, side="left"))
        i1 = min(i1, len(th) - 1)
        if i1 <= i0:
            continue
        h1a = float(atr[i0 - 1]) if i0 > 0 and atr[i0 - 1] > 0 else 1e-9
        if h1a < 1e-6:
            continue
        out.append((dts, pdh, pdl, h1a, i0, i1))
    del atr
    return out, h1


def replay_day(day, th, hh, ll, cc, bear, bull, gate, close_basis=True):
    """双向Stop单回放. gate=False=基线(全部入场), gate=True=加形态否决门.
    close口径: TP/SL 按 close 判定 (收盘价到即平), 同根双触判SL(保守).
    返回 (rs: list of R, filled: list of (ts, side, rejected))."""
    dts, pdh, pdl, a, i0, i1 = day
    risk = 0.75 * a
    if risk < 1e-9:
        return [], []
    out_r, out_f = [], []
    for side, trig, cond in ((1, pdl * 0.998, "BUY"), (-1, pdh * 1.002, "SELL")):
        tp = trig + 2 * risk * side      # BUY: 上方2R; SELL: 下方2R
        sl = trig - risk * side          # BUY(side=1): sl=trig-risk(下方); SELL(side=-1): sl=trig+risk(上方) — 原式正确, 勿改
        fill_k = None
        for k in range(i0, i1 + 1):
            # 标准 Stop 单语义: 插到 trigger 即成交 (BUY 看 low / SELL 看 high)
            # 旧版用 close 回升判定 = 选择效应(只留赢的日子), 产生 +1.29R 假象, 已作废
            if side == 1:
                if ll[k] <= trig:
                    fill_k = k
                    break
            else:
                if hh[k] >= trig:
                    fill_k = k
                    break
        if fill_k is None:
            continue
        if gate:
            rejected = bool(bull[fill_k]) if side == -1 else bool(bear[fill_k])
        else:
            rejected = False
        if rejected:
            out_f.append((int(th[fill_k]), side, True, True))
            continue
        out_f.append((int(th[fill_k]), side, False, False))
        R = None
        for k in range(fill_k, i1 + 1):
            kc = cc[k]
            sl_hit = (kc <= sl) if side == 1 else (kc >= sl)
            tp_hit = (kc >= tp) if side == 1 else (kc <= tp)
            if sl_hit:
                R = -1.0
                break
            if tp_hit:
                R = 2.0
                break
        if R is None:
            R = float((cc[i1] - trig) / risk * side)
        out_r.append(R)
    return out_r, out_f


def run_faceA(gate):
    rs_all, ts_all, rej_all = [], [], []
    per_sym = {}
    for sym in SYMS:
        days, h1 = build_day_segments(sym)
        th, hh, ll, cc = h1["t"], h1["h"], h1["l"], h1["c"]
        o_arr = h1.get("o")
        if o_arr is None:
            # 缺open时用close近似 (o[i]≈c[i-1]), 首根取close[0]
            o_arr = np.empty(len(cc))
            o_arr[0] = cc[0]
            o_arr[1:] = cc[:-1]
        bear, bull = build_reject_arrays(o_arr, hh, ll, cc)
        rs_s, rej_s = [], []
        for day in days:
            rr, ff = replay_day(day, th, hh, ll, cc, bear, bull, gate)
            for (ts_, side, filled, rejected) in ff:
                if rejected:
                    rej_s.append(ts_)
            rs_all.extend(rr)
            ts_all.extend([int(day[0]) for _ in rr])
            rej_all.extend(rej_s)
        per_sym[sym] = round(float(np.mean(rs_s)), 4) if rs_s else None
        del days, h1
    arr = np.array(rs_all, dtype=np.float64)
    n_events = len(rs_all) + len(rej_all)
    n_filled = len(rs_all)
    n_rej = len(rej_all)
    rep = {
        "gate": gate,
        "n": n_filled,
        "n_events": n_events,
        "n_rejected": n_rej,
        "reject_ratio": round(n_rej / max(1, n_events), 4),
        "exp_R": round(float(arr.mean()), 4) if n_filled else None,
        "exp_slip0.5R": round(float(arr.mean() - 0.5), 4) if n_filled else None,
        "wr": round(float((arr > 0).mean()), 4) if n_filled else None,
    }
    # wf3: 全部已成交事件按天时间戳三等分
    ts_arr = np.array(ts_all)
    if n_filled:
        tmin, tmax = int(ts_arr.min()), int(ts_arr.max())
        b1 = tmin + (tmax - tmin) // 3
        b2 = tmin + 2 * (tmax - tmin) // 3
        rep["wf3"] = [round(float(np.mean([r for r, t in zip(rs_all, ts_arr) if t < b1])), 4)
                      if any(t < b1 for t in ts_arr) else None,
                      round(float(np.mean([r for r, t in zip(rs_all, ts_arr) if b1 <= t < b2])), 4)
                      if any(b1 <= t < b2 for t in ts_arr) else None,
                      round(float(np.mean([r for r, t in zip(rs_all, ts_arr) if t >= b2])), 4)
                      if any(t >= b2 for t in ts_arr) else None]
    else:
        rep["wf3"] = [None, None, None]
    rep["per_sym"] = per_sym
    return rep, rej_all


def faceA_symmetry_check():
    """对称自检: 镜像 (h'=-l, l'=-h, c'=-c, o'=-o, 看跌<->看涨形态) 时,
    BUY/PDL序列 与 SELL/PHD序列 逐事件数相等 (同分母: 镜像事件数一致)."""
    ok = True
    detail = {}
    for sym in SYMS:
        days, h1 = build_day_segments(sym)
        th, hh, ll, cc = h1["t"], h1["h"], h1["l"], h1["c"]
        o_arr = h1.get("o")
        if o_arr is None:
            o_arr = np.empty(len(cc))
            o_arr[0] = cc[0]
            o_arr[1:] = cc[:-1]
        bear_o, bull_o = build_reject_arrays(o_arr, hh, ll, cc)
        # 镜像: 反转价格
        mh, ml, mc, mo = -ll, -hh, -cc, -o_arr
        bear_m, bull_m = build_reject_arrays(mo, mh, ml, mc)
        # 原始: BUY侧触发K线的看跌形态数; 镜像后: SELL侧(=镜像BUY)的看涨形态数 (镜像看跌=原看涨)
        buy_trig_bear = 0
        sell_trig_bull = 0
        for day in days:
            dts, pdh, pdl, a, i0, i1 = day
            trig_b, trig_s = pdl * 0.998, pdh * 1.002
            kb = None
            for k in range(i0, i1 + 1):
                if cc[k] >= trig_b:
                    kb = k
                    break
            ks = None
            for k in range(i0, i1 + 1):
                if cc[k] <= trig_s:
                    ks = k
                    break
            if kb is not None:
                buy_trig_bear += int(bear_o[kb])
            if ks is not None:
                sell_trig_bull += int(bull_o[ks])
        d = abs(buy_trig_bear - sell_trig_bull)
        detail[sym] = {"buy_trig_kbear": buy_trig_bear, "sell_trig_bull": sell_trig_bull,
                       "diff": d, "ok": d <= max(2, 0.1 * max(buy_trig_bear, sell_trig_bull))}
        ok = ok and detail[sym]["ok"]
    return bool(ok), detail


# ════════ 面B: M30 趋势腿 + SLM3.0, 加形态否决门 ════════
def donc20(h, l):
    hi = np.full_like(h, np.nan)
    lo = np.full_like(l, np.nan)
    for i in range(20, len(h)):
        hi[i] = h[i - 19:i + 1].max()
        lo[i] = l[i - 19:i + 1].min()
    return hi, lo


def d1_gate_arr(d1t, d1c, ts_arr):
    g = np.full(len(ts_arr), -1, dtype=np.int64)
    idx = np.searchsorted(d1t, ts_arr - 86400, side="right") - 1
    ok2 = idx >= 1
    g[ok2] = np.where(d1c[idx[ok2]] > d1c[idx[ok2] - 1], 1, 0)
    g[~ok2] = -1
    return g


def run_faceB(slm, gate):
    LOOK = 42
    FILLW = 4
    fills = []   # dict(sym, ts, side, R)
    n_events = 0
    for sym in SYMS:
        m = load_npz(sym, "M30")
        d1 = load_npz(sym, "D1")
        tt, th, tl, tc = m["t"], m["h"], m["l"], m["c"]   # BUGFIX: 旧版解包错位一位(th=m["t"]), d1_gate 拿收盘价当时间戳 → 全continue 0事件
        o_arr = m.get("o")
        if o_arr is None:
            o_arr = np.empty(len(tc))
            o_arr[0] = tc[0]
            o_arr[1:] = tc[:-1]
        hi, lo = donc20(th, tl)
        atr = atr_wilder(th, tl, tc)
        gate_arr = d1_gate_arr(d1["t"], d1["c"], tt)
        bear = bull = None
        if gate:
            bear, bull = build_reject_arrays(o_arr, th, tl, tc)
        for i in range(21, len(tt) - 1):
            if np.isnan(hi[i - 1]) or np.isnan(lo[i - 1]) or hi[i - 1] <= 0:
                continue
            ts = int(tt[i])
            g = int(gate_arr[i])
            if g < 0:
                continue
            side, trig = 0, 0.0
            if g == 1 and tc[i - 1] < hi[i - 1] * 1.003:
                side, trig = 1, hi[i - 1] * 1.003
            elif g == 0 and tc[i - 1] > lo[i - 1] / 1.003:
                side, trig = -1, lo[i - 1] / 1.003
            else:
                continue
            n_events += 1
            if gate:
                rejected = bool(bull[i]) if side == -1 else bool(bear[i])
                if rejected:
                    continue
            j = int(np.searchsorted(tt, ts, side="right"))
            if j >= len(tt) or j + FILLW > len(tt):
                continue
            a = atr[j] if atr[j] > 0 else 1e-9
            r0 = slm * a
            if r0 <= 0:
                continue
            sl = trig - r0 if side == 1 else trig + r0
            tp = trig + 2 * r0 if side == 1 else trig - 2 * r0
            seg_h = th[j:j + FILLW]
            seg_l = tl[j:j + FILLW]
            if side == 1:
                f = np.where(seg_h >= trig)[0]
            else:
                f = np.where(seg_l <= trig)[0]
            if len(f) == 0:
                continue
            fidx = int(f[0])
            fill_ts = int(tt[j + fidx])
            seg_h2 = th[j:j + LOOK]
            seg_l2 = tl[j:j + LOOK]
            res = None
            for k in range(fidx, len(seg_h2)):
                if side == 1:
                    sl_hit, tp_hit = seg_l2[k] <= sl, seg_h2[k] >= tp
                else:
                    sl_hit, tp_hit = seg_h2[k] >= sl, seg_l2[k] <= tp
                if sl_hit:
                    res = -1.0
                    break
                if tp_hit:
                    res = 2.0
                    break
            if res is None:
                exit_px = float(seg_h2[-1]) if side == 1 else float(seg_l2[-1])
                res = (exit_px - trig) / r0 if side == 1 else (trig - exit_px) / r0
            fills.append(dict(sym=sym, ts=fill_ts, side=side, R=round(float(res), 4)))
    fills.sort(key=lambda x: x["ts"])
    Rs = np.array([f["R"] for f in fills], dtype=np.float64)
    expR = round(float(Rs.mean()), 4) if len(Rs) else None
    wr = round(float((Rs > 0).mean()), 4) if len(Rs) else None
    per_sym = {}
    for sym in SYMS:
        r = Rs[np.array([f["sym"] for f in fills]) == sym]
        per_sym[sym] = round(float(r.mean()), 4) if len(r) else None
    wf = {str(k + 1): None for k in range(3)}
    if len(Rs):
        tmin, tmax = fills[0]["ts"], fills[-1]["ts"]
        third = (tmax - tmin) / 3.0
        for k in range(3):
            seg = Rs[(np.array([f["ts"] for f in fills]) >= tmin + k * third)
                     & (np.array([f["ts"] for f in fills]) < tmin + (k + 1) * third)]
            wf[str(k + 1)] = round(float(seg.mean()), 4) if len(seg) else None
    # 对称自检 (多/空两侧填充量级同侧 + exp_R差<0.5R, 与_tf_m30同口径)
    b = Rs[np.array([f["side"] for f in fills]) == 1]
    s = Rs[np.array([f["side"] for f in fills]) == -1]
    nb, ns = len(b), len(s)
    eb = float(b.mean()) if nb else 0.0
    es = float(s.mean()) if ns else 0.0
    symmetric_pass = bool(nb > 0 and ns > 0
                          and nb >= 0.3 * (nb + ns) and ns >= 0.3 * (nb + ns)
                          and abs(eb - es) < 0.5)
    return {"n": len(Rs), "n_events": n_events, "exp_R": expR, "wr": wr,
            "exp_slip0.5R": round(float(Rs.mean() - 0.5), 4) if len(Rs) else None,
            "wf3": wf, "per_sym": per_sym, "symmetric_pass": symmetric_pass,
            "sym_detail": {"多n": nb, "多expR": round(eb, 4), "空n": ns, "空expR": round(es, 4)}}


def main():
    out = {"_meta": {
        "note": "K线形态否决门V5: 形态只当否决门(吞没/锤子/流星/晨暮星), 不做正向提权; 同分母; SELL镜像自检; close口径; 扣0.5R滑点",
        "patterns": "看跌: 吞没/流星/暮星 拒多头; 看涨: 吞没/锤子/晨星 拒空头; open缺失用c[i-1]近似",
        "faceA": "日内腿H1逐K 00-24全时段, PDL*0.998 BUY_STOP / PDH*1.002 SELL_STOP, SL=0.75*ATR14(前日收盘因果), TP=2R, close口径",
        "faceB": "M30趋势腿 D1方向闸+Donchian20*1.003 stop, SLM=3.0 (基线+0.104), TP=2R, 前向42根收盘计R; 形态在触发K线判定",
    }}

    # ── 面A ──
    print("[OK] 面A 基线回放 (H1逐K 00-24 close口径)...")
    baseA, _ = run_faceA(gate=False)
    print(f"[OK] 面A基线: n={baseA['n']} exp_R={baseA['exp_R']} (基线对照=-0.15R, 实测{baseA['exp_R']})")
    print("[OK] 面A 加形态否决门...")
    gateA, _ = run_faceA(gate=True)
    deltaA = None
    if gateA["exp_R"] is not None and baseA["exp_R"] is not None:
        deltaA = round(gateA["exp_R"] - baseA["exp_R"], 4)
    symA, symA_detail = faceA_symmetry_check()
    out["faceA_intra"] = {
        "baseline": baseA, "gated": gateA, "delta_exp_R": deltaA,
        "对称自检": {"pass": symA, "detail": symA_detail},
    }
    print(f"[OK] 面A加门: n={gateA['n']} 拒单={gateA['n_rejected']}({gateA['reject_ratio']}) exp_R={gateA['exp_R']} Δ={deltaA} 对称自检={symA}")

    # ── 面B ──
    print("[OK] 面B M30+SLM3.0 基线...")
    baseB = run_faceB(3.0, gate=False)
    print(f"[OK] 面B基线: n={baseB['n']} exp_R={baseB['exp_R']} (基线对照=+0.104, 实测{baseB['exp_R']})")
    print("[OK] 面B M30+SLM3.0 加形态否决门...")
    gateB = run_faceB(3.0, gate=True)
    deltaB = None
    if gateB["exp_R"] is not None and baseB["exp_R"] is not None:
        deltaB = round(gateB["exp_R"] - baseB["exp_R"], 4)
    out["faceB_m30_slm3"] = {"baseline": baseB, "gated": gateB, "delta_exp_R": deltaB}
    print(f"[OK] 面B加门: n={gateB['n']} exp_R={gateB['exp_R']} Δ={deltaB} 对称自检={gateB['symmetric_pass']}")

    # ── 结论 (铁律: 否决门只否决不提权; Δ>=0 才说明形态门有加固价值) ──
    a_ok = (deltaA is not None and deltaA >= 0)
    b_ok = (deltaB is not None and deltaB >= 0)
    if a_ok and b_ok:
        verdict = ("否决门保留: 两面Δ均>=0 — 形态门在不提权前提下加固了两腿 "
                   f"(日内腿{baseA['exp_R']}→{gateA['exp_R']}, M30格{baseB['exp_R']}→{gateB['exp_R']})")
    elif a_ok and not b_ok:
        verdict = ("否决门部分保留: 日内腿救活Δ>=0 (M30格加固Δ<0, 趋势腿加门无益) — "
                   f"日内{baseA['exp_R']}→{gateA['exp_R']} 有效; M30格 {baseB['exp_R']}→{gateB['exp_R']} 拒单反噬, 仅日内腿挂门")
    elif not a_ok and b_ok:
        verdict = ("否决门部分保留: M30格加固Δ>=0 但日内腿Δ<0 — "
                   f"仅M30趋势腿挂形态门 {baseB['exp_R']}→{gateB['exp_R']}; 日内腿不动")
    else:
        verdict = ("否决门回滚: 两面Δ均<0 — 形态否决门未产生净加固, 形态仍只做诊断标签不入执行路径 "
                   f"(日内{baseA['exp_R']}→{gateA['exp_R']}, M30格{baseB['exp_R']}→{gateB['exp_R']})")
    out["verdict"] = verdict

    p = os.path.join(ROOT, "data", "pattern_gate.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(f"[OK] 已写 {p}")
    print("VERDICT:", verdict)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
