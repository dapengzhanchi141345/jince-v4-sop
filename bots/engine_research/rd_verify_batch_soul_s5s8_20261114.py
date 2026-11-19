# -*- coding: utf-8 -*-
"""rd_verify_batch_soul_s5s8_20261114.py —— 灵魂闸 S5-S8 家窗口批 同分母五验
====================================================================
红线: 纯研究. 引擎 jince_live24.py / tools / REAL 零动. 产物落 data/ 与 research/.
同分母: 复用 research/rd_verify_batch_20261114.py (RB) 的引擎信号复现器
(prepare30/gen_signals/simulate, base=现行突破追进场 100%放行, 出场=引擎REAL口径 18h硬平),
候选只在事件流上做 预交易过滤 / 延迟进场 / 出场截断, 与 S1-S4 批同底 (net20261114 8品种).
规格: research/soul_s5s8_famwin_spec_20261114.md (全网实证只当料不当令).
口径钉死 (文档化代理, 可复跑):
  时区: tf_cache/M15 npz 的 t 均为 EET 墙钟 epoch (冬 UTC+2 / 夏 EEST UTC+3, K线铁律).
        EEST 段(墙钟 t): [3月末周日02:00, 10月首周日03:00) → off=3h 否则 2h; utc = t - off.
        美 DST(utc 坐标): [3月次周日07:00UTC, 11月首周日06:00UTC) → 金/股指窗口 +1h.
  S5 家时段窗闸 (事件触发 te=信号M30根收线+30min; kill 窗直接砍, go 窗仅预期语境):
    fx kill 00-07/21-24UTC(冬), 夏+1h; gold kill 00-07+12-13(衰竭窗), 夏+1h;
    stock kill 00-07, 夏+1h (16-19 段段①④双证据冲突→只砍00-07, 衰竭交S8出场端, 留痕);
    crypto kill 01-05(低收益窗), 无夏令.
  S6 定位图闸 (M15 tick_volume 重建, 只在 M15 窗口内激活, 窗口外保留=门不激活):
    三锚 00/07/13UTC 预标记 (只用锚前数据): ①昨日 POC/VAH/VAL (0.5×ATR15 分箱 70%值域)
    ②session 高低 (亚洲区 00-07UTC 当日; 00:00 锚用前日全日) ③VWAP (当日 00:00 UTC 日锚累计).
    事件落点(M15 收) 距任一 level ≤0.3×ATR15 → 进 S6 组, 其余剔除.
  S7b 吸收代理 (在 S6 事件集上; 无 footprint, M15 代理):
    8根窗口 max(tv)≥1.5×mean(100根tv) 且 7根价推进<0.5×ATR15 = 吸收签名 → 不追,
    等 2-3 根 M15 守住+翻转 (long: ≥2根收线≥吸收低+0.2ATR15; short 镜像) → 延迟 ~90min 进场
    (k+2 M30 根, SL/TP 几何随新根 ATR); 3根内未确认 = 该单剔除出 S7b 组.
  S7c 裸reclaim否决 (在 S6 事件集上; ②实证裸reclaim=50/50):
    reclaim=前根 M15 收<VWAP 且当根收>VWAP (long; short 镜像);
    结构=当根 M15 高≥当日亚洲区高(新高) 或 收于任一预标记 level 上/下方(对侧共振);
    裸 reclaim(无结构) 剔除出 S7c 组.
  S8 时间衰减离场 (管持仓端, base 事件集全量):
    开仓后到本族衰竭窗 (fx 16UTC/gold 15UTC/stock 19UTC/crypto 21UTC, 夏+1h) 未达TP → 平;
    与 12h 不过夜取先到: cap=min(下一到期衰竭窗, te+12h).
    对照 base = RB 引擎口径 18h 硬平 (spec 说 base"12h强平"=L4实盘红线口径, 回放 base
    沿用引擎 18h 保持与 S1-S4 批同分母, 差异留痕).
  五验 (逐品种, 禁跨品种平均): T1 净R(扣0.095)>0 且>=base | T2 胜率>=base-0.02 |
    T3 5折时间切分全正(n>=5) | T4 OOS70/30 两段皆正 | T5 成本0.15R 仍正 | ⑥净期望(均R)>=1.0.
    裁定: APPROVE=6/6 | WATCH=T1-T5>=3/5 且 (T4或T3) | REJECT=其余. 未过线=WATCH 0放大.
  US30: spec 要求首次入池; tf_cache 无 US30 M30/D1/M15 (今日回填未含) → 缺数挂账,
    本批 RB.SYMS 8 品种, US30 待下轮回填补跑 (spec "不够=降3折留痕" 升级口径).
"""
import os, sys, json, datetime as dt, calendar
import numpy as np

ROOT = "E:/GoldstrategyEngine"
sys.path.insert(0, os.path.join(ROOT, "research"))
import rd_verify_batch_20261114 as RB  # noqa: E402

SYMS = list(RB.SYMS)
M15DIR = os.path.join(ROOT, "research", "net20261114_m15")
COST, COST_T5 = RB.COST, RB.COST_T5

FAM = {"XAUUSD": "gold", "EURUSD": "fx",
       "BTCUSD": "crypto", "ETHUSD": "crypto", "SOLUSD": "crypto",
       "XRPUSD": "crypto", "LTCUSD": "crypto", "BNBUSD": "crypto",
       "US30": "stock", "US100": "stock"}
KILL_WIN = {"fx": ([0, 7], [21, 24]), "gold": ([0, 7], [12, 13]),
            "stock": ([0, 7],), "crypto": ([1, 5],)}
DECAY_H = {"fx": 16, "gold": 15, "stock": 19, "crypto": 21}
DST_KIND = {"fx": "eu", "gold": "us", "stock": "us", "crypto": None}


def _nth_sunday(year, month, n):
    last = calendar.monthrange(year, month)[1]
    d = dt.datetime(year, month, last)
    while d.weekday() != 6:
        d -= dt.timedelta(days=1)
    for _ in range(n - 1):
        d -= dt.timedelta(days=7)
    return d


def _bounds(kind, coord):
    lo, hi = [], []
    for y in range(2008, 2027):
        if kind == "eu":
            if coord == "wall":
                s = _nth_sunday(y, 3, 4).replace(hour=2)
                e = _nth_sunday(y, 10, 1).replace(hour=3)
            else:
                s = _nth_sunday(y, 3, 4).replace(hour=1)
                e = _nth_sunday(y, 10, 1).replace(hour=1)
        else:
            s = _nth_sunday(y, 3, 2).replace(hour=7)
            e = _nth_sunday(y, 11, 1).replace(hour=6)
        lo.append(s.timestamp()); hi.append(e.timestamp())
    return np.array(lo, dtype=np.int64), np.array(hi, dtype=np.int64)


def _in_ranges(t, lo, hi):
    m = np.zeros(len(t), dtype=bool)
    for i in range(len(lo)):
        m |= (t >= lo[i]) & (t < hi[i])
    return m


def eu_dst_on_wall(t):
    lo, hi = _bounds("eu", "wall")
    return _in_ranges(np.asarray(t, dtype=np.int64), lo, hi)


def us_dst_on_utc(utc):
    lo, hi = _bounds("us", "utc")
    return _in_ranges(np.asarray(utc, dtype=np.int64), lo, hi)


def utc_of(t_wall):
    off = np.where(eu_dst_on_wall(t_wall), 3, 2).astype(np.int64) * 3600
    return np.asarray(t_wall, dtype=np.int64) - off, off


def fam_dst_mask(utc_te, fam):
    kind = DST_KIND[fam]
    if kind is None:
        return np.zeros(len(utc_te), dtype=bool)
    if kind == "us":
        return us_dst_on_utc(utc_te)
    lo, hi = _bounds("eu", "utc")
    return _in_ranges(utc_te, lo, hi)


def s5_kill_mask(utc_te, fam):
    h = (utc_te // 3600).astype(np.int64) % 24
    d = fam_dst_mask(utc_te, fam)
    he = np.where(d, h + 1, h) % 24
    m = np.zeros(len(utc_te), dtype=bool)
    for lo, hi in KILL_WIN[fam]:
        m |= (he >= lo) & (he <= hi % 24)
    return m


def s8_cap(utc_te, off_te, fam):
    d = fam_dst_mask(utc_te, fam)
    dh = DECAY_H[fam] + np.where(d, 1, 0)
    day_utc = utc_te // 86400 * 86400
    decay_ts = day_utc + dh * 3600
    decay_ts = np.where(decay_ts <= utc_te + 1800, decay_ts + 86400, decay_ts)
    cap_utc = np.minimum(decay_ts, utc_te + 12 * 3600)
    return cap_utc + off_te  # 回墙钟 (跨 DST 切换误差≤1h, 研究口径留痕)


# ── M15 预标记 level (UTC 日坐标) ─────────────────────────────────
def build_levels(m15):
    t = m15["t"].astype(np.int64)
    h, l, c, tv = m15["h"], m15["l"], m15["c"], m15["tv"]
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(np.maximum(h - l, np.abs(h - pc)), np.abs(l - pc))
    atr15 = RB.rollmean(tr, 14)
    utc, off = utc_of(t)
    day_utc = utc // 86400 * 86400
    hour_utc = (utc % 86400) // 3600
    typ = (h + l + c) / 3.0
    n = len(t)
    out = dict(t=t, c=c, tv=tv, atr15=atr15,
               poc=np.full(n, np.nan), vah=np.full(n, np.nan), val=np.full(n, np.nan),
               pre_hi=np.full(n, np.nan), pre_lo=np.full(n, np.nan),
               a_hi=np.full(n, np.nan), a_lo=np.full(n, np.nan),
               vwap_last=np.full(n, np.nan))
    uniq = np.unique(day_utc)
    d_poc = {v: np.nan for v in uniq}
    d_vah = dict(d_poc); d_val = dict(d_poc)
    d_hi = dict(d_poc); d_lo = dict(d_poc)
    d_a_hi = dict(d_poc); d_a_lo = dict(d_poc)
    d_vwap_last = dict(d_poc)
    for d0 in uniq:
        m_d = day_utc == d0
        hh, ll, cc, vv = h[m_d], l[m_d], c[m_d], tv[m_d]
        if len(hh) < 4:
            continue
        hi_v, lo_v = float(hh.max()), float(ll.min())
        d_hi[d0] = hi_v; d_lo[d0] = lo_v
        ma = hour_utc[m_d] < 7
        if ma.any():
            d_a_hi[d0] = float(hh[ma].max()); d_a_lo[d0] = float(ll[ma].min())
        if vv.sum() > 0:
            d_vwap_last[d0] = float((typ[m_d] * vv).sum() / vv.sum())
        a15 = float(np.nanmax(atr15[m_d])) if np.any(np.isfinite(atr15[m_d])) else 0.0
        if a15 > 0 and hi_v > lo_v:
            nb = max(4, int(np.ceil((hi_v - lo_v) / (0.5 * a15))))
            edges = np.linspace(lo_v, hi_v, nb + 1)
            bidx = np.clip(np.searchsorted(edges, cc, side="right") - 1, 0, nb - 1)
            vol = np.zeros(nb)
            np.add.at(vol, bidx, vv)
            if vol.max() > 0:
                order = np.argsort(-vol)
                poc_b = int(order[0])
                cum = 0.0
                va = {poc_b}
                i = 1
                target = 0.70 * vol.sum()
                while i < len(order) and cum + vol[order[i]] < target:
                    va.add(int(order[i])); cum += vol[order[i]]; i += 1
                d_poc[d0] = 0.5 * (edges[poc_b] + edges[poc_b + 1])
                d_vah[d0] = 0.5 * (edges[max(va)] + edges[max(va) + 1])
                d_val[d0] = 0.5 * (edges[min(va)] + edges[min(va) + 1])
    prev_key = {v: u for u, v in zip(uniq[:-1], uniq[1:])}
    for i in range(n):
        d0 = day_utc[i]
        pk = prev_key.get(d0, -1)
        if pk in d_poc:
            out["poc"][i] = d_poc[pk]
            out["vah"][i] = d_vah[pk]
            out["val"][i] = d_val[pk]
        out["pre_hi"][i] = d_hi.get(pk, np.nan)
        out["pre_lo"][i] = d_lo.get(pk, np.nan)
        out["a_hi"][i] = d_a_hi.get(d0, np.nan)
        out["a_lo"][i] = d_a_lo.get(d0, np.nan)
        out["vwap_last"][i] = d_vwap_last.get(d0, np.nan)
    return out


def event_levels(lv, j, hour_u):
    lvls = np.array([lv["poc"][j], lv["vah"][j], lv["val"][j],
                     lv["a_hi"][j] if hour_u >= 7 else lv["pre_hi"][j],
                     lv["a_lo"][j] if hour_u >= 7 else lv["pre_lo"][j],
                     lv["vwap_last"][j]])
    return lvls


def masks_s6_s7(P, kb, sb, db, tb, lv, te_wall, utc_te, j):
    """返回 (s6_keep, s7c_keep, s7b_delay, s7b_drop, s7b_k_new, n_inwin). 窗口外保留."""
    n = len(kb)
    c15, tv15, a15 = lv["c"], lv["tv"], lv["atr15"]
    inwin = (j >= 100) & (j < len(lv["t"]))
    s6_keep = np.ones(n, dtype=bool)
    s7c_keep = np.ones(n, dtype=bool)
    s7b_delay = np.zeros(n, dtype=bool)
    s7b_drop = np.zeros(n, dtype=bool)
    s7b_k_new = kb.copy()
    hour_u = (utc_te % 86400) // 3600
    px = np.full(n, np.nan)
    atr_e = np.full(n, np.nan)
    if inwin.any():
        px[inwin] = c15[j[inwin]]
        atr_e[inwin] = a15[j[inwin]]
        lvls = np.array([event_levels(lv, int(jj), int(hh)) for jj, hh in zip(j[inwin], hour_u[inwin])])
        dist = np.abs(lvls - px[inwin, None])
        with np.errstate(invalid="ignore"):
            near = (dist <= 0.3 * atr_e[inwin, None]) & np.isfinite(lvls)
        s6_keep[inwin] = near.any(axis=1)
        rj = j[inwin]
        cj1 = c15[np.clip(rj - 1, 0, len(c15) - 1)]
        fin = np.isfinite(lvls[:, 5])
        longm = sb[inwin] > 0
        rec = np.zeros(int(inwin.sum()), dtype=bool)
        idx_l = np.where(longm & fin)[0]
        if len(idx_l):
            rec[idx_l] = (cj1[idx_l] < lvls[idx_l, 5]) & (c15[rj[idx_l]] > lvls[idx_l, 5])
        idx_s = np.where((~longm) & fin)[0]
        if len(idx_s):
            rec[idx_s] = (cj1[idx_s] > lvls[idx_s, 5]) & (c15[rj[idx_s]] < lvls[idx_s, 5])
        struct = np.zeros(int(inwin.sum()), dtype=bool)
        a_fin = np.isfinite(lvls[:, 3]) & np.isfinite(lvls[:, 4])
        near_lvl = (np.abs(lvls[:, :5] - c15[rj][:, None]).min(axis=1) <= 0.3 * atr_e[inwin])
        if len(idx_l):
            struct[idx_l] = ((c15[rj[idx_l]] >= lvls[idx_l, 3]) & a_fin[idx_l]) | \
                ((c15[rj[idx_l]] >= lvls[idx_l, 0]) & near_lvl[idx_l])
        if len(idx_s):
            struct[idx_s] = ((c15[rj[idx_s]] <= lvls[idx_s, 4]) & a_fin[idx_s]) | \
                ((c15[rj[idx_s]] <= lvls[idx_s, 0]) & near_lvl[idx_s])
        s7c_keep[inwin] = ~(rec & ~struct)
        for i in np.where(inwin)[0]:
            jj = int(j[i])
            wtv = tv15[jj - 7:jj + 1]
            if len(wtv) < 8:
                continue
            m100 = float(tv15[jj - 99:jj + 1].mean())
            if m100 <= 0:
                continue
            a = float(atr_e[i])
            if not np.isfinite(a) or a <= 0:
                continue
            absorbed = (float(wtv.max()) >= 1.5 * m100) and (abs(float(c15[jj] - c15[jj - 7])) < 0.5 * a)
            if not absorbed:
                continue
            s7b_delay[i] = True
            cf = c15[jj + 1:jj + 4]
            if len(cf) < 2:
                s7b_drop[i] = True
                continue
            la = float(np.min(lv["l"][jj - 7:jj + 1]))
            ha = float(np.max(lv["h"][jj - 7:jj + 1]))
            if sb[i] > 0:
                ok = int((cf >= la + 0.2 * a).sum()) >= 2
            else:
                ok = int((cf <= ha - 0.2 * a).sum()) >= 2
            if not ok:
                s7b_drop[i] = True
            else:
                s7b_k_new[i] = kb[i] + 2
    return s6_keep, s7c_keep, s7b_delay, s7b_drop, s7b_k_new, int(inwin.sum())


def simulate_cap(P, g, k, s, dist, tp_d, cap, cost=COST):
    """RB.simulate 复制 + 逐单时间帽 (epoch 墙钟): 到帽未达 TP/SL → 该根收线平 (etype=3)."""
    N = P["n"]
    e = k + 1
    ok = e < N
    k, s, e, dist, tp_d, cap = k[ok], s[ok], e[ok], dist[ok], tp_d[ok], cap[ok]
    nC = len(k)
    if nC == 0:
        return dict(R=np.array([]), et=np.array([]), ty=np.array([]))
    Lmax = int(g["max_hold_h"] / 0.5)
    idx = e[:, None] + np.arange(Lmax)[None, :]
    beyond = idx >= N
    ic = np.minimum(idx, N - 1)
    Hs = P["h"][ic] * s[:, None]
    Ls = P["l"][ic] * s[:, None]
    HI = np.where(beyond, -np.inf, np.maximum(Hs, Ls))
    LO = np.where(beyond, -np.inf, np.minimum(Hs, Ls))
    Cs = P["c"][ic] * s[:, None]
    A = P["atr"][ic]
    entry = P["o"][e] * s
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
        timed = alive & (P["t"][ic[:, kk]] + 1800 > cap)
        if timed.any():
            R[timed] = (cc[timed] - entry[timed]) / dist[timed] - cost
            etype[timed] = 3
            exit_t[timed] = P["t"][ic[timed, kk]]
            alive[timed] = False
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
    R = np.clip(np.where(np.isfinite(R), R, 0.0), RB.WINSOR_LO, RB.WINSOR_HI)
    exit_bar = np.minimum(e + Lmax - 1, N - 1)
    order = np.argsort(k)
    taken, nb = [], -1
    for i in order:
        if k[i] >= nb:
            taken.append(i)
            nb = exit_bar[i]
    taken = np.array(taken, dtype=np.int64)
    return dict(R=R[taken], et=exit_t[taken], ty=etype[taken])


def ev(res):
    R, et = res["R"], res["et"]
    n = len(R)
    return dict(n=n, net=float(R.sum()) if n else 0.0,
                avg=float(R.mean()) if n else 0.0,
                win=float((R > 0).mean()) if n else 0.0, R=R, et=et)


def gates_of(c, base, c015, oos_cut):
    mtr = c["et"] <= oos_cut
    tr = dict(n=int(mtr.sum()), net=float(c["R"][mtr].sum()),
              avg=float(c["R"][mtr].mean()) if mtr.any() else 0.0)
    te = dict(n=int((~mtr).sum()), net=float(c["R"][~mtr].sum()),
              avg=float(c["R"][~mtr].mean()) if (~mtr).any() else 0.0)
    g6 = c["avg"] >= 1.0
    g = dict(T1=bool(c["net"] > 0 and c["net"] >= base["net"]),
             T2=bool(c["win"] >= base["win"] - 0.02),
             T3=bool(c["n"] >= 5 and all(x.sum() > 0 for x in np.array_split(c["R"], 5))),
             T4=bool(tr["net"] > 0 and te["net"] > 0),
             T5=bool(c015["net"] > 0), g6=bool(g6), train=tr, test=te)
    g["passed"] = sum(int(g[x]) for x in ("T1", "T2", "T3", "T4", "T5", "g6"))
    t15 = g["passed"] - int(g["g6"])
    g["verdict"] = "APPROVE" if g["passed"] == 6 else ("WATCH" if t15 >= 3 and (g["T4"] or g["T3"]) else "REJECT")
    return g


def main():
    params = json.load(open(os.path.join(ROOT, "data", "practice_params_all_symbols.json"), encoding="utf-8"))
    results = {}
    us30_note = ("tf_cache 无 US30 M30/D1/M15 (今日回填未含) → 按 spec 降折留痕: "
                 "本批 RB.SYMS 8 品种, US30 待下轮回填后补跑同分母")
    for s in SYMS:
        P = RB.prepare30(s)
        p = params.get(s, {})
        g = dict(adx_min=float(p.get("adx_min", 35.0)), break_margin=0.6, min_body=0.3,
                 h1_on=False, max_hold_h=18, giveback=0.6,
                 sl_mult=float(p.get("sl_mult", 1.0)), tp_mult=float(p.get("tp_mult", 3.0)))
        kb, sb, db, tb = RB.gen_signals(P, g)
        base = ev(RB.simulate(P, g, kb, sb, dist=db, tp_d=tb))
        base015 = ev(RB.simulate(P, g, kb, sb, dist=db, tp_d=tb, cost=COST_T5))
        oos_cut = float(np.quantile(P["t"], 0.70))
        fam = FAM[s]
        te_wall = P["t"][kb] + 1800
        utc_te, off_te = utc_of(te_wall.astype(np.int64))
        m15f = os.path.join(M15DIR, f"{s}_M15.npz")
        n_inwin = 0
        s6_keep = s7c_keep = np.ones(len(kb), dtype=bool)
        s7b_delay = s7b_drop = np.zeros(len(kb), dtype=bool)
        s7b_k_new = kb.copy()
        if os.path.exists(m15f):
            z = np.load(m15f)
            m15d = {k: z[k] for k in ("t", "h", "l", "c", "tv") if k in z.files}
            z.close()
            lv = build_levels(m15d)
            lv["h"] = m15d["h"]
            lv["l"] = m15d["l"]
            j = np.searchsorted(lv["t"], te_wall.astype(np.int64) - 900, side="right") - 1
            s6_keep, s7c_keep, s7b_delay, s7b_drop, s7b_k_new, n_inwin = \
                masks_s6_s7(P, kb, sb, db, tb, lv, te_wall, utc_te, j)
        kill = s5_kill_mask(utc_te, fam)
        cap = s8_cap(utc_te, off_te, fam)
        rows = {"base": dict(n=base["n"], net=round(base["net"], 2), avg=round(base["avg"], 4),
                             win=round(base["win"], 4), netR_015=round(base015["net"], 2),
                             verdict="BASE")}

        def run_row(name, k, ss, dd, tt, cap_arr=None):
            if len(k) == 0:
                rows[name] = dict(n=0, net=0.0, avg=0.0, win=0.0, netR_015=0.0,
                                  gates=dict(T1=False, T2=False, T3=False, T4=False, T5=False,
                                             g6=False, passed=0), verdict="REJECT", empty=True)
                return
            res = RB.simulate(P, g, k, ss, dist=dd, tp_d=tt) if cap_arr is None \
                else simulate_cap(P, g, k, ss, dd, tt, cap_arr)
            c = ev(res)
            res0 = RB.simulate(P, g, k, ss, dist=dd, tp_d=tt, cost=COST_T5) if cap_arr is None \
                else simulate_cap(P, g, k, ss, dd, tt, cap_arr, cost=COST_T5)
            c015 = ev(res0)
            gt = gates_of(c, base, c015, oos_cut)
            rows[name] = dict(n=c["n"], net=round(c["net"], 2), avg=round(c["avg"], 4),
                              win=round(c["win"], 4), netR_015=round(c015["net"], 2),
                              gates={k2: v2 for k2, v2 in gt.items() if k2 not in ("train", "test", "verdict")},
                              train=gt["train"], test=gt["test"], verdict=gt["verdict"])

        k5 = kb[~kill]
        run_row("s5", k5, sb[~kill], db[~kill], tb[~kill])
        rows["s5"]["n_killed"] = int(kill.sum())
        run_row("s6", kb[s6_keep], sb[s6_keep], db[s6_keep], tb[s6_keep])
        rows["s6"]["n_killed"] = int((~s6_keep).sum())
        idx6 = np.where(s6_keep)[0]
        kb2 = s7b_k_new[idx6]
        sb2 = sb[idx6]
        keep2 = ~s7b_drop[idx6]
        kb2, sb2 = kb2[keep2], sb2[keep2]
        if len(kb2):
            a0 = np.maximum(P["atr"][np.clip(kb2, 0, P["n"] - 1)], 1e-9)
            slm = min(g["sl_mult"], RB.REAL_SL_CAP)
            db2 = slm * a0
            tb2 = np.clip(np.maximum(g["tp_mult"] * a0, 2.0 * db2), 2.0 * db2, 12.0 * a0)
        else:
            db2 = tb2 = np.array([])
        run_row("s7b", kb2, sb2, db2, tb2)
        rows["s7b"]["n_killed"] = int(len(idx6) - len(kb2))
        rows["s7b"]["n_delayed"] = int(s7b_delay[idx6][keep2].sum()) if len(idx6) else 0
        run_row("s7c", kb[s7c_keep], sb[s7c_keep], db[s7c_keep], tb[s7c_keep])
        rows["s7c"]["n_killed"] = int((~s7c_keep).sum())
        run_row("s8", kb, sb, db, tb, cap_arr=cap)
        run_row("s5s8", k5, sb[~kill], db[~kill], tb[~kill], cap_arr=cap[~kill])
        rows["n_events"] = len(kb)
        rows["n_inwin_m15"] = n_inwin
        rows["fam"] = fam
        results[s] = rows
        print(s, "fam=%s n_events=%d inwin=%d" % (fam, len(kb), n_inwin),
              {nm: r["verdict"] for nm, r in rows.items()
               if isinstance(r, dict) and "verdict" in r and nm != "base"},
              "base_net=%.1f" % rows["base"]["net"], flush=True)
    out = dict(
        meta=dict(ts=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                  kline_source=RB.KLINE_SRC + " | M15=net20261114_m15 (tick_volume; 窗口 XAU/EUR 2025-03/04~11-13, 币系 2025-09~11-14, 窗口外 M15 门不激活保留)",
                  cost=COST, cost_t5=COST_T5,
                  us30_note=us30_note,
                  protocol=("同分母五验 S5-S8: base=RB引擎复现100%放行(18h硬平, 与S1-S4批同底); "
                            "T1净R扣0.095>0且>=base / T2胜率不劣 / T3五折全正 / T4 OOS70/30两段皆正 / "
                            "T5 0.15R成本仍正 / ⑥净期望(均R)>=1.0; 逐品种裁定, 禁跨品种平均; "
                            "未过线=WATCH 0放大, 翻闸走 chief R11 双裁"),
                  real_account_untouched="30261104 零动; 引擎只读"),
        symbols=results)
    with open(os.path.join(ROOT, "data", "rd_verify_batch_soul_s5s8_20261114.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=float)
    print("DONE json written: data/rd_verify_batch_soul_s5s8_20261114.json", flush=True)


if __name__ == "__main__":
    main()
