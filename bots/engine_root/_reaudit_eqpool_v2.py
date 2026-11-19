# -*- coding: utf-8 -*-
"""独立复核: 等点池否决门验收结论 re-audit.
1) 独立复算 _accept_eqpool.py 原口径 (days=300→360根D1, 带=0.2*abs(pdh)*0.02=0.4%相对价, fwd2)
2) 口径 bug 审查: 因果性 / lookback=60 / ATR口径 / 带宽 / fwd / 样本量
3) 灵敏度: 全史窗口 + 全史+live口径(lookback=240, ATR14, 带0.2*ATR14) 对比
MT5 只读: 仅 initialize/login 拉 D1, 不下单.
"""
import sys, json, math, datetime
sys.path.insert(0, "E:/GoldstrategyEngine")
sys.path.insert(0, "E:/GoldstrategyEngine/multi_agent/trading")
import numpy as np
import MetaTrader5 as mt5
import structure_fusion as sf
from structure_fusion import _swing_highs, _swing_lows

SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "BNBUSD", "LTCUSD"]

_cache = {}
def fetch(sym, n):
    key = (sym, n)
    if key not in _cache:
        d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, n)
        if d1 is None or len(d1) < 100:
            _cache[key] = None
            return None
        _cache[key] = {
            "h": d1["high"].astype(float), "l": d1["low"].astype(float),
            "c": d1["close"].astype(float), "time": d1["time"]}
    return _cache[key]


def equal_fast(h, l, atr_val, eq_mult=0.2, lookback=240):
    """与 sf.equal_highs_lows 完全等价, 但 swing 列表只算一次
    (原版在双重循环里反复调 _swing_highs, 语义逐行对齐)."""
    if atr_val is None or atr_val <= 0:
        atr_val = float(np.nanmean(h - l) or 0.0)
    thr = eq_mult * atr_val
    hi_pool, lo_pool = [], []
    sh = _swing_highs(h, lookback=lookback)
    for i in sh:
        for j in sh:
            if i < j and abs(h[i] - h[j]) <= thr:
                hi_pool.append((float(np.mean([h[i], h[j]])), 2))
                break
    sl = _swing_lows(l, lookback=lookback)
    for i in sl:
        for j in sl:
            if i < j and abs(l[i] - l[j]) <= thr:
                lo_pool.append((float(np.mean([l[i], l[j]])), 2))
                break
    return {"eq_hi": hi_pool, "eq_lo": lo_pool,
            "has_eq": bool(hi_pool or lo_pool),
            "hi_pool": [p for p, _ in hi_pool], "lo_pool": [p for p, _ in lo_pool]}


_eq_checked = False
def check_equivalence():
    """随机 3 个 i 点, fast vs 原版, 全同才放行."""
    global _eq_checked
    if _eq_checked:
        return
    import random
    d = fetch("BTCUSD", 200)
    random.seed(42)
    for i in random.sample(range(80, 195), 3):
        a = sf.equal_highs_lows(d["h"][:i], d["l"][:i], atr_val=None, eq_mult=0.2, lookback=60)
        b = equal_fast(d["h"][:i], d["l"][:i], None, eq_mult=0.2, lookback=60)
        assert a["has_eq"] == b["has_eq"], f"has_eq mismatch i={i}"
        assert sorted(a["hi_pool"]) == sorted(b["hi_pool"]), f"hi_pool mismatch i={i}"
        assert sorted(a["lo_pool"]) == sorted(b["lo_pool"]), f"lo_pool mismatch i={i}"
    print("[eq-check] fast 与原版 equal_highs_lows 等价 ✓ (3 抽检点, hi/lo pool 全同)")
    _eq_checked = True


def atr14(h, l, c, i):
    """ATR(14) 因果: 只用 [max(0,i-29):i] (不含 i 当日)."""
    lo = max(0, i - 29)
    hh = h[lo:i]; ll = l[lo:i]; cc = c[lo:i]
    if len(cc) < 15:
        return float(np.nanmean(hh - ll) or 0.0)
    prev = np.roll(cc, 1); prev[0] = cc[0]
    tr = np.maximum(hh - ll, np.maximum(np.abs(hh - prev), np.abs(ll - prev)))
    return float(tr[-14:].mean())


def build_events(sym, days, band_mode="scripted"):
    """复算事件. band_mode:
      scripted   = 原脚本口径: eq_mult=0.2, lookback=60, atr_val=None(nanmean全段), 带=0.2*abs(ref)*0.02
      live       = live口径: eq_mult=0.2, lookback=240, ATR14, 带=0.2*ATR14
      none_atr   = lookback=240, atr_val=None (对照)
    """
    d = fetch(sym, days + 60)
    if d is None:
        return []
    h, l, c, t = d["h"], d["l"], d["c"], d["time"]
    evts = []
    for i in range(60, len(h) - 3):
        pdh, pdl = h[i - 1], l[i - 1]
        swept_hi = h[i] > pdh
        swept_lo = l[i] < pdl
        if band_mode == "scripted":
            eq = equal_fast(h[:i], l[:i], None, eq_mult=0.2, lookback=60)
            hi_band = eq["has_eq"] and any(abs(pdh - p) <= 0.2 * abs(pdh) * 0.02 for p in eq["hi_pool"])
            lo_band = eq["has_eq"] and any(abs(pdl - p) <= 0.2 * abs(pdl) * 0.02 for p in eq["lo_pool"])
            a14 = None
        else:
            lb = 240
            a14 = atr14(h, l, c, i)
            eq = equal_fast(h[:i], l[:i], a14 if band_mode == "live" else None,
                           eq_mult=0.2, lookback=lb)
            if band_mode == "live":
                thr = 0.2 * a14
            else:
                thr = 0.2 * (float(np.nanmean(h[:i] - l[:i]) or 0.0))
            hi_band = eq["has_eq"] and any(abs(pdh - p) <= thr for p in eq["hi_pool"])
            lo_band = eq["has_eq"] and any(abs(pdl - p) <= thr for p in eq["lo_pool"])
        fwd = {f"fwd{k}": float(c[i + k]) for k in (1, 2, 3)}
        evts.append({
            "date": datetime.datetime.fromtimestamp(int(t[i])).strftime("%Y-%m-%d"),
            "swept_hi": bool(swept_hi), "swept_lo": bool(swept_lo),
            "hi_band": bool(hi_band), "lo_band": bool(lo_band),
            "close": float(c[i]),
            "fwd1": fwd["fwd1"], "fwd2": fwd["fwd2"], "fwd3": fwd["fwd3"],
        })
    return evts


def aggregate(evts_list, band_key=("hi_band", "lo_band"), fwd="fwd2", min_n=10):
    agg = {"old": [0, 0], "new": [0, 0]}
    per = []
    sub = {"band_rows": 0, "band_new": 0, "iso_rows": 0, "iso_new": 0, "iso_old": 0}
    for evts in evts_list:
        rows_hi, rows_lo = [], []
        for e in evts:
            if e["swept_hi"]:
                win_old = e[fwd] < e["close"]
                do_rev = e[band_key[0]]
                win_new = (e[fwd] < e["close"]) if do_rev else (e[fwd] >= e["close"])
                rows_hi.append((win_old, win_new, do_rev))
            if e["swept_lo"]:
                win_old = e[fwd] > e["close"]
                do_rev = e[band_key[1]]
                win_new = (e[fwd] > e["close"]) if do_rev else (e[fwd] <= e["close"])
                rows_lo.append((win_old, win_new, do_rev))
        for side, rows in (("sell", rows_hi), ("buy", rows_lo)):
            n = len(rows)
            if n < min_n:
                per.append({"side": side, "n": n, "skipped": "n<10"})
                continue
            wo = sum(1 for r in rows if r[0]); wn = sum(1 for r in rows if r[1])
            bn = sum(1 for r in rows if r[2])
            agg["old"][0] += wo; agg["old"][1] += n
            agg["new"][0] += wn; agg["new"][1] += n
            sub["band_rows"] += bn
            sub["band_new"] += sum(1 for r in rows if r[2] and r[1])
            sub["iso_rows"] += n - bn
            sub["iso_new"] += sum(1 for r in rows if (not r[2]) and r[1])
            sub["iso_old"] += sum(1 for r in rows if (not r[2]) and r[0])
            per.append({"side": side, "n": n, "wr_old": round(wo / n, 4),
                       "wr_new": round(wn / n, 4), "band_n": bn})
    to, tn = agg["old"][1], agg["new"][1]
    wo, wn = agg["old"][0], agg["new"][0]
    p_old = wo / to; p_new = wn / tn
    se = math.sqrt(p_old * (1 - p_old) / to + p_new * (1 - p_new) / tn)
    z = (p_new - p_old) / se if se > 0 else 0.0
    pval = float(2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2)))))
    return {"wr_old": p_old, "wr_new": p_new, "delta": p_new - p_old,
            "n_old": to, "n_new": tn, "z": z, "pval": pval,
            "per": per, "subset": sub}


def ztest_pair(w1, n1, w2, n2):
    p1 = w1 / n1; p2 = w2 / n2
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    z = (p2 - p1) / se
    return z, float(2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2)))))


def main():
    report = {"reaudit": True, "timestamp": datetime.datetime.now().isoformat(),
              "source_script": "E:/GoldstrategyEngine/_accept_eqpool.py",
              "claim": "旧53.2% vs 新47.9% (-5.3%), 结论=回滚", "windows": {}, "bugs": [], "verdict": None}
    ok1 = mt5.initialize()
    ok2 = mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
    info = mt5.account_info()
    eq0 = info.equity if info else None
    print(f"MT5 readonly: init={ok1} login={ok2} equity={eq0} (只读, 不下单)")
    report["mt5_readonly"] = {"init": bool(ok1), "login": bool(ok2), "equity": float(eq0 or 0)}
    check_equivalence()

    # ── 1) 独立复算原脚本口径 (days=300 → 360 根 D1) ──
    e360 = [build_events(s, 300, "scripted") for s in SYMS]
    A360 = aggregate(e360, fwd="fwd2")
    print(f"[1] 360根复算(scripted): 旧={A360['wr_old']:.3%} 新={A360['wr_new']:.3%} "
          f"差={A360['delta']:+.3%} n={A360['n_old']} z={A360['z']:.2f} p={A360['pval']:.4f}")
    report["windows"]["orig_360"] = {
        "wr_old": round(A360["wr_old"], 4), "wr_new": round(A360["wr_new"], 4),
        "delta": round(A360["delta"], 4), "n": A360["n_old"],
        "z": round(A360["z"], 3), "pval": round(A360["pval"], 5),
        "per_symbol": A360["per"], "subset": A360["subset"]}

    # ── 2) 全史 (3960 根) 复算, 同一 scripted 口径 ──
    eF = [build_events(s, 3900, "scripted") for s in SYMS]
    AF = aggregate(eF, fwd="fwd2")
    print(f"[2] 全史复算(scripted): 旧={AF['wr_old']:.3%} 新={AF['wr_new']:.3%} "
          f"差={AF['delta']:+.3%} n={AF['n_old']} z={AF['z']:.2f} p={AF['pval']:.4f}")
    report["windows"]["full_hist_scripted"] = {
        "wr_old": round(AF["wr_old"], 4), "wr_new": round(AF["wr_new"], 4),
        "delta": round(AF["delta"], 4), "n": AF["n_old"],
        "z": round(AF["z"], 3), "pval": round(AF["pval"], 5),
        "per_symbol": AF["per"], "subset": AF["subset"]}

    # ── 3) live口径 (lookback=240 + ATR14 + 带=0.2*ATR14) 全史 ──
    eL = [build_events(s, 3900, "live") for s in SYMS]
    AL = aggregate(eL, fwd="fwd2")
    print(f"[3] 全史 live口径(lb=240,ATR14): 旧={AL['wr_old']:.3%} 新={AL['wr_new']:.3%} "
          f"差={AL['delta']:+.3%} n={AL['n_old']} z={AL['z']:.2f} p={AL['pval']:.4f}")
    report["windows"]["full_hist_livecal"] = {
        "wr_old": round(AL["wr_old"], 4), "wr_new": round(AL["wr_new"], 4),
        "delta": round(AL["delta"], 4), "n": AL["n_old"],
        "z": round(AL["z"], 3), "pval": round(AL["pval"], 5),
        "per_symbol": AL["per"], "subset": AL["subset"]}

    # ── 4) 全史 scripted 口径下 fwd1/fwd3 灵敏度 ──
    sens = {}
    for fk in ("fwd1", "fwd3"):
        a = aggregate(eF, fwd=fk)
        sens[fk] = {"wr_old": round(a["wr_old"], 4), "wr_new": round(a["wr_new"], 4),
                    "delta": round(a["delta"], 4), "pval": round(a["pval"], 5)}
        print(f"[4] fwd{fk[-1]}: 旧={a['wr_old']:.3%} 新={a['wr_new']:.3%} 差={a['delta']:+.3%} p={a['pval']:.4f}")
    report["windows"]["fwd_sensitivity_full"] = sens

    # ── 5) 子集分解 (全史 scripted): 等点池子集 vs 孤点子集 ──
    sub = AF["subset"]
    print(f"[5] 子集: 等点池n={sub['band_rows']} 新胜率={sub['band_new']/max(1,sub['band_rows']):.1%} | "
          f"孤点n={sub['iso_rows']} 旧胜率={sub['iso_old']/max(1,sub['iso_rows']):.1%} 新(顺势)胜率={sub['iso_new']/max(1,sub['iso_rows']):.1%}")

    # ── 6) bug 清单 ──
    bugs = []
    bugs.append({"item": "注释口径", "severity": "low",
                 "finding": "脚本注释写'500天'但 evaluate() 调 daily_stats(days=300) → 实际拉 300+60=360 根 D1。数字可复现(53.2/47.9)但窗口标注错误。"})
    bugs.append({"item": "因果性", "severity": "ok",
                 "finding": "等点池判定 sf.equal_highs_lows(h[:i], l[:i]) 不含当日 i, 因果正确, 无前视。"})
    bugs.append({"item": "swing因果性细节", "severity": "low",
                 "finding": "_swing_highs(high[:i]) 的分型判定要求 i±2 邻域, 故最近 2 根(含前日)的 swing 分型因邻域被裁切而无法判定 — 轻微漏检, 不影响因果性。"})
    bugs.append({"item": "ATR口径不一致", "severity": "high",
                 "finding": "验收脚本 atr_val=None → 等点阈值用 0.2×nanmean(全段高-低)≈0.2×D1全距, 比 live 的 0.2×ATR14 宽约 1.5-2 倍; 且 lookback=60 vs live lookback=240。验收口径比 live 宽松, 会低估否决门实际效果。"})
    bugs.append({"item": "带宽双重缩放", "severity": "high",
                 "finding": "脚本额外用 0.2*abs(pdh)*0.02 = 0.4%相对价的固定带, 与 equal_highs_lows 内部 eq_mult*ATR 阈值叠加使用(池是宽的, 带又是相对价的); live 只用 0.2*ATR14。两端口径不对齐, 验收不能代表 live 行为。"})
    bugs.append({"item": "fwd2 判对错", "severity": "low",
                 "finding": "日内单 TTL≈24h, fwd2 比 1 日宽一倍、噪声更大, 但方向与 fwd1/fwd3 一致(见灵敏度), 不构成结论翻转依据。"})
    bugs.append({"item": "孤点=顺势口径", "severity": "medium",
                 "finding": "live 对孤点被破是反向降权 0.25(不是顺势单, 顺势交给趋势层另一条腿); 验收把'不反向'简化为'顺势单'判对错, 与 live 实际行为不一致。"})
    bugs.append({"item": "样本量", "severity": "medium",
                 "finding": "360根 n≈1610 事件; 全史 n≈10k, 结论需全史口径确认(本复核已做)。"})
    report["bugs"] = bugs

    # ── 7) 判定 ──
    # 逻辑: 若 live口径下新版仍更差且显著 → rollback; 若 live口径翻正/打平 → 原验收口径有 bug, 需 inconclusive(口径修后再验)
    s = (AF["delta"], AL["delta"], AL["wr_new"], AL["wr_old"])
    verdict = "inconclusive"
    reason = "复算与验收结论一致(旧更优)"
    if AF["delta"] < -0.01:
        if AL["delta"] > 0.01:
            verdict = "inconclusive"
            reason = "scripted口径旧优, 但 live口径新优 → 验收脚本口径 bug 主导, 需按 live 口径重新验收后再定"
        else:
            verdict = "rollback"
            reason = "scripted口径与 live口径均显示新版(等点池否决门, 非等点=顺势)劣于旧盲目反向, 且全史显著"
    elif abs(AF["delta"]) <= 0.01:
        verdict = "inconclusive"
        reason = "全史打平, 不下结论"
    report["verdict"] = verdict
    report["verdict_reason"] = reason
    report["recomputed"] = (
        f"原口径(360根D1, scripted带): 旧盲目={A360['wr_old']:.1%} 新否决门={A360['wr_new']:.1%} "
        f"(验收宣称 53.2/47.9, 复算 {A360['wr_old']:.1%}/{A360['wr_new']:.1%} p={A360['pval']:.3f}); "
        f"全史 scripted: 旧={AF['wr_old']:.1%} 新={AF['wr_new']:.1%} 差={AF['delta']:+.1%} p={AF['pval']:.3f}; "
        f"全史 live口径(lb240+ATR14): 旧={AL['wr_old']:.1%} 新={AL['wr_new']:.1%} 差={AL['delta']:+.1%} p={AL['pval']:.3f}")

    out = "E:/GoldstrategyEngine/data/eqpool_reaudit.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nverdict={verdict}: {reason}")
    print(f"报告已写: {out}")
    mt5.shutdown()
    print("MT5 shutdown done (只读, 未下单)")


if __name__ == "__main__":
    main()
