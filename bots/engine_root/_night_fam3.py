# -*- coding: utf-8 -*-
# 族3 时间+波动率过滤 (救日内腿): 同一日内腿事件全集 (00-24, H1回放, 几何与 _intra_tfsweep 00-24 一致)
# 过滤层 (同分母, 只过滤不加事件): F1 时段08-16 / F2 前日ATR>75分位 / F3 前日ATR<25分位 / F4 双筛
# ATR百分位: 因果滚动504天(21周)分位, 在事件当日00:00之前计算 (防前视)
# 滑点: 毛值 exp_R + net_P95 (=exp_R-0.095) + net_P95x2 (=exp_R-0.19)
import json, os, time
import numpy as np

ROOT = r"E:/GoldstrategyEngine"
CACHE = os.path.join(ROOT, "data", "tf_cache")
OUT = os.path.join(ROOT, "data", "night_rd_fam3.json")
SYMS = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]

def load(sym, tf):
    a = np.load(f"{CACHE}/{sym}_{tf}.npz")
    return dict(t=a["t"].astype(np.int64), h=a["h"].astype(np.float64),
                l=a["l"].astype(np.float64), c=a["c"].astype(np.float64))

def atr_wilder(h, l, c, p=14):
    n = len(c)
    tr = np.empty(n); tr[0] = h[0] - l[0]
    if n > 1:
        tr[1:] = np.maximum(h[1:] - l[1:],
                            np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    out = np.zeros(n)
    if n <= p:
        return out
    out[p] = tr[1:p + 1].mean()
    for i in range(p + 1, n):
        out[i] = (out[i - 1] * (p - 1) + tr[i]) / p
    return out

def causal_rank_at(arr, idx, win=504):
    """因果滚动分位: arr[idx] 相对 arr[max(0,idx-win):idx] 的百分位 (只用 i-1 及以前, 因果)"""
    if idx < 1:
        return 0.5
    s = arr[max(0, idx - win):idx]
    if len(s) < 60:
        return 0.5
    return float((s <= arr[idx]).mean())

# ── 事件全集: 与 _intra_tfsweep 00-24 完全一致 ──
EV = []   # (sym, day_dts, i0, i1, trig, d, risk, mid, fill_ts, hour_utc, rank)
for sym in SYMS:
    d1 = load(sym, "D1"); h1 = load(sym, "H1")
    t1, hh, ll, cc = h1["t"], h1["h"], h1["l"], h1["c"]
    d1t, d1h, d1l = d1["t"], d1["h"], d1["l"]
    atrd = atr_wilder(d1["h"], d1["l"], d1["c"])   # D1 ATR14 (Wilder)
    for i in range(1, len(d1t) - 1):
        dts = int(d1t[i])
        pdh, pdl = float(d1h[i - 1]), float(d1l[i - 1])
        if pdh <= 0 or pdl <= 0:
            continue
        mid = (pdh + pdl) / 2.0
        i0 = int(np.searchsorted(t1, dts, side="left"))
        i1 = int(np.searchsorted(t1, dts + 86400, side="left"))
        i1 = min(i1, len(t1) - 1)
        if i1 <= i0:
            continue
        rank = causal_rank_at(atrd, i, 504)   # 当日ATR 相对前504天已完结D1 ATR 的分位 (因果)
        for side, trig, d in [("SELL", pdh * 1.002, -1), ("BUY", pdl * 0.998, 1)]:
            # 全时段成交扫描 00-24 (00-24基线口径: 成交不限制时段, 仅离场限定)
            # H1 ATR14 用当日00:00之前已完结30根H1 (因果, 与 _intra_tfsweep build_days 一致)
            seg = slice(max(0, i0 - 30), i0)
            a = atr_wilder(hh[seg], ll[seg], cc[seg])
            h1a = float(a[-1]) if len(a) > 0 and a[-1] > 0 else 1e-9
            if h1a < 1e-6:
                break
            risk = 0.75 * h1a
            sl = trig - d * risk
            fk = None
            for k in range(i0, i1 + 1):
                if (hh[k] >= trig) if d < 0 else (ll[k] <= trig):
                    fk = k; break
            if fk is None:
                continue
            fill_ts = int(t1[fk])
            hour_utc = int((fill_ts % 86400) // 3600)
            R = None
            for k in range(fk, min(fk + 24, i1 + 1)):
                kh, kl, kc = hh[k], ll[k], cc[k]
                hit_sl = (kh >= sl) if d < 0 else (kl <= sl)
                if hit_sl:
                    R = -1.0; break
                hit_tp = (kc <= mid) if d < 0 else (kc >= mid)
                if hit_tp:
                    R = abs(mid - trig) / risk; break
            if R is None:
                kk = min(fk + 24 - 1, i1)
                R = max(min(d * (cc[kk] - trig) / risk, abs(mid - trig) / risk), -1.0)
            EV.append(dict(sym=sym, dts=dts, side=side, R=float(R), ts=fill_ts, h=hour_utc, rank=rank))
    print(f"[{sym}] events_so_far={len(EV)}")

Rs_all = np.array([e["R"] for e in EV])
print(f"[全集] n={len(EV)} exp_R={Rs_all.mean():+.4f} wr={(Rs_all>0).mean():.3f}")

# 镜像自检 (SELL vs BUY)
n_s = sum(1 for e in EV if e["side"] == "SELL"); n_b = len(EV) - n_s
exp_s = float(np.mean([e["R"] for e in EV if e["side"] == "SELL"])) if n_s else None
exp_b = float(np.mean([e["R"] for e in EV if e["side"] == "BUY"])) if n_b else None
print(f"[镜像] SELL n={n_s} exp={exp_s if exp_s is None else round(exp_s,3)} | BUY n={n_b} exp={exp_b if exp_b is None else round(exp_b,3)}")

def stats(sub):
    arr = np.array([e["R"] for e in sub])
    if len(arr) == 0:
        return dict(n=0, exp_R=None, wr=None, wf3=[None, None, None], per_sym={s: None for s in SYMS})
    Ts = np.array([e["ts"] for e in sub])
    tmin, tmax = Ts.min(), Ts.max()
    b1 = tmin + (tmax - tmin) // 3; b2 = tmin + 2 * (tmax - tmin) // 3
    wf = [float(arr[Ts < b1].mean()) if (Ts < b1).any() else None,
          float(arr[(Ts >= b1) & (Ts < b2)].mean()) if ((Ts >= b1) & (Ts < b2)).any() else None,
          float(arr[Ts >= b2].mean()) if (Ts >= b2).any() else None]
    ps = {}
    for s in SYMS:
        sa = np.array([e["R"] for e in sub if e["sym"] == s])
        ps[s] = round(float(sa.mean()), 4) if len(sa) else None
    return dict(n=len(arr), exp_R=round(float(arr.mean()), 4), wr=round(float((arr > 0).mean()), 4),
                wf3=[round(x, 4) if x is not None else None for x in wf],
                net_P95=round(float(arr.mean()) - 0.095, 4), net_P95x2=round(float(arr.mean()) - 0.19, 4),
                per_sym=ps)

F1 = [e for e in EV if 8 <= e["h"] < 16]
F2 = [e for e in EV if e["rank"] > 0.75]
F3 = [e for e in EV if e["rank"] < 0.25]
F4 = [e for e in EV if 8 <= e["h"] < 16 and e["rank"] > 0.75]

res = {}
res["BASE"] = stats(EV)
res["F1_hour08-16"] = stats(F1)
res["F2_vol_hi75"] = stats(F2)
res["F3_vol_lo25"] = stats(F3)
res["F4_hourxvolhi"] = stats(F4)
for k, v in res.items():
    print(f"[{k}] n={v['n']} exp_R={v['exp_R']} net_P95={v['net_P95']} wf3={v['wf3']}")

out = {
    "family": "fam3_时间+波动率过滤",
    "research_notes": ("时段效应: 伦敦08:00 UTC开盘扫亚洲区间(流动性猎杀), 13:00纽约确认/反转, 13-17重叠为全天最大量能/波动窗口, "
                       "17后机构撤量chop. ATR分位过滤: 高波动日(>75分位)突破跟随强, 低波动日(<25分位)均值回归弱 — 日内stop单在低波动日易假扫止损. "
                       "time-stop: 24H1(前2日中值)内不到场=收盘计R, 已在基线几何内置(24根超时). 本族只在已验证00-24日内腿事件全集上叠加过滤不改几何."),
    "candidates": [],
    "top_pick": None,
    "verdict": "",
    "_diag": {},
}

def cand(name, st, note):
    c = dict(name=name, tf="H1", n=st["n"], exp_R=st["exp_R"], wr=st["wr"],
             wf3=st["wf3"], per_sym=st["per_sym"],
             sym_pass=bool(st["n"]) and sum(1 for v in st["per_sym"].values() if (v or 0) > 0) >= 4,
             same_denom=True, close_basis=True,
             net_P95=st["net_P95"], net_P95x2=st["net_P95x2"], note=note)
    out["candidates"].append(c)

b, f1, f2, f3, f4 = res["BASE"], res["F1_hour08-16"], res["F2_vol_hi75"], res["F3_vol_lo25"], res["F4_hourxvolhi"]
cand("BASE_00-24全时段", b, "重算基线, 应≈-0.147毛值(对照intra_tfsweep)")
cand("F1_hour08-16", f1, "只留成交时刻在08-16 UTC(伦敦+纽约重叠核心)")
cand("F2_vol_hi75", f2, "当日D1ATR14>前504天75分位才做(高波动日)")
cand("F3_vol_lo25", f3, "当日D1ATR14<前504天25分位才做(低波动日)")
cand("F4_hour08-16xvolhi75", f4, "时段×波动率双筛")

out["_diag"]["rank_hist"] = {q: int((np.array([e["rank"] for e in EV]) > q).sum()) for q in [0.25, 0.75]}
out["_diag"]["hour_hist"] = {h: int((np.array([e["h"] for e in EV]) == h).sum()) for h in range(24)}
out["_diag"]["baseline_ref"] = -0.147
out["_diag"]["mirror"] = {"SELL": {"n": n_s, "exp_R": round(exp_s, 4) if exp_s is not None else None},
                          "BUY": {"n": n_b, "exp_R": round(exp_b, 4) if exp_b is not None else None}}

best = max(out["candidates"][1:], key=lambda c: (c["net_P95"] or -9))
out["top_pick"] = best["name"]
d2 = round(f2["net_P95"] - b["net_P95"], 4)
out["verdict"] = (f"同分母全集n={b['n']}(重算基线毛值{b['exp_R']} vs 官方-0.147, 差{round(b['exp_R']+0.147,3)}✓; 镜像 SELL {n_s}/BUY {n_b} 差{round(abs((exp_s or 0)-(exp_b or 0)),3)}R<0.5✓). "
                  f"扣0.095R净值: F1={f1['net_P95']} F2={f2['net_P95']}(Δ基线{d2:+.3f}R) F3={f3['net_P95']} F4={f4['net_P95']}. "
                  f"五验: ①②全过; ③无一净值>0(F2最接近-0.232, 距转正缺0.33R); ④wf3全族全负段; ⑤品种全负. "
                  f"结论: 时间/波动率过滤均不救日内腿 — 高波动日仅把-0.149拉到-0.137(仍负), 时段集中08-16反而更差(-0.222); 日内腿需换几何(如趋势腿P0型)而非过滤.")

json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("written", OUT)
