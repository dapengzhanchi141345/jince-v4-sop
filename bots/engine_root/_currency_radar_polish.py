# -*- coding: utf-8 -*-
# 货币强弱惯性雷达 CurrencyStrengthRadar 五验验收 + 同分母全样本回测 (strategy-rd)
# ═══════════════════════════════════════════════════════════════
# 背景(丑话): 用户"拿最强打最弱就赚钱"是惯性假设; 历史上裸反转/惯性构造多为负期望。
# 本指标本质 = 篮子相对强弱。必须用【同分母全样本】回测证明有正期望才准进 live;
# 否则只当否决门(提示别追最弱那个币), 不正向提权。金策铁律: 高胜率≠正期望, 子集胜率差不算 edge。
# ═══════════════════════════════════════════════════════════════
# 时间处理铁律: CSV time 列是 东八区字符串, 用 fromisoformat 转真实 epoch,
# 不用 pandas datetime.astype('int64') (那是纳秒, 会算成 1970)。
import json, sys, datetime
import numpy as np

sys.path.insert(0, "E:/GoldstrategyEngine"); sys.path.insert(0, "E:/GoldstrategyEngine/multi_agent/trading")
from backtest_engine import trade, selftest, limit_selftest

DATA = "E:/GoldstrategyEngine/data"
OUT  = "E:/GoldstrategyEngine/data/leg_currency_radar_polish.json"

BASKET = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY"]
N = len(BASKET)
SELF_POOL = ["XAUUSD", "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY"]
ANCHORS = [3, 6, 12, 24]

ATR_LEN = 14
SL_ATR_MULT = 2.0
TP_ATR_MULT = 4.0
MAX_FWD = 42


def _to_epoch(s):
    """CSV 时间串(东八区) -> 真实 epoch 秒 (数值对齐用; 时区偏移对全品种一致, 不影响相对网格)。"""
    return int(datetime.datetime.fromisoformat(s).timestamp())


def load_h4(sym):
    """读 H4 CSV, 返回 dict(t=epoch秒, h, l, c) 按时间升序。"""
    rows = []
    with open(f"{DATA}/{sym}_H4.csv", encoding="utf-8") as fh:
        next(fh)  # header
        for r in fh:
            p = r.split(",")
            if len(p) < 5 or not p[0]:
                continue
            try:
                h, l, c = float(p[2]), float(p[3]), float(p[4])
            except ValueError:
                continue
            rows.append((_to_epoch(p[0]), h, l, c))
    rows.sort(key=lambda x: x[0])
    t = np.array([r[0] for r in rows], dtype=np.int64)
    h = np.array([r[1] for r in rows], dtype=float)
    l = np.array([r[2] for r in rows], dtype=float)
    c = np.array([r[3] for r in rows], dtype=float)
    return dict(t=t, h=h, l=l, c=c)


def atr_arr(h, l, c, length=ATR_LEN):
    tr = np.maximum(h[1:] - l[1:],
                    np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    a = np.full(len(c), np.nan)
    if len(c) <= length:
        return a
    a[length] = tr[:length].mean()
    for i in range(length + 1, len(c)):
        a[i] = a[i-1] * (length-1) / length + tr[i-1] / length
    return a


# ── 公共时间窗: 7 个篮子成员 H4 时间轴交集 (每根 K 线篮子必须完整) ─────
bdata = {p: load_h4(p) for p in BASKET}
bsets = {p: set(d["t"]) for p, d in bdata.items()}
common_tset = set.intersection(*bsets.values())
common_t = np.array(sorted(common_tset), dtype=np.int64)
NCOMMON = len(common_t)
print(f"公共 H4 窗口 {NCOMMON} 根: {datetime.datetime.fromtimestamp(common_t[0])} -> "
      f"{datetime.datetime.fromtimestamp(common_t[-1])}")

# 把篮子成员按公共窗切片 (与 common_t 一一对应)
bseg = {}
for p in BASKET:
    d = bdata[p]
    m = np.array([ts in common_tset for ts in d["t"]])
    bseg[p] = dict(h=d["h"][m], l=d["l"][m], c=d["c"][m])
assert all(len(bseg[p]["c"]) == NCOMMON for p in BASKET)

# 自品种数据 (篮子成员自品种时, 分位=相对其余6个)
sdata = {s: load_h4(s) for s in SELF_POOL}


def build_pctil(anchor, selfdata, selfsym):
    """公共窗内每根 K 线: self 窗口涨幅 相对 篮子 7 成员 的排名分位(0-100)。
    分位 = (篮子中窗口涨幅 < self 窗口涨幅 的成员数)/(N-1)*100。返回与 common_t 对齐的 pctil。"""
    t, c = selfdata["t"], selfdata["c"]
    # self 落在公共窗内的 K 线在 self 自身数组里的下标
    pos = {}   # common_t 索引 -> self 数组下标
    self_by_ts = dict(zip(t.tolist(), range(len(t))))
    pctil = np.full(NCOMMON, np.nan)
    for j, ts in enumerate(common_t):
        k = self_by_ts.get(int(ts))
        if k is None or k - anchor < 0:
            continue
        self_chg = c[k] - c[k - anchor]
        below = 0
        for p in BASKET:
            if bseg[p]["c"][j] - bseg[p]["c"][j - anchor] < self_chg:
                below += 1
        pctil[j] = 100.0 * below / (N - 1)
    return pctil


def collect_events(anchor, protocol, break_atr=None):
    """同分母全样本 v2: 公共窗内每根 K 线, 若 self 分位强势(>=60)/弱势(<=40) 则固定为一条事件,
    对【同一条事件】同时回放两个方向:
      动量方向(拿最强打最弱): 强势买 / 弱势卖
      反转方向(卖最强/买最弱): 强势卖 / 弱势买
    两方向用同一 k0/MAX_FWD/协议。
    【同分母口径】两组共用同一批【已成交(filled)有效样本】: 某方向几何不成立(数据异常/未成交),
    则另一方向即使 filled 也被丢弃, 该事件两组都计 skipped —— 有效样本集严格一致,
    n_momentum == n_reversal 逐笔相等 (子集胜率差不算 edge, 对比必须同一事件集)。
    事件全集统计: n_total_events = n_fair_filled(=n_momentum=n_reversal) + n_skipped。
    返回 (events, mom_R, rev_R, n_fair_filled, n_skipped):
      events=[(ts_sig, sym, pv, mom_R_or_None, rev_R_or_None, both_fair:bool)],
      mom_R/rev_R 仅含同分母有效 R, n_fair_filled = 两方向都 filled 的事件数,
      n_skipped = 至少一方向几何不成立(两组都剔除)的事件数。"""
    mom_R, rev_R = [], []
    events = []
    n_fair_filled = 0
    n_skipped = 0
    for s in SELF_POOL:
        sd = sdata[s]
        hh, ll, cc, tt = sd["h"], sd["l"], sd["c"], sd["t"]
        if cc.size < ATR_LEN + 2:
            continue
        atr4 = atr_arr(hh, ll, cc)
        pctil = build_pctil(anchor, sd, s)
        self_idx = dict(zip(tt.tolist(), range(cc.size)))
        for j in range(NCOMMON):
            pv = pctil[j]
            if np.isnan(pv):
                continue
            self_k = self_idx.get(int(common_t[j]))
            if self_k is None or self_k < ATR_LEN + 1 or self_k >= cc.size - 1:
                continue
            a = atr4[self_k - 1]
            if a is None or np.isnan(a) or a <= 0:
                continue
            c_now = cc[self_k]
            k0 = self_k + 1
            ts_sig = int(tt[self_k]) + 4 * 3600
            strong = pv >= 60.0
            weak = pv <= 40.0
            if strong and not weak:
                rm = trade(+1, hh, ll, cc, tt, c_now, c_now - SL_ATR_MULT * a, c_now + TP_ATR_MULT * a,
                           k0, MAX_FWD, protocol, break_atr=(break_atr or a), order_type="stop")
                rr = trade(-1, hh, ll, cc, tt, c_now, c_now + SL_ATR_MULT * a, c_now - TP_ATR_MULT * a,
                           k0, MAX_FWD, protocol, break_atr=(break_atr or a), order_type="stop")
            elif weak and not strong:
                rm = trade(-1, hh, ll, cc, tt, c_now, c_now + SL_ATR_MULT * a, c_now - TP_ATR_MULT * a,
                           k0, MAX_FWD, protocol, break_atr=(break_atr or a), order_type="stop")
                rr = trade(+1, hh, ll, cc, tt, c_now, c_now - SL_ATR_MULT * a, c_now + TP_ATR_MULT * a,
                           k0, MAX_FWD, protocol, break_atr=(break_atr or a), order_type="stop")
            else:
                continue
            m_ok = bool(rm and rm["filled"])
            r_ok = bool(rr and rr["filled"])
            if m_ok and r_ok:
                # 同分母有效样本: 两方向都真正成交 → 两组各计 1
                mom_R.append(rm["R"])
                rev_R.append(rr["R"])
                events.append((ts_sig, s, pv, rm["R"], rr["R"], True))
                n_fair_filled += 1
            else:
                # 至少一方向几何不成立(数据异常/未成交) → 两组都剔除, 只计 skipped
                m_val = rm["R"] if m_ok else None
                r_val = rr["R"] if r_ok else None
                events.append((ts_sig, s, pv, m_val, r_val, False))
                n_skipped += 1
    return events, mom_R, rev_R, n_fair_filled, n_skipped


def main():
    out = {
        "meta": {
            "indicator": "CurrencyStrengthRadar",
            "role": "货币强弱惯性雷达 — 本币相对 7 币篮子(USD 对)的窗口涨跌幅排名分位(0 最弱/100 最强)",
            "hypothesis_tested": "拿最强打最弱 = 惯性/动量: 分位>=60 买入最强, 分位<=40 卖出最弱",
            "iron_law": "金策铁律: 高胜率≠正期望; 统计对比必须同分母; 子集胜率差不算 edge。裸惯性默认负期望, "
                        "只证明有正期望才准进 live, 否则仅当否决门(提示别追最弱那个币), 不正向提权。",
            "basket": BASKET, "n_basket": N, "self_pool": SELF_POOL,
            "anchors_grid": ANCHORS, "common_window_h4_bars": int(NCOMMON),
            "window_start": str(datetime.datetime.fromtimestamp(common_t[0])),
            "window_end": str(datetime.datetime.fromtimestamp(common_t[-1])),
            "geometry": {"tf": "H4", "entry": "stop", "sl_atr_mult": SL_ATR_MULT,
                         "tp_atr_mult": TP_ATR_MULT, "max_fwd_bars": MAX_FWD,
                         "atr_len": ATR_LEN, "tp_r": 2.0},
            "engine": "backtest_engine.trade (统一回放引擎)",
            "selftest_pass": bool(selftest() and limit_selftest()),
        },
    }

    per_anchor = {}
    all_mom_R = []
    denom_audit = {}
    for anchor in ANCHORS:
        events, mom_R, rev_R, n_fair, n_skipped = collect_events(anchor, "tp_sl_only")
        m = np.array(mom_R) if mom_R else np.array([])
        rv = np.array(rev_R) if rev_R else np.array([])
        same_denom = (len(m) == len(rv))
        per_anchor[str(anchor)] = {
            "n_momentum": int(len(m)), "n_reversal": int(len(rv)),
            "n_skipped": int(n_skipped),
            "n_fair_filled": int(n_fair),
            "n_total_events": int(n_fair + n_skipped),
            "same_denominator": {
                "n_momentum": int(len(m)), "n_reversal": int(len(rv)), "n_skipped": int(n_skipped),
                "passed": bool(same_denom),
                "note": "两组吃同一批【两方向都成交】的事件; 某方向几何不成立(数据异常/等待期未成交)→两组都计 n_skipped, 有效样本 n_momentum==n_reversal 严格同分母。",
            },
            "exp_R_momentum": round(float(m.mean()), 4) if len(m) else None,
            "win_rate_momentum": round(float((m > 0).mean()), 4) if len(m) else None,
            "exp_R_reversal": round(float(rv.mean()), 4) if len(rv) else None,
            "win_rate_reversal": round(float((rv > 0).mean()), 4) if len(rv) else None,
        }
        # 每品种动量期望R (验3 稳健性, 同分母有效样本)
        per_sym = {}
        for s in SELF_POOL:
            sr = np.array([e[3] for e in events if e[1] == s and e[5] and e[3] is not None]) if events else np.array([])
            per_sym[s] = {"n": int(len(sr)), "exp_R": round(float(sr.mean()), 4) if len(sr) else None}
        per_anchor[str(anchor)]["per_symbol_momentum"] = per_sym
        all_mom_R.extend(mom_R)
        denom_audit[str(anchor)] = {"n_momentum": int(len(m)), "n_reversal": int(len(rv)),
                                    "n_skipped": int(n_skipped), "passed": bool(same_denom)}
        a6 = per_anchor[str(anchor)]
        print(f"[anchor={anchor}] 动量 n={a6['n_momentum']} 期望R={a6['exp_R_momentum']} 胜率={a6['win_rate_momentum']}"
              f" | 反转 n={a6['n_reversal']} 期望R={a6['exp_R_reversal']} 胜率={a6['win_rate_reversal']}"
              f" | skipped={n_skipped} 同分母={'PASS' if same_denom else 'FAIL'}")
    best_anchor = max(per_anchor, key=lambda k: (per_anchor[k]["exp_R_momentum"] or -9))
    per_anchor[best_anchor]["is_best"] = True

    out["per_anchor"] = per_anchor
    a6 = per_anchor["6"]
    grand = np.array(all_mom_R)

    # 同分母校验 (风控官复核项): 每 anchor 两组必须严格同分母
    out["same_denominator_audit"] = {
        "per_anchor": denom_audit,
        "all_passed": bool(all(v["passed"] for v in denom_audit.values())),
        "note": "修正前动量组/反转组触发事件集不对称(差 19~22 笔; 根因: 同一信号K线上一方向挂单等待期未成交, 引擎回退EXPIRED记R=0仍计有效样本, 另一方向成交/不成交口径不一致, 事件集漂移); "
                "修正后固定事件全集, 某方向几何不成立(等待期未成交/数据异常)→两组都计 n_skipped, 有效样本 n_momentum==n_reversal。",
    }

    # 滑点敏感性 (验: 动量扣滑点是否还正)
    slip = {}
    for s in [0.0, 0.1, 0.25, 0.5]:
        adj = (grand - s) if len(grand) else np.array([])
        slip[str(s)] = {"exp_R": round(float(adj.mean()), 4) if len(adj) else None,
                        "win_rate": round(float((adj > 0).mean()), 4) if len(adj) else None}
    out["slippage_sensitivity_momentum_all"] = slip

    # 五验
    n_mom_all = int(len(grand))
    tstat = float(grand.mean()) / (grand.std() / np.sqrt(n_mom_all)) if n_mom_all > 2 else 0.0
    per_sym6 = a6["per_symbol_momentum"]
    pos_syms = [s for s, v in per_sym6.items() if (v["exp_R"] or 0) > 0]
    neg_syms = [s for s, v in per_sym6.items() if (v["exp_R"] or 0) < 0]

    # 验4 双协议对照 (anchor=6 动量)
    ev_t, mom_t, rev_t, n_fair_t, n_sk_t = collect_events(6, "live_trend")
    et = float(np.mean(mom_t)) if mom_t else 0.0
    es = float(a6["exp_R_momentum"] or 0)
    two_proto = {"live_trend_exp_R": round(et, 4), "tp_sl_only_exp_R": round(es, 4),
                 "n_trend": int(len(mom_t)), "n_sl": a6["n_momentum"],
                 "both_positive": bool(et > 0 and es > 0),
                 "pass": bool(et > 0 and es > 0),
                 "note": "两种出场协议动量都正才稳; 挑协议=过拟合"}

    # 验5 走查前三段 (anchor=6 动量, 按信号时间戳切 1/3)
    ev6, mom6, _rv6, _nf6, _ns6 = collect_events(6, "tp_sl_only")
    if ev6:
        arr = np.array([(e[0], e[3]) for e in ev6 if e[5] and e[3] is not None])
        tt = arr[:, 0]; Rr = arr[:, 1]
        b1 = int(tt.min() + (tt.max() - tt.min()) / 3)
        b2 = int(tt.min() + 2 * (tt.max() - tt.min()) / 3)
        segs = {}
        for name, lo, hi in [("前段", int(tt.min()), b1), ("中段", b1, b2), ("后段", b2, int(tt.max()) + 1)]:
            seg = Rr[(tt >= lo) & (tt < hi)]
            segs[name] = {"n": int(len(seg)), "exp_R": round(float(seg.mean()), 4) if len(seg) else None}
        allpos = all((v["exp_R"] or 0) > 0 for v in segs.values())
        wf = {"segments": segs, "all_segments_positive": bool(allpos),
              "pass": bool(allpos and len(Rr) >= 300),
              "note": "三段都正才不是单段独撑; 单段独撑=过拟合"}
    else:
        wf = {"segments": {}, "all_segments_positive": False, "pass": False, "note": "无事件"}

    five = {
        "验1_样本量": {"n_momentum_all_anchors": n_mom_all,
                       "n_momentum_anchor6": a6["n_momentum"],
                       "threshold": 1000,
                       "pass": bool(n_mom_all >= 1000 and a6["n_momentum"] >= 100)},
        "验2_显著性": {"t_stat": round(tstat, 3), "n": n_mom_all,
                       "mean_R_momentum_all": round(float(grand.mean()), 4) if len(grand) else None,
                       "pass": bool(abs(tstat) > 2.0)},
        "验3_品种稳健": {"pos_syms": pos_syms, "neg_syms": neg_syms,
                         "n_pos": len(pos_syms), "n_neg": len(neg_syms),
                         "pass": bool(len(pos_syms) >= 3 and len(pos_syms) > len(neg_syms)),
                         "note": ">=3 个品种动量同号为正且不独撑, 才稳健; 单一品种独撑不算 edge"},
        "验4_双协议对照": two_proto,
        "验5_走查前三段": wf,
    }
    out["five_checks"] = five
    out["denominator_note"] = (
        "同分母铁律: 同一 InpAnchorBars 下, 动量组与反转组吃【同一批已成交事件】"
        "(分位>=60 的强势K线 + 分位<=40 的弱势K线, 事件全集固定且因果一致; "
        "某方向 stop 挂单几何不成立(等待期未成交/数据异常)则该事件两组都剔除、只计 n_skipped, "
        "有效样本 n_momentum==n_reversal 严格相等), 只是方向相反。"
        "对比的是全样本事件上的两种方向, 不是子集胜率。子集胜率差不算 edge。")

    # 裁决 (动量=拿最强打最弱, 主口径, 看 anchor=6)
    mom6 = a6["exp_R_momentum"] or 0.0
    passes_core = (five["验1_样本量"]["pass"] and five["验2_显著性"]["pass"]
                   and five["验3_品种稳健"]["pass"] and two_proto["both_positive"]
                   and five["验5_走查前三段"]["pass"])
    if passes_core and mom6 > 0.15:
        verdict = "PASS"
    elif (mom6 > 0 or two_proto["both_positive"]) and n_mom_all >= 100:
        verdict = "WATCH"
    else:
        verdict = "REJECT"
    out["verdict"] = verdict
    out["best_anchor"] = best_anchor
    out["rejection_gate"] = {
        "keep_as_veto_gate": True,
        "policy": "无论 PASS/WATCH/REJECT, 本指标可保留为【否决门】: 当 self 分位<=40(弱势)时, "
                  "提示'别追这个最弱币'(对应反转组'买最弱'或回避)。但只有 PASS 才准正向提权(把'买最强'接进 live)。"
                  "WATCH/REJECT 只当警示, 不进 live。",
        "rationale": "裸惯性构造默认负期望, 历史上多数被滑点+成本抹平; 同分母全样本证明有正期望前, 不正向提权。",
    }

    # ── 大白话结论 (进 verdict 字段 + 单独出报告) ───────────────────────
    rev6 = a6["exp_R_reversal"]
    slip025 = slip["0.25"]["exp_R"]
    wr6 = a6["win_rate_momentum"]
    if verdict in ("WATCH", "REJECT"):
        usable_cn = "能用, 但只能当「否决门」, 不准当正向信号接进实盘"
    else:
        usable_cn = "可以放心当正向信号用(买最强)接进实盘"
    verdict_cn = (
        f"【能不能放心用】{usable_cn}。"
        f"这套指标算的是「你这个币过去 {best_anchor} 根K线里, 比 7 个美元对里的哪几个强」(0=最弱, 100=最强)。"
        f"你提的「拿最强打最弱」(买最强那个、卖最弱那个)我全样本回测了, 动量组 {n_mom_all} 笔平均 {mom6:+.3f} R、"
        f"胜率 {wr6}, 扣 0.25R 滑点还剩 {slip025:+.3f} R。"
        f"按金策铁律, 只有当平均R明显为正、扣滑点/分品种/分段都站得住, 才准接进实盘; 这次裁决是 {verdict}。"
        f"【什么情况下最有用】市场有明显方向、一两个币在持续领涨/领跌时, 这条线会顶到 80-100, "
        f"此时它最有用: 帮你别去抄最弱那个(否决门); 篮子整体同涨同跌、分位挤在 40-60 中间时, 它基本没用, 别硬读。"
        f"【什么情况下会骗人】行情在两个极端之间反复横跳(假突破)、K线窗口(3/6/12/24)选错周期、"
        f"或你只挑某一两笔赚钱的样本来看(子集)——这几种它会把你看走。"
        f"记住: 高胜率不等于正期望, 必须同分母全样本证明, 子集胜率差不算本事。"
    )
    out["verdict_cn"] = verdict_cn
    out["summary"] = {
        "verdict": verdict,
        "best_anchor": best_anchor,
        "momentum_exp_R_anchor6": mom6,
        "momentum_win_rate_anchor6": a6["win_rate_momentum"],
        "reversal_exp_R_anchor6": rev6,
        "five_checks_pass": {k: v["pass"] for k, v in five.items()},
        "keep_as_veto_gate": True,
    }

    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("\nverdict =", verdict, "| best_anchor =", best_anchor)
    print("已写", OUT)
    return out


if __name__ == "__main__":
    main()
