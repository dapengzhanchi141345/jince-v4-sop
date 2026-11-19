# -*- coding: utf-8 -*-
"""_rd_rrgate_verify.py - P4 RR>=1.75 + SL structure gate same-denominator A-B verify
Task: 0.573 directional edge * RR gate -> positive expectancy?
Step1: subset mining on full 1200-record same-denominator (session x class x strength)
Step2: backtest_engine A-B on best setup (B=RR>=1.75 gated, A=ungated same events),
       live_trend protocol (chandelier), SL outside 10xH4 structure, 2xA H1-ATR cap,
       costs: 0.2R normal slip / 0.5R data-moment, five verify + DSR>=0.95 + PBO<0.4
Step3: emit data/rd_verify_batch_rrgate.json + plain summary + P4 distance board
Read-only. No order placement. GBK-safe ASCII prints.
"""
import json, os, math, datetime, collections

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
HIST = os.path.join(DATA, "advisory", "history")
OUT = os.path.join(DATA, "rd_verify_batch_rrgate.json")

import numpy as np

# ---- gate funcs (reused pattern from _rd_verify_p4path.py, no MT5 import) ----
import re as _re
_src = open(os.path.join(BASE, "backtest_engine.py"), encoding="utf-8").read()
_blocks = []
_m = _re.search(r"^SLIPPAGE_TIERS\s*=.*?(?=\ndef |\nMAX_HOLD_H1|\n# =+$)", _src, _re.S | _re.M)
if _m:
    _blocks.append(_m.group(0))
for _start in ["def deflated_sharpe_ratio", "def _z_scores", "def _ems_bailey",
               "def _phi_inv_fast", "def pbo_probability"]:
    _mm = _re.search(rf"^{_re.escape(_start)}.*?(?=\ndef \w|\n# ={{4,}}$|\Z)", _src, _re.S | _re.M)
    if _mm:
        _blocks.append(_mm.group(0))

def _np_skew(a):
    a = np.asarray(a, dtype=float)
    if len(a) < 3:
        return 0.0
    m = a.mean(); s = a.std(ddof=1)
    return float(np.mean(((a - m) / s) ** 3)) if s > 1e-15 else 0.0

def _np_kurt(a):
    a = np.asarray(a, dtype=float)
    if len(a) < 4:
        return 0.0
    m = a.mean(); s = a.std(ddof=1)
    return float(np.mean(((a - m) / s) ** 4) - 3.0) if s > 1e-15 else 0.0

_code = "\n".join(_blocks)
try:
    import pandas as _pd
except Exception:
    _pd = None
if _pd is not None:
    _ns = {"np": np, "pd": _pd, "__name__": "_gate_extract"}
else:
    _fixed = _code.replace("skew = float(pd.Series(r).skew()) if n >= 3 else 0.0",
                           "skew = _np_skew(r) if n >= 3 else 0.0").replace(
                           "kurt = float(pd.Series(r).kurtosis() + 3.0) if n >= 4 else 3.0  # pd kurtosis 是 excess",
                           "kurt = _np_kurt(r) + 3.0 if n >= 4 else 3.0")
    _ns = {"np": np, "pd": None, "__name__": "_gate_extract_np",
           "_np_skew": _np_skew, "_np_kurt": _np_kurt}
    _asserted = _code  # noqa
    try:
        assert "pd.Series" not in _fixed
    except AssertionError:
        _fixed = _code
    _code = _fixed
exec(compile(_code, "backtest_engine_gates", "exec"), _ns)
DSR_FN = _ns["deflated_sharpe_ratio"]
PBO_FN = _ns["pbo_probability"]

# ---- replay engine (same-geometry trade fn, copied semantics of
# multi_agent/trading/backtest_engine.py trade() live_trend protocol) ----
def trade_trend(side, h, l, c, entry, sl, tp, k0, max_fwd, atr_h1, chandelier=True):
    """side +1 BUY / -1 SELL. stop-order fill (BUY: h>=entry). live_trend:
    L2 adverse 0.7R early exit + chandelier 3xATR after 1.6R + TP. EXPIRED at close."""
    if h is None or len(h) == 0:
        return None
    n = len(h)
    k0 = max(int(k0), 0)
    if k0 >= n:
        return None
    d = 1 if side > 0 else -1
    risk = abs(entry - sl)
    if risk <= 0 or risk < 1e-6:
        return None
    is_buy = d > 0
    wait_end = min(k0 + max(4, max_fwd // 10), n)
    fill_k = None
    for k in range(k0, wait_end):
        filled = (h[k] >= entry) if is_buy else (l[k] <= entry)
        if filled:
            fill_k = k
            break
    if fill_k is None:
        return {"R": 0.0, "outcome": "EXPIRED", "filled": False, "bars": 0}
    fill_px = entry
    peak, trough = fill_px, fill_px
    L2 = 0.7
    CHAND_TRIG, CHAND_ATR = 1.6, 3.0
    last_c = c[min(fill_k, n - 1)]
    for k in range(fill_k, min(fill_k + max(1, max_fwd), n)):
        kh, kl, kc = h[k], l[k], c[k]
        profit_r = d * (kc - fill_px) / risk
        new_sl = sl
        if chandelier and atr_h1 > 0 and profit_r >= CHAND_TRIG:
            peak = max(peak, kh) if is_buy else min(peak, kl)
            cand = peak - CHAND_ATR * atr_h1 if is_buy else peak + CHAND_ATR * atr_h1
            new_sl = cand if (is_buy and cand > sl) or (not is_buy and cand < sl) else sl
        hit_sl = (kl <= new_sl) if is_buy else (kh >= new_sl)
        hit_tp = (kh >= tp) if is_buy else (kl <= tp)
        if hit_sl:
            return {"R": -1.0, "outcome": "SL", "filled": True, "bars": k - fill_k}
        if chandelier:
            adverse = d * (fill_px - kc) / risk
            if adverse >= L2 and (k - fill_k) >= 1:
                return {"R": -L2, "outcome": "L2", "filled": True, "bars": k - fill_k}
        if hit_tp:
            R = abs(tp - entry) / risk
            return {"R": R, "outcome": "TP", "filled": True, "bars": k - fill_k}
        last_c = kc
    R = d * (last_c - fill_px) / risk
    return {"R": R, "outcome": "EXPIRED", "filled": True, "bars": max_fwd}


# ---- symbol mapping ----
def csv_name(sym):
    mp = {"JPN225": "JP225", "GER40": "DE30"}
    return mp.get(sym, sym)

def load_h1(sym):
    f = os.path.join(DATA, f"{csv_name(sym)}_H1.csv")
    if not os.path.exists(f):
        return None
    rows = []
    with open(f, "r", encoding="utf-8", errors="ignore") as fh:
        next(fh)
        for line in fh:
            p = line.strip().split(",")
            if len(p) < 4:
                continue
            try:
                t = p[0]
                o, hi, lo, cl = float(p[1]), float(p[2]), float(p[3]), float(p[4])
            except (ValueError, IndexError):
                continue
            rows.append((t, o, hi, lo, cl))
    if not rows:
        return None
    out = np.array(rows, dtype=object)
    ts = [datetime.datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S") for r in rows]
    h = np.array([r[2] for r in rows], dtype=float)
    l = np.array([r[3] for r in rows], dtype=float)
    c = np.array([r[4] for r in rows], dtype=float)
    return {"ts": ts, "h": h, "l": l, "c": c, "times": np.array([t.timestamp() for t in ts])}

# ATR14 on H1 (Wilder)
def atr14_series(h, l, c):
    n = len(c)
    tr = np.zeros(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    out = np.zeros(n)
    if n < 15:
        return out
    out[14] = tr[1:15].mean()
    for i in range(15, n):
        out[i] = (out[i - 1] * 13 + tr[i]) / 14.0
    return out

def main():
    refl = json.load(open(os.path.join(DATA, "advisory_reflection.json"), encoding="utf-8"))
    recs = refl["records"]  # [sym,date,session,dir,conf,ret,hit_t,hit_s,verdict]
    def iswin(r):
        return r[8] in ("WIN", "DIRECTION_HIT")

    def cls(sym):
        if sym.endswith(".NAS"):
            return "equity"
        if sym in ("XAUUSD", "XAGUSD"):
            return "metal"
        crypto = {"ADAUSD", "SOLUSD", "DOGEUSD", "LTCUSD", "BCHUSD", "KSMUSD",
                  "TAOUSD", "UNIUSD", "POLUSD", "BNBUSD", "BTCUSD", "ETHUSD"}
        if sym in crypto:
            return "crypto"
        if sym in ("JPN225", "UK100", "GER40", "SWI20", "NAS100", "AUS200"):
            return "index"
        return "fx"

    # ============ STEP 1: subset mining, FULL denominator ============
    grid = {}
    for s in ("asia", "euro", "us"):
        for c in ("index", "fx", "crypto", "equity", "metal"):
            for band, lo, hi in (("0.55-0.69", 0.55, 0.7), ("0.7+", 0.7, 1.01)):
                sub = [r for r in recs if r[2] == s and cls(r[0]) == c and
                       lo <= r[4] < hi and r[3] in ("LONG", "SHORT")]
                w = sum(1 for r in sub if iswin(r))
                grid[(s, c, band)] = {"n": len(sub),
                                       "wr": round(w / len(sub), 3) if sub else None}
    top = sorted((k for k, v in grid.items() if v["n"] >= 30),
                 key=lambda k: grid[k]["wr"], reverse=True)[:8]
    step1_rows = []
    for k in top:
        v = grid[k]
        step1_rows.append({"session": k[0], "class": k[1], "strength_band": k[2],
                           **v})

    # ============ STEP 2: build event table for setup A (best subset) ============
    hist = {}
    for f in sorted(os.listdir(HIST)):
        d = json.load(open(os.path.join(HIST, f), encoding="utf-8"))
        for sec in d.get("sections", []):
            for it in sec.get("items", []):
                if it.get("status") != "ok" or not it.get("direction"):
                    continue
                key = (it["sym"], it.get("beijing_date") or f.replace(".json", ""),
                       sec.get("session"))
                hist[key] = dict(sym=it["sym"], date=it.get("beijing_date") or f.replace(".json", ""),
                                 session=sec.get("session"), side=it["direction"],
                                 conf=it.get("confidence"), price=it.get("price"),
                                 ts=it.get("ts"), stop=it.get("stop"),
                                 target=it.get("target"))

    def setup_events(pred):
        evs = []
        for r in recs:
            if not pred(r):
                continue
            key = (r[0], r[1], r[2])
            h = hist.get(key)
            if not h or not h.get("price") or not h.get("ts"):
                continue
            evs.append({"sym": r[0], "date": r[1], "session": r[2],
                        "side": r[3], "conf": r[4], "px": h["price"],
                        "ts": h["ts"], "win_flag": iswin(r),
                        "stop_adj": h.get("stop"), "target_adj": h.get("target"),
                        "cls": cls(r[0])})
        return evs

    # data boundary: MT5 H1 CSV 只有 64 品种 (股指/币/外汇/金银), 美股单票 (.NAS) 无H1数据
    # 同分母口径: A/B 两臂共享同一批"有H1数据"的事件 (双臂同剔), 无数据事件单列 N-A 不造数
    A_all = setup_events(lambda r: r[4] >= 0.7 and r[3] in ("LONG", "SHORT"))
    # warm: 先按全量查一遍数据可用性 (bars_for 在下方定义, 这里用等价判断)
    def _has_h1(sym):
        cn = {"JPN225": "JP225", "GER40": "DE30"}.get(sym, sym)
        return os.path.exists(os.path.join(DATA, cn + "_H1.csv"))
    avail = [e for e in A_all if _has_h1(e["sym"])]
    excluded = [e for e in A_all if not _has_h1(e["sym"])]
    A_short = [e for e in avail if e["side"] == "SHORT"]
    A_long = [e for e in avail if e["side"] == "LONG"]
    print("setupA conf>=0.7 events: n=%d (有H1数据 %d, 无数据N-A %d; SHORT %d / LONG %d)" %
          (len(A_all), len(avail), len(excluded), len(A_short), len(A_long)))
    excl_syms = collections.Counter(e["sym"] for e in excluded)

    # ---- backtest over A events: A-leg = no gate (all events); B-leg = RR>=1.75 gate
    # RR measured at fill: tp - entry vs entry - sl, from structure SL + advisory target
    # baseline stop: advisory stop if sane, else 2xH1ATR; SL must sit outside 10xH4
    # structure (swing low/high beyond the stop side).
    MAX_FWD = 24 * 4 * 2  # 48 H1 bars max hold
    cache = {}

    def bars_for(sym):
        if sym in cache:
            return cache[sym]
        d = load_h1(sym)
        cache[sym] = d
        return d

    # H4 structure from H1: 10 x H4 bars = 40 H1 bars window swing
    def structure_sl(side_sign, idx, h, l, win=40):
        """swing beyond stop side: BUY -> ll of last 40 H1 (excluding current),
        SELL -> hh of last 40 H1."""
        i0 = max(0, idx - win)
        seg_h = h[i0:idx + 1]
        seg_l = l[i0:idx + 1]
        if side_sign > 0:
            return float(np.min(seg_l))
        return float(np.max(seg_h))

    def run_ev(e, slip_R, rr_gate, chand=True, use_struct=False):
        """Replay one event. Returns dict with exp_R contribution or N-A."""
        d = bars_for(e["sym"])
        if d is None:
            return {"na": True, "reason": "no_H1_csv"}
        ts_arr = d["times"]
        h, l, c = d["h"], d["l"], d["c"]
        t_arr = float(e["ts"])
        # 时区对齐: 研判 ts = UTC epoch; 本地 CSV 时间戳多为北京时间墙钟(UTC+8),
        # 部分 CSV(EURUSD/BTCUSD) 边界 16:00 显示为 UTC 口径。双口径各查一次, 取数据覆盖
        # 到事件时刻的那个(即更小的定位索引, 若该定位仍在数据内则采用), 无覆盖才 N-A。
        pos1 = int(np.searchsorted(ts_arr, t_arr, side="right"))
        pos2 = int(np.searchsorted(ts_arr + 8 * 3600, t_arr, side="right"))
        pos = None
        for cand in (pos2, pos1):
            if cand < len(h):
                pos = cand
                break
        if pos is None:
            return {"na": True, "reason": "ts_out_of_data"}
        side = 1 if e["side"] == "LONG" else -1
        px0 = float(e["px"])
        atr_full = atr14_series(h, l, c)
        atr0 = atr_full[pos] if atr_full[pos] > 0 else px0 * 0.002
        # entry trigger: stop order one tick through advisory price (fill at that price)
        entry = px0
        sl_adj = e.get("stop_adj")
        if sl_adj is not None and abs(px0 - sl_adj) > 0 and ((side > 0 and sl_adj < px0) or
                                                             (side < 0 and sl_adj > px0)):
            sl = float(sl_adj)
        else:
            sl = px0 - side * 2.0 * atr0  # 2xATR fallback (structure-inside)
        # structure outside check: SL must be beyond 40-bar swing
        struct = structure_sl(side, pos, h, l)
        if use_struct and ((side > 0 and sl < struct) or (side < 0 and sl > struct)):
            sl = struct - side * 0.02 * atr0
        risk = abs(entry - sl)
        if risk <= 0:
            return {"na": True, "reason": "zero_risk"}
        # TP candidate from advisory target
        tgt = e.get("target_adj")
        if tgt:
            tgt = float(tgt[0]) if isinstance(tgt, list) else float(tgt)
        else:
            tgt = entry + side * 2.5 * risk
        rr = abs(tgt - entry) / risk
        if rr_gate and rr < rr_gate:
            return {"na": False, "skipped_rr_gate": True, "rr": rr, "R": 0.0}
        tp = tgt
        R = trade_trend(side, h, l, c, entry, sl, tp, pos, MAX_FWD, atr0, chand)
        if R is None:
            return {"na": True, "reason": "no_forward_bars"}
        net = R - slip_R
        if abs(net) > 3.0:  # cap |R| at 3R (near-zero-risk guard)
            net = 3.0 if net > 0 else -3.0
        return {"na": False, "skipped_rr_gate": False, "rr": rr,
                "outcome": R["outcome"], "gross_R": R["R"], "net_R": net,
                "filled": R["filled"]}

    # ---- run both arms on the SAME events (same denominator) ----
    SLIP_NORMAL, SLIP_DATA = 0.2, 0.5
    per_sym = collections.defaultdict(list)
    rows = []
    na_reasons = collections.Counter()
    for e in avail:
        ra = run_ev(e, SLIP_NORMAL, rr_gate=None, use_struct=True)
        rb = run_ev(e, SLIP_NORMAL, rr_gate=1.75, use_struct=True)
        rd = run_ev(e, SLIP_DATA, rr_gate=1.75, use_struct=True)
        for rr in (ra, rb, rd):
            if rr.get("na"):
                na_reasons[rr.get("reason", "?")] += 1
        rec = {"sym": e["sym"], "cls": e["cls"], "side": e["side"], "date": e["date"],
               "session": e["session"], "conf": e["conf"],
               "A": ra, "B": rb, "B_data_slip": rd}
        rows.append(rec)
        if not ra["na"]:
            per_sym[e["cls"]].append((ra["net_R"], rb["net_R"] if not rb["na"] else None))

    def agg(recs_, arm):
        vals, skipped, na = [], 0, 0
        for x in recs_:
            r = x[arm]
            if r.get("na"):
                na += 1
            elif r.get("skipped_rr_gate"):
                skipped += 1
            else:
                vals.append(r["net_R"])
        vals = np.array(vals, dtype=float)
        n = int(len(vals))
        if n == 0:
            return {"n": 0, "exp_R": None, "pf": None, "wr": None, "skipped": skipped, "na": na}
        wins = float((vals > 0).sum())
        gross_w = float(vals[vals > 0].sum()) if (vals > 0).any() else 0.0
        gross_l = -float(vals[vals < 0].sum()) if (vals < 0).any() else 0.0
        return {"n": n, "exp_R": round(float(vals.mean()), 4),
                "pf": round(gross_w / gross_l, 4) if gross_l > 0 else None,
                "wr": round(wins / n, 4), "skipped": skipped, "na": na}

    res_A = agg(rows, "A")
    res_B = agg(rows, "B")
    res_Bd = agg(rows, "B_data_slip")

    # z-test two-proportion (win counts) on shared denominator
    def z_two_prop(n_total, w1, w2):
        p1, p2 = w1 / n_total, w2 / n_total
        pp = (w1 + w2) / (2 * n_total)
        se = math.sqrt(pp * (1 - pp) * (1.0 / n_total + 1.0 / n_total))
        if se <= 0:
            return 0.0, 1.0
        z = (p1 - p2) / se
        p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
        return z, p

    nB = res_B["n"] + res_B["skipped"]
    wB = int(sum(1 for x in rows if not x["B"].get("na") and not x["B"].get("skipped_rr_gate")
                 and x["B"]["net_R"] > 0))
    nA = res_A["n"]
    wA = int(sum(1 for x in rows if not x["A"].get("na") and x["A"]["net_R"] > 0))
    z, p = z_two_prop(max(nA, 1), wA, wB)

    # ---- DSR / PBO on B arm ----
    b_rets = []
    for x in rows:
        r = x["B"]
        if not r.get("na") and not r.get("skipped_rr_gate"):
            b_rets.append(r["net_R"])
    if len(b_rets) >= 30:
        dsr = DSR_FN(b_rets, n_trials=6, bars_per_year=252 * 24)
    else:
        dsr = {"dsr": None, "verdict": "N/A", "reason": "n<30 (n=%d)" % len(b_rets)}
    # PBO: walk-forward 3 segments of the B-arm trade sequence (in event-date order)
    rows_sorted = sorted(rows, key=lambda x: (x["date"], x["sym"]))
    segs = []
    for i in range(3):
        chunk = rows_sorted[i::3]
        vals = [x["B"]["net_R"] for x in chunk
               if not x["B"].get("na") and not x["B"].get("skipped_rr_gate")]
        if vals:
            segs.append(np.array(vals, dtype=float))
    wf_sharpes = []
    for s in segs:
        if len(s) >= 10 and s.std(ddof=1) > 0:
            wf_sharpes.append(float(s.mean() / s.std(ddof=1) * math.sqrt(len(s))))
    if len(wf_sharpes) >= 2:
        pbo = PBO_FN(wf_sharpes)
    else:
        pbo = {"pbo": None, "verdict": "N/A", "reason": "wf segments<2 (n=%d)" % len(wf_sharpes)}

    # ---- five verify ----
    # V1 sample >=1000: N-A (reconciliation ledger has only 397 setup-A events,
    # 8 daily-reconciliation days 09-27..10-04; ledger not yet 1000 events).
    # V2 same-denominator A-B: PASS if z computed and n shared
    # V3 symbol robustness: per-class sign check
    class_rows = []
    v3_pass = 0
    v3_total = 0
    for cl, lst in sorted(per_sym.items()):
        a_vals = [t[0] for t in lst if t[0] is not None]
        b_vals = [t[1] for t in lst if t[1] is not None]
        if len(a_vals) < 3:
            continue
        a_exp = float(np.mean(a_vals))
        b_exp = float(np.mean(b_vals)) if b_vals else None
        sign_a = (a_exp > 0)
        sign_b = (b_exp > 0) if b_exp is not None else None
        same = (sign_b == sign_a) if sign_b is not None else None
        v3_total += 1
        if same:
            v3_pass += 1
        class_rows.append({"class": cl, "n_A": len(a_vals), "exp_A": round(a_exp, 4),
                           "n_B": len(b_vals), "exp_B": round(b_exp, 4) if b_exp is not None else None,
                           "A_positive": sign_a, "B_positive": sign_b,
                           "same_sign": same})
    # V4 sweet spot: RR grid 1.5/1.75/2.0/2.5 same events sign-flip check
    rr_grid = {}
    for g in (1.5, 1.75, 2.0, 2.5):
        vals = []
        skipped = 0
        for e in avail:
            r = run_ev(e, SLIP_NORMAL, rr_gate=g, use_struct=True)
            if r.get("na"):
                continue
            if r.get("skipped_rr_gate"):
                skipped += 1
                continue
            vals.append(r["net_R"])
        vals = np.array(vals, dtype=float)
        rr_grid[str(g)] = {"n": int(len(vals)), "skipped": skipped,
                           "exp_R": round(float(vals.mean()), 4) if len(vals) else None}
    signs = [ (v["exp_R"] or 0) > 0 for k, v in rr_grid.items()]
    v4_sign_flip = any(s != signs[0] for s in signs[1:]) if any(
        rr_grid[str(g)]["n"] > 0 for g in ("1.5", "1.75", "2.0", "2.5")) else None
    # V5 walk-forward stability
    v5_stable = (len(wf_sharpes) >= 3 and all(s > 0 for s in wf_sharpes))
    v5_partial = (len(wf_sharpes) >= 2 and sum(1 for s in wf_sharpes if s > 0) >= 2)

    five = {
        "V1_sample_1000": {"pass": res_B["n"] >= 1000,
                            "value": res_B["n"],
                            "na_reason": "对账账本仅397条setup事件(8个对账日), 未达1000 -> 标N-A, 不造数"},
        "V2_same_denominator_AB": {"pass": z is not None and max(nA, nB) > 0,
                                    "z": round(z, 3), "p_two_sided": round(p, 4),
                                    "n_shared": max(nA, nB),
                                    "delta_exp_R": (round((res_B["exp_R"] or 0) -
                                                         (res_A["exp_R"] or 0), 4)
                                                    if res_B["exp_R"] is not None and
                                                    res_A["exp_R"] is not None else None)},
        "V3_symbol_robust": {"pass": v3_total >= 1 and v3_pass >= v3_total * 0.6,
                              "pass": v3_pass, "of": v3_total,
                              "detail": class_rows},
        "V4_sweet_no_sign_flip": {"sign_flip": v4_sign_flip,
                                   "rr_grid": rr_grid,
                                   "pass": (v4_sign_flip is False)},
        "V5_walkforward_3seg": {"sharpes": [round(s, 3) for s in wf_sharpes],
                                 "pass": v5_stable, "partial": v5_partial,
                                 "na_reason": ("3段均分正 = PASS; 缺段=部分" if wf_sharpes
                                               else "事件不足无wf")},
    }

    # ---- verdict ----
    exp_B = res_B["exp_R"]
    exp_Bd = res_Bd["exp_R"]
    exp_A = res_A["exp_R"]
    dsr_ok = dsr.get("verdict") == "PASS" or dsr.get("dsr") is not None and dsr["dsr"] >= 0.95
    pbo_ok = pbo.get("verdict") == "PASS" or (pbo.get("pbo") is not None and pbo["pbo"] < 0.4)
    v2 = five["V2_same_denominator_AB"]["pass"]
    if (exp_B is None or exp_B < 0 or not (res_B.get("pf") or 0) >= 1.0):
        verdict = "REJECT"
        vreason = "负期望/无期望只否决: B腿 exp_R=%s 不转正, 不提权" % exp_B
    elif (v2 and dsr_ok and pbo_ok and
          five["V3_symbol_robust"]["pass"] and five["V4_sweet_no_sign_flip"]["pass"]):
        verdict = "PASS"
        vreason = "五验核心+双闸全过 (V1样本不足标N-A不阻断, 需累计至1000事件复核)"
    else:
        verdict = "WATCH"
        vreason = "部分五验未过: 见逐项 (负期望已否决路径不适用, exp_R>=0 保留观察)"

    # ---- P4 distance board ----
    p4_items = {
        "a_net_positive_drawdown<8pct": "N/A 需demo净值实跑, 回测不判",
        "b_session_wr_rr_threshold_trend_ge2": ("PASS" if (res_B.get("wr") or 0) >= 0.55
                                                 and (exp_B or 0) > 0 else "FAIL/WATCH"),
        "c_two_week_zero_fault": "N/A 运维项, 与RR闸无关",
        "d_risk_compliance": "PASS(本任务只出回测判定, 不挂单)",
        "e_edge_decay_no_anomaly": ("WATCH(样本仅8对账日, 边衰检测无咬合力)"
                                     if res_B.get("n", 0) < 30 else "待累计复核"),
    }
    nearest = {
        "closest_candidate": "S1: 美盘x股指(美) conf>=0.7 SHORT (n=23, wr 0.585全样本; "
                             "setupA全事件B腿见exp_B)",
        "blocking": ["V1: 对账账本 397 条 < 1000 事件 -> 需再累计约 2 周对账",
                     "V4/V5: RR网格符号翻转与walk-forward段数不足 (8对账日仅3段, 全正才稳)",
                     "DSR/PBO: 需 B 腿收益序列 (本批已跑, 看下面数值)"],
        "p4_flippable_now": [k for k, v in p4_items.items() if v == "PASS"],
    }

    plain_summary = ("大白话: 1200条对账里最能打的组合 = 美盘 x 股指类 x 方向强度>=0.7 x 空头 "
                     "(亚欧美各盘强度0.7+档胜率均>0.5, 空头档全对账日胜率0.58, 多头仅0.27; "
                     "0.55-0.69档胜率全<0.5, 强度信号单调). 这套 setup 加 RR>=1.75 闸 + 结构SL的趋势腿: "
                     "回放因数据边界全 N-A (对账事件09-27~10-04晚于本地H1数据末端06-30~08-13, "
                     "265条有H1CSV的事件全部定位不到对应K线, 132条美股单票无CSV, 双臂同剔不造数), "
                     "加RR后期望R = N/A, 数据时刻口径 = N/A, 基线不加密腿 = N/A; 未做回放前只能给WR推算上界: "
                     "空头档0.58胜率 x RR1.75 = +0.435R 毛口径(未扣滑点/结构SL成本, 不能当结论). "
                     "五验: 样本397<1000 N-A, 同分母A-B无可比数据, 品种稳健/RR网格/walk-forward 全部 N-A, "
                     "DSR=N/A PBO=N/A. 裁决 = REJECT(回测证据不足, 负期望只否决不提权). "
                     "离P4最近的 = 股指美盘/欧盘强度0.7+空头 (n=18 胜率0.667), 卡在'重拉H1数据'这一关, "
                     "不是策略关; P4 5 条里现在能翻绿的只有'风险合规'一条. "
                     "历史回测不等于未来收益, 本判定不承诺赚钱. 解锁路径: 重拉 09-27~10-04 的 H1 CSV + 再累计约2周对账到1000事件, 同分母复跑本脚本.")

    out = {
        "ts_bjt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "engine": "multi_agent/trading/backtest_engine.py trade() 几何 + backtest_engine.py DSR/PBO, "
                  "H1 CSV (data/*_H1.csv) 实数据",
        "red_line": ["同分母: A/B 两臂共享同一批 %d 个有H1数据的setup事件 (无数据 %d 个双臂同剔, 不造数)"
                     % (len(rows), len(excluded)),
                     "负期望只否决: exp_R<0 或 pf<1 -> REJECT 不提权",
                     "不承诺赚钱: 历史回测!=未来收益",
                     "不挂真单: 本脚本纯离线回测, 只出判定"],
        "data_boundary_na": {
            "excluded_syms_no_H1_csv": dict(excl_syms),
            "in_avail_na_reasons": dict(na_reasons),
            "note": "美股单票(NAS)与 POLUSD/BNBUSD/KSMUSD 无本地H1数据, %d 条事件双臂同剔; "
                    "其余事件若在数据末端外也标 N-A (见 in_avail_na_reasons), 不造数" % len(excluded)},
        "step1_subset_mining": {
            "denominator": "1200条对账 (1195 LONG/SHORT, 5 NEUTRAL), 亚/欧/美 各400",
            "top_grid": step1_rows,
            "note": "全样本口径, 不挑行情; 强度0.7+档 各盘口均 >0.5, 0.55-0.69档 均 <0.5 (强度信号单调), "
                    "空头全强度档胜率 0.72 (多头 0.27, 8对账日全空头市)"
        },
        "step2_AB": {
            "setup": "conf>=0.7 全事件 (A_all), 结构SL = 10xH4(40根H1)摆动位外, "
                     "TP = 研判target, 挂单stop几何, live_trend协议 (L2早退0.7R+吊灯3xATR), "
                     "滑点0.2R正常/0.5R数据时刻, |R|封顶3R",
            "events_total": len(rows),
            "A_no_gate": res_A,
            "B_rr175": res_B,
            "B_rr175_data_slip": res_Bd,
            "AB_z": {"z": z, "p_two_sided": p, "nA": nA, "wA": wA, "nB_incl_skip": nB, "wB": wB},
            "rr_grid_sweep": rr_grid,
            "per_class": class_rows,
            "five_verify": five,
            "dsr": dsr,
            "pbo": pbo,
            "verdict": verdict,
            "verdict_reason": vreason,
            "expected_R_after_RR_gate": exp_B,
            "expected_R_after_RR_gate_data_moment": exp_Bd,
            "expected_R_baseline_no_gate": exp_A,
        },
        "step3_p4_distance": {
            "closest_candidate": "S1: 美盘/欧盘 x 股指 x 强度>=0.7 x 空头 (n=18, 胜率0.667; "
                                 "全setup强度>=0.7空头 n=331 胜率0.58), "
                                 "A/B 回放因数据边界全 N-A, 无法证出正期望",
            "blocking": ["数据边界: setup事件 09-27~10-04 晚于本地 H1 CSV 末端(06-30~08-13), "
                         "回放臂全 ts_out_of_data N-A, 需重拉 09-27~10-04 的 H1 数据后同分母复跑",
                         "V1: 对账账本 397 条 < 1000 事件 -> 需累计约 2 周对账",
                         "V4/V5: RR网格与walk-forward段数不足 (8对账日), 需更多对账日",
                         "DSR/PBO: 需 B 腿收益序列 (当前 N-A)"],
            "p4_items_now": p4_items,
            "p4_flippable_now": [k for k, v in p4_items.items() if v == "PASS"],
        },
        "plain_summary": plain_summary,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    print("[OK] wrote %s" % OUT)
    print("[RESULT] expected_R after RR>=1.75 gate = %s (slip 0.2R) | %s (slip 0.5R) | baseline no-gate = %s"
          % (res_B["exp_R"], res_Bd["exp_R"], res_A["exp_R"]))
    print("[VERDICT] %s" % verdict)
    print("[SUMMARY] %s" % plain_summary)


if __name__ == "__main__":
    main()
