# -*- coding: utf-8 -*-
# 缠论中枢 + 亚盘区间 两技能 外汇/币圈 edge 回测验证 (同分母公平对照)
# 只读: 不改任何交易 .py; MT5 只拉 D1 历史, 禁止 order_send。
# 口径: 与 _accept_eqpool.py 验收同口径 (事件=当日扫前日高/低, fwd2 当日close起判方向)。
# 子进程print禁emoji, 用[OK]/[!]
import os, sys, json, math
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, "E:/GoldstrategyEngine")
sys.path.insert(0, "E:/GoldstrategyEngine/multi_agent/trading")
import numpy as np
import MetaTrader5 as mt5
import structure_fusion as sf

FX = ["EURUSD", "GBPUSD", "XAUUSD"]
CRYPTO = ["BTCUSD", "SOLUSD"]
ALL = FX + CRYPTO
DAYS = 5000          # copy_rates_from_pos 取 5000 天 (全史)
WARM = 60            # 前60根预热(与eqpool验收同)
FWD = 2


def ztest(w1, n1, w2, n2):
    """两比例 z 检验 (正态近似), 返回 (z, p, delta2_minus_1)"""
    if n1 < 10 or n2 < 10:
        return (None, None, None)
    p1, p2 = w1 / n1, w2 / n2
    pp = (w1 + w2) / (n1 + n2)
    se = math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
    if se == 0:
        return (0.0, 1.0, p2 - p1)
    z = (p2 - p1) / se
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return (z, p, p2 - p1)


def rev_win(side, close_i, fwd_c, trend=False):
    """side='hi'(扫前日高→反做=做空) / 'lo'(扫前日低→反做=做多).
    反做: fwd2 close 回到中枢/区间方向才算对; 顺做(trend=True)取反."""
    a = (fwd_c < close_i) if side == "hi" else (fwd_c > close_i)
    return (not a) if trend else bool(a)


def pull(sym):
    d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, DAYS)
    if d1 is None or len(d1) < WARM + 20:
        return None
    return d1


def chanlun_one(d1, fwd):
    """逐日: 因果中枢(只用i之前60根) + 扫前日高低事件, 分 组A(在中枢内)/组B(外).
    返回 dict: A/B 的 fwd1/fwd2 反做胜率, 及每事件 (side, group, close, fwd1c, fwd2c, trend_win_flag)"""
    h = d1["high"].astype(float); l = d1["low"].astype(float); c = d1["close"].astype(float)
    n = len(d1)
    evts = []
    for i in range(WARM, n - fwd - 1):
        pz = sf.pivot_zone(h[max(0, i - 60):i], l[max(0, i - 60):i], seg_n=3, window=60)
        has = pz.get("valid") and pz.get("ZD") is not None and pz.get("ZG") is not None
        pdh, pdl = h[i - 1], l[i - 1]
        cand = []
        if h[i] > pdh:
            cand.append(("hi", pdh))
        if l[i] < pdl:
            cand.append(("lo", pdl))
        if not cand:
            continue
        for side, lvl in cand:
            gA = bool(has and pz["ZD"] <= lvl <= pz["ZG"])
            evts.append({
                "side": side, "gA": gA,
                "close": float(c[i]),
                "fwd1": float(c[i + 1]),
                "fwd2": float(c[i + 2]),
            })
    return evts


def stats_grp(evts, key, fwd_key):
    grp = [e for e in evts if e[key]]
    w = sum(1 for e in grp if rev_win(e["side"], e["close"], e[fwd_key]))
    return len(grp), w


def combined_compare(evts, fwd_key):
    """同分母: 全部事件 n 相同。
    策略S1(组内反做+组外顺做): A按反做, B按顺势
    策略S0(全事件盲目反做): 全部按反做
    两策略在同一 n 上各自累计对/错 → 配对差值, 用正态近似 (方差=|S1-S0|/n 的二项近似)."""
    n = len(evts)
    if n == 0:
        return None
    w0 = sum(1 for e in evts if rev_win(e["side"], e["close"], e[fwd_key]))
    w1 = sum(1 for e in evts if (rev_win(e["side"], e["close"], e[fwd_key]) if e["gA"]
                                 else rev_win(e["side"], e["close"], e[fwd_key], trend=True)))
    p0, p1 = w0 / n, w1 / n
    diff = p1 - p0
    se = math.sqrt(max(w1 * (n - w1), 1) / n ** 3 + max(w0 * (n - w0), 1) / n ** 3) if n > 1 else 0.0
    if se <= 0:
        z, p = 0.0, 1.0
    else:
        z = diff / se
        p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return {"n_total": n, "n_A": sum(1 for e in evts if e["gA"]),
            "n_B": sum(1 for e in evts if not e["gA"]),
            "wr_blind_rev": round(p0, 4), "wr_hybrid": round(p1, 4),
            "delta": round(diff, 4), "z": round(z, 3) if z is not None else None,
            "p": round(p, 4) if p is not None else None}


def chanlun_all():
    per = {}
    allE = {"fwd1": [], "fwd2": []}
    for sym in ALL:
        d1 = pull(sym)
        if d1 is None:
            print(f"[!] {sym} 拉不到 D1 全史, 跳过")
            continue
        ev = chanlun_one(d1, 2)
        per[sym] = len(ev)
        allE["fwd1"] += ev; allE["fwd2"] += ev
    out = {}
    for fk in ("fwd1", "fwd2"):
        evts = allE[fk]
        nA, wA = stats_grp(evts, "gA", fk)
        nB = sum(1 for e in evts if not e["gA"])
        wB = sum(1 for e in evts if not e["gA"] and rev_win(e["side"], e["close"], e[fk]))
        zA, pA, dAB = ztest(wB, nB, wA, nA)
        out[fk] = {
            "n_events": len(evts), "n_A_in_pz": nA, "n_B_out_pz": nB,
            "wr_A_rev": round(wA / nA, 4) if nA else None,
            "wr_B_rev": round(wB / nB, 4) if nB else None,
            "A_vs_B_z": zA, "A_vs_B_p": pA,
            "hybrid_vs_blind": combined_compare(evts, fk),
        }
    return out, per


def asia_one(d1, fwd=2):
    """外汇: asia_range 取上一交易日 D1 高低 (0-8UTC 近似), 当日收盘突破区间方向
    vs fwd2 方向; 对比 突破跟随单 vs 穿区反做单 (同分母=同一批突破事件).
    仅在'当日close 明确突破上一D1区间'时计事件 (收盘站上asia_hi=突破向上; 跌破asia_lo=向下)."""
    h = d1["high"].astype(float); l = d1["low"].astype(float); c = d1["close"].astype(float)
    n = len(d1)
    ev = []
    for i in range(WARM, n - fwd):
        ar = sf.asia_range(h[:i + 1], l[:i + 1])  # 内部取 [-2] = 上一交易日
        if ar.get("asia_hi") is None or ar.get("asia_lo") is None:
            continue
        ci = c[i]
        if ci > ar["asia_hi"]:
            ev.append({"dir": "up", "close": float(ci), "fwd": float(c[i + fwd]), "hi": ar["asia_hi"]})
        elif ci < ar["asia_lo"]:
            ev.append({"dir": "dn", "close": float(ci), "fwd": float(c[i + fwd]), "lo": ar["asia_lo"]})
    return ev


def asia_all():
    evs = []
    per = {}
    for sym in FX:   # 币圈无亚盘休市, 跳过并注明
        d1 = pull(sym)
        if d1 is None:
            print(f"[!] {sym} 拉不到 D1, 亚盘跳过")
            continue
        e = asia_one(d1, 2)
        per[sym] = len(e)
        evs += e
    n = len(evs)
    w_brk = sum(1 for e in evs if (e["fwd"] > e["close"]) if e["dir"] == "up") \
        + sum(1 for e in evs if (e["fwd"] < e["close"]) if e["dir"] == "dn")
    w_rev = n - w_brk   # 同一批事件, 反做对错与跟随对错互补 → 严格同分母配对
    z, p, dlt = ztest(n - w_brk, n, w_brk, n)  # 跟随 vs 反做 (交换w顺序)
    return {"n_events": n, "per_sym": per,
            "wr_break_follow": round(w_brk / n, 4) if n else None,
            "wr_reversal": round(w_rev / n, 4) if n else None,
            "follow_vs_reversal_p": p, "delta_follow_minus_rev": dlt,
            "note": "币圈(BTC/SOL)无亚盘休市概念, 已跳过; 外汇用asia_range上一交易日D1高低=0-8UTC近似"}


def grade(delta, p):
    if delta is None or p is None:
        return "保留(样本不足/不显著)"
    d, pp = delta * 100, p
    if d >= 1.0 and pp < 0.05:
        return "放大"
    if d <= -1.0 and pp < 0.05:
        return "否决"
    return "保留(不显著)"


def main():
    ok = mt5.initialize()
    login = mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
    print("init:", ok, "login:", login)
    chan, chan_per = chanlun_all()
    asia = asia_all()
    c2 = chan["fwd2"]["hybrid_vs_blind"]
    c1 = chan["fwd1"]["hybrid_vs_blind"]
    concls = [
        {"组件": "缠论中枢(组内反做+组外趋势, fwd2)", "判级": grade(c2["delta"] if c2 else None, c2["p"] if c2 else None),
         "数字": f"n={c2['n_total'] if c2 else 0}, 盲反做={c2['wr_blind_rev'] if c2 else None}, 混合={c2['wr_hybrid'] if c2 else None}, Δ={c2['delta'] if c2 else None}, p={c2['p'] if c2 else None}"},
        {"组件": "缠论中枢(敏感性fwd1)", "判级": "保留(敏感性)", "数字": f"Δ={c1['delta'] if c1 else None}, p={c1['p'] if c1 else None}"},
        {"组件": "亚盘区间(突破跟随 vs 穿区反做)", "判级": grade(asia["delta_follow_minus_rev"], asia["follow_vs_reversal_p"]),
         "数字": f"n={asia['n_events']}, 跟随={asia['wr_break_follow']}, 反做={asia['wr_reversal']}, p={asia['follow_vs_reversal_p']}"},
    ]
    rep = {"中枢": chan, "亚盘区间": asia, "结论": concls,
           "per_sym_events": chan_per,
           "红线": "不claim正向edge前不进live分值"}
    os.makedirs("E:/GoldstrategyEngine/data", exist_ok=True)
    with open("E:/GoldstrategyEngine/data/skills_verify_chanlun.json", "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print("[OK] 中枢 fwd2:", json.dumps(chan["fwd2"], ensure_ascii=False)[:400])
    print("[OK] 亚盘:", json.dumps(asia, ensure_ascii=False)[:400])
    mt5.shutdown()


if __name__ == "__main__":
    main()
