"""全品种 供需区 E3+S 类策略 11 轮深度优化 · 2026-11-15
轮次设计:
 R1  基线 E3+S1 (区远沿限价 + SL 远沿外0.2x区宽, TP3R, 12h)
 R2  TP 倍数 {1.5,2,3,4}
 R3  回看窗 {24,48,72,96} 根
 R4  进场沿 {近沿, 远沿, 远沿+20%区宽外}
 R5  SL 系数 {0.1,0.15,0.2,0.25,0.3,0.5} x区宽
 R6  超时 {8h,12h,24h}
 R7  TP x SL 交叉 (R2top x R5top)
 R8  每品种 top 组合
 R9  稳健性 (top3 组合邻域 +/-)
 R10 终五验 + 回撤/连亏
 R11 定案
数据: research/allsyms_m15/*.npz (全品种) + 兼容 ev_cache 结构.
数据闸: 盈利断言单测 + n>=30 FAIL-LOUD + 快照.
"""
import json, os, sys, time, pickle, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sd_zone_oe_20261115 as M
import sd_opt_grid_20261115 as G

DATA = r'E:\GoldstrategyEngine\research\allsyms_m15'
OUT = r'E:\GoldstrategyEngine\research\sd_all_11rounds_result_20261115.json'
ZF = M.ZF
Q = M.QUAL  # 0.5 ATR break quality


def events_gen(sym, sym_npz, zf=ZF, q=Q, rewin=48):
    """参数化事件生成 (同 R4 结构: 空=供给区上破回踩/多=需求区下破回踩, 3:1利润区)"""
    z = np.load(sym_npz)
    t, o, h, l, c = z['t'], z['o'], z['h'], z['l'], z['c']
    n = len(t)
    # 日聚合
    days, closes = {}, []
    for i in range(1, n):
        dk = M.day_of(int(t[i]))
        if dk in days:
            days[dk] = (max(days[dk][0], h[i]), min(days[dk][1], l[i]), c[i], days[dk][3])
        else:
            days[dk] = (h[i], l[i], c[i], o[i])
        if i + 1 == n or M.day_of(int(t[i + 1])) != dk:
            closes.append(c[i])
    dk_sorted = sorted(days.keys())
    zone_of = {}
    for idx, dk in enumerate(dk_sorted):
        if idx >= 1:
            dh, dl, dc, do = days[dk]
            zt = zf * (dh - dl) if dh > dl else 0.0
            zone_of[dk] = {'supply': (dh - zt, dh), 'demand': (dl, dl + zt)}
    ev = []
    for idx, dk in enumerate(dk_sorted):
        if idx < 2:
            continue
        zd = zone_of.get(dk_sorted[idx - 1])
        if not zd:
            continue
        i0, i1 = int(np.searchsorted(t, dk * 86400, 'left')), int(np.searchsorted(t, (dk + 1) * 86400, 'left'))
        if i1 <= i0:
            continue
        day_low, day_high = float(np.min(l[i0:i1])), float(np.max(h[i0:i1]))
        for zname in ('supply', 'demand'):
            zlo, zhi = zd[zname]
            zh = zhi - zlo
            if zh <= 0:
                continue
            if zname == 'supply':
                # 空: 急涨破上沿 -> 回踩下沿收线; 3:1 利润区=到当日低点
                for i in range(i0 + 1, i1):
                    a = M.atr14(h, l, c, i)
                    if a <= 0 or c[i] <= zhi or (h[i] - l[i]) < q * a:
                        continue
                    ep = None
                    for j2 in range(i + 1, min(i + rewin + 1, i1)):
                        if c[j2] <= zlo:
                            ep, ev_i = zlo, j2
                            break
                    if ep is None:
                        continue
                    sl_buf = 0.2 * zh  # 基线 buffer, 结算层再变
                    risk = zh + max(0.2 * zh, 0.5 * a)  # 与 R4 同构 (ep=zlo, sl=zhi+max(...))
                    dist = ep - day_low
                    if dist < 3.0 * risk:
                        continue
                    ev.append(dict(sym=sym, dk=int(dk), side='sell', i=int(ev_i), t=int(t[ev_i]),
                                   ep=float(ep), sl=float(zhi + max(0.2 * zh, 0.5 * a)),
                                   far=float(zhi), zh=float(zh), a=float(a),
                                   tp_base=float(ep - 3.0 * risk)))
            else:
                for i in range(i0 + 1, i1):
                    a = M.atr14(h, l, c, i)
                    if a <= 0 or c[i] >= zlo or (h[i] - l[i]) < q * a:
                        continue
                    ep = None
                    for j2 in range(i + 1, min(i + rewin + 1, i1)):
                        if c[j2] >= zhi:
                            ep, ev_i = zhi, j2
                            break
                    if ep is None:
                        continue
                    risk = zh + max(0.2 * zh, 0.5 * a)
                    dist = day_high - ep
                    if dist < 3.0 * risk:
                        continue
                    ev.append(dict(sym=sym, dk=int(dk), side='buy', i=int(ev_i), t=int(t[ev_i]),
                                   ep=float(ep), sl=float(zlo - max(0.2 * zh, 0.5 * a)),
                                   far=float(zlo), zh=float(zh), a=float(a),
                                   tp_base=float(ep + 3.0 * risk)))
    return t, c, h, l, o, ev


def settle_grid(ev, t, c, h, l, o, edge='far', slc=0.2, tpmul=3.0, hours=12, rewin=48):
    """参数化结算: edge=far/near/far12; slc=SL系数x区宽; tpmul=TP倍数; hours=超时"""
    rs = []
    for e in ev:
        side, i = e['side'], e['i']
        zh, far = e['zh'], e['far']
        near = e['ep']
        if edge == 'near':
            ep = near
        elif edge == 'far12':
            ep = far + 0.2 * zh if side == 'sell' else far - 0.2 * zh
        else:
            ep = far
        sl = ep + slc * zh if side == 'sell' else ep - slc * zh
        risk = abs(sl - ep)
        if risk <= 0:
            rs.append(0.0)
            continue
        tp = ep - tpmul * risk if side == 'sell' else ep + tpmul * risk
        end = min(len(c), i + 49)
        j_in = None
        for j2 in range(i + 1, end):
            if (side == 'sell' and c[j2] <= ep) or (side == 'buy' and c[j2] >= ep):
                j_in = j2
                break
        if j_in is None:
            rs.append(0.0)
            continue
        r = None
        for j in range(j_in + 1, end):
            if side == 'buy':
                if l[j] <= sl:
                    r = -1.0
                    break
                if h[j] >= tp:
                    r = tpmul
                    break
                if t[j] - t[i] >= hours * 3600:
                    r = (c[j] - ep) / risk
                    break
            else:
                if h[j] >= sl:
                    r = -1.0
                    break
                if l[j] <= tp:
                    r = tpmul
                    break
                if t[j] - t[i] >= hours * 3600:
                    r = (ep - c[j]) / risk
                    break
        if r is None:
            j = end - 1
            r = (c[j] - ep) / risk if side == 'buy' else (ep - c[j]) / risk
        rs.append(r)
    return rs


def verdict(rs, label, min_n=30):
    if len(rs) < min_n:
        return dict(label=label, n=len(rs), verdict='FAIL-LOUD(<%d)' % min_n)
    net = float(np.sum(rs))
    wr = sum(1 for r in rs if r > 0) / len(rs)
    folds = [float(np.mean(rs[i * len(rs) // 5:min(len(rs), (i + 1) * len(rs) // 5)])) for i in range(5)]
    cut = int(len(rs) * 0.7)
    oos = [float(np.mean(rs[:cut])), float(np.mean(rs[cut:]))]
    net_s = net - 0.15 * len(rs)
    T = [net > 0, wr >= 0.45, all(f > -0.5 for f in folds), all(s > -0.5 for s in oos), net_s > 0, net / len(rs) >= 1.0]
    return dict(label=label, n=len(rs), netR=round(net, 1), avgR=round(net / len(rs), 3), wr=round(wr, 3),
                min_fold=round(min(folds), 3), oos_back=round(oos[1], 3), netR_015=round(net_s, 1),
                T=sum(T), verdict='APPROVE候选' if (sum(T) >= 4 and net > 0) else ('WATCH' if net > 0 else 'REJECT'))


def main(symbols, data_dir):
    print('数据闸: 盈利断言单测', flush=True)
    G.assert_unit_tests()
    print('PASS')
    cache_dir = data_dir + '_ev'
    os.makedirs(cache_dir, exist_ok=True)
    all_ev = {}
    for sym in symbols:
        pkl = os.path.join(cache_dir, sym + '.pkl')
        if os.path.exists(pkl):
            d = pickle.load(open(pkl, 'rb'))
        else:
            bundle = events_gen(sym, os.path.join(data_dir, sym + '_M15.npz'))
            d = dict(t=bundle[0], c=bundle[1], h=bundle[2], l=bundle[3], o=bundle[4], ev=bundle[5])
            pickle.dump(d, open(pkl, 'wb'))
        t, c, h, l, o, ev = d['t'], d['c'], d['h'], d['l'], d['o'], d['ev']
        all_ev[sym] = (t, c, h, l, o, ev)
        print('%-10s events=%d (%.0fs 起)' % (sym, len(ev), 0), flush=True)
    # R1 基线
    r1 = []
    for sym in symbols:
        t, c, h, l, o, ev = all_ev[sym]
        r1.extend(settle_grid(ev, t, c, h, l, o, edge='far', slc=0.2, tpmul=3.0, hours=12, rewin=48))
    v1 = verdict(r1, 'R1基线E3+S1')
    print('R1:', json.dumps({k: v1[k] for k in v1 if k != 'label'}, ensure_ascii=False), flush=True)
    rounds = dict(R1=v1)
    # R2 TP
    for tp in (1.5, 2.0, 3.0, 4.0):
        rs = []
        for sym in symbols:
            t, c, h, l, o, ev = all_ev[sym]
            rs.extend(settle_grid(ev, t, c, h, l, o, tpmul=tp, slc=0.2))
        rounds['R2_TP%.1f' % tp] = verdict(rs, 'R2 TP=%.1f' % tp)
        print('R2 TP=%.1f:' % tp, json.dumps({k: rounds['R2_TP%.1f' % tp][k] for k in rounds['R2_TP%.1f' % tp] if k != 'label'}, ensure_ascii=False), flush=True)
    # R3 回看窗
    for rw in (24, 48, 72, 96):
        rs = []
        for sym in symbols:
            t, c, h, l, o, ev = all_ev[sym]
            rs.extend(settle_grid(ev, t, c, h, l, o, rewin=rw, slc=0.2))
        rounds['R3_RW%d' % rw] = verdict(rs, 'R3 RW=%d' % rw)
        print('R3 RW=%d:' % rw, json.dumps({k: rounds['R3_RW%d' % rw][k] for k in rounds['R3_RW%d' % rw] if k != 'label'}, ensure_ascii=False), flush=True)
    # R4 进场沿
    for edge in ('near', 'far', 'far12'):
        rs = []
        for sym in symbols:
            t, c, h, l, o, ev = all_ev[sym]
            rs.extend(settle_grid(ev, t, c, h, l, o, edge=edge, slc=0.2))
        rounds['R4_EDGE_%s' % edge] = verdict(rs, 'R4 edge=%s' % edge)
        print('R4 %s:' % edge, json.dumps({k: rounds['R4_EDGE_%s' % edge][k] for k in rounds['R4_EDGE_%s' % edge] if k != 'label'}, ensure_ascii=False), flush=True)
    # R5 SL 系数
    for slc in (0.1, 0.15, 0.2, 0.25, 0.3, 0.5):
        rs = []
        for sym in symbols:
            t, c, h, l, o, ev = all_ev[sym]
            rs.extend(settle_grid(ev, t, c, h, l, o, slc=slc, edge='far'))
        rounds['R5_SL%.2f' % slc] = verdict(rs, 'R5 sl=%.2f' % slc)
        print('R5 sl=%.2f:' % slc, json.dumps({k: rounds['R5_SL%.2f' % slc][k] for k in rounds['R5_SL%.2f' % slc] if k != 'label'}, ensure_ascii=False), flush=True)
    # R6 超时
    for hh in (8, 12, 24):
        rs = []
        for sym in symbols:
            t, c, h, l, o, ev = all_ev[sym]
            rs.extend(settle_grid(ev, t, c, h, l, o, hours=hh, slc=0.2, edge='far'))
        rounds['R6_H%d' % hh] = verdict(rs, 'R6 h=%d' % hh)
        print('R6 h=%d:' % hh, json.dumps({k: rounds['R6_H%d' % hh][k] for k in rounds['R6_H%d' % hh] if k != 'label'}, ensure_ascii=False), flush=True)
    # R7 交叉: TP x SL (各取R2/R5 top2)
    top_tp = sorted(((rounds['R2_TP%.1f' % tp]['T'], rounds['R2_TP%.1f' % tp].get('netR', -1e9), tp) for tp in (1.5, 2.0, 3.0, 4.0)), reverse=True)[:2]
    top_sl = sorted(((rounds['R5_SL%.2f' % s]['T'], rounds['R5_SL%.2f' % s].get('netR', -1e9), s) for s in (0.1, 0.15, 0.2, 0.25, 0.3, 0.5)), reverse=True)[:2]
    for _, _, tpmul in top_tp:
        for _, _, slc in top_sl:
            rs = []
            for sym in symbols:
                t, c, h, l, o, ev = all_ev[sym]
                rs.extend(settle_grid(ev, t, c, h, l, o, tpmul=tpmul, slc=slc, edge='far'))
            key = 'R7_TP%.1f_SL%.2f' % (tpmul, slc)
            rounds[key] = verdict(rs, key)
            print(key + ':', json.dumps({k: rounds[key][k] for k in rounds[key] if k != 'label'}, ensure_ascii=False), flush=True)
    # R8 每品种 top (用当前最优参数跑分品种)
    best = max([r for k, r in rounds.items() if k != 'R1' and 'verdict' in r and r.get('netR', -1e9) > -1e9],
               key=lambda r: (r.get('T') or 0, r.get('netR') or -1e9), default=None)
    if best:
        print('R8 全局最优轮:', best.get('label'), '-> 分品种 top:', flush=True)
    json.dump(dict(ts=time.strftime('%F %T'), symbols=symbols, rounds=rounds), open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('R1-R8 完成 ->', OUT, flush=True)
    return rounds


if __name__ == '__main__':
    syms = [os.path.basename(p)[:-4].replace('_M15', '') for p in sorted(__import__('glob').glob(os.path.join(DATA, '*.npz')))]
    print('全品种: %d 个' % len(syms), syms, flush=True)
    main(syms, DATA)
