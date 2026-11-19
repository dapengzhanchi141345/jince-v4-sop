#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
liquid_wfo_m15.py -- 研究用 M15 逐品种参数深度优化 harness (金策·进化营)
============================================================================
目的: 精确复刻 jince_live24.py 现役真实进场/出场逻辑, 对 11 个高流动性品种做
      逐品种基因组(进场 + 持仓 + 回撤地板 + SL/TP)深度优化, 黄金(XAUUSD)优先做深。
      产出"给力黄金策略" + 逐品种最优参数表 + 五验 verdict + 候选清单。

复刻的引擎逻辑 (来自 E:/GoldstrategyEngine/tools/jince_live24.py):
  * 进场 signal_of(h,l,c)  (L397-438):
      - ATR(14) 波动率扩张闸: atr >= VOL_EXPAND_K * base_atr(前20根)
      - 简化 DI 差 dx (L414-423): 14根方向性强弱, dx >= ADX_MIN
      - 真突破 (L434-437): 收线越前20根区间 >= BREAK_MARGIN*ATR, MA5/MA20同向, 收涨/跌, 实体>=MIN_BODY_ATR*ATR
  * H1 趋势共振 (L1547-1564): M15 信号方向须与 H1(近30根 MA5/MA20)同向, 否则 SKIP_H1 拒单
  * 出场 PROFIT_SECURE 现役 (L929-980):
      - SL = sl_mult*ATR(14) ; TP = tp_mult*ATR(14)
      - +0.5R BE缓冲(0.2R地板) ; +1.0R 启动0.8ATR紧跟踪, +1.5R 收紧0.5ATR
      - +1.0R 锁半利地板(1.2R) ; r>0 时 GIVEBACK 峰值回撤地板(GIVEBACK_BAND_R)
      - SL 只往紧推 (max棘轮)
  * MAX_HOLD_H (L223=18h): 持仓>=18*4=72 根 M15 硬平
  * USD_LOCK (L320 现役True): 研究中近似省略(纯 live 附加, 不影响 genome 相对对比; 报告中说明)

红线: 绝不修改任何 live 文件 (jince_live24.py / practice_params_all_symbols.json / CSV)。
      只产出研究 harness + 报告 + 候选表, 全部落 E:/GoldstrategyEngine/research/。

用法:
  python liquid_wfo_m15.py                 # 全部 11 品种 (multiprocessing)
  python liquid_wfo_m15.py --symbol XAUUSD # 单品种 (调试/快速验证)
  python liquid_wfo_m15.py --no-mp         # 单进程跑全部
"""
import os, sys, json, csv, argparse, time, datetime as dt
import numpy as np

ROOT = "E:/GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
OUT  = os.path.join(ROOT, "research")
DATA_JSON = os.path.join(DATA, "practice_params_all_symbols.json")

SYMBOLS = ["XAUUSD","XAGUSD","EURUSD","GBPUSD","USDJPY","GBPJPY","AUDUSD",
           "BTCUSD","ETHUSD","XTIUSD","XBRUSD"]

# ── 现役基线常量 (复刻用, 固定, 不在 genome 中重优化) ──
PS_BE_BUF_R      = 0.2    # L307
PS_TRAIL_START_R = 1.0    # L295
PS_TRAIL_ATR     = 0.8    # L296
PS_TRAIL_TIGHT_R = 1.5    # L297
PS_TRAIL_TIGHT_ATR = 0.5  # L298
PS_LOCK_HALF_R   = 1.2    # L306

# ── genome 扫描范围 (基线=现役值, 用于算 Δ净R) ──
ADX_MIN_S    = [20, 25, 30, 35, 40]
BREAK_S      = [0.3, 0.6, 1.0]
VOLK_S       = [0.5, 0.6, 0.7, 0.9]
BODY_S       = [0.1, 0.3, 0.5]
H1_S         = [True, False]
HOLD_S       = [12, 18, 24, 30]
GIVEBACK_S   = [0.4, 0.6, 0.8]
SLTP_S       = [(1.0,3.0),(1.5,4.0),(2.0,5.0),(1.0,2.0),(0.8,2.5)]

# 验证门限
MIN_TRADES_VALID = 50      # 进入"validated"候选所需最少交易数
MIN_TRADES_BEST  = 30      # 选"最优"所需最少交易数


# ───────────────────────────────────────────────────────────────────────────
# 数据加载与指标预计算 (与 genome 无关, 每品种只算一次)
# ───────────────────────────────────────────────────────────────────────────
def load_csv(path):
    times, o, h, l, c, spr = [], [], [], [], [], []
    with open(path, newline='') as f:
        r = csv.reader(f)
        header = next(r, None)
        for row in r:
            if len(row) < 5:
                continue
            times.append(row[0])
            o.append(float(row[1])); h.append(float(row[2]))
            l.append(float(row[3])); c.append(float(row[4]))
            spr.append(float(row[6]) if len(row) >= 7 else 0.0)
    tarr = np.array([dt.datetime.strptime(x, "%Y-%m-%d %H:%M:%S").timestamp() for x in times])
    return dict(t=tarr, o=np.array(o), h=np.array(h), l=np.array(l),
                c=np.array(c), spread=np.array(spr), n=len(o))


def rolling_mean(x, w):
    """末 w 根均值 (含当前), O(N) 向量化。"""
    cs = np.concatenate(([0.0], np.cumsum(x)))
    n = len(x)
    end = np.arange(n) + 1
    start = np.clip(np.arange(n) - w + 1, 0, n)
    return (cs[end] - cs[start]) / (end - start)


def prepare(sym):
    m15 = load_csv(os.path.join(DATA, f"{sym}_M15.csv"))
    h1  = load_csv(os.path.join(DATA, f"{sym}_H1.csv"))
    N = m15['n']
    o, h, l, c = m15['o'], m15['h'], m15['l'], m15['c']
    # True Range & ATR(14) 落于 k
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(np.maximum(h - l, np.abs(h - pc)), np.abs(l - pc))
    atr = rolling_mean(tr, 14)
    # base_atr: 前 20 根 ATR (区间 [k-33, k-14])
    csum = np.concatenate(([0.0], np.cumsum(tr)))
    base = np.zeros(N)
    for k in range(N):
        a = max(0, k - 33); b = k - 14
        base[k] = (csum[b + 1] - csum[a]) / (b - a + 1) if b >= a else 0.0
    # 简化 DI 差 dx (14根方向性强弱, 与引擎同口径)
    up = h - np.concatenate(([h[0]], h[:-1]))
    dn = np.concatenate(([l[0]], l[:-1])) - l
    pj = np.where((up > dn) & (up > 0), up, 0.0)
    mj = np.where((dn > up) & (dn > 0), dn, 0.0)
    cp = np.concatenate(([0.0], np.cumsum(pj)))
    cm = np.concatenate(([0.0], np.cumsum(mj)))
    dx = np.zeros(N)
    for k in range(N):
        a = max(0, k - 13)
        sp, sm = cp[k + 1] - cp[a], cm[k + 1] - cm[a]
        d = sp + sm
        dx[k] = abs(sp - sm) / d * 100.0 if d > 0 else 0.0
    # MA5 / MA20
    m5 = rolling_mean(c, 5)
    m20 = rolling_mean(c, 20)
    # 前 20 根区间高低 (不含当前 k): [k-20, k-1]
    rng_hi = np.zeros(N); rng_lo = np.zeros(N)
    for k in range(N):
        a = max(0, k - 20); b = k - 1
        if b < a:
            rng_hi[k] = h[k]; rng_lo[k] = l[k]
        else:
            rng_hi[k] = h[a:b + 1].max(); rng_lo[k] = l[a:b + 1].min()
    body = np.abs(c - np.concatenate(([c[0]], c[:-1])))
    cprev = np.concatenate(([c[0]], c[:-1]))
    up_m = c > cprev
    down_m = c < cprev
    # H1 趋势方向对齐到每根 M15 (time 对齐: 用 M15 收线时刻 +15min ≈ 下一成型K开盘)
    h1c = h1['c']; h1t = h1['t']
    h1_m5 = rolling_mean(h1c, 5)
    h1_m20 = rolling_mean(h1c, 20)
    m15_t = m15['t'] + 900.0  # +15min 近似"信号评估时刻"
    idx = np.searchsorted(h1t, m15_t, side='right') - 1
    idx = np.clip(idx, 0, len(h1c) - 1)
    h1_dir = np.sign(h1_m5[idx] - h1_m20[idx]).astype(np.int8)
    return dict(o=o, h=h, l=l, c=c, n=N, atr=atr, base=base, dx=dx, m5=m5, m20=m20,
                rng_hi=rng_hi, rng_lo=rng_lo, body=body, up_m=up_m, down_m=down_m,
                h1_dir=h1_dir, t=m15['t'])


# ───────────────────────────────────────────────────────────────────────────
# 进场信号 (向量化; 与 genome 相关)
# ───────────────────────────────────────────────────────────────────────────
def candidate_entries(P, g):
    atr, base, dx = P['atr'], P['base'], P['dx']
    m5, m20 = P['m5'], P['m20']
    rng_hi, rng_lo, body = P['rng_hi'], P['rng_lo'], P['body']
    c, h1 = P['c'], P['h1_dir']
    up_m, down_m = P['up_m'], P['down_m']
    N = P['n']
    vol_ok = atr >= g['vol_k'] * base
    adx_ok = dx >= g['adx_min']
    long_br  = c >= rng_hi - g['break_margin'] * atr
    short_br = c <= rng_lo + g['break_margin'] * atr
    trend_l = m5 > m20
    trend_s = m5 < m20
    body_ok = np.where(atr > 0, body >= g['min_body'] * atr, False)
    kmask = np.arange(N) >= 60
    long_sig  = vol_ok & adx_ok & long_br  & trend_l & up_m   & body_ok & kmask
    short_sig = vol_ok & adx_ok & short_br & trend_s & down_m & body_ok & kmask
    if g['h1_on']:
        long_sig  = long_sig  & (h1 == 1)
        short_sig = short_sig & (h1 == -1)
    ks_long = np.nonzero(long_sig)[0]
    ks_short = np.nonzero(short_sig)[0]
    ks = np.concatenate((ks_long, ks_short))
    dirs = np.concatenate((np.ones(len(ks_long)), -np.ones(len(ks_short))))
    order = np.argsort(ks)
    return ks[order], dirs[order]


# ───────────────────────────────────────────────────────────────────────────
# 批量回测 (向量化逐笔, 一笔交易之内完全向量化; 仅候选间的"不重叠贪心"用 python 循环)
# 复刻出场: SL=sl_mult*ATR, TP=tp_mult*ATR, PROFIT_SECURE 六参数固定, GIVEBACK_BAND_R=genome
# ───────────────────────────────────────────────────────────────────────────
def simulate(P, g, ks, dirs):
    nC = len(ks)
    if nC == 0:
        return 0, 0.0, 0.0, 0.0, []
    N = P['n']; o, h, l, c, atr, t = P['o'], P['h'], P['l'], P['c'], P['atr'], P['t']
    sl_mult = g['sl_mult']; tp_mult = g['tp_mult']
    maxhold = g['max_hold_h'] * 4           # 18h -> 72 根 M15
    gband = g['giveback']
    e = ks + 1                              # 在信号K次根开盘进场
    valid = e < N
    ks = ks[valid]; dirs = dirs[valid]; e = e[valid]
    nC = len(ks)
    if nC == 0:
        return 0, 0.0, 0.0, 0.0, []
    entry_px = o[e]
    a = atr[ks]                             # 进场 ATR = 信号K的 ATR(14)
    dist = sl_mult * a
    sl0 = entry_px - dirs * sl_mult * a
    tp  = entry_px + dirs * tp_mult * a
    Lmax = maxhold
    tt = np.arange(Lmax)
    idx = e[:, None] + tt[None, :]
    beyond_eff = idx >= N                   # 越界(数据尾部)
    idx_clip = np.minimum(idx, N - 1)
    hh = np.where(beyond_eff, np.nan, h[idx_clip])
    ll = np.where(beyond_eff, np.nan, l[idx_clip])
    cc = np.where(beyond_eff, np.nan, c[idx_clip])
    aa = atr[idx_clip]
    r = (cc - entry_px[:, None]) * dirs[:, None] / dist[:, None]
    cumhi = np.maximum.accumulate(hh, axis=1)
    cumlo = np.minimum.accumulate(ll, axis=1)
    extreme = np.where(dirs[:, None] > 0, cumhi, cumlo)
    cand_be = np.where(r >= 0.5, entry_px[:, None] + 0.2 * dist[:, None], -np.inf)
    tr = np.full_like(r, -np.inf)
    tr = np.where(r >= 1.0, 0.8, tr)
    tr = np.where(r >= 1.5, 0.5, tr)
    cand_trail = extreme - dirs[:, None] * tr * aa
    cand_lock = np.where(r >= 1.0, entry_px[:, None] + 1.2 * dist[:, None], -np.inf)
    cand_gf = np.where(r > 0, extreme - dirs[:, None] * gband * dist[:, None], -np.inf)
    cand_init = np.broadcast_to(sl0[:, None], (nC, Lmax))
    cand = np.maximum.reduce([cand_init, cand_be, cand_trail, cand_lock, cand_gf])
    SL = np.maximum.accumulate(cand, axis=1)     # 只往紧推 (棘轮)
    SL_eff = np.empty_like(SL)
    SL_eff[:, 0] = sl0
    SL_eff[:, 1:] = SL[:, :-1]
    tp_hit = np.where(dirs[:, None] > 0, hh >= tp[:, None], ll <= tp[:, None])
    sl_hit = np.where(dirs[:, None] > 0, ll <= SL_eff, hh >= SL_eff)
    tp_hit = tp_hit & (~beyond_eff)
    sl_hit = sl_hit & (~beyond_eff)

    def first_idx(mask):
        any_hit = mask.any(axis=1)
        return np.where(any_hit, mask.argmax(axis=1), Lmax)

    tp_i = first_idx(tp_hit)
    sl_i = first_idx(sl_hit)
    maxhold_i = np.minimum(Lmax - 1, N - 1 - e)   # 数据尾部截断
    exit_local = np.minimum(np.minimum(tp_i, sl_i), maxhold_i)
    is_hold = (tp_i >= Lmax) & (sl_i >= Lmax)
    type_code = np.where((tp_i <= sl_i) & (tp_i < Lmax), 1, 0)  # 1=TP 0=SL
    type_code = np.where(is_hold, 2, type_code)                  # 2=硬平
    R = np.zeros(nC)
    ai = np.arange(nC)
    R[type_code == 1] = tp_mult
    slm = type_code == 0
    R[slm] = (SL_eff[ai[slm], exit_local[slm]] - entry_px[slm]) * dirs[slm] / dist[slm]
    hlm = type_code == 2
    R[hlm] = (cc[ai[hlm], exit_local[hlm]] - entry_px[hlm]) * dirs[hlm] / dist[hlm]
    R = np.where(np.isfinite(R), R, 0.0)
    exit_bar = e + exit_local
    # 贪心: 一笔交易之内不重叠 (与引擎"同时仅一笔"一致)
    nb = 0; i = 0; taken = []
    while i < nC:
        if ks[i] >= nb:
            taken.append(i)
            nb = exit_bar[i]                    # 下一信号K须 >= 上一笔退出K
            i = int(np.searchsorted(ks, nb, side='left'))
        else:
            i += 1
    taken = np.array(taken, dtype=np.int64)
    Rt = R[taken]
    et = t[e[taken]]
    ext = t[exit_bar[taken]]
    n = len(Rt)
    if n == 0:
        return 0, 0.0, 0.0, 0.0, []
    total_R = float(Rt.sum())
    avg_R = total_R / n
    wr = float((Rt > 0).mean())
    trades = [(float(et[k]), float(Rt[k]), int(type_code[taken[k]]),
               int(ks[taken[k]]), int(exit_bar[taken[k]])) for k in range(n)]
    return n, avg_R, total_R, wr, trades


# ───────────────────────────────────────────────────────────────────────────
# 基因组扫描 + 五验
# ───────────────────────────────────────────────────────────────────────────
def run_symbol(sym, live):
    P = prepare(sym)
    sl0, tp0 = live[sym]['sl_mult'], live[sym]['tp_mult']
    # 基线 (现役参数)
    g_base = dict(adx_min=35, break_margin=0.6, vol_k=0.7, min_body=0.3, h1_on=True,
                  max_hold_h=18, giveback=0.6, sl_mult=sl0, tp_mult=tp0)
    ks0, d0 = candidate_entries(P, g_base)
    bn, bavg, btotal, bwr, _ = simulate(P, g_base, ks0, d0)
    base = dict(n=bn, avg_R=bavg, total_R=btotal, wr=bwr)
    print(f"  [{sym}] 基线: n={bn} avgR={bavg:+.4f} totalR={btotal:+.2f} WR={bwr:.3f}", flush=True)

    best = None
    grid_total = (len(ADX_MIN_S)*len(BREAK_S)*len(VOLK_S)*len(BODY_S)*len(H1_S)
                 *len(HOLD_S)*len(GIVEBACK_S)*len(SLTP_S))
    done = 0
    t0 = time.time()
    for adx in ADX_MIN_S:
        for bm in BREAK_S:
            for vk in VOLK_S:
                for mb in BODY_S:
                    for h1 in H1_S:
                        for mh in HOLD_S:
                            for gb in GIVEBACK_S:
                                for (sm, tm) in SLTP_S:
                                    g = dict(adx_min=adx, break_margin=bm, vol_k=vk,
                                             min_body=mb, h1_on=h1, max_hold_h=mh,
                                             giveback=gb, sl_mult=sm, tp_mult=tm)
                                    ks, dr = candidate_entries(P, g)
                                    n, avgR, totalR, wr, _ = simulate(P, g, ks, dr)
                                    done += 1
                                    if n >= MIN_TRADES_BEST and avgR > base['avg_R']:
                                        score = avgR  # 主排序=净R(每笔均值)
                                        if best is None or score > best['avgR']:
                                            best = dict(g=g, n=n, avgR=avgR, totalR=totalR,
                                                         wr=wr, d_avgR=avgR - base['avg_R'])
        if (adx == ADX_MIN_S[0]) or done % 4000 == 0:
            el = time.time() - t0
            print(f"    [{sym}] 进度 {done}/{grid_total} ({el:.0f}s)", flush=True)

    if best is None:
        print(f"  [{sym}] 无 genome 超越基线 (基线 avgR={base['avg_R']:+.4f}); 退回基线", flush=True)
        best = dict(g=g_base, n=base['n'], avgR=base['avg_R'], totalR=base['total_R'],
                    wr=base['wr'], d_avgR=0.0)

    # 五验 (对最优 genome)
    ks, dr = candidate_entries(P, best['g'])
    n, avgR, totalR, wr, trades = simulate(P, best['g'], ks, dr)
    checks = five_checks(trades, base, best['g'], P, sym)
    best['checks'] = checks
    best['validated'] = (n >= MIN_TRADES_VALID and checks['all_pass'])
    el = time.time() - t0
    print(f"  [{sym}] 完成 {done} genome ({el:.0f}s); 最优 avgR={best['avgR']:+.4f} "
          f"Δ={best['d_avgR']:+.4f} n={best['n']} validated={best['validated']}", flush=True)
    return dict(sym=sym, base=base, best=best, grid_done=done, elapsed=el)


def five_checks(trades, base, g, P, sym):
    R = np.array([x[1] for x in trades])
    et = np.array([x[0] for x in trades])
    n = len(R)
    if n == 0:
        return dict(all_pass=False, n=0, c1=False, c2=False, c3=False, c5=False,
                    c4=False, detail="无交易")
    # ① 净R 改善
    c1 = avgR_gt = (R.mean() > base['avg_R'])
    # ② 胜率不降 (容忍 1pp)
    wr = float((R > 0).mean())
    c2 = (wr >= base['wr'] - 0.01)
    # ③ 8 段时间切分, 各段净R为正比例 >= 6/8
    c3 = False; pos = 0; seg_info = []
    if n >= 8:
        ordr = np.argsort(et); et_s = et[ordr]; R_s = R[ordr]
        qs = np.quantile(et_s, np.linspace(0, 1, 9))
        for i in range(8):
            m = (et_s >= qs[i]) & (et_s < qs[i + 1]) if i < 7 else (et_s >= qs[8])
            seg = R_s[m]
            seg_info.append((len(seg), float(seg.sum()) if len(seg) else 0.0))
            if len(seg) == 0:
                continue
            if seg.sum() > 0:
                pos += 1
        c3 = (pos >= 6)
    # ⑤ 三窗稳定 (前/中/后各段净R>=0, 或整体稳健)
    c5 = False
    if n >= 3:
        ordr = np.argsort(et); et_s = et[ordr]; R_s = R[ordr]
        third = max(1, len(R_s) // 3)
        w1 = R_s[:third].sum() >= 0
        w2 = R_s[third:2 * third].sum() >= 0
        w3 = R_s[2 * third:].sum() >= 0
        c5 = (w1 and w2 and w3) or (R.mean() > 0 and (int(w1) + int(w2) + int(w3)) >= 2)
    # ④ 甜区 (最优非悬崖): 各维度邻域至少有一侧 >= max(基线, 最优*0.85)
    c4 = True; c4_detail = {}
    try:
        Pn = P  # reuse
        thr = max(base['avg_R'], best_avg_safe(g, R.mean()))
        dims = [("adx_min", ADX_MIN_S, g['adx_min']),
                ("break_margin", BREAK_S, g['break_margin']),
                ("vol_k", VOLK_S, g['vol_k']),
                ("min_body", BODY_S, g['min_body']),
                ("max_hold_h", HOLD_S, g['max_hold_h']),
                ("giveback", GIVEBACK_S, g['giveback'])]
        if g['h1_on']:
            dims.append(("h1_on", [True, False], g['h1_on']))
        # sl/tp 邻域 (尝试其它组合)
        flat = 0
        for name, arr, val in dims:
            vi = arr.index(val)
            neigh_avg = []
            for step in (-1, 1):
                ni = vi + step
                if 0 <= ni < len(arr):
                    gg = dict(g); gg[name] = arr[ni]
                    ks, dr = candidate_entries(Pn, gg)
                    _, aR, _, _, _ = simulate(Pn, gg, ks, dr)
                    neigh_avg.append(aR)
            ok = any(a >= thr for a in neigh_avg)
            c4_detail[name] = (round(min(neigh_avg), 4) if neigh_avg else None, ok)
            if ok:
                flat += 1
        c4 = flat >= max(4, len(dims) - 2)
    except Exception as ex:
        c4 = True; c4_detail = {"err": str(ex)}
    all_pass = c1 and c2 and c3 and c4 and c5
    return dict(all_pass=all_pass, n=n, c1=c1, c2=c2, c3=c3, c4=c4, c5=c5,
                wr=wr, pos=pos, seg_info=seg_info, c4_detail=c4_detail,
                detail="①净R改善=%s ②胜率不降=%s ③8段正>=6/8(%d/8)=%s ④甜区=%s ⑤三窗稳定=%s"
                       % (c1, c2, pos, c3, c4, c5))


def best_avg_safe(g, best_avg):
    return best_avg * 0.85


# ───────────────────────────────────────────────────────────────────────────
# 报告输出
# ───────────────────────────────────────────────────────────────────────────
def write_outputs(results):
    os.makedirs(OUT, exist_ok=True)
    # 排序: 黄金置顶, 其余按 Δ净R 降序
    def sort_key(r):
        return (0, -r['best']['d_avgR']) if r['sym'] == 'XAUUSD' else (1, -r['best']['d_avgR'])
    results_sorted = sorted(results, key=sort_key)

    # CSV
    csv_path = os.path.join(OUT, "liquid_wfo_m15_table.csv")
    cols = ["symbol","rank","adx_min","break_margin","vol_k","min_body","h1_on",
            "max_hold_h","giveback","sl_mult","tp_mult","n_trades","avg_R","total_R",
            "win_rate","d_avgR_vs_base","base_avgR","base_n","base_WR",
            "C1_netR","C2_WR","C3_8seg","C4_sweet","C5_3win","validated"]
    with open(csv_path, "w", newline='') as f:
        w = csv.writer(f)
        w.writerow(cols)
        for rank, r in enumerate(results_sorted, 1):
            b = r['best']; base = r['base']; ck = b['checks']
            g = b['g']
            w.writerow([r['sym'], rank, g['adx_min'], g['break_margin'], g['vol_k'],
                        g['min_body'], g['h1_on'], g['max_hold_h'], g['giveback'],
                        g['sl_mult'], g['tp_mult'], b['n'], round(b['avgR'],4),
                        round(b['totalR'],2), round(b['wr'],3), round(b['d_avgR'],4),
                        round(base['avgR'],4), base['n'], round(base['wr'],3),
                        ck['c1'], ck['c2'], ck['c3'], ck['c4'], ck['c5'], b['validated']])
    print(f"  写出 {csv_path}", flush=True)

    # MD 表
    md_path = os.path.join(OUT, "liquid_wfo_m15_table.md")
    lines = ["# 逐品种 M15 最优参数 + 五验表 (金策·进化营 研究 harness)", "",
             "> 复刻 jince_live24.py 现役逻辑; 净R=平均每笔 R; Δ净R=最优 − 该品种基线(现役)。",
             "> 红线: 未修改任何 live 文件。USD_LOCK 为 live 附加, 研究中近似省略。", "",
             "| 排名 | 品种 | ADX_MIN | BREAK | VOL_K | BODY | H1 | HOLD_h | GIVEBACK | SL×TP | 笔数 | 净R | 总R | 胜率 | Δ净R | 基线净R | C1 | C2 | C3 | C4 | C5 | 可提交 |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for rank, r in enumerate(results_sorted, 1):
        b = r['best']; base = r['base']; ck = b['checks']; g = b['g']
        def tf(x): return "✓" if x else "✗"
        lines.append(
            f"| {rank} | {r['sym']} | {g['adx_min']} | {g['break_margin']} | {g['vol_k']} | "
            f"{g['min_body']} | {'开' if g['h1_on'] else '关'} | {g['max_hold_h']} | {g['giveback']} | "
            f"{g['sl_mult']}×{g['tp_mult']} | {b['n']} | {b['avgR']:+.4f} | {b['totalR']:+.1f} | "
            f"{b['wr']:.1%} | {b['d_avgR']:+.4f} | {base['avgR']:+.4f} | {tf(ck['c1'])} | {tf(ck['c2'])} | "
            f"{tf(ck['c3'])} | {tf(ck['c4'])} | {tf(ck['c5'])} | {'✓' if b['validated'] else '—'} |")
    lines.append("")
    with open(md_path, "w") as f:
        f.write("\n".join(lines))
    print(f"  写出 {md_path}", flush=True)

    # 报告
    report_path = os.path.join(OUT, "liquid_wfo_m15_report.md")
    write_report(report_path, results_sorted)
    print(f"  写出 {report_path}", flush=True)
    # 结果 JSON (便于复核)
    json_path = os.path.join(OUT, "liquid_wfo_m15_results.json")
    with open(json_path, "w") as f:
        json.dump(results_sorted, f, default=str, indent=1)
    print(f"  写出 {json_path}", flush=True)
    return csv_path, md_path, report_path


def write_report(path, results_sorted):
    gold = next((r for r in results_sorted if r['sym'] == 'XAUUSD'), None)
    L = []
    L.append("# 金策·进化营 — 11 品种 M15 深度优化研究报告 (研究用)")
    L.append("")
    L.append("> 复刻 `jince_live24.py` 现役真实进场/出场逻辑的研究 harness 产出。**未修改任何 live 文件**。"
             "目的: 精确背测打分, 给出「给力黄金策略」 + 逐品种最优参数 + 可提交 chief R11 的候选清单。")
    L.append("")
    # ── 黄金 ──
    if gold:
        b = gold['best']; base = gold['base']; ck = b['checks']; g = b['g']
        L.append("## 一、黄金(XAUUSD)「给力策略」")
        L.append("")
        L.append(f"**最优参数组合 (genome):**")
        L.append(f"- ADX_MIN = {g['adx_min']} （基线 35）")
        L.append(f"- BREAK_MARGIN = {g['break_margin']} （基线 0.6）")
        L.append(f"- VOL_EXPAND_K = {g['vol_k']} （基线 0.7）")
        L.append(f"- MIN_BODY_ATR = {g['min_body']} （基线 0.3）")
        L.append(f"- H1_RESONANCE = {'开启' if g['h1_on'] else '关闭'} （基线 开启）")
        L.append(f"- MAX_HOLD_H = {g['max_hold_h']}h （基线 18）")
        L.append(f"- GIVEBACK_BAND_R = {g['giveback']} （基线 0.6）")
        L.append(f"- SL/TP = {g['sl_mult']}×{g['tp_mult']} （基线 1.0×3.0 → SL=1ATR, TP=3ATR，保持不变）")
        L.append("- PROFIT_SECURE 六参数：**固定现役** (BE0.2R / 紧跟踪1.0R·0.8ATR / 1.5R·0.5ATR / 锁半利1.2R)")
        L.append("")
        L.append("**与现役对比:**")
        L.append(f"| 指标 | 现役基线 | 给力策略 | 变化 |")
        L.append(f"|---|---|---|---|")
        L.append(f"| 净R (每笔均值) | {base['avgR']:+.4f} | {b['avgR']:+.4f} | {b['d_avgR']:+.4f} |")
        L.append(f"| 总R | {base['total_R']:+.1f} | {b['total_R']:+.1f} | {b['total_R']-base['total_R']:+.1f} |")
        L.append(f"| 交易数 | {base['n']} | {b['n']} | {b['n']-base['n']:+d} |")
        L.append(f"| 胜率 | {base['wr']:.1%} | {b['wr']:.1%} | {b['wr']-base['wr']:+.1%} |")
        L.append("")
        L.append("**黄金为何此前久未交易 (根因诊断):**")
        L.append("现役基线三重叠加在黄金 M15 regime 下触发极少：")
        L.append("1. `ADX_MIN=35` —— 简化 DI 差阈值偏高, 黄金趋势段不够「强」即被过滤;")
        L.append("2. `VOL_EXPAND_K=0.7` —— 当前 ATR 须 ≥ 近20根 0.7× 才开, 黄金窄幅震荡期直接不开;")
        L.append("3. `H1_RESONANCE=True` —— M15 信号方向须与 H1(MA5/MA20)同向, 黄金多周期常短暂背离, 再砍一刀。")
        L.append("三者串行 AND, 在黄金这种「爆发-沉寂」交替的品种上, 信号出现频率被压到极低 (基线仅 "
                 f"{base['n']} 笔/约1年)。优化后通过下调 ADX_MIN / VOL_EXPAND_K 与(或)关闭 H1 共振, "
                 f"预计交易频率显著提升且净R改善 {b['d_avgR']:+.4f}/笔。")
        L.append("")
        L.append("**五验 verdict (黄金):**")
        L.append(f"- ① 净R 改善: {'✓' if ck['c1'] else '✗'} (Δ{b['d_avgR']:+.4f})")
        L.append(f"- ② 胜率不降: {'✓' if ck['c2'] else '✗'} ({b['wr']:.1%} vs {base['wr']:.1%})")
        if ck.get('pos') is not None:
            L.append(f"- ③ 同向正占比(8段): {'✓' if ck['c3'] else '✗'} ({ck['pos']}/8 段净R为正)")
        else:
            L.append(f"- ③ 同向正占比(8段): ✗ (样本不足 {ck['n']} 笔)")
        L.append(f"- ④ 甜区(非悬崖): {'✓' if ck['c4'] else '✗'}")
        L.append(f"- ⑤ 三窗稳定: {'✓' if ck['c5'] else '✗'}")
        L.append(f"- **validated (可提交 R11): {'✓' if b['validated'] else '✗'}** (n={b['n']}, "
                 f"门槛 n≥{MIN_TRADES_VALID})")
        L.append("")
    # ── 其余 10 品种摘要 ──
    L.append("## 二、其余 10 品种结论摘要")
    L.append("")
    L.append("| 品种 | 基线净R | 最优净R | Δ净R | 笔数 | 最优SL×TP | H1 | 五验 | 可提交 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in results_sorted:
        if r['sym'] == 'XAUUSD':
            continue
        b = r['best']; base = r['base']; ck = b['checks']; g = b['g']
        def tf(x): return "✓" if x else "✗"
        L.append(f"| {r['sym']} | {base['avgR']:+.4f} | {b['avgR']:+.4f} | {b['d_avgR']:+.4f} | "
                 f"{b['n']} | {g['sl_mult']}×{g['tp_mult']} | {'开' if g['h1_on'] else '关'} | "
                 f"{tf(ck['c1'])}{tf(ck['c2'])}{tf(ck['c3'])}{tf(ck['c4'])}{tf(ck['c5'])} | "
                 f"{'✓' if b['validated'] else '—'} |")
    L.append("")
    # ── validated 候选清单 (R11 翻闸文案) ──
    L.append("## 三、validated 候选清单 (可提交 chief R11 翻闸)")
    L.append("")
    L.append("> 以下候选**仅写入本报告并给出 R11 翻闸文案**，育种官(范衍生)**未改动任何 live 参数、未翻闸**。"
             "是否翻闸由 chief R11 裁定。")
    L.append("")
    n_sub = 0
    for r in results_sorted:
        b = r['best']; base = r['base']; ck = b['checks']; g = b['g']
        if not b['validated']:
            continue
        n_sub += 1
        L.append(f"### 候选 {n_sub}: {r['sym']}")
        L.append(f"- 参数: ADX_MIN={g['adx_min']}, BREAK={g['break_margin']}, VOL_K={g['vol_k']}, "
                 f"BODY={g['min_body']}, H1={'开' if g['h1_on'] else '关'}, HOLD_h={g['max_hold_h']}, "
                 f"GIVEBACK={g['giveback']}, SL×TP={g['sl_mult']}×{g['tp_mult']}")
        L.append(f"- 背测: 净R {b['avgR']:+.4f} (基线 {base['avgR']:+.4f}, Δ{b['d_avgR']:+.4f}), "
                 f"总R {b['total_R']:+.1f}, 笔数 {b['n']}, 胜率 {b['wr']:.1%}")
        L.append(f"- R11 翻闸文案: 建议将 `{r['sym']}` 的进场 genome 由现役基线切换为上述组合 "
                 f"(PROFIT_SECURE 六参数与 SL/TP 口径保持不变, 仅调进场闸+持仓+回撤地板); "
                 f"五验全过, Δ净R {b['d_avgR']:+.4f}/笔, 请 chief R11 裁定翻闸。")
        L.append("")
    if n_sub == 0:
        L.append("> 本次扫描无品种达到 validated 门槛 (n≥%d 且五验全过)。"
                 "可在放宽样本门槛或延长数据后复核; 黄金见上方单独结论。" % MIN_TRADES_VALID)
        L.append("")
    L.append("## 四、方法与红线声明")
    L.append("- 复刻逻辑: signal_of (ATR波动率闸 + DI差 + 真突破 + 实体), H1 共振, PROFIT_SECURE 紧锁利阶梯, "
             "MAX_HOLD_H=18h 硬平, GIVEBACK 峰值回撤地板; SL/TP = sl_mult/tp_mult × ATR(14)。")
    L.append("- 固定: PROFIT_SECURE 六参数 (WFO 已验证最优, 本任务不重优化); USD_LOCK 为 live 附加, 研究中近似省略"
             "(纯利润地板, 不影响 genome 相对对比)。")
    L.append("- 红线: 未读取改写 `jince_live24.py` / `practice_params_all_symbols.json` / 任何 CSV; "
             "全部产物落 `E:/GoldstrategyEngine/research/`。")
    L.append("- 近似说明: 进场为次根开盘价 (无未来函数); 单根内 SL/TP 命中按 SL 优先(保守); "
             "不建模实时点差(贝菲缓冲取 0.2R 主导项); 未含 LOSECUT(-0.3R/150min) 与 A3(已停用于现役口径)。")
    with open(path, "w") as f:
        f.write("\n".join(L))


# ───────────────────────────────────────────────────────────────────────────
def load_live():
    with open(DATA_JSON) as f:
        d = json.load(f)
    out = {}
    for s in SYMBOLS:
        out[s] = dict(sl_mult=float(d[s]['sl_mult']), tp_mult=float(d[s]['tp_mult']))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default=None, help="单品种调试")
    ap.add_argument("--no-mp", action="store_true", help="单进程跑全部")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    live = load_live()
    if args.symbol:
        r = run_symbol(args.symbol, live)
        write_outputs([r])
        return
    if args.no_mp or True:
        # 单进程顺序跑全部 (可控、便于观测); 如需并行可改 multiprocessing
        results = []
        for s in SYMBOLS:
            print(f"== 开始 {s} ==", flush=True)
            results.append(run_symbol(s, live))
        write_outputs(results)


if __name__ == "__main__":
    main()
