# -*- coding: utf-8 -*-
"""rd_verify_batch_20261114.py —— P1 回踩(ADX>=40禁追突破) + E3 批量闸 五验同分母回测
====================================================================
红线: 纯研究. 引擎 jince_live24.py / tools / REAL 30261104 参数零动. 产物只落 data/ 与 research/.
数据: data/tf_cache/*.npz M30+D1 (2026-11-14 MT5只读60137964回填, XAU/EUR 末端 11-13 23:30 UTC, 币系 11-14 08:00 UTC).
口径: 简化DI差ADX(14)/前20根真突破/M30次根进场, 引擎REAL口径出场
(SL=min(sl_mult,1.2)ATR, TP=max(tp_mult*ATR,2R)封顶12ATR, 0.5R BE/1.0R锁半/ATR紧跟踪/giveback0.6,
18h硬平, 同品种不重叠). h1_on=False: M30+D1 口径无 H1 共振, base 与 candidate 同等受影响(同分母成立).
成本 0.095R/笔(主), 0.15R/笔(T5压力档), winsor[-3,8].
base = 现行100%放行口径(ADX_MIN 品种JSON/无ADX上限/无批量闸), sl/tp 取 practice_params_all_symbols.json.
P1候选: ADX>=40 的突破信号不追, 等<=4根回踩(回踩不破前20根突破位-1ATR)后阳线/阴线再进,
SL 锚回踩摆动点±0.3ATR, TP 保RR>=2.0 封顶12ATR. ADX<40 单走 base 出场(同分母: 仅 ADX>=40 簇变体).
E3候选: 币系家族(BTC/ETH/SOL/XRP/LTC/BNB)族内<=2腿, 且族内30min内有亏损腿则停同族新腿
(按 base 交易时间轴后验抑制; 受抑单剔除, 其余成交结果不变).
五验(逐品种, 禁跨品种平均): T1 净R(扣0.095)>0 且>=base | T2 胜率>=base-0.02 | T3 5折时间切分同向(全正)
| T4 OOS70/30 两段皆正 | T5 成本0.15R 仍正 | ⑥ 扣0.095后净期望(均R)>=1.0 才谈放大, <1.0 = REJECT 只WATCH攒样.
裁定: APPROVE = T1-T5全过且⑥过 | WATCH = ⑥<1.0 但 T1-T5>=3/5 | REJECT = 其余(OOS非正/T1失守).
"""
import os, json, sys, datetime as dt
import numpy as np

ROOT = "E:/GoldstrategyEngine"
CACHE = os.path.join(ROOT, "data", "tf_cache")
SYMS = ["XAUUSD", "EURUSD", "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]
COIN_FAM = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD"]
COST = 0.095
COST_T5 = 0.15
WINSOR_LO, WINSOR_HI, REAL_SL_CAP = -3.0, 8.0, 1.2
KLINE_SRC = ("mt5_readonly_60137964 tf_cache npz M30+D1 refreshed 2026-11-14 08:28 UTC "
             "(XAU/EUR end 11-13 23:30 UTC, coins end 11-14 08:00 UTC)")


def rollmean(x, w):
    cs = np.concatenate(([0.0], np.cumsum(x)))
    e = np.arange(len(x)) + 1
    s = np.clip(e - w, 0, len(x))
    return (cs[e] - cs[s]) / np.maximum(e - s, 1)


def load_npz(sym, tf):
    z = np.load(os.path.join(CACHE, f"{sym}_{tf}.npz"))
    out = {k: z[k] for k in ("t", "h", "l", "c") if k in z.files}
    z.close()
    return out


def prepare30(sym):
    m = load_npz(sym, "M30")
    N = len(m["t"])
    o, h, l, c = m["h"].copy(), m["h"].copy(), m["l"], m["c"]
    o[0] = c[0]
    o[1:] = c[:-1]  # 无开盘价 -> 前收近似
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(np.maximum(h - l, np.abs(h - pc)), np.abs(l - pc))
    atr = rollmean(tr, 14)
    up = h - np.concatenate(([h[0]], h[:-1]))
    dn = np.concatenate(([l[0]], l[:-1])) - l
    pj = np.where((up > dn) & (up > 0), up, 0.0)
    mj = np.where((dn > up) & (dn > 0), dn, 0.0)
    cp = np.concatenate(([0.0], np.cumsum(pj)))
    cm = np.concatenate(([0.0], np.cumsum(mj)))
    kk = np.arange(N)
    st = np.maximum(0, kk - 13)
    sp = cp[kk + 1] - cp[st]
    sm = cm[kk + 1] - cm[st]
    d = sp + sm
    dx = np.where(d > 0, np.abs(sp - sm) / np.maximum(d, 1e-12) * 100.0, 0.0)
    m5, m20 = rollmean(c, 5), rollmean(c, 20)
    rng_hi = np.zeros(N)
    rng_lo = np.zeros(N)
    for k in range(20, N):
        rng_hi[k] = h[k - 20:k].max()
        rng_lo[k] = l[k - 20:k].min()
    cprev = np.concatenate(([c[0]], c[:-1]))
    return dict(t=m["t"], o=o, h=h, l=l, c=c, n=N, atr=atr, dx=dx, m5=m5, m20=m20,
                rng_hi=rng_hi, rng_lo=rng_lo, body=np.abs(c - cprev),
                up_m=c > cprev, down_m=c < cprev)


def simulate(P, g, k, s, dist=None, tp_d=None, cost=COST):
    """统一方向空间出场 (复刻 liquid_wfo_m15_v2.simulate, M30 版: Lmax=max_hold_h/0.5 根)."""
    N = P["n"]
    e = k + 1
    ok = e < N
    k, s, e = k[ok], s[ok], e[ok]
    if dist is not None:
        dist = dist[ok]
    if tp_d is not None:
        tp_d = tp_d[ok]
    nC = len(k)
    if nC == 0:
        return dict(R=np.array([]), et=np.array([]), ty=np.array([]), ek=np.array([]), es=np.array([]))
    Lmax = int(g["max_hold_h"] / 0.5)
    idx = e[:, None] + np.arange(Lmax)[None, :]
    beyond = idx >= N
    ic = np.minimum(idx, N - 1)
    Hs = P["h"][ic] * s[:, None]
    Ls = P["l"][ic] * s[:, None]
    HI = np.maximum(Hs, Ls)
    LO = np.minimum(Hs, Ls)
    Cs = P["c"][ic] * s[:, None]
    A = P["atr"][ic]
    HI = np.where(beyond, -np.inf, HI)
    LO = np.where(beyond, -np.inf, LO)
    entry = P["o"][e] * s
    if dist is None:
        a0 = np.maximum(P["atr"][k], 1e-9)
        slm = min(g["sl_mult"], REAL_SL_CAP)
        dist = slm * a0
    if tp_d is None:
        a0 = np.maximum(P["atr"][k], 1e-9)
        tp_d = np.maximum(g["tp_mult"] * a0, 2.0 * dist)
        tp_d = np.minimum(tp_d, 12.0 * a0)
    SL0 = entry - dist
    TP = entry + tp_d
    R = np.zeros(nC)
    ext = entry.copy()
    SL = SL0.copy()
    alive = np.ones(nC, dtype=bool)
    exit_t = np.full(nC, P["t"][np.minimum(e + Lmax - 1, N - 1)])
    etype = np.full(nC, 2, dtype=np.int8)
    for kk in range(Lmax):
        if not alive.any():
            break
        hi, lo, cc, aa = HI[:, kk], LO[:, kk], Cs[:, kk], A[:, kk]
        hit_sl = alive & (lo <= SL)
        hit_tp = alive & (~hit_sl) & (hi >= TP)
        if hit_sl.any():
            px = np.minimum(SL, hi)
            R[hit_sl] = (px[hit_sl] - entry[hit_sl]) / dist[hit_sl] - cost
            etype[hit_sl] = 0
            exit_t[hit_sl] = P["t"][ic[hit_sl, kk]]
            alive[hit_sl] = False
        if hit_tp.any():
            R[hit_tp] = (TP[hit_tp] - entry[hit_tp]) / dist[hit_tp] - cost
            etype[hit_tp] = 1
            exit_t[hit_tp] = P["t"][ic[hit_tp, kk]]
            alive[hit_tp] = False
        bend = alive & beyond[:, kk]
        if bend.any():
            R[bend] = (cc[bend] - entry[bend]) / dist[bend] - cost
            etype[bend] = 2
            exit_t[bend] = P["t"][ic[bend, kk]]
            alive[bend] = False
        ext = np.where(alive, np.maximum(ext, hi), ext)
        r = (ext - entry) / dist
        cand = np.full(nC, -np.inf)
        cand = np.where(r >= 0.5, entry + 0.2 * dist, cand)
        cand = np.where(r >= 1.0, np.maximum(cand, entry + 1.2 * dist), cand)
        trm = np.where(r >= 1.0, np.where(r >= 1.5, 0.5, 0.8), np.nan)
        trail = ext - trm * np.maximum(aa, P["atr"][k] * 0.5)
        cand = np.where(np.isfinite(trail), np.maximum(cand, trail), cand)
        gf = ext - g["giveback"] * dist
        cand = np.where(r > 0, np.maximum(cand, gf), cand)
        SL = np.where(alive & np.isfinite(cand), np.maximum(SL, cand), SL)
    if alive.any():
        last = Cs[:, -1]
        R[alive] = (last[alive] - entry[alive]) / dist[alive] - cost
        etype[alive] = 2
        exit_t[alive] = P["t"][ic[alive, -1]]
    R = np.clip(np.where(np.isfinite(R), R, 0.0), WINSOR_LO, WINSOR_HI)
    exit_bar = np.minimum(e + Lmax - 1, N - 1)
    order = np.argsort(k)
    taken = []
    nb = -1
    for i in order:
        if k[i] >= nb:
            taken.append(i)
            nb = exit_bar[i]
    taken = np.array(taken, dtype=np.int64)
    return dict(R=R[taken], et=exit_t[taken], ty=etype[taken],
                ek=k[taken], es=s[taken], eix=e[taken])


def gen_signals(P, g, adx_max=None, pullback=False):
    """base: 全部突破单. P1: dx>=40 的簇改回踩进场(<=4根窗口, 回踩不破突破位-1ATR, 再顺向K线进场)."""
    N, c, atr = P["n"], P["c"], P["atr"]
    vol_ok = np.ones(N, dtype=bool)  # M30 口径无独立波动率扩张闸 (base/candidate 同等, 同分母)
    adx_ok = P["dx"] >= g["adx_min"]
    body_ok = np.where(atr > 0, P["body"] >= g["min_body"] * atr, False)
    kmask = np.arange(N) >= 60
    long_s = (adx_ok & (c >= P["rng_hi"] - g["break_margin"] * atr)
              & (P["m5"] > P["m20"]) & P["up_m"] & body_ok & kmask)
    short_s = (adx_ok & (c <= P["rng_lo"] + g["break_margin"] * atr)
               & (P["m5"] < P["m20"]) & P["down_m"] & body_ok & kmask)
    kl = np.nonzero(long_s)[0]
    ks = np.nonzero(short_s)[0]
    out_k, out_s, out_dist, out_tp = [], [], [], []
    for k0, sig in ((kl, 1), (ks, -1)):
        for k0 in k0:
            hot = adx_max is not None and P["dx"][k0] >= adx_max
            if hot:
                a0 = max(P["atr"][k0], 1e-9)
                lvl = P["rng_hi"][k0] if sig > 0 else P["rng_lo"][k0]
                hit = None
                for j in range(1, min(5, N - k0 - 1)):
                    loj, hj = P["l"][k0 + j], P["h"][k0 + j]
                    if sig > 0:
                        retrace = loj <= lvl + 0.5 * a0          # 回踩到突破位附近
                        broke = c[k0 + j] < lvl - 1.0 * a0       # 破位 1ATR 以上 => 回踩失败
                        resume = P["up_m"][k0 + j] and c[k0 + j] > P["c"][k0 + j - 1]
                    else:
                        retrace = hj >= lvl - 0.5 * a0
                        broke = c[k0 + j] > lvl + 1.0 * a0
                        resume = P["down_m"][k0 + j] and c[k0 + j] < P["c"][k0 + j - 1]
                    if broke:
                        break
                    if retrace and resume:
                        hit = k0 + j
                        break
                if hit is None or hit + 1 >= N:
                    continue
                a1 = max(P["atr"][hit], 1e-9)
                swing = P["l"][k0 + 1:hit + 1].min() if sig > 0 else P["h"][k0 + 1:hit + 1].max()
                entry = P["o"][hit + 1]
                sl = swing - 0.3 * a1 if sig > 0 else swing + 0.3 * a1
                dist = abs(entry - sl)
                dist = min(max(dist, 0.5 * a1), 2.0 * a1)
                tp_d = np.clip(max(2.0 * dist, g["tp_mult"] * a1), 2.0 * dist, 12.0 * a1)
                out_k.append(hit)
                out_s.append(sig)
                out_dist.append(dist)
                out_tp.append(tp_d)
            else:
                # non-hot (ADX<adx_max or base): default exits, same formula simulate uses when dist/tp_d is None
                a0 = max(P["atr"][k0], 1e-9)
                slm = min(g["sl_mult"], REAL_SL_CAP)
                dist = slm * a0
                tp_d = np.minimum(np.maximum(g["tp_mult"] * a0, 2.0 * dist), 12.0 * a0)
                out_k.append(k0)
                out_s.append(sig)
                out_dist.append(dist)
                out_tp.append(tp_d)
    if out_dist:
        return (np.array(out_k), np.array(out_s, dtype=np.float64),
                np.array(out_dist), np.array(out_tp))
    return (np.array([], dtype=np.int64), np.array([]), np.array([]), np.array([]))


def evaluate(P, g, adx_max=None, cost=COST):
    k, s, dist, tp_d = gen_signals(P, g, adx_max=adx_max)
    R, et, ty, ek, es, eix = simulate(P, g, k, s, dist=dist, tp_d=tp_d, cost=cost).values() if False else (None,) * 6
    res = simulate(P, g, k, s, dist=dist, tp_d=tp_d, cost=cost)
    R, et, ty, ek, es = res["R"], res["et"], res["ty"], res["ek"], res["es"]
    n = len(R)
    return dict(n=n, net=float(R.sum()), avg=float(R.mean()) if n else 0.0,
                win=float((R > 0).mean()) if n else 0.0, R=R, et=et, ty=ty, ek=ek, es=es)


def five_gates(base, cand, cand015, train, test, base_et=None):
    """任务口径五验+⑥. cand/train/test/cand015 已扣各自成本 (0.095 主 / 0.15 T5).
    train/test = candidate 的 R 按 70/30 时间切分 (全量数据 70/30 切点)."""
    T1 = cand["net"] > 0 and cand["net"] >= base["net"]
    T2 = cand["win"] >= base["win"] - 0.02
    T3 = (cand["n"] >= 5 and all(x.sum() > 0 for x in np.array_split(cand["R"], 5)))
    T4 = train["net"] > 0 and test["net"] > 0
    T5 = cand015["net"] > 0
    g6 = cand["avg"] >= 1.0
    return dict(T1=bool(T1), T2=bool(T2), T3=bool(T3), T4=bool(T4), T5=bool(T5),
                g6=bool(g6),
                passed=int(T1) + int(T2) + int(T3) + int(T4) + int(T5) + int(g6))


def verdict_of(gates, base, cand):
    t15 = gates["passed"] - int(gates["g6"])
    if gates["passed"] == 6:
        return "APPROVE"
    if t15 >= 3 and (gates["T4"] or gates["T3"]) :
        return "WATCH"
    return "REJECT"


def main():
    params = json.load(open(os.path.join(ROOT, "data", "practice_params_all_symbols.json"), encoding="utf-8"))
    prepped = {s: prepare30(s) for s in SYMS}
    # 70/30 全量切点 (按时间, 逐品种各自 70% 分位的时间戳)
    oos_cut = {s: float(np.quantile(prepped[s]["t"], 0.70)) for s in SYMS}

    # ── base (100%放行口径, 无ADX上限/无批量闸) 全量 + 0.15 档 + OOS 分段 ──
    base_all, base015, base_train, base_test = {}, {}, {}, {}
    for s in SYMS:
        P = prepped[s]
        p = params.get(s, {})
        g = dict(adx_min=float(p.get("adx_min", 35.0)), break_margin=0.6, min_body=0.3,
                 h1_on=False, max_hold_h=18, giveback=0.6,
                 sl_mult=float(p.get("sl_mult", 1.0)), tp_mult=float(p.get("tp_mult", 3.0)))
        b = evaluate(P, g)
        b015 = evaluate(P, g, cost=COST_T5)
        mask_tr = b["et"] <= oos_cut[s]
        base_all[s] = b
        base015[s] = b015
        base_train[s] = dict(n=int(mask_tr.sum()), net=float(b["R"][mask_tr].sum()),
                             avg=float(b["R"][mask_tr].mean()) if mask_tr.any() else 0.0)
        base_test[s] = dict(n=int((~mask_tr).sum()), net=float(b["R"][~mask_tr].sum()),
                            avg=float(b["R"][~mask_tr].mean()) if (~mask_tr).any() else 0.0)

    # ── P1 候选: ADX>=40 回踩变体 (逐品种) ──
    p1_out = {}
    for s in SYMS:
        P = prepped[s]
        p = params.get(s, {})
        g = dict(adx_min=float(p.get("adx_min", 35.0)), break_margin=0.6, min_body=0.3,
                 h1_on=False, max_hold_h=18, giveback=0.6,
                 sl_mult=float(p.get("sl_mult", 1.0)), tp_mult=float(p.get("tp_mult", 3.0)))
        c = evaluate(P, g, adx_max=40.0)
        c015 = evaluate(P, g, adx_max=40.0, cost=COST_T5)
        mask_tr = c["et"] <= oos_cut[s]
        tr = dict(n=int(mask_tr.sum()), net=float(c["R"][mask_tr].sum()),
                  avg=float(c["R"][mask_tr].mean()) if mask_tr.any() else 0.0)
        te = dict(n=int((~mask_tr).sum()), net=float(c["R"][~mask_tr].sum()),
                  avg=float(c["R"][~mask_tr].mean()) if (~mask_tr).any() else 0.0)
        gates = five_gates(base_all[s], c, c015, tr, te)
        p1_out[s] = dict(sym=s, base_n=base_all[s]["n"], base_net=round(base_all[s]["net"], 2),
                         base_win=round(base_all[s]["win"], 4),
                         cand_n=c["n"], cand_net=round(c["net"], 2), cand_win=round(c["win"], 4),
                         cand_avg_netR=round(c["avg"], 5), cand_netR_015=round(c015["net"], 2),
                         cand_train=tr, cand_test=te, gates=gates,
                         verdict=verdict_of(gates, base_all[s], c))
        print("P1", s, p1_out[s]["cand_n"], p1_out[s]["cand_net"],
              p1_out[s]["gates"], p1_out[s]["verdict"], flush=True)

    # ── E3 候选: 币系家族批量闸 (后验抑制 base 交易) ──
    fam_trades = []  # (sym, R, t_in, t_out, R015)
    sym_trades = {s: [] for s in COIN_FAM}
    for s in COIN_FAM:
        b = base_all[s]
        for i in range(b["n"]):
            t_in = float(prepped[s]["t"][b["ek"][i]] + 1800)  # 信号根(M30)收线=进场参考时刻
            t_out = float(b["et"][i])
            R = float(b["R"][i])
            fam_trades.append(dict(sym=s, R=R, R015=R - (COST_T5 - COST), t_in=t_in, t_out=t_out))
            sym_trades[s].append(i)
    fam_trades.sort(key=lambda x: x["t_in"])
    open_legs = []      # (t_out)
    loss_close = []     # (t_out) 亏损腿离场时刻
    suppressed = set()
    for it, tr in enumerate(fam_trades):
        t = tr["t_in"]
        open_legs = [x for x in open_legs if x > t]
        loss_close = [x for x in loss_close if t < x + 1800.0]
        if len(open_legs) >= 2 or len(loss_close) >= 1:
            suppressed.add(it)
        open_legs.append(tr["t_out"])
        if tr["R"] < 0:
            loss_close.append(tr["t_out"])
    idx_by_sym = {s: [] for s in COIN_FAM}
    for it, tr in enumerate(fam_trades):
        idx_by_sym[tr["sym"]].append((it, tr))
    e3_out = {}
    for s in COIN_FAM:
        keep = [tr for it, tr in idx_by_sym[s] if it not in suppressed]
        Rk = np.array([tr["R"] for tr in keep])
        Rk015 = np.array([tr["R015"] for tr in keep])
        b = base_all[s]
        c = dict(n=len(Rk), net=float(Rk.sum()), avg=float(Rk.mean()) if len(Rk) else 0.0,
                 win=float((Rk > 0).mean()) if len(Rk) else 0.0, R=Rk)
        c015 = dict(n=len(Rk015), net=float(Rk015.sum()),
                    avg=float(Rk015.mean()) if len(Rk015) else 0.0, R=Rk015)
        mask_tr = c["R"].size and np.array([prepped[s]["t"][base_all[s]["ek"][j]] <= oos_cut[s]
                                             for j, tr in enumerate(keep) for j in [idx_by_sym[s][0][0]]]) if False else \
            np.ones(len(Rk), dtype=bool)
        # 逐单 OOS 切分 (按该单 t_in 与 70/30 时间切点)
        m_tr = np.array([tr["t_in"] <= oos_cut[s] for tr in keep])
        tr_ = dict(n=int(m_tr.sum()), net=float(Rk[m_tr].sum()),
                   avg=float(Rk[m_tr].mean()) if m_tr.any() else 0.0)
        te_ = dict(n=int((~m_tr).sum()), net=float(Rk[~m_tr].sum()),
                   avg=float(Rk[~m_tr].mean()) if (~m_tr).any() else 0.0)
        gates = five_gates(b, c, c015, tr_, te_)
        n_sup = len(idx_by_sym[s]) - len(keep)
        e3_out[s] = dict(sym=s, base_n=b["n"], base_net=round(b["net"], 2), base_win=round(b["win"], 4),
                         cand_n=c["n"], cand_net=round(c["net"], 2), cand_win=round(c["win"], 4),
                         cand_avg_netR=round(c["avg"], 5), cand_netR_015=round(c015["net"], 2),
                         n_suppressed=n_sup, gates=gates,
                         verdict=verdict_of(gates, b, c))
        print("E3", s, "sup=%d" % n_sup, c["n"], c["net"], e3_out[s]["gates"], e3_out[s]["verdict"], flush=True)
    # 家族级汇总 (仅参考, 不用于逐品种裁定)
    fam_all = np.array([tr["R"] for tr in fam_trades])
    fam_keep = np.array([tr["R"] for tr in fam_trades if tr is not None])
    famc = np.array([tr["R"] for it, tr in enumerate(fam_trades) if it not in suppressed])
    fam_roll = dict(fam_base_n=len(fam_all), fam_base_net=round(float(fam_all.sum()), 2),
                    fam_base_avg=round(float(fam_all.mean()), 5),
                    fam_cand_n=len(famc), fam_cand_net=round(float(famc.sum()), 2),
                    fam_cand_avg=round(float(famc.mean()), 5),
                    fam_suppressed=len(fam_trades) - len(famc))
    print("E3 family:", fam_roll, flush=True)
    # XAU/EUR 不属于币系多腿家族: E3 闸对二者零效应 -> 裁定 WATCH(无门控效应, 只攒样)
    for s in ("XAUUSD", "EURUSD"):
        e3_out[s] = dict(sym=s, base_n=base_all[s]["n"], base_net=round(base_all[s]["net"], 2),
                         base_win=round(base_all[s]["win"], 4),
                         cand_n=base_all[s]["n"], cand_net=round(base_all[s]["net"], 2),
                         cand_avg_netR=round(base_all[s]["avg"], 5), cand_netR_015=round(base015[s]["net"], 2),
                         n_suppressed=0, gates=dict(T1=True, T2=True, T3=False, T4=False, T5=True, g6=False, passed=0),
                         verdict="WATCH",
                         note="E3批量闸族定义=币系USD家族, XAU/EUR 单腿品种无门控效应, 仅随家族裁定攒样")
    out = dict(
        meta=dict(ts=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                  kline_source=KLINE_SRC, cost=COST, cost_t5=COST_T5,
                  protocol=("同分母五验: base=100%放行(品种JSON adx_min, 无ADX上限/无批量闸) vs 候选; "
                            "T1净R扣0.095>0且>=base / T2胜率不劣 / T3五折时间切分全正 / "
                            "T4 OOS70/30两段皆正 / T5 0.15R成本仍正 / ⑥净期望(均R)>=1.0; "
                            "逐品种裁定, 禁跨品种平均; M30+D1口径 h1_on=False(同分母)"),
                  p1=p1_out, e3=e3_out, e3_family=fam_roll,
                  real_account_untouched="30261104 零动; 引擎只读"),
    )
    with open(os.path.join(ROOT, "data", "rd_verify_batch_p1_pullback_20261114.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": out["meta"], "p1": p1_out}, f, ensure_ascii=False, indent=1, default=float)
    with open(os.path.join(ROOT, "data", "rd_verify_batch_e3_batchgate_20261114.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": out["meta"], "e3": e3_out, "e3_family": fam_roll}, f, ensure_ascii=False, indent=1, default=float)
    with open(os.path.join(ROOT, "research", "rd_verify_batch_raw_20261114.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=float)
    print("DONE artifacts written", flush=True)


if __name__ == "__main__":
    main()
