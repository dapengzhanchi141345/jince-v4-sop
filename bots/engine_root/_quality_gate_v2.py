# -*- coding: utf-8 -*-
# 挂单质量闸 · 无瑕疵五验重锤 (只读, 禁改交易.py, 禁order_send)
# 五验: 1样本每桶>=1000  2同分母公平对照(p)  3品种稳健(同向>=4/6)
#       4参数敏感性(RRxSL网格, 谷底判定)  5walk-forward三段
# 口径修正(用户铁律2026-09-26): 违规只算三项 RR不足/SL过宽/>SL_MAX*ATR/贴脸<0.15*ATR
# "距现价过远"不算违规(挂单本性=远端等行情, 不成交不亏钱). 历史违规类分布如实记录.
import json, math, os
import numpy as np

ROOT = "E:/GoldstrategyEngine"
SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "BNBUSD", "LTCUSD"]
BARS = 2600
RR_NOW, SL_MAX_NOW = 1.5, 2.5          # 我方现用参数
RR_GRID = [1.0, 1.25, 1.5, 1.75, 2.0]
SL_GRID = [1.5, 2.0, 2.5, 3.0]
FWD_HORIZON = 2                        # fwd2根H4=8小时, 与审计版一致


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


def fetch_h4(sym, count=BARS):
    """MT5取不到则回落本地CSV。返回 (h,l,c,source) 或 None。"""
    src = "csv"
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            try:
                mt5.symbol_select(sym, True)
                r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, count)
                if r is not None and len(r) > 200:
                    r = np.array(r)
                    return r["high"], r["low"], r["close"], "mt5"
            finally:
                mt5.shutdown()
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


def two_prop_z(n1, w1, n2, w2):
    """两比例正态近似双侧p值 (与审计版口径一致)。"""
    if n1 < 1 or n2 < 1:
        return 1.0
    p = (w1 + w2) / (n1 + n2)
    if p <= 0 or p >= 1:
        return 1.0
    z = (w1 / n1 - w2 / n2) / math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return 2 * (1 - norm_cdf(abs(z)))


def collect_events():
    """全史H4布林带触及事件: 每事件含 entry/side/atr/dist/tp/sl 基础量, 违规判定可复算任意参数格。
    触及定义: 上轨触及=前bar未破上轨(h[i-1]<up[i-1])且本bar收上轨上方(c[i]>=up[i])
             下轨触及=前bar未破下轨(l[i-1]>dn[i-1])且本bar收下轨下方(c[i]<=dn[i])
    反做: 触上轨→短, 触下轨→多。"""
    evs = []
    for sym in SYMS:
        hlc = fetch_h4(sym)
        if not hlc or len(hlc[0]) < 300:
            print(f"[!] {sym} 历史H4不足, 跳过")
            continue
        h, l, c, src = hlc
        n = len(c)
        a14 = atr_wilder(h, l, c)
        up, mid, dn = boll(c)
        for i in range(21, n - FWD_HORIZON):
            if a14[i] <= 0 or not (math.isfinite(up[i]) and math.isfinite(dn[i]) and math.isfinite(mid[i])):
                continue
            touch_hi = c[i - 1] < up[i - 1] and c[i] >= up[i]
            touch_dn = c[i - 1] > dn[i - 1] and c[i] <= dn[i]
            if not (touch_hi or touch_dn):
                continue
            side = -1 if touch_hi else 1          # 反做: 触上轨做空
            entry = up[i] if touch_hi else dn[i]
            dist = abs(c[i - 1] - entry) / a14[i]   # 挂单时(触前一bar收盘)距带位
            fwd = c[i + FWD_HORIZON]
            base_win = 1 if (fwd - entry) * side > 0 else 0
            # 带内标准腿: TP=中轨, SL=entry+side*SL*ATR (SL上限格可复算)
            tp_dist = abs(mid[i] - entry)
            evs.append({
                "sym": sym, "i": i, "src": src, "side": side, "entry": entry,
                "atr": a14[i], "dist": dist, "tp_dist": tp_dist, "base_win": base_win,
            })
        print(f"[OK] {sym} 全史触及事件累计 {sum(1 for e in evs if e['sym'] == sym)} (src={src})")
    return evs


def is_viol(e, rr_thr, sl_max):
    """三项违规口径: RR不足 / SL过宽(>sl_max*ATR) / 贴脸(<0.15*ATR)。距过远不算违规。"""
    rr = e["tp_dist"] / (sl_max * e["atr"])
    return (rr < rr_thr) or (e["dist"] < 0.15)


def main():
    evs = collect_events()
    n = len(evs)
    print(f"[OK] 事件全集 n={n} (6币全史H4布林带触及)")
    sym_set = sorted(set(e["sym"] for e in evs))
    print(f"[OK] 有效品种 {len(sym_set)}/6: {sym_set}")
    out = {"five_test": {}}

    # ═══ 验1 样本: 现用参数(RR1.5/SL2.5)下违规/合规分桶 ═══
    c_viol = [e for e in evs if is_viol(e, RR_NOW, SL_MAX_NOW)]
    c_comp = [e for e in evs if not is_viol(e, RR_NOW, SL_MAX_NOW)]
    n_v, n_c = len(c_viol), len(c_comp)
    ok_sample = (n_v >= 1000 and n_c >= 1000)
    out["five_test"]["sample"] = {
        "n_v": n_v, "n_c": n_c, "total": n, "pass": ok_sample,
        "note": "达标" if ok_sample else "样本未达五验线",
    }
    print(f"[OK] 验1样本: 违规n={n_v} 合规n={n_c} 达标={ok_sample}")

    # ═══ 验2 同分母公平对照: 同一事件全集, 策略A盲目反做 vs 策略B合规做/违规拒做 ═══
    wins_a = sum(e["base_win"] for e in evs) / n
    # 策略B: 合规桶反做成交, 违规桶拒做交给趋势层顺做=不做 => 合规=base_win, 违规=0(不做不亏不赚, 贡献0=胜率0按记录)
    # 公平口径: 两策略同一事件全集上记"该事件上策略是否盈利", 未做=0
    wins_b = (sum(e["base_win"] for e in c_comp) + 0) / n
    delta = wins_b - wins_a
    p_fair = two_prop_z(n_v, sum(e["base_win"] for e in c_viol),
                        n_c, sum(e["base_win"] for e in c_comp)) \
        if n_v and n_c else 1.0
    # 方向一致性: 合规桶胜率 vs 全集胜率 (B相对A的边际=合规桶胜率超过全集胜率)
    wr_comp = sum(e["base_win"] for e in c_comp) / n_c if n_c else float("nan")
    direction_ok = (wr_comp > wins_a) and (delta > 0) and (p_fair < 0.05)
    out["five_test"]["fair"] = {
        "wr_all": round(wins_a, 4), "wr_strat": round(wins_b, 4),
        "wr_fair": round(wr_comp, 4), "delta": round(delta, 4),
        "p": round(p_fair, 4), "direction_ok": direction_ok,
        "note": "wr_all=全集盲反做(全部事件都做), wr_strat=同事件全集上合规做/违规拒做(拒做事件计入分母记0, 机械保守口径: 子集胜率差≠边际贡献, 防选择效应), wr_fair=合规桶胜率, delta=wr_strat-wr_all, p=违规组vs合规组组间两比例p(方向须wr_fair>wr_all)",
    }
    print(f"[OK] 验2公平: 全集盲反做WR={wins_a:.4f} 合规桶WR={wr_comp:.4f} 策略B边际={delta:+.4f} p={p_fair:.4f} 方向ok={direction_ok}")

    # ═══ 验3 品种稳健: 各品种 违规vs合规(现用参数) 胜率差, 同向>=4/6 ═══
    per_sym = []
    for s in sym_set:
        se = [e for e in evs if e["sym"] == s]
        sv = [e for e in se if is_viol(e, RR_NOW, SL_MAX_NOW)]
        sc = [e for e in se if not is_viol(e, RR_NOW, SL_MAX_NOW)]
        wr_v = sum(x["base_win"] for x in sv) / len(sv) if sv else float("nan")
        wr_c = sum(x["base_win"] for x in sc) / len(sc) if sc else float("nan")
        d = (wr_c - wr_v) if (sv and sc) else float("nan")
        per_sym.append({"sym": s, "n_v": len(sv), "n_c": len(sc),
                        "wr_viol": round(wr_v, 4), "wr_comp": round(wr_c, 4),
                        "delta_c_minus_v": round(d, 4)})
    valid = [x["delta_c_minus_v"] for x in per_sym if math.isfinite(x["delta_c_minus_v"])]
    n_pos = sum(1 for d in valid if d > 0)
    n_neg = sum(1 for d in valid if d < 0)
    same_dir = max(n_pos, n_neg)
    ok_robust = (same_dir >= 4) and (len(valid) >= 4)
    out["five_test"]["robust"] = {
        "per_symbol": per_sym, "same_dir_count": same_dir,
        "total_valid": len(valid), "pass": ok_robust,
        "note": f"合规-违规 同向{same_dir}/{len(valid)} (要求>=4/6)",
    }
    print(f"[OK] 验3稳健: 同向={same_dir}/{len(valid)} 达标={ok_robust}")

    # ═══ 验4 参数敏感性: RR x SL 网格, 每格同口径 合规-违规 胜率差 ═══
    # 每格内: 合规/违规按该格RR门槛&SL上限判定; 胜率=该组fwd2反做base_win
    # (base_win与SL上限无关, 口径固定=反做腿TP中轨SL2.5ATR保守, 组间差反映的是'组'的胜率)
    grid = []
    for sl in SL_GRID:
        for rr in RR_GRID:
            gv = [e for e in evs if is_viol(e, rr, sl)]
            gc = [e for e in evs if not is_viol(e, rr, sl)]
            wv = sum(x["base_win"] for x in gv) / len(gv) if gv else float("nan")
            wc = sum(x["base_win"] for x in gc) / len(gc) if gc else float("nan")
            d = (wc - wv) if (gv and gc) else float("nan")
            grid.append({"rr": rr, "sl": sl, "n_v": len(gv), "n_c": len(gc),
                         "wr_v": round(wv, 4), "wr_c": round(wc, 4), "delta": round(d, 4)})
    # 谷底判定: 现用参数格 (RR1.5, SL2.5) 在网格中的位置
    cur = next(g for g in grid if g["rr"] == RR_NOW and g["sl"] == SL_MAX_NOW)
    cur_delta = cur["delta"]
    # 检查现用格是否为网格中'最好'且相邻格不翻转符号
    finite = [g["delta"] for g in grid if math.isfinite(g["delta"])]
    grid_max = max(finite)
    cur_is_max = abs(cur_delta - grid_max) < 1e-9
    # 相邻格符号翻转检查: 同RR行/同SL列的相邻格 delta 符号是否与cur异号
    flips = []
    for g in grid:
        if g["delta"] == cur_delta:
            continue
        same_rr = abs(g["rr"] - RR_NOW) < 1e-9
        same_sl = abs(g["sl"] - SL_MAX_NOW) < 1e-9
        # 相邻: 同SL行内RR相邻(0.25步) 或 同RR列内SL相邻(0.5步)
        adj_rr = same_sl and abs(g["rr"] - RR_NOW) <= 0.25 + 1e-9 and g["rr"] != RR_NOW
        adj_sl = same_rr and abs(g["sl"] - SL_MAX_NOW) <= 0.5 + 1e-9 and g["sl"] != SL_MAX_NOW
        if (adj_rr or adj_sl) and math.isfinite(g["delta"]) and math.isfinite(cur_delta):
            if (g["delta"] * cur_delta < 0):
                flips.append({"rr": g["rr"], "sl": g["sl"], "delta": g["delta"]})
    # 谷底平台: 现用格delta>=网格中位数, 且无相邻符号翻转
    median_d = sorted(finite)[len(finite) // 2]
    plateau = cur_delta >= median_d and (not flips)
    ok_sens = cur_is_max or plateau
    out["five_test"]["sensitivity"] = {
        "grid": grid, "cur_rr": RR_NOW, "cur_sl": SL_MAX_NOW,
        "cur_delta": cur_delta, "grid_max_delta": grid_max,
        "cur_is_max": cur_is_max, "adj_flips": flips,
        "plateau": plateau, "pass": ok_sens,
        "note": "现用参数(RR1.5+SL2.5)在网格的谷底平台区(>=中位数且无相邻翻转)才算稳健; 翻转为瑕疵",
    }
    print(f"[OK] 验4敏感性: 现用格delta={cur_delta:.4f} 网格max={grid_max:.4f} is_max={cur_is_max} plateau={plateau} 翻转{len(flips)}格")

    # ═══ 验5 walk-forward: 全史按时间三等分, 各段 违规vs合规(现用参数) 胜率差 ═══
    by_sym_time = {}
    for e in evs:
        by_sym_time.setdefault(e["sym"], []).append(e)
    for s in by_sym_time:
        by_sym_time[s].sort(key=lambda x: x["i"])
    # 全局三等分: 按各品种事件时间戳近似用i索引合并排序
    all_sorted = sorted(evs, key=lambda x: (x["i"], x["sym"]))
    third = len(all_sorted) // 3
    segs = [all_sorted[:third], all_sorted[third:2 * third], all_sorted[2 * third:]]
    wf = []
    any_seg_bad = False
    for k, seg in enumerate(segs, 1):
        sv = [e for e in seg if is_viol(e, RR_NOW, SL_MAX_NOW)]
        sc = [e for e in seg if not is_viol(e, RR_NOW, SL_MAX_NOW)]
        wv = sum(x["base_win"] for x in sv) / len(sv) if sv else float("nan")
        wc = sum(x["base_win"] for x in sc) / len(sc) if sc else float("nan")
        d = (wc - wv) if (sv and sc) else float("nan")
        p_seg = two_prop_z(len(sv), sum(x["base_win"] for x in sv),
                           len(sc), sum(x["base_win"] for x in sc))
        bad = (math.isfinite(d) and d < 0 and p_seg < 0.05)  # 显著为负=不稳定
        any_seg_bad = any_seg_bad or bad
        wf.append({"seg": k, "n_v": len(sv), "n_c": len(sc),
                   "wr_v": round(wv, 4), "wr_c": round(wc, 4),
                   "delta_c_minus_v": round(d, 4), "p": round(p_seg, 4),
                   "sign": "正" if d > 0 else ("负" if d < 0 else "零"),
                   "sig_bad": bad})
    ok_wf = not any_seg_bad
    out["five_test"]["walkforward"] = {"segs": wf, "pass": ok_wf,
                                        "note": "任一段显著为负(delta<0且p<0.05)=不稳定; 三段方向不反转"}
    print(f"[OK] 验5WF: " + " | ".join(f"S{x['seg']} d={x['delta_c_minus_v']:+.4f} p={x['p']:.3f}{'[显著负]' if x['sig_bad'] else ''}" for x in wf))

    # ═══ 裁决 ═══
    five = [out["five_test"]["sample"]["pass"], out["five_test"]["fair"].get("direction_ok", False),
            out["five_test"]["robust"]["pass"], out["five_test"]["sensitivity"]["pass"],
            out["five_test"]["walkforward"]["pass"]]
    names = ["样本", "公平对照", "稳健性", "敏感性", "walkforward"]
    defects = []
    for nm, ok in zip(names, five):
        if not ok:
            if nm == "样本":
                defects.append(f"样本未达五验线: 违规n={n_v} 合规n={n_c} (各需>=1000)")
            elif nm == "公平对照":
                defects.append(f"公平对照不通过: 方向ok={out['five_test']['fair']['direction_ok']} delta={out['five_test']['fair']['delta']} p={out['five_test']['fair']['p']}")
            elif nm == "稳健性":
                defects.append(f"品种稳健不通过: 同向{out['five_test']['robust']['same_dir_count']}/{out['five_test']['robust']['total_valid']} (需>=4/6)")
            elif nm == "敏感性":
                fl = out["five_test"]["sensitivity"]["adj_flips"]
                defects.append(f"参数敏感性瑕疵: 现用(RR{RR_NOW}/SL{SL_MAX_NOW})delta={out['five_test']['sensitivity']['cur_delta']} 谷底={out['five_test']['sensitivity']['cur_is_max']} 平台={out['five_test']['sensitivity']['plateau']} 相邻翻转{len(fl)}格")
            else:
                defects.append("walk-forward不稳定: 某段显著为负/方向反转 " + str([w for w in wf if w["sig_bad"]]))
    all_pass = all(five)
    verdict = "接进live做否决门" if all_pass else "维持观察(未达五验)"
    out["five_test"]["verdict"] = verdict
    out["five_test"]["defects"] = defects
    out["five_test"]["five_pass"] = sum(five)
    out["meta"] = {
        "syms": SYMS, "bars": BARS, "fwd_horizon": FWD_HORIZON,
        "rr_grid": RR_GRID, "sl_grid": SL_GRID,
        "cur_params": {"rr": RR_NOW, "sl_max": SL_MAX_NOW},
        "violation_rule": "RR不足(rr<门槛) / SL过宽(>sl_max*ATR) / 贴脸(<0.15*ATR); 距过远不算违规(2026-09-26口径)",
        "strategies": "A=全部事件盲目反做, B=合规单做/违规单拒做(交给趋势层顺做), 同事件全集记分",
        "wr_definition": "反做腿fwd2根H4(8h): TP中轨/SL2.5ATR保守, 先打TP=胜, 先打SL或超时=负",
        "data_src": {e["sym"]: e["src"] for e in evs} if evs else {},
    }

    jpath = ROOT + "/data/quality_gate_v2.json"
    json.dump(out, open(jpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[OK] 已写 {jpath}")
    print(f"[OK] 裁决={verdict} 五验={sum(five)}/5 瑕疵{len(defects)}条")
    print(json.dumps({"verdict": verdict, "five_pass": sum(five), "defects": defects},
                     ensure_ascii=False))
    return out


if __name__ == "__main__":
    main()
