# -*- coding: utf-8 -*-
# 只读审计: 挂单质量闸 — 当前挂单违规盘点 + 90天历史布林带limit单 fwd2胜率 违规vs合规
import json, math, os
import numpy as np
import MetaTrader5 as mt5

ROOT = "E:/GoldstrategyEngine"
MAGICS = [20260902, 20260903, 20260904]
STATE_FILES = {
    20260902: ROOT + "/data/pending_orders_state.json",
    20260903: ROOT + "/data/crypto_pending_state.json",
    20260904: ROOT + "/data/equity_pending_state.json",
}
T1_INTRADAY = ["BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD", "XRPUSD", "LTCUSD"]
RR_THR = {"trend": 2.0, "range": 1.5, "intra": 4.0}
SL_MAX = 2.5      # SL > 2.5*ATR 违规
DIST_MAX = 3.5    # 距现价 > 3.5*ATR 违规
DIST_MIN = 0.15   # 距现价 < 0.15*ATR 违规(贴脸, 形同市价单)


def atr_wilder(h, l, c, period=14):
    """与 multi_agent/trading/intraday_swing.py 的 atr() 完全一致 (Wilder)。"""
    n = len(c)
    out = np.zeros(n)
    if n < period + 1:
        return out
    tr = np.zeros(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    out[period - 1] = tr[1:period + 1].mean()
    for i in range(period, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def boll(c, period=20, k=2.0):
    mid = np.array([c[i - period:i].mean() if i >= period else np.nan for i in range(len(c))])
    sd = np.array([c[i - period:i].std() if i >= period else np.nan for i in range(len(c))])
    return mid + k * sd, mid, mid - k * sd


def fetch_h4(sym, count=2600):
    """拉2600根H4 (Wilder ATR)。MT5取不到则回落本地CSV。返回 (h,l,c,source) 或 None。"""
    try:
        mt5.symbol_select(sym, True)
        r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, count)
        if r is not None and len(r) > 100:
            r = np.array(r)
            return r["high"], r["low"], r["close"], "mt5"
    except Exception:
        pass
    p = os.path.join(ROOT, "data", sym + "_H4.csv")
    if os.path.exists(p):
        df = np.genfromtxt(p, delimiter=",", names=True)
        d = min(count, len(df["high"]))
        return (df["high"][-d:], df["low"][-d:], df["close"][-d:], "csv")
    return None


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def main():
    ok = mt5.initialize()
    print(f"[OK] MT5 init={ok}")
    acct = mt5.account_info()
    print(f"[OK] acct={acct.login} 净值=${acct.equity:.2f} (只读, 不下单)")

    orders = [o for o in (mt5.orders_get() or []) if int(getattr(o, "magic", 0)) in MAGICS]
    print(f"[OK] 挂单总数(magic{MAGICS[0]}/{MAGICS[1]}/{MAGICS[2]}) = {len(orders)}")

    # state 里的 layer/regime (用于判腿型; ticket 作键)
    layer_by_ticket = {}
    for mg in MAGICS:
        try:
            st = json.load(open(STATE_FILES[mg], encoding="utf-8"))
            for tk, p in (st.get("pending") or {}).items():
                layer_by_ticket[str(tk)] = p.get("layer", "trend" if p.get("regime") == "trending" else "range")
        except Exception:
            pass

    per_sym = {}
    audits = {}
    for o in orders:
        sym = o.symbol
        hlc = per_sym.get(sym)
        if hlc is None:
            hlc = fetch_h4(sym)
            per_sym[sym] = hlc
        a = atr_wilder(hlc[0], hlc[1], hlc[2])[-1] if hlc else 0.0
        if not a or a <= 0:
            print(f"[!] {sym} ATR取不到, 跳过")
            continue
        t = mt5.symbol_info_tick(sym)
        price = (t.bid + t.ask) / 2 if t and t.bid > 0 else 0
        e, sl, tp = float(o.price_open), float(getattr(o, "sl", 0) or 0), float(getattr(o, "tp", 0) or 0)
        layer = layer_by_ticket.get(str(o.ticket)) or ("range" if o.type in (2, 3) else "trend")
        dist = abs(e - price) / a
        slw = abs(e - sl) / a if sl > 0 else 99.0
        rr = abs(tp - e) / abs(e - sl) if sl > 0 and tp > 0 else 0.0
        thr = RR_THR.get(layer, 1.5)
        v = []
        if rr < thr * 0.999:
            v.append("RR不足")
        if slw > SL_MAX:
            v.append("SL过宽")
        if dist > DIST_MAX:
            v.append("距现价过远")
        elif dist < DIST_MIN:
            v.append("距现价过近")
        print(f"[{'!' if v else 'OK'}] {o.ticket} {sym} t={o.type} L={layer} "
              f"RR={rr:.2f}(<{thr}) SL={slw:.2f}x dist={dist:.2f}x {' '.join(v) or '合规'}")
        audits[o.ticket] = dict(sym=sym, layer=layer, rr=rr, slw=slw, dist=dist, v=v, a=a, price=price)

    n_total = len(orders)
    dist_cnt = {"RR不足": 0, "SL过宽": 0, "距现价过远": 0, "距现价过近": 0}
    n_viol = 0
    for tk, d in audits.items():
        if d["v"]:
            n_viol += 1
            for k in d["v"]:
                dist_cnt[k] += 1

    # ═══ 历史验证: 6 T1币 近90天布林带limit单 fwd2胜率 ═══
    ev_v, ev_c = [], []   # (win, sym)
    for sym in T1_INTRADAY:
        hlc = fetch_h4(sym)
        if not hlc or len(hlc[0]) < 600:
            print(f"[!] {sym} 历史H4不足600根, 跳过")
            continue
        h, l, c = hlc[0], hlc[1], hlc[2]
        a14 = atr_wilder(h, l, c)
        up, mid, dn = boll(c)
        start = max(21, len(c) - 540)  # 近90天(540根H4)
        for i in range(start, len(c) - 2):
            if a14[i] <= 0:
                continue
            atr_i, mi = a14[i], mid[i]
            touch_hi = i > 0 and up[i - 1] <= l[i - 1] and h[i] >= up[i]
            touch_dn = i > 0 and dn[i - 1] >= h[i - 1] and l[i] <= dn[i]
            if not (touch_hi or touch_dn):
                continue
            entry = up[i] if touch_hi else dn[i]
            side = 1 if touch_hi else -1
            win = 1 if (c[i + 2] - entry) * side > 0 else 0
            rr_sim = abs(mi - entry) / (2.0 * atr_i)     # 标准震荡腿: TP中轨, SL 2*ATR
            dist_sim = abs(c[i - 1] - entry) / atr_i      # 挂单时(触前一bar收盘)距带位
            viol = (rr_sim < RR_THR["range"]) or (dist_sim > DIST_MAX) or (dist_sim < DIST_MIN)
            (ev_v if viol else ev_c).append((win, sym))
        print(f"[OK] {sym} 历史事件累计 违规{len(ev_v)} 合规{len(ev_c)}")

    def wr(lst):
        return sum(w for w, _ in lst) / len(lst) if lst else float("nan")
    wrv, wrc = wr(ev_v), wr(ev_c)
    nv, nc = len(ev_v), len(ev_c)
    if nv and nc:
        p = (sum(w for w, _ in ev_v) + sum(w for w, _ in ev_c)) / (nv + nc)
        z = (wrv - wrc) / math.sqrt(p * (1 - p) * (1 / nv + 1 / nc))
        pval = 2 * (1 - norm_cdf(abs(z)))
    else:
        pval = 1.0
    print(f"[OK] 历史: 违规n={nv} WR={wrv:.3f} | 合规n={nc} WR={wrc:.3f} | 差={wrv-wrc:+.3f} p={pval:.3f}")

    out = {
        "当前挂单_总张数": n_total,
        "违规张数": n_viol,
        "各违规类分布": dist_cnt,
        "历史违规单胜率": round(wrv, 4) if nv else None,
        "历史合规单胜率": round(wrc, 4) if nc else None,
        "差值": round(wrv - wrc, 4) if nv and nc else None,
        "p值_正态近似": round(pval, 4),
        "历史样本": {"违规": nv, "合规": nc, "窗口": "近90天H4布林带触及", "品种": T1_INTRADAY},
        "结论": "建议质量闸(否决门):挂单前不达标就不挂, 失败开放",
    }
    jpath = ROOT + "/data/quality_gate_audit.json"
    json.dump(out, open(jpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    mpath = ROOT + "/data/quality_gate_audit.md"
    lines = ["# 挂单质量闸审计 (只读)", "",
             f"- 当前挂单 {n_total} 张, 违规 {n_viol} 张 ({n_viol/max(n_total,1)*100:.0f}%), 分布: {dist_cnt}",
             f"- 历史(6 T1币 近90天布林带触及 fwd2日): 违规单胜率 {wrv:.1%} vs 合规单 {wrc:.1%}, 差 {wrv-wrc:+.1%}, p={pval:.3f}",
             f"- 结论: {out['结论']}", ""]
    open(mpath, "w", encoding="utf-8").write("\n".join(lines))
    print(f"[OK] 已写 {jpath}")
    print(json.dumps(out, ensure_ascii=False))
    mt5.shutdown()


if __name__ == "__main__":
    main()
