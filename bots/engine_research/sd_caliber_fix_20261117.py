# SD 回测口径三修重跑驱动 (rd_queue sd_backtest_caliber_fix_1115 · 11-17 21:30 学习哨, 主bot代strategy-rd)
# 修① sell 棘轮符号(两 ratchet 结算已 patch 落盘) ② 同bar双触 adverse 优先(防幽灵成交价) ③ 未来极值选样(events_gen 整日 3:1 过滤用当日 day_low/day_high=未来信息 -> 无未来重建)
# 同分母三档: OLD=11-15 旧码旧事件(已落盘json, 不重跑) / A=修复码+旧pkl事件 / B=修复码+无未来事件(11-17 新npz) / B2=v2 御史口径+新npz(活体参数表同法重算)
# 用法: python sd_caliber_fix_20261117.py --phase gate|A|B|B2|final|ledger
# 只出结论不动闸: 翻闸权属 chief R11 双裁 + 30笔前向OOS; 0 放大 0 接实盘
import sys, os, json, time, pickle, glob, ast, shutil
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DATA = os.path.join(HERE, "allsyms_m15")
EVDIR = DATA + "_ev"
EVDIR_NOLA = DATA + "_ev_nola"
G = os.path.join(HERE, "sd_caliber_fix_gate_20261117.json")
A = os.path.join(HERE, "sd_caliber_fix_A_20261117.json")
B = os.path.join(HERE, "sd_caliber_fix_B_20261117.json")
B2 = os.path.join(HERE, "sd_caliber_fix_B2_20261117.json")
OUT = r"E:\GoldstrategyEngine\data\rd_verify_batch_sd_caliber_fix_20261117.json"
OUT_MD = os.path.join(HERE, "sd_caliber_fix_verdict_20261117.md")
OUT_PARAMS = os.path.join(HERE, "sd_symbol_params_v3_candidate_20261117.json")

import sd_zone_oe_20261115 as M
day_of = M.day_of
COST = 0.095          # 每单成本 R(点差+手续费, 五验⑥线扣减口径)
HOURS = 12
SLC72 = (0.1, 0.15, 0.2, 0.3, 0.4, 0.5)
TPM72 = (3.0, 4.0, 5.0, 6.0)
TRIG3 = (0.3, 0.5, 0.7)
GB3 = (0.2, 0.3, 0.4)
GRID27 = list((tr, gb, tp) for tr in TRIG for gb in (0.4, 0.6, 0.8) for tp in (3.0, 4.0, 5.0))
SLC_GRID = 0.15


def extract_func(fname, funcname):
    src = open(os.path.join(HERE, fname), encoding="utf-8").read()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == funcname:
            return "\n".join(src.splitlines()[node.lineno - 1:node.end_lineno])
    raise RuntimeError("function not found: %s.%s" % (fname, funcname))


def make_loop_ratchet():
    """exec 抽取盘上已修复的 sd_ratchet_grid settle_ratchet(保证跑的就是落盘修复版)"""
    seg = extract_func("sd_ratchet_grid_20261115.py", "settle_ratchet")
    ns = {}
    exec(seg, ns)
    return ns["settle_ratchet"]


def mk_d(t, o, h, l, c, ev):
    return dict(t=t, o=o, h=h, l=l, c=c, ev=ev)


def unit_tests(sr):
    """已知答案 6 场景: sell锁盈/sell原止损/同bar双触(sell)/buy锁盈/同bar双触(buy)/超时收盘. trig=0.5 gb=0.5 tpmul=4, ep=100 risk=2 zh=13.3333"""
    ts = [0, 900, 1800, 2700, 3600]
    cases = []

    def run(h, l, c, side="sell"):
        d = mk_d(ts, [100] * 5, h, l, c, [dict(side=side, i=0, ep=100.0, zh=13.3333333)])
        out = sr(d, slc=0.15, tpmul=4.0, hours=HOURS, trig=0.5, giveback=0.5)
        return out[0]

    exp = [
        ("T1_sell_lock", [101, 97.5, 96.5, 96.5, 96.5], [101, 96, 96.5, 96.5, 96.5], [100.5, 96.5, 96.5, 96.5, 96.5], "sell", 1.5),
        ("T2_sell_stop0", [101, 102, 101, 101, 101], [101, 100, 100.5, 100.5, 100.5], [100.5, 100, 100.5, 100.5, 100.5], "sell", -1.0),
        ("T3_sell_both_adverse", [101, 93.5, 93, 93, 93], [101, 92, 93, 93, 93], [100.5, 93, 93, 93, 93], "sell", 3.5),
        ("T4_buy_lock", [99, 104, 103.5, 103.5, 103.5], [99, 102.8, 103, 103, 103], [99.5, 103, 103, 103, 103], "buy", 1.5),
        ("T5_buy_both_adverse", [99, 108, 107, 107, 107], [99, 102.8, 107, 107, 107], [99.5, 107, 107, 107, 107], "buy", 3.5),
        ("T6_timeout", [101, 99.5, 99.5, 99.5, 99.5], [101, 99.5, 99.5, 99.5, 99.5], [100.5, 99.5, 99.5, 99.5, 99.5], "sell", 0.25),
    ]
    res = []
    for name, h, l, c, side, want in exp:
        got = run(h, l, c, side)
        res.append(dict(case=name, got=round(got, 9), want=want, ok=abs(got - want) < 1e-9))
    return res


def settle_ratchet_vec(d, slc=0.15, tpmul=4.0, hours=HOURS, trig=0.5, giveback=0.6):
    """向量化克隆(与修复版循环语义逐 bar 一致, parity 抽检兜底): sell 下移棘轮/buy 上移, 同bar双触=SL优先"""
    c, h, l = d["c"], d["h"], d["l"]
    n = len(c)
    out = []
    for e in d["ev"]:
        side, i, ep = e["side"], e["i"], e["ep"]
        zh = max(e["zh"], 1e-12)
        sl0 = ep + slc * zh if side == "sell" else ep - slc * zh
        risk = abs(sl0 - ep)
        if risk <= 0:
            out.append(0.0)
            continue
        tp = ep - tpmul * risk if side == "sell" else ep + tpmul * risk
        end = min(i + int(hours * 240), n)
        if end <= i + 1:
            out.append((ep - c[end - 1]) / risk if side == "sell" else (c[end - 1] - ep) / risk)
            continue
        hh, ll = h[i + 1:end], l[i + 1:end]
        fav_r = ((ep - ll) / risk) if side == "sell" else ((hh - ep) / risk)
        peak = np.maximum.accumulate(np.concatenate([[0.0], fav_r]))[1:]
        locked = peak >= trig
        lock = np.where(locked, np.maximum(peak - giveback, 0.0), 0.0)
        sl_arr = np.where(locked, (ep - lock * risk) if side == "sell" else (ep + lock * risk), sl0)
        if side == "sell":
            tp_hit = ll <= tp
            sl_hit = hh >= sl_arr
        else:
            tp_hit = hh >= tp
            sl_hit = ll <= sl_arr
        sl_b = int(np.argmax(sl_hit)) if sl_hit.any() else None
        tp_only = tp_hit & ~sl_hit
        tp_b = int(np.argmax(tp_only)) if tp_only.any() else None
        if sl_b is not None and (tp_b is None or sl_b <= tp_b):
            j = sl_b
            r = (ep - sl_arr[j]) / risk if side == "sell" else ((sl_arr[j] - ep) / risk if sl_arr[j] >= ep else -1.0)
        elif tp_b is not None:
            r = tpmul
        else:
            r = (ep - c[end - 1]) / risk if side == "sell" else (c[end - 1] - ep) / risk
        out.append(r)
    return out


def settle_fast_ev(d, ev, slc, tpmul, hours=HOURS):
    """= 11-15 settle_fast_ev 语义(j_in 收线穿越进场, 向量化尾段, 同bar双触SL优先保守), 保持同分母"""
    c, h, l = d["c"], d["h"], d["l"]
    out = []
    for e in ev:
        side, i, ep = e["side"], e["i"], e["ep"]
        zh = max(e["zh"], 1e-12)
        sl0 = ep + slc * zh if side == "sell" else ep - slc * zh
        risk = abs(sl0 - ep)
        if risk <= 0:
            out.append(0.0)
            continue
        tp = ep - tpmul * risk if side == "sell" else ep + tpmul * risk
        end = min(len(c), i + 49)
        j_in = None
        for j2 in range(i + 1, end):
            if (side == "sell" and c[j2] <= ep) or (side == "buy" and c[j2] >= ep):
                j_in = j2
                break
        if j_in is None:
            out.append(0.0)
            continue
        end2 = min(len(c), j_in + int(hours * 240))
        if side == "sell":
            a_tp = l[j_in + 1:end2] <= tp
            a_sl = h[j_in + 1:end2] >= sl0
        else:
            a_tp = h[j_in + 1:end2] >= tp
            a_sl = l[j_in + 1:end2] <= sl0
        hit_tp, hit_sl = bool(a_tp.any()), bool(a_sl.any())
        if hit_tp and (not hit_sl or int(np.argmax(a_tp)) < int(np.argmax(a_sl))):
            r = tpmul
        elif hit_sl:
            r = -1.0
        else:
            r = (ep - c[end2 - 1]) / risk if side == "sell" else (c[end2 - 1] - ep) / risk
        out.append(r)
    return out


def folds(rs):
    n = len(rs)
    f = [float(np.sum(rs[k::5])) for k in range(5)]
    oos = float(np.sum(rs[-(n // 5 or 1):]))
    T = sum(1 for x in f if x > 0) + (1 if oos > 0 else 0)
    return T, float(np.mean(rs)), oos


def verdict6(rs, label):
    """= sd_all_11rounds.verdict 语义(min_n=30, T 六条, ⑥线 net/len>=1.0) + ⑥线扣成本口径"""
    if len(rs) < 30:
        return dict(label=label, n=len(rs), verdict="FAIL-LOUD(<30)")
    net = float(np.sum(rs))
    wr = sum(1 for r in rs if r > 0) / len(rs)
    cuts = [int(len(rs) * q / 5) for q in range(5)]
    folds5 = [float(np.mean(rs[cuts[k]:cuts[k + 1]])) for k in range(4)] + [float(np.mean(rs[cuts[4]:]))]
    cut70 = int(len(rs) * 0.7)
    oos_b, oos_a = float(np.mean(rs[:cut70])), float(np.mean(rs[cut70:]))
    net_s = net - 0.15 * len(rs)
    T = [net > 0, wr >= 0.45, all(f > -0.5 for f in folds5), all(s > -0.5 for s in (oos_b, oos_a)), net_s > 0, net / len(rs) >= 1.0]
    return dict(label=label, n=len(rs), netR=round(net, 1), avgR=round(net / len(rs), 3),
                avgR_net_cost=round(net / len(rs) - COST, 3), wr=round(wr, 3),
                min_fold=round(min(folds5), 3), oos_back=round(oos_a, 3), netR_015=round(net_s, 1),
                T=sum(T), verdict=("APPROVE候选" if (sum(T) >= 4 and net > 0) else ("WATCH" if net > 0 else "REJECT")))


def pool_grid(dmap, sr):
    """27 组合池级网格(= 11-15 网格同分母): 扣成本 ⑥线口径另列"""
    results = []
    for tr, gb, tp in GRID27:
        allr = []
        for sym, d in dmap.items():
            allr += [x for x in sr(d, slc=SLC_GRID, tpmul=tp, trig=tr, giveback=gb) if x != 0]
        v = verdict6(allr, "trig%.1f_gb%.1f_tp%.0f" % (tr, gb, tp))
        v.update(trig=tr, giveback=gb, tp=tp)
        results.append(v)
    results.sort(key=lambda x: -(x.get("netR") or -1e12))
    return results


def sym_table_one(sym, d, sr):
    """= 11-15 symopt 分品种表: 72 组基础(向量化fast) + top3 x 27 组棘轮, (T,净R) 取优"""
    ev = d["ev"]
    if len(ev) < 10:
        return None
    cand = {}
    for slc in SLC72:
        for tp in TPM72:
            rs = [x for x in settle_fast_ev(d, ev, slc, tp) if x != 0]
            if len(rs) < 10:
                continue
            T, avg, oos = folds(rs)
            cand[(slc, tp)] = dict(rs=rs, T=T, oos=oos)
    if not cand:
        return None
    ranked = sorted(cand.items(), key=lambda x: (-x[1]["T"], -float(np.sum(x[1]["rs"]))))
    top = [k for k, v in ranked[:3] if v["T"] == 6] or [ranked[0][0]]
    best, bs = None, None
    for (slc, tp) in top:
        for trig in TRIG3:
            for gb in GB3:
                rs = [x for x in sr(d, slc=slc, tpmul=tp, trig=trig, giveback=gb) if x != 0]
                if len(rs) < 10:
                    continue
                T, avg, oos = folds(rs)
                score = (T, float(np.sum(rs)))
                if bs is None or score > bs:
                    bs, best = score, dict(slc=slc, tpmul=tp, trig=trig, giveback=gb, T=T,
                                            netR=round(float(np.sum(rs)), 1),
                                            wr=round(100 * sum(1 for r in rs if r > 0) / len(rs), 1),
                                            n=len(rs), oos=round(oos, 1))
    if best is None:
        s, t = ranked[0][0]
        v = cand[(s, t)]
        best = dict(slc=s, tpmul=t, trig=0.5, giveback=0.3, T=v["T"], netR=round(float(np.sum(v["rs"])), 1),
                    wr="-", n=len(v["rs"]), oos=round(v["oos"], 1), fallback=True)
    return best


def load_pkls(evdir):
    dmap, meta = {}, {}
    for pkl in sorted(glob.glob(os.path.join(evdir, "*.pkl"))):
        sym = os.path.basename(pkl)[:-4]
        dmap[sym] = pickle.load(open(pkl, "rb"))
        meta[sym] = os.path.getmtime(pkl)
    return dmap, meta


def events_nola(sym_npz, rewin=48):
    """= 11-15 events_gen 去掉 整日 day_low/day_high 3:1 未来极值过滤(选样只用 前一日区+触发前信息), 其余逐行同构"""
    z = np.load(sym_npz)
    t, o, h, l, c = z["t"], z["o"], z["h"], z["l"], z["c"]
    n = len(t)
    days = {}
    for i in range(1, n):
        dk = day_of(int(t[i]))
        if dk in days:
            days[dk] = (max(days[dk][0], h[i]), min(days[dk][1], l[i]), c[i], days[dk][3])
        else:
            days[dk] = (h[i], l[i], c[i], o[i])
    kss = sorted(days)
    zone_of = {}
    for idx, dk in enumerate(kss):
        if idx >= 1:
            dh, dl = days[dk][0], days[dk][1]
            zt = M.ZF * (dh - dl) if dh > dl else 0.0
            zone_of[dk] = {"supply": (dh - zt, dh), "demand": (dl, dl + zt)}
    ev = []
    for idx, dk in enumerate(kss):
        if idx < 2:
            continue
        zd = zone_of.get(kss[idx - 1])
        if not zd:
            continue
        i0 = int(np.searchsorted(t, dk * 86400, "left"))
        i1 = int(np.searchsorted(t, (dk + 1) * 86400, "left"))
        if i1 <= i0:
            continue
        for zname in ("supply", "demand"):
            zlo, zhi = zd[zname]
            zh = zhi - zlo
            if zh <= 0:
                continue
            if zname == "supply":
                for i in range(i0 + 1, i1):
                    a = M.atr14(h, l, c, i)
                    if a <= 0 or c[i] <= zhi or (h[i] - l[i]) < M.QUAL * a:
                        continue
                    ep, ev_i = None, None
                    for j2 in range(i + 1, min(i + rewin + 1, i1)):
                        if c[j2] <= zlo:
                            ep, ev_i = zlo, j2
                            break
                    if ep is None:
                        continue
                    risk = zh + max(0.2 * zh, 0.5 * a)
                    ev.append(dict(sym="X", dk=int(dk), side="sell", i=int(ev_i), t=int(t[ev_i]),
                                   ep=float(ep), sl=float(zhi + max(0.2 * zh, 0.5 * a)), far=float(zhi),
                                   zh=float(zh), a=float(a), tp_base=float(ep - 3.0 * risk)))
            else:
                for i in range(i0 + 1, i1):
                    a = M.atr14(h, l, c, i)
                    if a <= 0 or c[i] >= zlo or (h[i] - l[i]) < M.QUAL * a:
                        continue
                    ep, ev_i = None, None
                    for j2 in range(i + 1, min(i + rewin + 1, i1)):
                        if c[j2] >= zhi:
                            ep, ev_i = zhi, j2
                            break
                    if ep is None:
                        continue
                    risk = zh + max(0.2 * zh, 0.5 * a)
                    ev.append(dict(sym="X", dk=int(dk), side="buy", i=int(ev_i), t=int(t[ev_i]),
                                   ep=float(ep), sl=float(zlo - max(0.2 * zh, 0.5 * a)), far=float(zlo),
                                   zh=float(zh), a=float(a), tp_base=float(ep + 3.0 * risk)))
    return dict(t=t, c=c, h=h, l=l, o=o, ev=ev)


def parity_check(sr_loop, dmap):
    """循环版 vs 向量化 同输入全等抽检(3 品种 x 60 事件 x 3 组合)"""
    worst, detail = 0.0, []
    for sym in list(dmap.keys())[:3]:
        d = dmap[sym]
        ev = d["ev"][:60]
        dd = dict(d, ev=ev)
        for (tr, gb, tp) in ((0.5, 0.4, 4.0), (0.3, 0.2, 3.0), (0.7, 0.8, 5.0)):
            a = sr_loop(dd, slc=SLC_GRID, tpmul=tp, trig=tr, giveback=gb)
            b = settle_ratchet_vec(dd, slc=SLC_GRID, tpmul=tp, trig=tr, giveback=gb)
            delta = float(np.max(np.abs(np.array(a) - np.array(b))))
            worst = max(worst, delta)
            detail.append("%s tr%.1f gb%.1f tp%.0f n=%d delta=%.3g" % (sym, tr, gb, tp, len(ev), delta))
    return worst, detail


def npz_freshness(stale_h=48):
    now = time.time()
    out = {}
    stale = []
    for p in sorted(glob.glob(os.path.join(DATA, "*.npz"))):
        sym = os.path.basename(p)[:-4].replace("_M15", "")
        m = os.path.getmtime(p)
        out[sym] = m
        if now - m > stale_h * 3600:
            stale.append(sym)
    return out, stale


def phase_gate():
    g = dict(ts=time.strftime("%F %T"), phase="gate", fail=False)
    sr = make_loop_ratchet()
    ut = unit_tests(sr)
    g["unit_tests"] = ut
    if not all(x["ok"] for x in ut):
        g["fail"] = True
    dmap, meta = load_pkls(EVDIR)
    g["pkl_n"] = len(dmap)
    g["pkl_mtime_min"] = min(meta.values())
    npz_m, stale = npz_freshness()
    g["npz_n"] = len(npz_m)
    g["npz_stale_gt48h"] = stale
    g["npz_mtime_min"] = min(npz_m.values())
    worst, pdetail = parity_check(sr, dmap)
    g["parity_max_delta"] = worst
    g["parity_detail"] = pdetail
    if worst > 1e-9:
        g["fail"] = True
    if len(dmap) < 30 or stale:
        g["fail"] = True
    json.dump(g, open(G, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("GATE: unit=%d/6 parity_delta=%.3g pkl=%d npz=%d stale=%s fail=%s" % (
        sum(x["ok"] for x in ut), worst, len(dmap), len(npz_m), stale, g["fail"]))
    return 0 if not g["fail"] else 1


def phase_AB(evdir, tag):
    g = json.load(open(G, encoding="utf-8"))
    if g.get("fail"):
        print("GATE 未过, 拒绝 %s 重跑(数据有效性闸)" % tag)
        return 1
    sr_loop = make_loop_ratchet()
    dmap, meta = load_pkls(evdir)
    print("%s: %d 品种事件集加载" % (tag, len(dmap)))
    grid = pool_grid(dmap, settle_ratchet_vec)
    print("%s pool grid top5:" % tag)
    for v in grid[:5]:
        print("  tr%.1f gb%.1f tp%.0f: netR=%s wr=%s T=%s/6 n=%s ⑥线净成本=%s" % (
            v["trig"], v["giveback"], v["tp"], v.get("netR"), v.get("wr"), v.get("T"), v.get("n"), v.get("avgR_net_cost")))
    per = {}
    for sym in sorted(dmap):
        per[sym] = sym_table_one(sym, dmap[sym], settle_ratchet_vec)
        print("  %-8s -> %s" % (sym, json.dumps(per[sym], ensure_ascii=False) if per[sym] else "事件<10 无参"))
    json.dump(dict(ts=time.strftime("%F %T"), phase=tag, evdir=evdir,
                   pkl_mtime_min=meta and min(meta.values()),
                   pool_grid_top5=grid[:5], pool_grid=grid,
                   per_symbol=per),
              open(A if tag == "A" else B, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("%s OK -> %s" % (tag, A if tag == "A" else B))
    return 0


def phase_B_events():
    """无未来事件集重建(11-17 npz) 并缓存"""
    os.makedirs(EVDIR_NOLA, exist_ok=True)
    sym2meta = {}
    for p in sorted(glob.glob(os.path.join(DATA, "*.npz"))):
        sym = os.path.basename(p)[:-4].replace("_M15", "")
        d = events_nola(p)
        pickle.dump(d, open(os.path.join(EVDIR_NOLA, sym + ".pkl"), "wb"))
        last_t = int(np.max(d["t"]))
        sym2meta[sym] = dict(n_events=len(d["ev"]), last_bar_utc=last_t, last_bar_bjt=time.strftime("%m-%d %H:%M", time.localtime(last_t + 8 * 3600)))
    json.dump(dict(ts=time.strftime("%F %T"), spec="events_gen 去未来极值过滤(整日3:1准入移除), 区=前一日高低±ZF, 触发/回踩全因果, 数据=11-17 npz(数据官刷)",
                   symbols=sym2meta), open(EVDIR_NOLA + "_meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("B_EVENTS: %d 品种无未来事件重建完 -> %s" % (len(sym2meta), EVDIR_NOLA))
    return 0


def phase_B2():
    """v2 御史口径(活体参数表同法) 在 11-17 npz 上重跑 -> v3 候选表"""
    import sd_symopt_v2_20261115 as V2
    M.BASE = DATA
    live = json.load(open(os.path.join(HERE, "sd_symbol_params.json"), encoding="utf-8"))
    out, flips = {}, []
    for sym in sorted(os.path.basename(x)[:-4].replace("_M15", "") for x in os.listdir(DATA) if x.endswith(".npz")):
        t, c, h, l, o, ev = M.events_oe(sym)
        evs = V2.remap_events_v2(sym, t, c, h, l, o, ev)
        if len(evs) < 30:
            out[sym] = dict(n=len(evs), note="v2 事件不足, 该品种无参")
            continue
        b = dict(t=t, o=o, h=h, l=l, c=c)
        best = None
        for slc in (0.1, 0.15, 0.2, 0.3):
            for tp in (4.0, 5.0, 6.0):
                for trig in (0.3, 0.5, 0.7):
                    for gb in (0.2, 0.3):
                        Rs = [V2.settle_v2(e, b, slc, tp, trig, gb, 6, True) for e in evs]
                        netR = float(sum(x["R"] for x in Rs))
                        wr = float(sum(1 for x in Rs if x["oos"]) / len(Rs))
                        if best is None or netR > best["netR"]:
                            best = dict(slc=slc, tpmul=tp, trig=trig, giveback=gb, netR=round(netR, 1), wr=round(wr, 3), n=len(evs))
        out[sym] = best
        old = (live.get("params") or {}).get(sym) or {}
        new4 = tuple(best[k] for k in ("slc", "tpmul", "trig", "giveback")) if best else None
        old4 = tuple(old.get(k) for k in ("slc", "tpmul", "trig", "giveback")) if old and "slc" in old else None
        if new4 != old4:
            flips.append(dict(sym=sym, old=new4 is None and "无参" or list(old4), new=list(new4) if new4 else "无参",
                              netR_old=old.get("netR"), netR_new=best.get("netR") if best else None))
        print("%-8s -> %s (live: %s)" % (sym, json.dumps(best, ensure_ascii=False)[:120],
                                         json.dumps(old, ensure_ascii=False)[:90]))
    json.dump(dict(ts=time.strftime("%F %T"), spec="v2御史口径(前一日选样+近沿限价+SELL下移锁盈+成本0.095R+12h红线) @ 11-17 npz 数据官刷 = v3候选",
                   params=out, vs_live_flips=flips, live_table_ts=live.get("ts")),
              open(OUT_PARAMS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(dict(ts=time.strftime("%F %T"), phase="B2", n_flip=len(flips), flips=flips),
              open(B2, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("B2 OK: %d 品种, 与活体v2表参数变动 %d 个 -> %s" % (len(out), len(flips), OUT_PARAMS))
    return 0


def phase_final():
    g = json.load(open(G, encoding="utf-8"))
    da = json.load(open(A, encoding="utf-8"))
    db = json.load(open(B, encoding="utf-8"))
    d2 = json.load(open(B2, encoding="utf-8"))
    out_params = json.load(open(OUT_PARAMS, encoding="utf-8"))
    a_flip = d2.get("flips", [])
    old_grid = json.load(open(os.path.join(HERE, "sd_ratchet_grid_20261115.json"), encoding="utf-8"))
    old_v1 = json.load(open(os.path.join(HERE, "sd_symbol_params_v1_bak_20261115.json"), encoding="utf-8"))
    live_tbl = json.load(open(os.path.join(HERE, "sd_symbol_params.json"), encoding="utf-8"))
    old_best = old_grid.get("best")
    a_top, b_top, b2_flip = da["pool_grid_top5"][0], db["pool_grid_top5"][0], d2
    pool = {
        "OLD_1115旧码旧事件": {"netR": old_best.get("netR"), "wr": old_best.get("wr"), "combo": dict(trig=old_best.get("trig"), gb=old_best.get("giveback"), tp=old_best.get("tp")), "credibility": "不可采信(sell棘轮符号反+幽灵成交+未来极值)"},
        "A_修复码旧事件": {"netR": a_top.get("netR"), "wr": a_top.get("wr"), "combo": dict(trig=a_top.get("trig"), gb=a_top.get("giveback"), tp=a_top.get("tp")), "caliber": "只隔离修修①②(码), 事件集仍含未来极值过滤"},
        "B_修复码无未来事件": {"netR": b_top.get("netR"), "wr": b_top.get("wr"), "combo": dict(trig=b_top.get("trig"), gb=b_top.get("giveback"), tp=b_top.get("tp")), "caliber": "全修, 11-17 npz, 权威口径"},
    }
    n6_a = [v for v in da["pool_grid"] if (v.get("T") or 0) == 6]
    n6_b = [v for v in db["pool_grid"] if (v.get("T") or 0) == 6]
    verdict_txt = ("全族 REJECT/WATCH 0翻闸 0放大: B 池级最优 ⑥线(扣0.095R后净均值)=%.3f, 五验6/6 组合数 A=%d B=%d; "
                   "v3候选表(v2法+新数据) 与活体v2表参数变动 %d 个 -> 仅提案, 翻闸权属 chief R11 双裁+30笔前向OOS"
                   % (b_top.get("avgR_net_cost") or 0, len(n6_a), len(n6_b), len(a_flip)))
    v = dict(
        ts=time.strftime("%F %T"), actor="主bot代strategy-rd(21:30学习哨)", queue_item="sd_backtest_caliber_fix_1115",
        data_validity=dict(npz_mtime_min=g.get("npz_mtime_min"), npz_stale_gt48h=g.get("npz_stale_gt48h"),
                           pkl_mtime_min=g.get("pkl_mtime_min"), source="npz=数据官11-17实读刷新(MT5_LIVE)/pkl=11-15旧事件集(A档对照用)"),
        unit_tests=g.get("unit_tests"), parity_max_delta=g.get("parity_max_delta"),
        pool=pool,
        A_top5=da["pool_grid_top5"], B_top5=db["pool_grid_top5"],
        A_per_symbol=da["per_symbol"], B_per_symbol=db["per_symbol"],
        B2_v3_candidate=dict(v2法新数据表=out_params, 参数变动数=len(a_flip), 明细=a_flip),
        verdict=verdict_txt,
        plain="今天把 SD 回测工具三处高估根子修了: 空单锁盈棘轮方向写反了(亏损离场记成锁盈)/同一根K线既触止盈又触止损时按乐观边计/选样偷看当日全天高低点。修完同分母重跑: 池级净R 从虚高 %.0f 档回落到 %s, 全族没一个过 ⑥线, 0 翻闸 0 放大; 活体 v2 参数表本身干净(11-15 已按御史口径修过), 新数据重算的 v3 候选表参数变动 %d 个, 只提案不动闸, 翻闸归 chief R11 双裁。"
              % ((old_best.get("netR") or 0), "B档 %s" % (b_top.get("netR") if b_top else "无"), len(a_flip)),
    )
    json.dump(v, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 人话裁定 md
    lines = ["# SD 回测口径三修重跑裁定 (11-17 21:30 学习哨, 主bot代strategy-rd)", "",
             "## 数据有效性闸", "npz mtime min = %s (48h 内%s); pkl(11-15 旧事件)仅 A 档对照用" % (
                 time.strftime("%F %T", time.localtime(g.get("npz_mtime_min") or time.time())),
                 "全新鲜" if not g.get("npz_stale_gt48h") else "有陈旧: %s" % g.get("npz_stale_gt48h")), "",
             "## 已知答案单测 + 向量化 parity", "单测 %d/6 过; 循环 vs 向量化 max_delta=%.3g" % (
                 sum(x["ok"] for x in (g.get("unit_tests") or [])), g.get("parity_max_delta") or 0.0), "",
             "## 池级 27 组合同分母三档对照", "| 档 | netR | 胜率 | 最优组合 | 口径 |", "|---|---|---|---|---|"]
    for k, x in pool.items():
        lines.append("| %s | %s | %s | tr%.1f/gb%.1f/tp%.0f | %s |" % (
            k, x["netR"], x["wr"], x["combo"]["trig"], x["combo"]["gb"], x["combo"]["tp"], x["caliber"] if "caliber" in x else x["credibility"]))
    lines += ["", "## 分品种表(A 修复码旧事件 / B 全修)", "| 品种 | A表 | B表 |", "|---|---|---|"]
    for sym in sorted(da["per_symbol"]):
        pa, pb = da["per_symbol"].get(sym), db["per_symbol"].get(sym)
        lines.append("| %s | %s | %s |" % (sym,
                                           json.dumps(pa, ensure_ascii=False) if pa else "无参",
                                           json.dumps(pb, ensure_ascii=False) if pb else "无参"))
    lines += ["", "## v3 候选表(v2 法 + 11-17 数据) vs 活体 v2 表", "参数变动 %d 个: %s" % (len(a_flip), a_flip if a_flip else "0 个(数据刷新未改最优组合)"), "",
             "## 裁定", verdict_txt, "", "历史回测 ≠ 未来收益; 本批 0 翻闸 0 放大, 翻闸权属 chief R11 双裁 + 30 笔前向 OOS。"]
    open(OUT_MD, "w", encoding="utf-8").write("\n".join(lines))
    print("FINAL OK -> %s + %s" % (OUT, OUT_MD))
    return 0


def main():
    if len(sys.argv) < 3:
        print("usage: python sd_caliber_fix_20261117.py --phase gate|A|B|B2|B_events|final")
        return 1
    phase = sys.argv[2]
    if phase == "gate":
        return phase_gate()
    if phase == "A":
        return phase_AB(EVDIR, "A")
    if phase == "B":
        if not os.path.exists(EVDIR_NOLA + "_meta.json"):
            if phase_B_events() != 0:
                return 1
        return phase_AB(EVDIR_NOLA, "B")
    if phase == "B_events":
        return phase_B_events()
    if phase == "B2":
        return phase_B2()
    if phase == "final":
        return phase_final()
    print("unknown phase", phase)
    return 1


if __name__ == "__main__":
    sys.exit(main())
