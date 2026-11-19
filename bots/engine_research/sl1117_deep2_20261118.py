# -*- coding: utf-8 -*-
"""sl1117_deep2_20261118.py — 11-17止损单深度调研 v2(数据源=tf_cache npz优先, MT5 D1兜底)
李令'是不是进场点位/时机不对, 如何避免继续止损'. 纯研究只读.
"""
import os, json, sys, glob, datetime as dt, time
import numpy as np
import MetaTrader5 as mt5

ROOT = "E:/GoldstrategyEngine"
CACHE = os.path.join(ROOT, "data", "tf_cache")
OUT = os.path.join(ROOT, "data", "sl1117_deep_20261118.json")
D0 = dt.datetime(2026, 11, 17, 0, 0)


def cache_name(sym):
    n = sym.replace(".", "_")
    if not os.path.exists(os.path.join(CACHE, f"{n}_M30.npz")) and n.endswith("_NYS"):
        n2 = n[:-4] + "_NAS"
        if os.path.exists(os.path.join(CACHE, f"{n2}_M30.npz")) or os.path.exists(os.path.join(CACHE, f"{n2}_M15.npz")):
            n = n2
    return n


def load_series(sym):
    """返回 (t, h, l, c, atr14, tf_used) 或 None. npz M15 -> M30 -> D1, MT5 D1 兜底."""
    cn = cache_name(sym)
    for tf in ("M15", "M30", "H4", "D1"):
        f = os.path.join(CACHE, f"{cn}_{tf}.npz")
        if os.path.exists(f):
            m = np.load(f)
            t, h, l, c, a = m["t"], m["h"], m["l"], m["c"], m.get("atr", None)
            if t is None or len(t) < 50:
                continue
            if a is None:
                pc = np.concatenate(([c[0]], c[:-1]))
                tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
                a = np.convolve(tr, np.ones(14) / 14, "valid")
                a = np.concatenate([a, np.full(5, a[-1])])
            return t, h, l, c, a, tf
    # MT5 D1 兜底
    if mt5.initialize() or True:
        for tf, name in ((mt5.TIMEFRAME_D1, "D1"), (mt5.TIMEFRAME_H4, "H4")):
            r = mt5.copy_rates_from_pos(sym, tf, 0, 30)
            if r is not None and len(r) >= 30:
                t, h, l, c = r["time"], r["high"], r["low"], r["close"]
                pc = np.concatenate(([c[0]], c[:-1]))
                tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
                a = np.convolve(tr, np.ones(14) / 14, "valid")
                return t, h, l, c, a, name + "(mt5)"
    return None


def atr_at(t, a, i):
    return float(a[min(max(i - 1, 0), len(a) - 1)])


def main():
    mt5.initialize()
    deals = [d for d in mt5.history_deals_get(D0, dt.datetime.now())
             if d.entry == 1 and d.reason == 4 and (d.magic == 20261104 or d.magic == 20261105)]
    orders = {o.ticket: o for o in mt5.history_orders_get(D0 - dt.timedelta(days=3), dt.datetime.now())}
    out = dict(desc="11-17 SL单深度调研v2(tf_cache优先)", generated=dt.datetime.now().isoformat(), orders=[])
    print(f"11-17 SL触发 {len(deals)} 笔")
    for d in sorted(deals, key=lambda x: x.time):
        sym, px = d.symbol, d.price
        t_in = dt.datetime.fromtimestamp(d.time)
        s = load_series(sym)
        is_buy_close = d.type in (0, 2)  # 该仓方向=多
        row = dict(sym=sym, side=("sell" if not is_buy_close else "buy"), time=t_in.strftime("%m-%d %H:%M"),
                   hour_bj=t_in.hour, pnl=d.profit, tf=None,
                   sl_width_atr=None, mfe_atr=None, mae_atr=None, tp_hit=None,
                   near_struct_atr=None, classify=[])
        if s:
            t, h, l, c, a, tf_used = s
            row["tf"] = tf_used
            ti = t.astype("datetime64[s]").astype("int64") if t.dtype.kind == "M" else np.asarray(t, dtype="int64")
            i = int(np.searchsorted(ti, int(d.time)))
            A = atr_at(t, a, i)
            row["atr"] = round(A, 6)
            # SL 宽度: 找该平仓单对应的开仓单
            for o in orders.values():
                if o.symbol == sym and o.sl and abs(o.price_open - px) < A * 0.6:
                    row["sl_width_atr"] = round(abs(px - o.sl) / A, 2)
                    tp = o.tp
                    break
            else:
                tp = None
            # 扫损后 12h (按 tf 粒度截断)
            span_h = {"M15": 12, "M30": 12, "H4": 12, "D1": 48, "D1(mt5)": 48, "H4(mt5)": 24}.get(tf_used, 12)
            step = {"M15": 900, "M30": 1800, "H4": 14400, "D1": 86400, "D1(mt5)": 86400, "H4(mt5)": 14400}[tf_used.split("(")[0] if "(" in tf_used else tf_used]
            n12 = int(span_h * 3600 // step)
            post_h, post_l = h[i:i + n12 + 1], l[i:i + n12 + 1]
            if len(post_h) > 1:
                if is_buy_close:  # 多仓被扫: 看后续价格
                    mfe, mae = px - float(np.min(post_l)), float(np.max(post_h)) - px
                    tp_hit = (tp is not None and float(np.min(post_l)) <= tp)
                else:
                    mfe, mae = float(np.max(post_h)) - px, px - float(np.min(post_l))
                    tp_hit = (tp is not None and float(np.max(post_h)) >= tp)
                row.update(mfe_atr=round(mfe / A, 2), mae_atr=round(mae / A, 2), tp_hit=bool(tp_hit))
            # 进场点离近2日高低(结构距离)
            r1 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_D1, D0 - dt.timedelta(days=3), D0)
            if r1 is not None and len(r1) >= 2:
                hi2, lo2 = float(np.max(r1["high"])), float(np.min(r1["low"]))
                row["near_struct_atr"] = dict(hi=round(abs(px - hi2) / A, 2), lo=round(abs(px - lo2) / A, 2))
        # 归类
        cls = []
        if row["sl_width_atr"] is not None and row["sl_width_atr"] < 0.8:
            cls.append(f"SL太窄({row['sl_width_atr']}×ATR)")
        if row.get("mfe_atr") is not None:
            if row["mfe_atr"] >= 1.5 and not row.get("tp_hit"):
                cls.append("扫损后顺向≥1.5ATR(方向对, 被扫=时机/点位错)")
            if row.get("tp_hit"):
                cls.append("扫损后摸到TP(纯假扫损)")
            if row["mae_atr"] >= 2 and (row["mfe_atr"] or 0) < 0.5:
                cls.append("扫损后持续逆向≥2ATR(方向错, 不该进)")
        fam = ("JPY" if any(x in sym for x in ("JPY",)) else ("cross" if sym in ("EURGBP",) else (sym.split(".")[0] if "." in sym else "other")))
        row["family"] = fam
        row["classify"] = cls
        out["orders"].append(row)
        print(f"{row['side']:4s} {sym:10s} @{row['time']}(BJT{row['hour_bj']:02d}时) 盈{d.profit:+7.2f} tf={row['tf']} SL宽{row['sl_width_atr']} MFE{row['mfe_atr']} MAE{row['mae_atr']} TP摸到={row['tp_hit']} 结构{row.get('near_struct_atr')} -> {'; '.join(cls) or '未标记'}")
    # ② 同向族聚类: JPY 族
    jpy = [r for r in out["orders"] if r["family"] == "JPY"]
    if jpy:
        t0, t1 = min(r["time"] for r in jpy), max(r["time"] for r in jpy)
        out["jpy_batch"] = dict(n=len(jpy), span=f"{t0}~{t1}", all_sell=all(r["side"] == "sell" for r in jpy),
                                 note="同小时带同方向批量=相关性集中风险")
        print("JPY族:", out["jpy_batch"])
    # ③ 防损规则B: 位移确认闸(30日M30同分母)
    sys.path.insert(0, os.path.join(ROOT, "research"))
    from rd_verify_batch_20261114 import prepare30, gen_signals, simulate, COST
    params = json.load(open(os.path.join(ROOT, "data", "practice_params_all_symbols.json"), encoding="utf-8"))
    rb = {}
    for s in ("BTCUSD", "ETHUSD", "SOLUSD", "GBPUSD"):
        P = prepare30(s)
        p = params.get(s, {})
        g = dict(adx_min=float(p.get("adx_min", 35.0)), break_margin=0.6, min_body=0.3, h1_on=False,
                 max_hold_h=18, giveback=0.6, sl_mult=0.8, tp_mult=3.0)
        k, sgn, dist, tpd = gen_signals(P, g)
        if k.size == 0:
            print(s, "无信号"); continue
        c30 = P["c"]
        op = np.concatenate([c30[:1], c30[:-1]])
        body = np.abs(c30[k] - op[k])
        atr_m = np.maximum(P["atr"][k], 1e-9)
        mask = body >= 0.45 * atr_m
        kb, sb, db, tb = k[mask], sgn[mask], dist[mask], tpd[mask]
        base = simulate(P, g, k, sgn, dist=dist, tp_d=tpd, cost=COST)
        var = simulate(P, g, kb, sb, dist=db, tp_d=tb, cost=COST)
        rb[s] = dict(n=int(base["R"].size), n_var=int(var["R"].size),
                     net_base=round(float(base["R"].sum()), 1), net_var=round(float(var["R"].sum()), 1),
                     sl_rate_base=round(float((base["R"] <= -0.9).mean()), 3),
                     sl_rate_var=round(float((var["R"] <= -0.9).mean()), 3) if var["R"].size else None,
                     win_base=round(float((base["R"] > 0).mean()), 3), win_var=round(float((var["R"] > 0).mean()), 3) if var["R"].size else None)
        print(f"位移闸 {s}: n {rb[s]['n']}->{rb[s]['n_var']} 净R {rb[s]['net_base']}->{rb[s]['net_var']} 扫损率 {rb[s]['sl_rate_base']}->{rb[s]['sl_rate_var']}")
    out["rule_b_displacement"] = rb
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("产物:", OUT)
    mt5.shutdown()


if __name__ == "__main__":
    main()
