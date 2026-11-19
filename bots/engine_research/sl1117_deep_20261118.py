# -*- coding: utf-8 -*-
"""sl1117_deep_20261118.py — 11-17止损单深度调研(李令'是不是进场点位/时机不对, 如何避免继续止损')
① 逐单归因: 11-17全部SL单 -> 进场时段/SL宽度(ATR)/进场点离结构距离/扫损后12h MFE-MAE-是否摸到TP
② 归类: 点位错/时机错/SL太窄/方向错/正常扫损
③ 防损规则同分母回测: B位移确认闸(信号棒body≥0.5×ATR15才进) 30日M30五验 vs base
纯研究: MT5只读copy_rates+历史, 不动引擎/REAL. 产物 data/sl1117_deep_20261118.json
"""
import os, json, sys, datetime as dt, time
import numpy as np
import MetaTrader5 as mt5

ROOT = "E:/GoldstrategyEngine"
BASE = os.path.join(ROOT, "data")
OUT = os.path.join(BASE, "sl1117_deep_20261118.json")
D0, D1 = dt.datetime(2026, 11, 17, 0, 0), dt.datetime.now()


def atr15_close(rates):
    """M15 ATR14 (rates: MT5 rates array)"""
    import numpy as np
    h, l, c = rates["high"], rates["low"], rates["close"]
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    a = np.convolve(tr, np.ones(14) / 14, "valid")
    return a, c


def main():
    assert mt5.initialize(), "mt5 init fail"
    # 11-17 全部平仓单
    deals = [d for d in mt5.history_deals_get(D0, D1) if d.entry == 1 and (d.magic == 20261104 or d.magic == 20261105)]
    sl_deals = [d for d in deals if d.reason == 4]
    print(f"11-17 平仓{len(deals)}笔, 其中SL触发{len(sl_deals)}笔")
    # 开仓单(取SL/TP)
    orders = {o.ticket: o for o in mt5.history_orders_get(D0 - dt.timedelta(days=2), D1)}
    out = dict(desc="11-17止损单深度调研", generated=D1.isoformat(), orders=[])
    for d in sorted(sl_deals, key=lambda x: x.time):
        sym, px = d.symbol, d.price
        t_in = dt.datetime.fromtimestamp(d.time)
        rates, tf_used = None, "M15"
        for tf in (mt5.TIMEFRAME_M15, mt5.TIMEFRAME_M30):
            for _ in range(3):
                rates = mt5.copy_rates_range(sym, tf, D0 - dt.timedelta(hours=6), D1)
                if rates is not None and len(rates) >= 200:
                    tf_used = "M30" if tf == mt5.TIMEFRAME_M30 else "M15"
                    break
                time.sleep(2)
            if rates is not None and len(rates) >= 200:
                break
        if rates is None or len(rates) < 200:
            print(f"{sym} M15/M30均无数据, 跳过定量"); continue
        a15, c15 = atr15_close(rates)
        # 定位进场bar
        ts_arr = rates["time"]
        i = int(np.searchsorted(ts_arr, d.time))
        a = a15[min(i, len(a15)-1)]
        # 进场点离近2日高/低
        d1r = mt5.copy_rates_range(sym, mt5.TIMEFRAME_D1, D0 - dt.timedelta(days=3), D1)
        hi2, lo2 = float(np.max(d1r["high"][:2])), float(np.min(d1r["low"][:2]))
        side_sell = d.type == 1 or d.type == 2  # 平sell仓的deal type=1(BUY) ... 简化: 用方向字段
        # 扫损后12h MFE/MAE
        post = rates[ts_arr >= d.time]
        if d.type in (0, 2):  # 该仓是多(被平) -> 扫损后看价格往下走没
            mfe = float(np.min(post["low"])) - px if len(post) else 0
            mae = float(np.max(post["high"])) - px if len(post) else 0
        else:
            mfe = px - float(np.max(post["high"])) if len(post) else 0
            mae = px - float(np.min(post["low"])) if len(post) else 0
        # TP 是否摸到(取开仓单TP)
        tp_hit, tp = False, None
        for o in orders.values():
            if o.symbol == sym and abs(o.price - px) < a * 0.5 and o.sl:
                tp = o.tp or None
                break
        if tp:
            if d.type in (0, 2): tp_hit = bool(np.min(post["low"]) <= tp)
            else: tp_hit = bool(np.max(post["high"]) >= tp)
        # 归类
        cls = []
        if mfe > 1.0 * a and not tp_hit: cls.append("扫损后顺向(方向对, 时机/点位被扫)")
        if mfe > 2.0 * a and tp_hit: cls.append("扫损后摸到TP(假扫损)")
        hour_bj = t_in.hour
        if 0 <= hour_bj < 8 and sym not in ("BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "US30"):
            cls.append("亚盘低波窗(易噪声扫损)")
        # SL 宽度(ATR): 开仓单sl距px
        slw = None
        for o in orders.values():
            if o.symbol == sym and abs(o.price - px) < a * 0.5 and o.sl:
                slw = abs(px - o.sl) / a
                break
        if slw is not None and slw < 0.8:
            cls.append(f"SL太窄({slw:.2f}×ATR15<0.8)")
        r = dict(sym=sym, side=("sell" if d.type not in (0,2) else "buy"), time=t_in.strftime("%m-%d %H:%M"), tf=tf_used,
                 close_px=px, pnl=d.profit, atr15=round(float(a), 5), sl_width_atr15=(round(slw, 2) if slw else None),
                 mfe_atr=round(mfe / a, 2), mae_atr=round(mae / a, 2), tp_hit=bool(tp_hit),
                 near_2d_hi=round(abs(px - hi2) / a, 2), near_2d_lo=round(abs(px - lo2) / a, 2),
                 classify="; ".join(cls) if cls else "正常扫损(方向错)")
        out["orders"].append(r)
        print(f"{r['sym']} {r['side']} @{r['time']} 盈{d.profit:+.2f} SL宽{r['sl_width_atr15']}ATR15 扫损后MFE{r['mfe_atr']}R MAE{r['mae_atr']}R TP摸到={r['tp_hit']} -> {r['classify']}")
    # ③ 防损规则B: 位移确认闸同分母回测(30日M30, BTC/ETH/SOL/GBP)
    sys.path.insert(0, os.path.join(ROOT, "research"))
    from rd_verify_batch_20261114 import prepare30, gen_signals, simulate, five_gates, verdict_of, COST
    rules_b = {}
    for s in ("BTCUSD", "ETHUSD", "SOLUSD", "GBPUSD"):
        try:
            P = prepare30(s)
        except Exception as ex:
            print(s, "prepare fail", ex); continue
        g = dict(adx_min=35.0, break_margin=0.6, min_body=0.3, h1_on=False, max_hold_h=18,
                 giveback=0.6, sl_mult=0.8, tp_mult=3.0)
        k, sgn, dist, tpd = gen_signals(P, g)
        if k.size == 0:
            print(s, "无信号"); continue
        base = simulate(P, g, k, sgn, dist=dist, tp_d=tpd, cost=COST)
        # 位移确认: 信号棒 body ≥ 0.5×ATR15(折算M30≈0.9×ATR30)
        body = np.abs(P["close"][k] - P["open"][k])
        atr_m30 = np.maximum(P["atr"][k], 1e-9)
        mask = body >= 0.45 * atr_m30  # 0.5×ATR15≈0.45×ATR30
        kb, sb, db, tb = k[mask], sgn[mask], dist[mask], tpd[mask]
        v = simulate(P, g, kb, sb, dist=db, tp_d=tb, cost=COST)
        Rb, Rv = base["R"], v["R"]
        rules_b[s] = dict(n_base=int(Rb.size), n_var=int(Rv.size),
                          net_base=round(float(Rb.sum()), 1), net_var=round(float(Rv.sum()), 1),
                          sl_rate_base=round(float((Rb == -1.045).mean()), 3) if Rb.size else None,
                          sl_rate_var=round(float((Rv == -1.045).mean()), 3) if Rv.size else None,
                          avg_base=round(float(Rb.mean()), 3), avg_var=round(float(Rv.mean()), 3))
        print(f"位移确认闸 {s}: n {Rb.size}->{Rv.size} 净R {rules_b[s]['net_base']}->{rules_b[s]['net_var']} 扫损率 {rules_b[s]['sl_rate_base']}->{rules_b[s]['sl_rate_var']}")
    out["rule_b_displacement_gate"] = rules_b
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n产物:", OUT)
    mt5.shutdown()


if __name__ == "__main__":
    main()
