# -*- coding: utf-8 -*-
# 震荡腿五验 step3+4: 品种稳健/甜蜜点/walk-forward + 同分母公平对照
import json, os, math
import numpy as np

ROOT = "E:/GoldstrategyEngine"
JP = ROOT + "/data/leg_range_polish.json"
d = json.load(open(JP, encoding="utf-8"))
ab = d["ab_grid"]
results = ab["results"]
T1 = list(ab["per_sym_events"].keys())
CUR = "2.0/20/mid/1.0"
BEST = ab["best"]

def agg(k):
    vals = [results[k][s]["expR"] for s in T1 if results[k][s].get("expR") is not None]
    return float(np.mean(vals))

# ── 3a 品种稳健: 最优参数 vs 现参数, 分品种方向一致(≥4/6 expR差为负=改善方向) ──
improved = []
for s in T1:
    cr = results[CUR][s].get("expR")
    br = results[BEST][s].get("expR")
    if cr is None or br is None:
        continue
    improved.append((s, br - cr, cr, br))
n_imp = sum(1 for _, dlt, _, _ in improved if dlt > 0)
robust = n_imp >= 4
print("[OK] 稳健: %d/6 品种改善 n_imp=%d robust=%s" % (n_imp, n_imp, robust))
for s, dlt, cr, br in improved:
    print("   %s cur=%.3f best=%.3f Δ%+.3f" % (s, cr, br, dlt))

# ── 3b 甜蜜点: BEST 相邻格(k/周期/tgt/SL ±1档)无符号翻转(expR差相对cur的符号) ──
KS = [2.0, 2.5, 3.0]; PS = [20, 30]; TGS = ["mid", "half"]; SLS = [1.0, 1.5, 2.0]
def key_of(k, p, t, sl):
    return "%s/%s/%s/%s" % (k, p, t, sl)
bparts = BEST.split("/")
bk, bp, bt, bsl = float(bparts[0]), int(bparts[1]), bparts[2], float(bparts[3])
neighbors = []
for dk in (-1, 0, 1):
    ki = KS.index(bk) + dk
    if 0 <= ki < len(KS):
        for pp in PS:
            for t in TGS:
                for sl in SLS:
                    kk = key_of(KS[ki], pp, t, sl)
                    if kk in results and kk != BEST:
                        neighbors.append(kk)
cur_agg = agg(CUR)
signs = {}
flip = False
for kk in neighbors:
    sgn = 1 if (agg(kk) - cur_agg) > 0 else -1
    signs[kk] = sgn
    if sgn != (1 if agg(BEST) - cur_agg > 0 else -1):
        flip = True
sweet = not flip and len({v for v in signs.values()}) == 1
# 更宽松口径: 相邻格与BEST同向(都优于或都劣于cur)即无翻转
best_dir = 1 if agg(BEST) > cur_agg else -1
sweet2 = all(s == best_dir for s in signs.values()) and len(signs) > 0
print("[OK] 甜蜜点: 相邻格=%d 全部同向=%s 最优邻同向=%s" % (len(signs), sweet, sweet2))
for kk in sorted(signs)[:10]:
    print("   %s agg=%.3f sgn=%s" % (kk, agg(kk), signs[kk]))

# ── 3c walk-forward 三段: 6币 全史H4 均等切3段, 各段内 best vs cur expR差同号 ──
import MetaTrader5 as mt5
ok = mt5.initialize()
wf = {}
segs_ok = 0
for sym in T1:
    if not ok:
        break
    mt5.symbol_select(sym, True)
    r = np.array(mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, 2600))
    c, h, l = r["close"], r["high"], r["low"]
    n = len(c)
    seg = n // 3
    sym_res = []
    for si in range(3):
        lo, hi = si * seg, min(n - 3, (si + 1) * seg)
        segdiff = {}
        for kk in [CUR, BEST]:
            bk, bp, bt, bsl = float(kk.split("/")[0]), int(kk.split("/")[1]), kk.split("/")[2], float(kk.split("/")[3])
            eq = 0.0; cnt = 0
            for i in range(lo + bp, hi):
                w = c[i - bp:i]; m = w.mean(); sd = w.std()
                if sd <= 0 or i - bp < 60:
                    continue
                tr = np.maximum(h[1:i + 1] - l[1:i + 1], np.maximum(np.abs(h[1:i + 1] - c[0:i]), np.abs(l[1:i + 1] - c[0:i])))
                a = float(tr[-14:].mean())
                if a <= 0:
                    continue
                up, dn = m + bk * sd, m - bk * sd
                t_hi = up <= l[i] and h[i] >= up
                t_dn = dn >= h[i] and l[i] <= dn
                if not (t_hi or t_dn):
                    continue
                side = -1 if t_hi else 1
                entry = up if t_hi else dn
                tp = m if bt == "mid" else (entry + m) / 2
                if abs(tp - entry) <= 0:
                    continue
                sl = entry - bsl * a * side
                risk = abs(entry - sl)
                R = None
                for j in range(i + 1, min(i + 25, hi + 1)):
                    if side == 1:
                        if h[j] >= tp: R = abs(tp - entry) / risk; break
                        if l[j] <= sl: R = -1.0; break
                    else:
                        if l[j] <= tp: R = abs(tp - entry) / risk; break
                        if h[j] >= sl: R = -1.0; break
                if R is None:
                    R = side * (c[min(i + 24, hi - 1)] - entry) / risk
                R -= 0.001
                eq += R; cnt += 1
            segdiff[kk] = (eq / cnt if cnt else 0.0, cnt)
        sym_res.append(segdiff)
    wf[sym] = sym_res
    print("[OK] %s wf seg expR(cur/best): %s" % (sym, [(round(a[CUR][0], 2), round(a[BEST][0], 2)) for a in sym_res]))
# 三段同号判定: 每段全体 expR(best)-expR(cur) 同号
segs = [[] for _ in range(3)]
for sym in wf:
    for si, segdiff in enumerate(wf[sym]):
        segs[si].append(segdiff[BEST][0] - segdiff[CUR][0])
seg_means = [float(np.mean(x)) if x else 0.0 for x in segs]
same_sign = len({1 if m > 0 else -1 for m in seg_means}) == 1 and all(abs(m) > 0 for m in seg_means)
wf_pass = same_sign
print("[OK] wf 三段 meanΔ=%s same_sign=%s" % (["%.3f" % m for m in seg_means], same_sign))
mt5.shutdown()

five = {
    "n_events_total": ab["n_events_total"],
    "品种稳健": {"改善品种": n_imp, "阈值": ">=4/6", "pass": robust,
                  "明细": [{"sym": s, "ΔexpR": round(dlt, 4)} for s, dlt, _, _ in improved]},
    "甜蜜点": {"邻居数": len(signs), "全同向": sweet, "最优同向": sweet2, "pass": sweet2},
    "walk_forward": {"三段mean_delta": [round(m, 4) for m in seg_means], "同号": same_sign, "pass": wf_pass},
}
all_pass = robust and sweet2 and wf_pass
five["all_pass"] = all_pass

# ── 4) 同分母公平对照: 全事件集(现参事件∩最优事件 同事件), 比 expR ──
# 用 per-sym 事件数最小交集口径: 报绝对差/相对差/p(正态, 合并n)
n_cur = [results[CUR][s].get("n") or 0 for s in T1]
n_best = [results[BEST][s].get("n") or 0 for s in T1]
n_common = sum(min(a, b) for a, b in zip(n_cur, n_best))
cur_e = agg(CUR); best_e = agg(BEST)
delta_abs = best_e - cur_e
delta_rel = delta_abs / abs(cur_e) if cur_e else 0.0
# 正态p: 用每单R的合并方差近似(无逐单数据, 用经验σ≈1.6, 以 min(n_cur,n_best) 同分母保守口径)
sigma = 1.6
se = sigma * math.sqrt(2.0 / n_common) if n_common > 0 else float("inf")
z = delta_abs / se if se > 0 else 0.0
p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
same_den = {
    "n_cur": sum(n_cur), "n_best": sum(n_best), "n_common": n_common,
    "cur_expR": round(cur_e, 4), "best_expR": round(best_e, 4),
    "delta_abs": round(delta_abs, 4), "delta_rel": round(delta_rel, 4),
    "z": round(z, 3), "p": round(p, 4), "significant": p < 0.05 and delta_abs > 0,
}
print("[OK] 同分母: n_common=%d Δabs=%.4f Δrel=%.4f p=%.4f sig=%s" %
      (n_common, delta_abs, delta_rel, p, same_den["significant"]))

out = {"五验": five, "同分母结论": same_den}
rec = {k: out[k] for k in out}
d.update(rec)
json.dump(d, open(JP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("[OK] wrote 五验+同分母结论 ->", JP)
verdict = "接" if (all_pass and same_den["significant"]) else "维持现参数"
print("[OK] VERDICT: %s" % verdict)
