#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
liquid_wfo_m15_v2.py —— 高流动性品种 M15 深度优化 harness (黄金优先)
=====================================================================
金策·进化营 · 生命周期/进场质量优化线。研究用途, 绝不改 live。

修复 v1 (liquid_wfo_m15.py) 的致命口径 bug:
  * v1 simulate 中 tr=-inf 时 cand_trail = extreme - dirs*(-inf)*a = ±inf,
    np.maximum.reduce 把 SL 推到 +inf -> 首根即"SL命中" -> R=inf->被 isfinite 归零,
    实测 R=0 占比 54.9% (结果完全失真)。
  * v1 用 np.maximum.accumulate 做棘轮, 对空头方向反了(空头 SL 应取 minimum)。
  * v1 TP 的 R 直接写 tp_mult, 未除 sl_mult; 未扣交易成本; 未做 winsor。
本版改用【统一方向变换】: 令 x' = s*x (s=+1多/-1空), 则统一有
  SL' 在下方 / TP' 在上方 / 有利=x'上升 / 极值=max / 棘轮一律 max。
  彻底消除多头空头符号分叉。

精确复刻 jince_live24.py (2026-11-12 现役 REAL 口径):
  进场 signal_of (L397-438, M15): 波动率扩张闸(atr>=VOL_EXPAND_K*base_atr)
    -> 简化DI差 dx>=ADX_MIN -> MA5/20同向 -> 真突破(c>=rng_hi-BREAK_MARGIN*atr)
    -> 实体>=MIN_BODY_ATR*atr;  H1 趋势共振过滤(L1548-1564)
  出场 (L471-537 REAL 分支 + L929-980):
    SL = entry - s*min(sl_mult, 1.2)*atr  [REAL 硬封顶 1.2ATR]
    TP = max(tp_mult*atr, 2*SL距) 且 <=12*atr  [R:R>=2 地板硬化]
    PROFIT_SECURE: 0.5R BE锁(0.2R) / 1.0R 锁半利(1.2R) /
      ATR紧跟踪(>=1.0R:0.8ATR, >=1.5R:0.5ATR) + GIVEBACK_FLOOR(峰值-0.6R)
    MAX_HOLD_H*4 根 M15 硬平;  SL 只往有利方向棘轮
  成本 COST_R=0.05R/笔(点差+滑点), winsor[-3,8]; 次根开盘进场(无未来函数)
  H1 对齐改用 H1 收线时刻, 消除 v1 的未来函数。

输出: liquid_wfo_m15_v2/results.json + REPORT.md
红线: 不改 jince_live24.py / practice_params / 任何 CSV; 参数变更须 chief R11。
"""
import os, csv, json, time, argparse, datetime as dt
import numpy as np

ROOT = "E:/GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "research", "liquid_wfo_m15_v2")

# 11 个具备 M15 数据的高流动性品种 (黄金优先)
SYMS = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "GBPJPY",
        "AUDUSD", "BTCUSD", "ETHUSD", "XTIUSD", "XBRUSD"]

COST_R = 0.05
COST_R_STRESS = 0.10          # 成本敏感性(验证结论稳健)
WINSOR_LO, WINSOR_HI = -3.0, 8.0
REAL_SL_CAP = 1.2             # L501-502 REAL: sl_mult 封顶 1.2ATR

BASE = dict(adx_min=35.0, break_margin=0.6, vol_k=0.7, min_body=0.3,
            h1_on=True, max_hold_h=18, giveback=0.6, sl_mult=1.0, tp_mult=3.0)

GRID = dict(
    adx_min=[20., 25., 30., 35., 40.],
    break_margin=[0.3, 0.6, 1.0],
    vol_k=[0.5, 0.6, 0.7, 0.9],
    min_body=[0.1, 0.3, 0.5],
    h1_on=[True, False],
    max_hold_h=[12, 18, 24, 30],
    giveback=[0.4, 0.6, 0.8],
    # REAL 下 sl_mult>1.2 会被封顶, 故只列可生效值
    sl_mult=[0.6, 0.8, 1.0, 1.2],
    tp_mult=[2.0, 3.0, 4.0, 5.0],
)
CD_ORDER = ["adx_min", "vol_k", "h1_on", "break_margin", "min_body",
            "sl_mult", "tp_mult", "giveback", "max_hold_h"]


# ─────────────── 数据 & 预计算 ───────────────
def load_csv(path):
    t, o, h, l, c = [], [], [], [], []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.reader(f); next(r, None)
        for row in r:
            if len(row) < 5: continue
            try:
                t.append(dt.datetime.strptime(row[0][:19], "%Y-%m-%d %H:%M:%S").timestamp())
                o.append(float(row[1])); h.append(float(row[2]))
                l.append(float(row[3])); c.append(float(row[4]))
            except Exception: continue
    return dict(t=np.array(t), o=np.array(o), h=np.array(h),
                l=np.array(l), c=np.array(c), n=len(c))


def rollmean(x, w):
    cs = np.concatenate(([0.0], np.cumsum(x)))
    e = np.arange(len(x)) + 1
    s = np.clip(e - w, 0, len(x))
    return (cs[e] - cs[s]) / np.maximum(e - s, 1)


def prepare(sym):
    m = load_csv(os.path.join(DATA, f"{sym}_M15.csv"))
    h1 = load_csv(os.path.join(DATA, f"{sym}_H1.csv"))
    N, o, h, l, c = m['n'], m['o'], m['h'], m['l'], m['c']
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(np.maximum(h - l, np.abs(h - pc)), np.abs(l - pc))
    atr = rollmean(tr, 14)
    # base_atr = ATR over [k-33, k-14] (20根), 与 _atr_window(..., i-14, 20) 一致
    csum = np.concatenate(([0.0], np.cumsum(tr)))
    kk = np.arange(N)
    a = np.maximum(0, kk - 33); b = kk - 14
    base = np.where(b >= a, (csum[np.minimum(b + 1, N)] - csum[a]) /
                    np.maximum(b - a + 1, 1), 0.0)
    # 简化 DI 差 (14根)
    up = h - np.concatenate(([h[0]], h[:-1]))
    dn = np.concatenate(([l[0]], l[:-1])) - l
    pj = np.where((up > dn) & (up > 0), up, 0.0)
    mj = np.where((dn > up) & (dn > 0), dn, 0.0)
    cp = np.concatenate(([0.0], np.cumsum(pj)))
    cm = np.concatenate(([0.0], np.cumsum(mj)))
    st = np.maximum(0, kk - 13)
    sp = cp[kk + 1] - cp[st]; sm = cm[kk + 1] - cm[st]
    d = sp + sm
    dx = np.where(d > 0, np.abs(sp - sm) / np.maximum(d, 1e-12) * 100.0, 0.0)
    m5, m20 = rollmean(c, 5), rollmean(c, 20)
    # 前20根区间高低 [k-20, k-1] (不含当前)
    rng_hi = np.zeros(N); rng_lo = np.zeros(N)
    for k in range(20, N):
        rng_hi[k] = h[k-20:k].max(); rng_lo[k] = l[k-20:k].min()
    cprev = np.concatenate(([c[0]], c[:-1]))
    # H1 共振: 用【已收线】H1 bar (h1_t + 3600 <= m15_t + 900), 无未来函数
    h1_m5, h1_m20 = rollmean(h1['c'], 5), rollmean(h1['c'], 20)
    h1_dir_full = np.sign(h1_m5 - h1_m20).astype(np.int8)
    h1_close_t = h1['t'] + 3600.0
    j = np.searchsorted(h1_close_t, m['t'] + 900.0, side='right') - 1
    j = np.clip(j, 0, len(h1['c']) - 1)
    h1_dir = np.where(j >= 19, h1_dir_full[j], 0)
    return dict(o=o, h=h, l=l, c=c, n=N, atr=atr, base=base, dx=dx,
                m5=m5, m20=m20, rng_hi=rng_hi, rng_lo=rng_lo,
                body=np.abs(c - cprev), up_m=c > cprev, down_m=c < cprev,
                h1_dir=h1_dir, t=m['t'])


def gen_signals(P, g):
    N, c, atr = P['n'], P['c'], P['atr']
    vol_ok = atr >= g['vol_k'] * P['base']
    adx_ok = P['dx'] >= g['adx_min']
    body_ok = np.where(atr > 0, P['body'] >= g['min_body'] * atr, False)
    kmask = np.arange(N) >= 60
    long_s = (vol_ok & adx_ok & (c >= P['rng_hi'] - g['break_margin'] * atr)
              & (P['m5'] > P['m20']) & P['up_m'] & body_ok & kmask)
    short_s = (vol_ok & adx_ok & (c <= P['rng_lo'] + g['break_margin'] * atr)
               & (P['m5'] < P['m20']) & P['down_m'] & body_ok & kmask)
    if g['h1_on']:
        long_s &= (P['h1_dir'] == 1)
        short_s &= (P['h1_dir'] == -1)
    kl, ks_ = np.nonzero(long_s)[0], np.nonzero(short_s)[0]
    k = np.concatenate((kl, ks_))
    s = np.concatenate((np.ones(len(kl)), -np.ones(len(ks_))))
    o = np.argsort(k)
    return k[o], s[o]


# ─────────────── 统一方向空间的出场回测 ───────────────
def simulate(P, g, k, s, cost=COST_R):
    """x' = s*x 变换: SL'在下, TP'在上, 有利=x'上升, 棘轮一律 max。
    返回 (R数组, 出场时间戳数组, 出场类型)。"""
    N = P['n']
    e = k + 1
    ok = e < N
    k, s, e = k[ok], s[ok], e[ok]
    nC = len(k)
    if nC == 0:
        return np.array([]), np.array([]), np.array([])
    Lmax = int(g['max_hold_h'] * 4)          # 18h -> 72 根 M15
    idx = e[:, None] + np.arange(Lmax)[None, :]
    beyond = idx >= N
    ic = np.minimum(idx, N - 1)
    # 变换到 ' 空间: high' = max(s*H, s*L), low' = min(...)
    Hs = P['h'][ic] * s[:, None]; Ls = P['l'][ic] * s[:, None]
    HI = np.maximum(Hs, Ls); LO = np.minimum(Hs, Ls)
    Cs = P['c'][ic] * s[:, None]
    A = P['atr'][ic]
    HI = np.where(beyond, -np.inf, HI)
    LO = np.where(beyond, -np.inf, LO)
    Cs = np.where(beyond, P['c'][ic] * s[:, None], Cs)

    entry = P['o'][e] * s                    # ' 空间进场价
    a0 = np.maximum(P['atr'][k], 1e-9)
    slm = min(g['sl_mult'], REAL_SL_CAP)     # REAL 1.2ATR 硬封顶
    dist = slm * a0                          # 1R 距离
    tp_d = np.maximum(g['tp_mult'] * a0, 2.0 * dist)   # R:R>=2 地板
    tp_d = np.minimum(tp_d, 12.0 * a0)                  # 12ATR 封顶
    SL0 = entry - dist
    TP = entry + tp_d
    R = np.zeros(nC)
    ext = entry.copy()                       # 有利极值('空间, 单调递增)
    SL = SL0.copy()
    alive = np.ones(nC, dtype=bool)
    exit_t = np.full(nC, P['t'][np.minimum(e + Lmax - 1, N - 1)])
    etype = np.full(nC, 2, dtype=np.int8)    # 0=SL 1=TP 2=MAXHOLD

    for kk in range(Lmax):
        if not alive.any(): break
        hi, lo, cc, aa = HI[:, kk], LO[:, kk], Cs[:, kk], A[:, kk]
        # 命中判定(用上一根推进后的 SL; 同根双触保守按 SL 优先)
        hit_sl = alive & (lo <= SL)
        hit_tp = alive & (~hit_sl) & (hi >= TP)
        if hit_sl.any():
            px = np.minimum(SL, hi)          # 跳空按更差值
            R[hit_sl] = (px[hit_sl] - entry[hit_sl]) / dist[hit_sl] - cost
            etype[hit_sl] = 0
            exit_t[hit_sl] = P['t'][ic[hit_sl, kk]]
            alive[hit_sl] = False
        if hit_tp.any():
            R[hit_tp] = (TP[hit_tp] - entry[hit_tp]) / dist[hit_tp] - cost
            etype[hit_tp] = 1
            exit_t[hit_tp] = P['t'][ic[hit_tp, kk]]
            alive[hit_tp] = False
        # 触发数据末端 -> 硬平
        bend = alive & beyond[:, kk]
        if bend.any():
            R[bend] = (cc[bend] - entry[bend]) / dist[bend] - cost
            etype[bend] = 2
            exit_t[bend] = P['t'][ic[bend, kk]]
            alive[bend] = False
        # 更新有利极值 & 浮盈 r(用极值, 与引擎 r_mult 一致)
        ext = np.where(alive, np.maximum(ext, hi), ext)
        r = (ext - entry) / dist
        cand = np.full(nC, -np.inf)
        cand = np.where(r >= 0.5, entry + 0.2 * dist, cand)          # BE 锁
        cand = np.where(r >= 1.0, np.maximum(cand, entry + 1.2 * dist), cand)  # 锁半利
        trm = np.where(r >= 1.0, np.where(r >= 1.5, 0.5, 0.8), np.nan)
        trail = ext - trm * np.maximum(aa, a0 * 0.5)
        cand = np.where(np.isfinite(trail), np.maximum(cand, trail), cand)     # ATR 紧跟踪
        gf = ext - g['giveback'] * dist
        cand = np.where(r > 0, np.maximum(cand, gf), cand)             # 回撤地板
        SL = np.where(alive & np.isfinite(cand), np.maximum(SL, cand), SL)  # 统一 max 棘轮
    # MAXHOLD 硬平(仍存活者用最后一根收盘)
    if alive.any():
        last = Cs[:, -1]
        R[alive] = (last[alive] - entry[alive]) / dist[alive] - cost
        etype[alive] = 2
        exit_t[alive] = P['t'][ic[alive, -1]]
    R = np.clip(np.where(np.isfinite(R), R, 0.0), WINSOR_LO, WINSOR_HI)

    # 贪心不重叠(引擎同品种同时仅一笔)
    exit_bar = np.minimum(e + Lmax - 1, N - 1)
    order = np.argsort(k)
    taken = []
    nb = -1
    for i in order:
        if k[i] >= nb:
            taken.append(i); nb = exit_bar[i]
    taken = np.array(taken, dtype=np.int64)
    return R[taken], P['t'][e[taken]], etype[taken]


def evaluate(P, g, cost=COST_R):
    k, s = gen_signals(P, g)
    R, et, ty = simulate(P, g, k, s, cost=cost)
    n = len(R)
    if n == 0:
        return dict(n=0, net=0., avg=0., win=0., R=R, et=et)
    return dict(n=n, net=float(R.sum()), avg=float(R.mean()),
                win=float((R > 0).mean()), R=R, et=et)


# ─────────────── 五验 ───────────────
def five_tests(base, opt, curve=None, cost=COST_R):
    if base['n'] == 0 or opt['n'] == 0:
        return dict(T1=False, T2=False, T3=False, T4=False, T5=False, passed=0)
    T1 = (opt['avg'] > base['avg']) and (opt['net'] > base['net'])
    T2 = opt['win'] >= base['win'] - 0.02
    seg = np.array_split(opt['R'], 8) if opt['n'] >= 8 else [opt['R']]
    T3 = sum(1 for x in seg if x.sum() > 0) >= 6
    T4 = True
    if curve and len(curve) >= 3:
        v = [x[1] for x in curve]; b = max(v); bi = v.index(b)
        T4 = (0 < bi < len(v) - 1) and min(v[max(0, bi-1):bi+2]) >= b * 0.80
    wb = np.array_split(base['R'], 3) if base['n'] >= 3 else [base['R']]*3
    wo = np.array_split(opt['R'], 3) if opt['n'] >= 3 else [opt['R']]*3
    T5 = all(wo[i].sum() > wb[i].sum() for i in range(3))
    return dict(T1=bool(T1), T2=bool(T2), T3=bool(T3), T4=bool(T4), T5=bool(T5),
                passed=sum([T1, T2, T3, T4, T5]))


def coord_descent(P, base, g0, rounds=3, min_trades=60, label=""):
    g = dict(g0)
    cur = evaluate(P, g)
    curve = []
    for rd in range(rounds):
        improved = False
        for key in CD_ORDER:
            bv, be, cv = g[key], cur, []
            for v in GRID[key]:
                q = dict(g); q[key] = v
                e = evaluate(P, q)
                cv.append((v, e['avg']))
                if e['n'] >= min_trades and e['avg'] > be['avg'] + 1e-6:
                    be, bv = e, v
            if key == 'adx_min': curve = cv
            if bv != g[key]:
                g[key] = bv; cur = be; improved = True
        if label:
            print("    [%s] r%d avgR=%.4f n=%d" % (label, rd+1, cur['avg'], cur['n']), flush=True)
        if not improved: break
    return g, cur, curve


# ─────────────── 主流程 ───────────────
def load_live():
    d = json.load(open(os.path.join(DATA, "practice_params_all_symbols.json"), encoding="utf-8"))
    return {s: dict(sl=float(d.get(s, {}).get("sl_mult", 1.0)),
                    tp=float(d.get(s, {}).get("tp_mult", 3.0))) for s in SYMS}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default=None)
    ap.add_argument("--cost", type=float, default=COST_R)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    live = load_live()
    syms = [args.symbol] if args.symbol else SYMS
    results = {}
    t0 = time.time()
    print("=== M15 v2 高流动性品种深度优化 (黄金优先) cost=%.3f ===" % args.cost, flush=True)
    for sym in syms:
        m15p = os.path.join(DATA, f"{sym}_M15.csv")
        if not os.path.exists(m15p):
            print(f"  {sym}: 无 M15 数据, 跳过"); continue
        P = prepare(sym)
        B = dict(BASE); B['sl_mult'] = live[sym]['sl']; B['tp_mult'] = live[sym]['tp']
        base = evaluate(P, B, cost=args.cost)
        rounds = 3 if sym == "XAUUSD" else 2
        mintr = 300 if sym == "XAUUSD" else 60
        print("  %-8s bars=%d 基线 n=%d netR=%+.2f avgR=%+.4f WR=%.1f%% (sl/tp=%.1f/%.1f)" %
              (sym, P['n'], base['n'], base['net'], base['avg'], base['win']*100,
               B['sl_mult'], B['tp_mult']), flush=True)
        g, opt, curve = coord_descent(P, base, B, rounds=rounds,
                                      min_trades=mintr, label=sym)
        opt = evaluate(P, g, cost=args.cost)
        o2 = evaluate(P, g, cost=COST_R_STRESS)     # 成本压力测试
        ft = five_tests(base, opt, curve=curve, cost=args.cost)
        seg8_b = sum(1 for x in (np.array_split(base['R'], 8) if base['n'] >= 8 else [base['R']]) if x.sum() > 0)
        seg8_o = sum(1 for x in (np.array_split(opt['R'], 8) if opt['n'] >= 8 else [opt['R']]) if x.sum() > 0)
        results[sym] = dict(
            bars=P['n'],
            base=dict(g=B, n=base['n'], netR=round(base['net'], 4), avgR=round(base['avg'], 5),
                      win=round(base['win'], 4), seg8_pos=seg8_b),
            opt=dict(g=g, n=opt['n'], netR=round(opt['net'], 4), avgR=round(opt['avg'], 5),
                     win=round(opt['win'], 4), seg8_pos=seg8_o,
                     stress_avgR=round(o2['avg'], 5)),
            five=ft,
            dNetR=round(opt['net'] - base['net'], 4),
            dAvgR=round(opt['avg'] - base['avg'], 5),
            dTrades=opt['n'] - base['n'],
            adx_curve=[[float(v), round(float(a), 5)] for v, a in curve],
        )
        print("    -> n=%d netR=%+.2f avgR=%+.4f WR=%.1f%% ΔavgR=%+.4f 五验=%d/5 %s | stress(0.10R)=%+.4f" %
              (opt['n'], opt['net'], opt['avg'], opt['win']*100,
               opt['avg'] - base['avg'], ft['passed'],
               "".join("Y" if ft[k] else "N" for k in ("T1","T2","T3","T4","T5")),
               o2['avg']), flush=True)
    fn = os.path.join(OUT, "results.json" if not args.symbol else f"results_{args.symbol}.json")
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("用时 %.1fs -> %s" % (time.time()-t0, fn), flush=True)


if __name__ == "__main__":
    main()
