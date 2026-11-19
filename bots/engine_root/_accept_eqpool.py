# -*- coding: utf-8 -*-
# 等点池否决门验收 v2 (三处小改动, 机械执行):
# 1) atr_val=None 不再走 0.2×nanmean(全段H-L), 改 0.2×逐bar滚动因果ATR14(简单均值, 只用当根之前14根TR)
# 2) 删除脚本叠加的 0.2*abs(pdh)*0.02 (0.4%相对价固定带), 只保留与live一致的单一 0.2*ATR 口径
# 3) "孤点被破"不再按顺势单判对错: 反向降权0.25归live趋势层, 孤点事件标记"否决门未触发(交给趋势层)",
#    否决门胜负只统计等点池事件的"反向单"胜率(等权重模拟: 池内反向开仓, fwd2日close方向判对错)
# 3组验收: a)360根小窗口(bars, days=300+60)  b)全史D1  c)fwd1/fwd3灵敏度
# 输出: E:/GoldstrategyEngine/data/eqpool_accept_final.json
# 铁律: 全史 |Δ|<1% 或 p>0.2 → 结论"保留中性0.6待观察, 否决门不claim正向edge"
# 子进程print禁emoji, 用[OK]/[!]
import os, sys, json, math
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # GBK控制台保险
sys.path.insert(0, "E:/GoldstrategyEngine")
sys.path.insert(0, "E:/GoldstrategyEngine/multi_agent/trading")
import numpy as np
import MetaTrader5 as mt5
import structure_fusion as sf

SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "BNBUSD", "LTCUSD"]


def rolling_causal_atr14(h, l, c, period=14):
    """逐bar滚动因果ATR14(只用当根之前的数据): TR14简单均值, 第i根=前14根(不含i)的TR均值.
    选简单均值(SMA版)而非Wilder平滑: 逐bar独立窗口, 无递归状态, 因果性直观易复核."""
    m = len(h)
    tr = np.empty(m)
    tr[0] = h[0] - l[0]
    pc = np.concatenate([[np.nan], c[:-1]])
    tr[1:] = np.maximum(h[1:] - l[1:],
                        np.maximum(np.abs(h[1:] - pc[1:]), np.abs(l[1:] - pc[1:])))
    atr = np.full(m, np.nan)
    for i in range(period, m):
        atr[i] = np.nanmean(tr[i - period:i])
    return atr


def pull_d1(sym, days):
    d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, days + 60)
    if d1 is None or len(d1) < 100:
        return None
    return d1


def build_events(d1, fwd=2):
    """逐日扫前日高低事件. 返回 [(swept_side, in_eq_pool, close, fwd_close, lone_flag)]
    side: 'hi'=扫前日高(反向=做空), 'lo'=扫前日低(反向=做多).
    改动1: eq池阈值 = 0.2×因果ATR14[i] (传 atr_val 进 equal_highs_lows, 不再 None)
    改动2: 无 0.2*abs(px)*0.02 叠加带, 只保留单一 0.2*ATR 口径(等 high-low 距离<=thr)
    """
    h = d1["high"].astype(float)
    l = d1["low"].astype(float)
    c = d1["close"].astype(float)
    atr = rolling_causal_atr14(h, l, c)
    n = len(d1)
    evts = []
    for i in range(60, n - fwd):
        pdh, pdl = h[i - 1], l[i - 1]
        fv = c[i + fwd]
        ai = atr[i]  # 因果: 只用 i 之前数据
        if not np.isfinite(ai) or ai <= 0:
            continue
        thr = 0.2 * ai  # 与live一致的单一口径: 0.2*ATR
        eq = sf.equal_highs_lows(h[:i], l[:i], atr_val=ai, eq_mult=0.2, lookback=60)
        # 改动1+2: 前日高低是否落在等点池内 (距离 <= thr, 单一带, 无价格百分比叠加)
        hi_pool = eq["hi_pool"]; lo_pool = eq["lo_pool"]
        events_i = []
        if h[i] > pdh:
            in_band = any(abs(pdh - p) <= thr for p in hi_pool) if hi_pool else False
            # 改动3: 孤点(被破但不在池内) → 否决门未触发, 交给趋势层(顺势, 反向单降权0.25不在本模拟内)
            events_i.append(("hi", in_band, float(c[i]), float(fv), not in_band))
        if l[i] < pdl:
            in_band = any(abs(pdl - p) <= thr for p in lo_pool) if lo_pool else False
            events_i.append(("lo", in_band, float(c[i]), float(fv), not in_band))
        for side, in_band, close_i, f, lone in events_i:
            evts.append({"side": side, "in_pool": in_band, "close": close_i,
                        "fwd": f, "lone": lone})
    return evts


def ztest(w1, n1, w2, n2):
    """两比例 z 检验 (正态近似). 返回 (z, p, delta_new_minus_old)."""
    if n1 < 10 or n2 < 10:
        return (None, None, None)
    p1, p2 = w1 / n1, w2 / n2
    p_pool = (w1 + w2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return (0.0, 1.0, p2 - p1)
    z = (p2 - p1) / se
    p_val = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return (z, p_val, p2 - p1)


def group_report(all_evts, fwd_label):
    """全部币池化: 旧口径=全事件盲目反向胜率; 新口径=只统计池内事件的"反向单"胜率.
    孤点事件标记"否决门未触发(交给趋势层)", 不计入否决门胜负."""
    evts = [e for grp in all_evts for e in grp]
    n_old = len(evts)
    win_old = 0
    for e in evts:
        if e["side"] == "hi":
            win_old += (e["fwd"] < e["close"])   # 扫多→反向做空: fwd低于close=对
        else:
            win_old += (e["fwd"] > e["close"])   # 扫空→反向做多: fwd高于close=对
    pool_evts = [e for e in evts if e["in_pool"]]
    lone_evts = [e for e in evts if e["lone"]]
    n_new = len(pool_evts)
    win_new = 0
    for e in pool_evts:
        if e["side"] == "hi":
            win_new += (e["fwd"] < e["close"])
        else:
            win_new += (e["fwd"] > e["close"])
    wr_old = win_old / n_old if n_old else 0.0
    wr_new = win_new / n_new if n_new else 0.0
    z, p, delta = ztest(win_old, n_old, win_new, n_new)
    rep = {
        "fwd": fwd_label,
        "n_old_total_events": n_old,
        "wr_old": round(wr_old, 4),
        "n_new_pool_events": n_new,
        "lone_events_not_in_gate": len(lone_evts),
        "lone_note": "孤点事件: 否决门未触发(交给趋势层), 反向降权0.25, 不计入否决门胜负",
        "wr_new": round(wr_new, 4),
        "delta": round(delta, 4) if delta is not None else None,
        "z": round(z, 3) if z is not None else None,
        "p": round(p, 4) if p is not None else None,
    }
    print(f"[OK] {fwd_label}: n_old={n_old} wr_old={wr_old:.1%} | 池内n={n_new} "
          f"wr_new={wr_new:.1%} | 孤点={len(lone_evts)}(未触发/趋势层) | "
          f"Δ={delta:+.1%} z={z} p={p}" if z is not None else
          f"[!] {fwd_label}: 样本不足 n_old={n_old} 池内={n_new} 不统计")
    return rep


def main():
    ok = mt5.initialize()
    mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
    print(f"[OK] MT5 init={ok} equity={mt5.account_info().equity:.0f}")

    # a) 小窗口: 360根bar对照 (days=300, 脚本拉300+60=360根bar窗口, 旧默认口径)
    small = []
    for s in SYMS:
        d1 = pull_d1(s, days=300)
        small.append(build_events(d1, fwd=2) if d1 is not None else [])
        print(f"[OK] 小窗口 {s}: {len(small[-1])}事件")
    small_rep = group_report(small, "360bar小窗口 fwd2")

    # b) 全史 D1
    full = []
    maxn = 0
    for s in SYMS:
        d1 = pull_d1(s, days=5000)  # 要多少给多少, 全史
        ev = build_events(d1, fwd=2) if d1 is not None else []
        full.append(ev)
        maxn = max(maxn, len(d1)) if d1 is not None else 0
        print(f"[OK] 全史 {s}: {len(d1) if d1 is not None else 0}bar {len(ev)}事件")
    print(f"[OK] 全史最大bar数={maxn}")
    full_rep = group_report(full, "全史D1 fwd2")

    # c) fwd1 / fwd3 灵敏度
    sens = {}
    for f in (1, 3):
        g = []
        for s in SYMS:
            d1 = pull_d1(s, days=5000)
            g.append(build_events(d1, fwd=f) if d1 is not None else [])
        rep = group_report(g, f"fwd{f}灵敏度")
        sens[f"fwd{f}"] = rep
        print(f"[OK] fwd{f}: {rep}")

    # 结论: 铁律 — 全史 |Δ|<1% 或 p>0.2 → 保留中性0.6待观察
    delta = full_rep["delta"]; p = full_rep["p"]
    if delta is None or abs(delta) < 0.01 or (p is not None and p > 0.2):
        verdict = ("保留中性0.6待观察, 否决门不claim正向edge; "
                   f"理由: 全史|Δ|={abs(delta) if delta is not None else 'NA'}<1%或p={p}>0.2, 无显著差异")
    elif delta > 0:
        verdict = f"放大; 理由: 全史池内反向胜率{full_rep['wr_new']:.1%}高于旧{full_rep['wr_old']:.1%} (p={p})"
    else:
        verdict = f"回滚; 理由: 全史池内反向胜率{full_rep['wr_new']:.1%}低于旧{full_rep['wr_old']:.1%} (p={p})"

    out = {
        "小窗口": small_rep,
        "全史": full_rep,
        "灵敏度": sens,
        "结论": verdict,
        "口径说明": {
            "改动1": "atr_val=None→0.2×逐bar滚动因果ATR14(简单均值SMA版, 只用当根前14根TR)",
            "改动2": "删除0.2*abs(px)*0.02价格叠加带, 仅保留单一0.2*ATR口径",
            "改动3": "孤点被破=否决门未触发(交给趋势层, 反向降权0.25), 不计入否决门胜负; 胜负只统计池内事件反向单",
            "p值": "两比例正态近似 z 检验",
        },
    }
    os.makedirs("E:/GoldstrategyEngine/data", exist_ok=True)
    with open("E:/GoldstrategyEngine/data/eqpool_accept_final.json", "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=2)
    print(f"[OK] 已写 data/eqpool_accept_final.json | 结论: {verdict}")
    mt5.shutdown()


if __name__ == "__main__":
    main()
