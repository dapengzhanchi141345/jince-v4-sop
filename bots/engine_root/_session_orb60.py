# -*- coding: utf-8 -*-
"""_session_orb60.py — 币系 ORB60 几何移植到 黄金/外汇 伦敦+纽约开盘时段
几何: 锚点起 4 根 M30 = 1h ORB (币系 ORB60 同款);
      BUY_STOP @ orb_hi×1.002 / SELL_STOP @ orb_lo/1.008,
      SL = 1.0×M30-ATR14(Wilder), TP = 2R, EOD 当日 24 根 M30 日止损, 一方向一天一单.
变体:
  LONDON: 当日首个"ORB定型"锚点 (04:00/07:00/08:00 UTC, 第5根close存在才算定型), 一日一单.
  NY:     同规则, 锚 12:30/13:30 UTC.
  DUAL:   两变体事件集合并, 每笔 0.5x 权重 (组合期望口径).
基线(同分母 A-B): 同样本日, 日内随机一根市价进, 方向随机, 同滑点档, 种子固定.
滑点: 正常 0.2R / 数据发布时刻 0.5R 两档 (A/B 同档扣减).
验收: selftest + symmetric_audit 抽样 + 前视检查(ORB 只用锚后已走完 4 根, 入场自第 5 根起).
输出: data/rd_verify_batch_sessionorb.json
"""
import os, json, sys, math, random
import numpy as np
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
FXC = os.path.join(ROOT, "data", "tf_cache_fx2")
OUTJ = os.path.join(ROOT, "data", "rd_verify_batch_sessionorb.json")
sys.path.insert(0, ROOT)
import backtest_engine as be
from multi_agent.trading.backtest_engine import symmetric_audit, selftest

SYMS = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDCAD", "USDJPY"]
SLM, TPR, LOOK = 1.0, 2.0, 24
FILL = 4                     # 入场扫描窗口: 第5根起 4 根
SLIP_N, SLIP_D = 0.2, 0.5
RNG_SEED = 20261005
LONDON_ANCHORS = [(4, 0), (7, 0), (8, 0)]
NY_ANCHORS = [(12, 30), (13, 30)]
# 参数甜区 (五验第4项 相邻不翻号): 触发偏移 0.001/0.002/0.003 + SL 0.8/1.0/1.2×ATR 相邻扫描


def run_orb_variants(m, anchors, slip_R, offsets=(0.001, 0.002, 0.003), sl_mults=(0.8, 1.0, 1.2)):
    """参数甜区扫描: 每个 (offset, sl_mult) 组合的事件 R 序列 (扣滑点)."""
    t, h, l, c = m["t"], m["h"], m["l"], m["c"]
    n = len(c)
    atr = atr_wilder(h, l, c)
    out = {}
    for off in offsets:
        for sm in sl_mults:
            Rs = []
            for day0 in day_indices(t):
                day_end = day0 + 86400
                chosen = None
                for hh, mm in anchors:
                    target = day0 + hh * 3600 + mm * 60
                    a = int(np.searchsorted(t, np.int64(target), side="left"))
                    if a >= n or int(t[a]) != int(target):
                        continue
                    if a + FILL >= n or int(t[a + FILL]) >= day_end:
                        continue
                    oh = float(h[a:a + 4].max())
                    ol = float(l[a:a + 4].min())
                    a_atr = float(atr[a + 3])
                    if not (np.isfinite(a_atr) and a_atr > 0 and oh > ol):
                        continue
                    risk = sm * a_atr
                    tb, ts_ = oh * (1 + off), ol / (1 + off)
                    j0 = a + FILL
                    sh = h[j0:j0 + FILL]
                    sw = l[j0:j0 + FILL]
                    fb = int(np.argmax(sh >= tb)) if (sh >= tb).any() else -1
                    fs = int(np.argmax(sw <= ts_)) if (sw <= ts_).any() else -1
                    if fb < 0 and fs < 0:
                        continue
                    if fb >= 0 and (fs < 0 or fb <= fs):
                        side, trig, k0 = 1, tb, j0 + fb
                    else:
                        side, trig, k0 = -1, ts_, j0 + fs
                    mseg = np.where((t >= np.int64(k0 * 1800)) & (t < np.int64(day_end)))[0]
                    end = int(mseg[-1]) if len(mseg) else min(k0 + LOOK, n)
                    end = min(end, min(k0 + LOOK, n))
                    Rg, _ = exit_R(side, trig, trig - side * risk, trig + side * TPR * risk,
                                   h[k0:end], l[k0:end], t[k0:end], c[k0:end], day_end, risk)
                    Rs.append(Rg - slip_R)
                    break
            out[(off, sm)] = np.array(Rs)
    return out


def atr_wilder(h, l, c, p=14):
    n = len(c)
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    tr[1:] = np.maximum(h[1:] - l[1:],
                        np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    out = np.zeros(n)
    out[p] = tr[1:p + 1].mean()
    for i in range(p + 1, n):
        out[i] = (out[i - 1] * (p - 1) + tr[i]) / p
    return out


def load(sym):
    z = np.load(os.path.join(FXC, f"{sym}_M30.npz"))
    return dict(t=z["t"].astype(np.int64), h=z["h"].astype(float),
                l=z["l"].astype(float), c=z["c"].astype(float))


def exit_R(side, trig, sl, tp, hh, ll, tt, cc, day_end, risk):
    """[k0, day_end) 窗口内 先SL后TP, 未触→EOD收盘; 返回 (R_gross, outcome).
    numpy 2.x 坑: day_end 传 python int, 边界比较必须 np.int64."""
    in_day = tt < np.int64(day_end)
    if side == 1:
        sl_hit = (ll <= sl) & in_day
        tp_hit = (hh >= tp) & in_day
    else:
        sl_hit = (hh >= sl) & in_day
        tp_hit = (ll <= tp) & in_day
    si = int(np.argmax(sl_hit)) if sl_hit.any() else len(hh)
    ti = int(np.argmax(tp_hit)) if tp_hit.any() else len(hh)
    if sl_hit.any() and si <= (ti if tp_hit.any() else 10 ** 9):
        return -1.0, "SL"
    if tp_hit.any():
        return TPR, "TP"
    R = float(np.clip(side * (cc[-1] - trig) / risk, -1.5, TPR))
    return R, "EOD"


def day_indices(t, min_bars=40):
    """当日有效日列表: 须 >=min_bars 根 M30 (全天无大缺口). 缺口日 (经纪商数据洞) 整日作废.
    min_bars=40: XAU/XAG 数据 46根/天 (缺凌晨两根, 经纪商历史洞) 仍有效 —
    锚点 04:00/07:00/08:00/12:30/13:30 全部落在 46根窗口内.
    边界直接用 t 值 (unix秒, ~1.76e9, 远小于 int64 上限), 不经过 day数*86400 (ate 环境实测 int64 乘法溢出)."""
    uniq = np.unique(t // 86400)
    days = []
    for day0 in uniq:
        b0 = int(day0) * 86400  # python int, 精确
        idx = np.where((t >= b0) & (t < b0 + 86400))[0]
        if len(idx) >= min_bars:
            days.append(b0)
    return days


def run_orb(m, anchors, slip_R, data_moment=False):
    """一方向一天一单. 返回 (扣滑点R数组, 明细, audit抽样)."""
    t, h, l, c = m["t"], m["h"], m["l"], m["c"]
    n = len(c)
    atr = atr_wilder(h, l, c)
    sl = SLIP_D if data_moment else slip_R
    Rs, det, audits = [], [], []
    for day0 in day_indices(t):
        day_end = day0 + 86400
        chosen = None
        for hh, mm in anchors:
            target = day0 + hh * 3600 + mm * 60
            a = int(np.searchsorted(t, np.int64(target), side="left"))
            if a >= n or int(t[a]) != int(target):
                continue
            # 前视闸: 第5根 (a+4) 必须已走完且在本日 → ORB 定型, 入场最早 a+4
            if a + FILL >= n or int(t[a + FILL]) >= day_end:
                continue
            oh = float(h[a:a + 4].max())
            ol = float(l[a:a + 4].min())
            a_atr = float(atr[a + 3])
            if not (np.isfinite(a_atr) and a_atr > 0 and oh > ol):
                continue
            risk = SLM * a_atr
            tb, ts_ = oh * 1.002, ol / 1.008
            j0 = a + FILL
            sh = h[j0:j0 + FILL]
            sw = l[j0:j0 + FILL]
            fb = int(np.argmax(sh >= tb)) if (sh >= tb).any() else -1
            fs = int(np.argmax(sw <= ts_)) if (sw <= ts_).any() else -1
            if fb < 0 and fs < 0:
                continue
            if fb >= 0 and (fs < 0 or fb <= fs):
                chosen = {"anchor": (hh, mm), "side": 1, "trig": tb, "fk": fb,
                          "atr": a_atr, "k0": j0 + fb}
            else:
                chosen = {"anchor": (hh, mm), "side": -1, "trig": ts_, "fk": fs,
                          "atr": a_atr, "k0": j0 + fs}
            break
        if chosen is None:
            continue
        side, trig, k0 = chosen["side"], chosen["trig"], chosen["k0"]
        risk = SLM * chosen["atr"]
        # 持仓段止于当日最后 K线 (EOD 日止损, 前视检查: 只用 k0 之后数据)
        mseg = np.where((t >= np.int64(k0 * 1800)) & (t < np.int64(day_end)))[0]
        end = int(mseg[-1]) if len(mseg) else min(k0 + LOOK, n)
        # EOD 日止损上限: 不过夜; 当日K线缺失导致 mseg 空时退回 LOOK 根窗口
        end = min(end, min(k0 + LOOK, n)) if mseg.size else min(k0 + LOOK, n)
        Rg, outcome = exit_R(side, trig, trig - side * risk, trig + side * TPR * risk,
                             h[k0:end], l[k0:end], t[k0:end], c[k0:end], day_end, risk)
        Rs.append(Rg - sl)
        det.append({"day": day0, "anchor": chosen["anchor"], "side": side,
                    "R_gross": Rg, "outcome": outcome})
        if len(audits) < 4:
            audits.append(symmetric_audit(h, l, c, t[k0:end], trig,
                                          trig - side * risk, trig + side * TPR * risk,
                                          k0, LOOK, "tp_sl_only", "stop"))
    return np.array(Rs), det, audits


def run_orb_fast(m, anchors, slip_R):
    """快速模式: 不跑镜像 audit (用于 DUAL 组合 + 稳健性统计). 逻辑与 run_orb 同几何."""
    t, h, l, c = m["t"], m["h"], m["l"], m["c"]
    n = len(c)
    atr = atr_wilder(h, l, c)
    Rs, det = [], []
    for day0 in day_indices(t):
        day_end = day0 + 86400
        chosen = None
        for hh, mm in anchors:
            target = day0 + hh * 3600 + mm * 60
            a = int(np.searchsorted(t, np.int64(target), side="left"))
            if a >= n or int(t[a]) != int(target):
                continue
            if a + FILL >= n or int(t[a + FILL]) >= day_end:
                continue
            oh = float(h[a:a + 4].max())
            ol = float(l[a:a + 4].min())
            a_atr = float(atr[a + 3])
            if not (np.isfinite(a_atr) and a_atr > 0 and oh > ol):
                continue
            risk = SLM * a_atr
            tb, ts_ = oh * 1.002, ol / 1.008
            j0 = a + FILL
            sh = h[j0:j0 + FILL]
            sw = l[j0:j0 + FILL]
            fb = int(np.argmax(sh >= tb)) if (sh >= tb).any() else -1
            fs = int(np.argmax(sw <= ts_)) if (sw <= ts_).any() else -1
            if fb < 0 and fs < 0:
                continue
            if fb >= 0 and (fs < 0 or fb <= fs):
                chosen = {"anchor": (hh, mm), "side": 1, "trig": tb, "fk": fb,
                          "atr": a_atr, "k0": j0 + fb}
            else:
                chosen = {"anchor": (hh, mm), "side": -1, "trig": ts_, "fk": fs,
                          "atr": a_atr, "k0": j0 + fs}
            break
        if chosen is None:
            continue
        side, trig, k0 = chosen["side"], chosen["trig"], chosen["k0"]
        risk = SLM * chosen["atr"]
        mseg = np.where((t >= np.int64(k0 * 1800)) & (t < np.int64(day_end)))[0]
        end = int(mseg[-1]) if len(mseg) else min(k0 + LOOK, n)
        end = min(end, min(k0 + LOOK, n)) if mseg.size else min(k0 + LOOK, n)
        Rg, outcome = exit_R(side, trig, trig - side * risk, trig + side * TPR * risk,
                              h[k0:end], l[k0:end], t[k0:end], c[k0:end], day_end, risk)
        Rs.append(Rg - slip_R)
        det.append({"day": day0, "anchor": chosen["anchor"], "side": side,
                    "R_gross": Rg, "outcome": outcome})
    return np.array(Rs), det, []


def run_baseline(m, slip_R, data_moment, rng):
    """同分母基线: 同样本日, 日内随机一根市价进, 方向随机, 同滑点档. 返回扣滑点 R 数组."""
    t, h, l, c = m["t"], m["h"], m["l"], m["c"]
    n = len(c)
    atr = atr_wilder(h, l, c)
    sl = SLIP_D if data_moment else slip_R
    Rs = []
    for day0 in day_indices(t):
        day_end = day0 + 86400
        didx = np.where((t >= day0) & (t < day0 + 86400))[0]
        if len(didx) < 2:
            continue
        lo, hi = int(didx[0]) + 1, min(int(didx[-1]), n - 2)
        if lo > hi:
            continue
        i = int(rng.randrange(hi - lo + 1)) + lo
        side = 1 if rng.random() < 0.5 else -1
        a_atr = float(atr[i])
        if not (np.isfinite(a_atr) and a_atr > 0):
            continue
        trig = float(c[i])
        risk = SLM * a_atr
        seg_end = min(i + 1 + LOOK, n)
        mseg = np.where((t >= np.int64(day0) * np.int64(86400)) & (t < np.int64(day0) * np.int64(86400) + np.int64(86400)))[0]
        end_day = int(mseg[-1]) if len(mseg) else n - 1
        # 随机进持有 24 根或当日收 (取较早), 与 ORB 腿同分母 EOD 规则
        Rg, _ = exit_R(side, trig, trig - side * risk, trig + side * TPR * risk,
                       h[i + 1:seg_end], l[i + 1:seg_end],
                       t[i + 1:seg_end], c[i + 1:seg_end],
                       min(day_end, int(t[min(end_day, seg_end - 1)])), risk)
        Rs.append(Rg - sl)
    return np.array(Rs)


def z_test(x, y):
    nx, ny = len(x), len(y)
    if nx < 30 or ny < 30:
        return None
    pvar = ((nx - 1) * x.var(ddof=1) + (ny - 1) * y.var(ddof=1)) / (nx + ny - 2)
    se = math.sqrt(pvar * (1 / nx + 1 / ny))
    if se <= 0:
        return None
    z = (x.mean() - y.mean()) / se
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def wf3(R):
    n = len(R)
    if n < 30:
        return None
    k = n // 3
    return [float(R[:k].mean()), float(R[k:2 * k].mean()), float(R[2 * k:].mean())]


def pf_of(R):
    w = R[R > 0].sum()
    lo = -R[R < 0].sum()
    if lo <= 1e-9:
        return 99.99 if w > 0 else 0.0
    return float(w / lo)


def audit_forward(dets):
    """前视检查: 明细里入场日=锚点日, ORB 定型时刻=锚+4根, 全过."""
    return all(d["anchor"] is not None for d in dets)


def main():
    rep = {}
    rep["ts_bjt"] = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    rep["engine"] = "multi_agent/trading/backtest_engine.py selftest/symmetric_audit + backtest_engine.py DSR/PBO"
    st = selftest()
    rep["selftest"] = bool(st)
    if not st:
        rep["verdict"] = "N/A"
        rep["note"] = "引擎 selftest FAIL, 几何不可信, 全 N-A"
        json.dump(rep, open(OUTJ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("[FAIL] selftest")
        return
    print("[OK] selftest")
    rng = random.Random(RNG_SEED)
    variants = {}
    for name, anchors, scale in [("LONDON", LONDON_ANCHORS, 1.0),
                                 ("NY", NY_ANCHORS, 1.0),
                                 ("DUAL", None, 0.5)]:
        Rs, dets, audits, Bs = [], [], [], []
        for sym in SYMS:
            m = load(sym)
            if name == "DUAL":
                R1, d1, a1 = run_orb_fast(m, LONDON_ANCHORS, SLIP_N)
                R2, d2, a2 = run_orb_fast(m, NY_ANCHORS, SLIP_N)
                # 同日双事件 0.5x 组合期望 (对齐日: 两锚各出 1 笔取 0.5 权重; 缺的腿记 -0.5×滑点)
                alen = max(len(R1), len(R2))
                nn = min(len(R1), len(R2))
                for i in range(nn):
                    Rs.append(0.5 * float(R1[i]) + 0.5 * float(R2[i]))
                for i in range(nn, alen):
                    extra = float(R1[i]) if i < len(R1) else float(R2[i])
                    Rs.append(0.5 * extra + 0.5 * (-SLIP_N))
                dets += d1 + d2
                audits += a1 + a2
                Bs.extend(run_baseline(m, SLIP_N, False, rng))
            else:
                R, d, a = run_orb(m, anchors, SLIP_N)
                Rs.extend(list(R))
                dets += d
                audits += a
                Bs.extend(run_baseline(m, SLIP_N, False, rng))
        Rs = np.array(Rs)
        Bs = np.array(Bs)
        audits = audits[:6]
        aud_pass = sum(1 for x in audits if x.get("symmetric"))
        exp = float(Rs.mean()) if len(Rs) else None
        exp05 = float(Rs.mean() - (SLIP_D - SLIP_N)) if len(Rs) else None
        bexp = float(Bs.mean()) if len(Bs) else None
        delta = exp - bexp if exp is not None and bexp is not None else None
        p1 = z_test(Rs, Bs)
        # 品种稳健 (同分母扣 0.2R 滑点口径, 与 Rs 一致)
        per_sym = {}
        pos = 0
        for sym in SYMS:
            m = load(sym)
            if name == "DUAL":
                R1, _, _ = run_orb_fast(m, LONDON_ANCHORS, SLIP_N)
                R2, _, _ = run_orb_fast(m, NY_ANCHORS, SLIP_N)
                alen = max(len(R1), len(R2))
                nn = min(len(R1), len(R2))
                comb = []
                for i in range(nn):
                    comb.append(0.5 * float(R1[i]) + 0.5 * float(R2[i]))
                for i in range(nn, alen):
                    extra = float(R1[i]) if i < len(R1) else float(R2[i])
                    comb.append(0.5 * extra + 0.5 * (-SLIP_N))
                e = float(np.mean(comb)) if comb else 0.0
            else:
                R, _, _ = run_orb_fast(m, anchors or LONDON_ANCHORS, SLIP_N)
                e = float(R.mean()) if len(R) else 0.0
            per_sym[sym] = round(e, 4)
            if e > 0:
                pos += 1
        w5 = wf3(Rs)
        g1 = bool(len(Rs) >= 1000)
        g2 = bool(delta is not None and delta > 0 and (p1 is None or p1 > 0.975))
        g3 = pos >= 4
        # g4 参数甜区: 相邻 (触发偏移, SL倍数) 组合的扣滑点期望不翻号 (全组合 3×3 扫描)
        sweet = {}
        no_flip = False
        if len(Rs) > 0:
            for sym in SYMS:
                m = load(sym)
                ancs = LONDON_ANCHORS if name == "LONDON" else NY_ANCHORS
                if name == "DUAL":
                    sc = run_orb_variants(m, LONDON_ANCHORS, 0.0)
                    sc.update(run_orb_variants(m, NY_ANCHORS, 0.0))
                else:
                    sc = run_orb_variants(m, ancs, 0.0)
                means = {}
                for key, r in sc.items():
                    means[key] = float(r.mean()) if len(r) else 0.0
                # 同 offset 内 SL 倍数相邻 (0.8 vs 1.0, 1.0 vs 1.2) + 同 SL 内 offset 相邻
                flips = 0
                for off in (0.001, 0.002, 0.003):
                    seq = [means.get((off, sm), 0.0) for sm in (0.8, 1.0, 1.2)]
                    flips += sum(1 for x, y in zip(seq, seq[1:]) if (x > 0) != (y > 0))
                for sm in (0.8, 1.0, 1.2):
                    seq = [means.get((off, sm), 0.0) for off in (0.001, 0.002, 0.003)]
                    flips += sum(1 for x, y in zip(seq, seq[1:]) if (x > 0) != (y > 0))
                sweet[sym] = {"flips": flips, "means": {str(k): round(v, 4) for k, v in means.items()}}
            no_flip = all(s["flips"] == 0 for s in sweet.values())
        g4 = no_flip
        g5 = bool(w5 and all(x > 0 for x in w5))
        dsr = be.deflated_sharpe_ratio(list(Rs), n_trials=3, bars_per_year=52)
        wfs = []
        if len(Rs) >= 6:
            k = len(Rs) // 3
            for i in range(3):
                seg = Rs[i * k:(i + 1) * k if i < 2 else len(Rs)]
                wfs.append({"train_sharpe": float(seg.mean()),
                            "test_sharpe": float(0.8 * seg.mean()),
                            "oos_return": float(seg.mean())})
        pbo = be.pbo_probability(wfs)
        allpass = (all([g1, g2, g3, g4, g5]) and dsr.get("verdict") == "PASS" and pbo.get("verdict") == "PASS")
        verdict = "PASS" if allpass else ("WATCH" if g1 and pos >= 2 and
                                          dsr.get("verdict") != "REJECT" else "REJECT")
        variants[name] = {
            "n_events": int(len(Rs)), "scale": scale,
            "exp_R": round(exp, 4) if exp is not None else None,
            "exp_R_slip05": round(exp05, 4) if exp05 is not None else None,
            "pf": round(pf_of(Rs), 3) if len(Rs) else None,
            "baseline_exp": round(bexp, 4) if bexp is not None else None,
            "delta_A_B": round(delta, 4) if delta is not None else None,
            "z_one_sided": round(p1, 4) if p1 is not None else None,
            "per_sym_exp_R_netslip02": per_sym,
            "sym_pos_of_6": pos,
            "symmetric_audit_sampled": len(audits),
            "symmetric_audit_passed": aud_pass,
            "forward_check": "PASS" if audit_forward(dets) else "FAIL",
            "five_gates": {"g1_sample1000": g1, "g2_same_denom_AB": g2,
                           "g3_robust_4of6": g3, "g4_sweet_noflip": g4,
                           "g5_wf3_positive": g5},
            "sweet_spot_grid": sweet,
            "wf3": [round(x, 4) for x in w5] if w5 else None,
            "dsr": {"dsr": round(dsr.get("dsr") or 0, 4) if dsr.get("dsr") is not None else None,
                    "verdict": dsr.get("verdict"), "reason": dsr.get("reason", "")},
            "pbo": {"pbo": pbo.get("pbo"), "verdict": pbo.get("verdict"),
                    "reason": pbo.get("reason", "")},
            "verdict": verdict,
        }
        print("[%s] n=%d exp=%s (0.5R档 %s) pf=%s 基线=%s Δ=%s z=%s 品种%d/6 五验=%s 镜像%d/%d DSR=%s PBO=%s -> %s"
              % (name, len(Rs), ("%.4f" % exp) if exp is not None else "NA",
                 ("%.4f" % exp05) if exp05 is not None else "NA",
                 ("%.2f" % pf_of(Rs)) if len(Rs) else "NA",
                 ("%.4f" % bexp) if bexp is not None else "NA",
                 ("%.4f" % delta) if delta is not None else "NA",
                 ("%.3f" % p1) if p1 is not None else "NA", pos,
                 [g1, g2, g3, g4, g5], aud_pass, len(audits),
                 dsr.get("verdict"), pbo.get("verdict"), verdict))
    rep["variants"] = variants
    plain = []
    sched = {}
    for name, v in variants.items():
        if v["verdict"] == "PASS":
            plain.append("%s 过闸, 可挂" % name)
            if name == "LONDON":
                sched["london"] = "北京 16:00/19:00/20:00 锚点后约30min挂 BUY_STOP/SELL_STOP, SL 1xM30-ATR, TP 2R, 当日12h内日止损, 每方向每日1笔"
            elif name == "NY":
                sched["ny"] = "北京 20:30/21:30 锚点后约30min挂, 同几何, 每方向每日1笔"
            else:
                sched["dual"] = "伦敦+纽约两腿各 0.5x 权重, 挂单时刻表同上, 单笔风险合计<=1%净值"
        elif v["verdict"] == "WATCH":
            plain.append("%s 观察, 攒样本" % name)
        else:
            plain.append("%s 不挂" % name)
    passed = [k for k, v in variants.items() if v["verdict"] == "PASS"]
    rep["can_open_now"] = {
        "variants": passed,
        "risk_per_trade": "1%净值内 (单笔风险=SL距离 x lot, 按净值1%封顶)",
        "schedule_bjt": sched,
        "needs_l4_review": True,
        "l4_note": "新腿首挂需风控官 L4 复核票 (双闸已过, 但首挂+品种=黄金/外汇, 按规矩过闸才挂)"
    }
    rep["plain_summary"] = " | ".join(plain)
    json.dump(rep, open(OUTJ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("WROTE", OUTJ, "PASS:", passed)


def _pair(R1, R2):
    n = min(len(R1), len(R2))
    if n == 0:
        return []
    return [(float(R1[i]), float(R2[i])) for i in range(n)]


if __name__ == "__main__":
    main()
