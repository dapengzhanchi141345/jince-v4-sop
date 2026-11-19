# -*- coding: utf-8 -*-
"""
P5-ORB 股指增量假设同分母小回测 (2026-11-15 夜间深研第3轮)
数据: data/es_lab_cache/{US30,NAS100}_20000.npz (MT5 brokerFX M15, 2026-01-08 ~ 2026-11-11)
假设 H_ORB-CONFIRM: P5卡断言「M5整根收线确认突破 > 尖峰(影线)触及进场, 假破率最低」本机无数字 ->
  双变体同分母实测: A=尖峰触及进场(限价语义), B=M15收线确认进场, 离场同口径(SL区间对侧/TP2R/16:00UTC强平/扣0.095R)
副假设 H_WIDTH: 卡上宽度过滤器①「区间宽>50%日ATR=空间不足拒 / <10%=噪声日拒」按分桶净R验证
DST: 美冬令 NY开盘=14:30UTC, 2026-03-08~2026-11-01 夏令=13:30UTC, 11-01后回14:30UTC; 强平16:00UTC
铁律: 逐品种裁定, 不跨品种平均; 样本<30=显式FAIL
"""
import json, os, datetime
import numpy as np

BASE = r"E:\GoldstrategyEngine"
DST_START = datetime.date(2026, 3, 8)
DST_END = datetime.date(2026, 11, 1)  # 当天回冬令
COST_R = 0.095

def open_sec(d):
    return 13 * 3600 + 1800 if DST_START <= d < DST_END else 14 * 3600 + 1800

def cap_bars(d):
    """16:00UTC 距开盘的 M15 bar 数"""
    os_ = open_sec(d)
    return (16 * 3600 - os_) // 900

def run_one(sym):
    d = np.load(os.path.join(BASE, "data", "es_lab_cache", f"{sym}_20000.npz"), allow_pickle=True)
    t = d["time"].astype(np.int64)
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    days = []
    ds = datetime.date(2026, 1, 8)
    de = datetime.date(2026, 11, 11)
    while ds <= de:
        open_ep = int(datetime.datetime(ds.year, ds.month, ds.day, tzinfo=datetime.timezone.utc).timestamp())
        open_ep += open_sec(ds)
        i = int(np.searchsorted(t, open_ep, side="left"))
        if i < len(t) and int(t[i]) == open_ep:
            cb = cap_bars(ds)
            j_cap = i + cb
            if j_cap < len(t) and int(t[j_cap]) == open_ep + cb * 900:
                days.append((ds, i, j_cap))
        ds += datetime.timedelta(days=1)

    # 日区间序列(09:30开盘bar起, 到当日收盘) -> 14日ATR代理=过去14日区间中位数(无未来函数)
    day_ranges = []
    for idx, (ds, i, j_cap) in enumerate(days):
        i_next = days[idx + 1][1] if idx + 1 < len(days) else min(len(t), i + 4 * 96)
        day_ranges.append(float(h[i:i_next].max() - l[i:i_next].min()))
    atr14_list = []
    for k in range(len(days)):
        win = day_ranges[max(0, k - 14):k]
        atr14_list.append(float(np.median(win)) if len(win) >= 5 else None)

    events = []
    for idx, (ds, i, j_cap) in enumerate(days):
        hi, lo = h[i], l[i]
        rng = hi - lo
        a14 = atr14_list[idx]
        width_ratio = (rng / a14) if (a14 and a14 > 0) else float("nan")
        scan = range(i + 1, j_cap)  # 不含16:00强平bar
        # --- 变体A 尖峰触及 ---
        a_res = None
        for k in scan:
            up, dn = h[k] >= hi, l[k] <= lo
            if up and dn:
                a_res = ("ambiguous", k); break
            if up:
                entry, sl, side = hi, lo, +1; a_res = (side, k); break
            if dn:
                entry, sl, side = lo, hi, -1; a_res = (side, k); break
        # --- 变体B M15收线确认 ---
        b_res = None
        for k in scan:
            if c[k] > hi:
                entry, sl, side = c[k], lo, +1; b_res = (side, k); break
            if c[k] < lo:
                entry, sl, side = c[k], hi, -1; b_res = (side, k); break

        def settle(res):
            if res is None:
                return "none"
            side, k = res
            if side == "ambiguous":
                return (None, "amb", None)
            rng_r = hi - lo if side == +1 else lo - hi
            if rng_r <= 0:
                return (None, "amb", None)
            sl = lo if side == +1 else hi
            tp = sl + 2 * rng_r if side == +1 else sl - 2 * rng_r
            R = rng_r
            for m in range(k + 1, j_cap):
                if side == +1:
                    if l[m] <= sl: return (-1.0 - COST_R, "SL", m)
                    if h[m] >= tp: return (2.0 - COST_R, "TP", m)
                else:
                    if h[m] >= sl: return (-1.0 - COST_R, "SL", m)
                    if l[m] <= tp: return (2.0 - COST_R, "TP", m)
            cap_px = o[j_cap]
            pnl = (cap_px - entry) / R if side == +1 else (entry - cap_px) / R
            return (round(pnl, 4) - COST_R, "CAP", None)

        a_r, a_x, _ = settle(a_res) if a_res and a_res[0] != "none" else (None, "none", None)
        b_r, b_x, _ = settle(b_res) if b_res and b_res[0] != "none" else (None, "none", None)
        events.append(dict(day=str(ds), hi=round(float(hi), 2), lo=round(float(lo), 2),
                           width_ratio=round(float(width_ratio), 4),
                           A=(a_r if a_r is not None else None), A_exit=a_x,
                           B=(b_r if b_r is not None else None), B_exit=b_x))
    return events, days, len(days)

def agg(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return dict(n=0)
    a = np.array(vals)
    return dict(n=int(len(a)), mean_R=round(float(a.mean()), 4), win_rate=round(float((a > 0).mean()), 4),
                total_R=round(float(a.sum()), 2))

out = {}
for sym in ["US30", "NAS100"]:
    ev, day_list, n_days = run_one(sym)
    # 宽度分桶 (同分母=全部ORR日)
    buckets = {"w<0.10": [], "0.10<=w<=0.50": [], "w>0.50": []}
    for e in ev:
        w = e["width_ratio"]
        if not np.isfinite(w):
            continue
        key = "w<0.10" if w < 0.10 else ("w>0.50" if w > 0.50 else "0.10<=w<=0.50")
        for v in (e["A"], e["B"]):
            if v is not None:
                buckets[key].append(v)
    # 配对日(A与B都触发且非amb)
    paired_a, paired_b = [], []
    for e in ev:
        if e["A"] is not None and e["B"] is not None:
            paired_a.append(e["A"]); paired_b.append(e["B"])
    pa = agg(paired_a); pb = agg(paired_b)
    out[sym] = dict(
        data=dict(src="es_lab_cache %s_20000.npz (MT5 brokerFX M15)" % sym,
                  first_bar=str(datetime.datetime.fromtimestamp(np.load(f"data/es_lab_cache/{sym}_20000.npz", allow_pickle=True)['time'][0], tz=datetime.timezone.utc)),
                  last_bar=str(datetime.datetime.fromtimestamp(np.load(f"data/es_lab_cache/{sym}_20000.npz", allow_pickle=True)['time'][-1], tz=datetime.timezone.utc)),
                  n_days_with_open=int(sum(1 for e in ev))),
        ORR_days=int(len(ev)),
        A_touch=agg([e["A"] for e in ev]),
        B_close=agg([e["B"] for e in ev]),
        paired=dict(n_pairs=int(len(paired_a)), A=pa, B=pb,
                    paired_mean_diff_B_minus_A=(round(float(np.mean([b - a for a, b in zip(paired_a, paired_b)])), 4) if paired_a else None)),
        width_buckets={k: agg(v) for k, v in buckets.items()},
        exit_mix=dict(A={x: sum(1 for e in ev if e["A_exit"] == x) for x in ("TP", "SL", "CAP", "amb", "none")},
                      B={x: sum(1 for e in ev if e["B_exit"] == x) for x in ("TP", "SL", "CAP", "none")}),
    )
res_path = os.path.join(BASE, "research", "p5_orb_confirm_result_20261115.json")
json.dump(out, open(res_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("written:", res_path)
for sym, o in out.items():
    okA, okB = o["A_touch"]["n"] >= 30, o["B_close"]["n"] >= 30
    print(f"\n== {sym} == ORR日={o['ORR_days']}")
    print(f"  A尖峰触及: n={o['A_touch']['n']} {'FAIL<30' if not okA else 'PASS'} meanR={o['A_touch'].get('mean_R')} WR={o['A_touch'].get('win_rate')} exits={o['exit_mix']['A']}")
    print(f"  B收线确认: n={o['B_close']['n']} {'FAIL<30' if not okB else 'PASS'} meanR={o['B_close'].get('mean_R')} WR={o['B_close'].get('win_rate')} exits={o['exit_mix']['B']}")
    p = o["paired"]
    print(f"  配对n={p['n_pairs']} A:{p['A'].get('mean_R')} B:{p['B'].get('mean_R')} Δ(B-A)={p['paired_mean_diff_B_minus_A']}")
    print(f"  宽度桶: " + " | ".join(f"{k} n={v['n']} μR={v.get('mean_R')}" for k, v in o["width_buckets"].items()))
