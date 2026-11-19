"""供需区 进场点位 x 止损点位 网格深度优化(42组) · 防扫损最优解 · 2026-11-15
李彦明令: 深度优化进场点位和止损点位, 防扫损, 深度优化10次以上找最优方案.
事件源=R4 原文标准结构(空=供给区上破回踩/多=需求区下破回踩, 3:1利润区), 同分母=ev_cache.
进场法 E1-E6 x 止损法 S1-S7 = 42 组; TP=3R(随SL), 12h红线, 0.15R压测, 五验.
数据闸: 盈利断言单测先跑(buy/sell 确定性盈利样本必须=+3R), 不过=FAIL-LOUD 禁止出裁定.
"""
import json, os, sys, time, pickle, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sd_zone_oe_20261115 as M

CACHE = r'E:\GoldstrategyEngine\research\ev_cache'
OUT = r'E:\GoldstrategyEngine\research\sd_opt_grid_result_20261115.json'
STRESS = 0.15


def atr14v(h, l, c, i):
    return M.atr14(h, l, c, i)


def assert_unit_tests():
    """盈利断言单测: 构造确定性序列, buy/sell 都必须在TP先到达时返回 +3.0 (防符号bug再犯)"""
    n = 60
    t = np.arange(n) * 900 + 1_700_000_000
    # BUY: ep=100, sl=99, tp=103, K线路径: 先不触sl, 第2根K摸到tp
    c_b = np.full(n, 100.5)
    h_b = np.full(n, 100.5); l_b = np.full(n, 100.2); o_b = np.full(n, 100.4)
    h_b[2] = 103.0  # TP先到达
    r_b = M.run_trade(t, c_b, h_b, l_b, 1, 100.0, 99.0, 103.0, 'buy')
    assert abs(r_b - 3.0) < 1e-6, 'BUY盈利断言失败 r=%.3f' % r_b
    # SELL: ep=100, sl=101, tp=97, 第2根K摸到tp
    c_s = np.full(n, 99.5)
    h_s = np.full(n, 99.5); l_s = np.full(n, 99.8); o_s = np.full(n, 99.6)
    l_s[2] = 97.0
    r_s = M.run_trade(t, c_s, h_s, l_s, 1, 100.0, 101.0, 97.0, 'sell')
    assert abs(r_s - 3.0) < 1e-6, 'SELL盈利断言失败 r=%.3f' % r_s
    # 止损优先: sl先触=-1 (j 从 i+1=2 起, 用 j=2 触发)
    h_s2 = h_s.copy(); h_s2[2] = 101.5
    r_s2 = M.run_trade(t, c_s, h_s2, l_s, 1, 100.0, 101.0, 97.0, 'sell')
    assert abs(r_s2 + 1.0) < 1e-6, 'SELL止损断言失败 r=%.3f' % r_s2
    return True


def attach_zone_h(t, h, l, ev):
    """事件反算 zone_h: 前交易日高低价 range x ZF (与 events_oe zone_of 同构)"""
    days = {}
    for i in range(1, len(t)):
        dk = M.day_of(int(t[i]))
        if dk in days:
            days[dk] = (max(days[dk][0], h[i]), min(days[dk][1], l[i]))
        else:
            days[dk] = (h[i], l[i])
    dk_sorted = sorted(days)
    zone_of = {}
    for idx, dk in enumerate(dk_sorted):
        if idx >= 1:
            dh, dl = days[dk_sorted[idx - 1]]
            zone_of[dk] = M.ZF * (dh - dl) if dh > dl else 0.0
    for e in ev:
        e['zone_h'] = zone_of.get(e['dk'], 0.0)


def settle(ev, t, c, h, l, o, E, S, sym):
    """E/S 方法结算. E: 'E1'..'E6'; S: 'S1'..'S7'"""
    a14 = [atr14v(h, l, c, i) for i in range(len(t))]
    rs = []
    for e in ev:
        side, i = e['side'], e['i']
        zone_h = e.get('zone_h')
        if zone_h is None or zone_h <= 0:
            continue
        near = e['ep']
        # sell 事件: ep=zlo(区下沿), 区上沿 zhi = ep + zone_h; buy: ep=zhi(需求上沿), zlo = ep - zone_h
        far = near + zone_h if side == 'sell' else near - zone_h
        a = a14[i] if a14[i] > 0 else 0.0
        # ---- 止损法 (SL 锚定在区远沿外) ----
        S_map = {
            'S1': far + (0.2 * zone_h if side == 'sell' else -0.2 * zone_h),
            'S2': far + (0.5 * zone_h if side == 'sell' else -0.5 * zone_h),
            'S3': far + (1.0 * zone_h if side == 'sell' else -1.0 * zone_h),
            'S4': far + (1.8 * zone_h if side == 'sell' else -1.8 * zone_h),
            'S5': far + (2.5 * zone_h if side == 'sell' else -2.5 * zone_h),
            'S6': far + ((max(1.8 * zone_h, 1.0 * a) if side == 'sell' else -max(1.8 * zone_h, 1.0 * a))),
            'S7': far + ((zone_h + 1.0 * a) if side == 'sell' else -(zone_h + 1.0 * a)),
        }
        sl = S_map[S]
        # ---- 进场法 ----
        ep, entered = None, False
        end = min(len(c), i + 49)
        if E == 'E1':  # 回踩K收线(现状): 48根内首次收线破回近沿
            for j2 in range(i + 1, end):
                if (side == 'sell' and c[j2] <= near) or (side == 'buy' and c[j2] >= near):
                    ep, j_in = near, j2
                    entered = True
                    break
        elif E == 'E2':  # 区中限价
            zmid = (near + far) / 2
            for j2 in range(i + 1, end):
                if (side == 'sell' and c[j2] <= zmid) or (side == 'buy' and c[j2] >= zmid):
                    ep, j_in = zmid, j2
                    entered = True
                    break
        elif E == 'E3':  # 远沿限价(进得早)
            for j2 in range(i + 1, end):
                if (side == 'sell' and c[j2] <= far) or (side == 'buy' and c[j2] >= far):
                    ep, j_in = far, j2
                    entered = True
                    break
        elif E == 'E4':  # 回踩后强K确认收线进
            for j2 in range(i + 1, end):
                if (side == 'sell' and c[j2] <= near) or (side == 'buy' and c[j2] >= near):
                    body = abs(c[j2] - o[j2])
                    rng = h[j2] - l[j2]
                    strong = rng > 0 and body / rng >= 0.5 and ((side == 'sell' and c[j2] < o[j2]) or (side == 'buy' and c[j2] > o[j2]))
                    if strong:
                        ep, j_in = c[j2], j2
                        entered = True
                    break
        elif E == 'E5':  # 扫损确认(S4扫损位)后下一K确认收线
            sl4 = far + (1.8 * zone_h if side == 'sell' else -1.8 * zone_h)
            touched, j_touch = False, None
            for j2 in range(i + 1, end):
                if (side == 'sell' and h[j2] >= sl4) or (side == 'buy' and l[j2] <= sl4):
                    touched, j_touch = True, j2
                    break
            if touched and j_touch + 1 < end:
                j2 = j_touch + 1
                ok = (side == 'sell' and c[j2] < o[j2]) or (side == 'buy' and c[j2] > o[j2])
                if ok:
                    ep, j_in = c[j2], j2
                    entered = True
        elif E == 'E6':  # 第二次回踩近沿
            cnt = 0
            for j2 in range(i + 1, end):
                if (side == 'sell' and c[j2] <= near) or (side == 'buy' and c[j2] >= near):
                    cnt += 1
                    if cnt == 2:
                        ep, j_in = near, j2
                        entered = True
                    break
        if not entered or ep is None:
            rs.append(0.0)
            continue
        risk = abs(sl - ep)
        if risk <= 0:
            rs.append(0.0)
            continue
        tp = ep - 3 * risk if side == 'sell' else ep + 3 * risk
        # 结算: 从 j_in+1 起, SL/TP/12h(以事件i为基准)
        r = None
        for j in range(j_in + 1, end):
            if side == 'buy':
                if l[j] <= sl:
                    r = -1.0
                    break
                if h[j] >= tp:
                    r = (tp - ep) / risk
                    break
                if t[j] - t[i] >= M.HOURS * 3600:
                    r = (c[j] - ep) / risk
                    break
            else:
                if h[j] >= sl:
                    r = -1.0
                    break
                if l[j] <= tp:
                    r = (ep - tp) / risk
                    break
                if t[j] - t[i] >= M.HOURS * 3600:
                    r = (ep - c[j]) / risk
                    break
        if r is None:
            j = end - 1
            r = (c[j] - ep) / risk if side == 'buy' else (ep - c[j]) / risk
        rs.append(r)
    return rs


def five_verdict(rs):
    if len(rs) < 30:
        return dict(n=len(rs), verdict='FAIL-LOUD(<30)')
    net = float(np.sum(rs))
    wr = sum(1 for r in rs if r > 0) / len(rs)
    folds = [float(np.mean(rs[i * len(rs) // 5:min(len(rs), (i + 1) * len(rs) // 5)])) for i in range(5)]
    cut = int(len(rs) * 0.7)
    oos = [float(np.mean(rs[:cut])), float(np.mean(rs[cut:]))]
    net_s = net - STRESS * len(rs)
    T = [net > 0, wr >= 0.45, all(f > -0.5 for f in folds), all(s > -0.5 for s in oos), net_s > 0, net / len(rs) >= 1.0]
    v = 'APPROVE候选' if (sum(T) >= 4 and net > 0) else ('WATCH' if net > 0 else 'REJECT')
    return dict(n=len(rs), netR=round(net, 1), avgR=round(net / len(rs), 4), wr=round(wr, 3),
                min_fold=round(min(folds), 3), oos_back=round(oos[1], 3), netR_015=round(net_s, 1),
                T=sum(T), verdict=v)


def main():
    assert_unit_tests()
    print('盈利断言单测 PASS (buy/sell 盈利=+3R, 扫损=-1R)')
    grids = {}
    for sym in ['XAUUSD', 'EURUSD', 'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'LTCUSD', 'BNBUSD']:
        d = pickle.load(open(os.path.join(CACHE, sym + '.pkl'), 'rb'))
        t, c, h, l, o, ev = d['t'], d['c'], d['h'], d['l'], d['o'], d['ev']
        attach_zone_h(t, h, l, ev)
        grids[sym] = (t, c, h, l, o, ev)
    rows = []
    E_list = ['E1', 'E2', 'E3', 'E4', 'E5', 'E6']
    S_list = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7']
    t0 = time.time()
    for E in E_list:
        for S in S_list:
            allrs = []
            for sym, (t, c, h, l, o, ev) in grids.items():
                allrs.extend(settle(ev, t, c, h, l, o, E, S, sym))
            v = five_verdict(allrs)
            combo = '%s+%s' % (E, S)
            v['combo'] = combo
            rows.append(v)
            print('%-6s n=%-5d 净R=%-9s 平均R=%-7s 胜率=%-5s 五验=%d/6 %s (%.0fs)' % (
                combo, v.get('n', 0), v.get('netR', '-'), v.get('avgR', '-'),
                ('%d%%' % round(v['wr'] * 100)) if 'wr' in v else '-', v.get('T', 0),
                v.get('verdict', ''), time.time() - t0), flush=True)
    rows.sort(key=lambda r: (-(r.get('T') or 0), -(r.get('netR') or -9e9)))
    top = rows[:10]
    print('\n=== TOP10 (按五验通过数+净R) ===')
    for r in top:
        print('%-6s 净R=%-8s 胜率=%-5s 五验=%d/6 最低折=%s OOS后段=%s 压测后=%s -> %s' % (
            r['combo'], r.get('netR'), ('%d%%' % round(r['wr'] * 100) if 'wr' in r else '-'),
            r.get('T', 0), r.get('min_fold'), r.get('oos_back'), r.get('netR_015'), r.get('verdict')))
    json.dump(dict(ts=time.strftime('%F %T'),
                   spec='42组网格(E1-E6 x S1-S7) 同分母R4事件集 TP3R/12h/0.15R压测; E1回踩收线 E2区中 E3远沿 E4强K确认 E5扫损确认 E6二次回踩; S1=0.2x区宽...S7=区宽+1ATR扫损垫',
                   top10=top, all_rows=rows),
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('OK ->', OUT, '(%.0fs)' % (time.time() - t0))


if __name__ == '__main__':
    main()
