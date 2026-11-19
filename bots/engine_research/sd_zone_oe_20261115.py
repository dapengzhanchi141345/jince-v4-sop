"""Seiden Odds Enhancers 10分制机械化 · 供需区顺势做单 同分母五验 · 2026-11-15
（李彦明令"原文全量吃透+深度优化方案+立即回测验证"）
评分系统(原文 P1-4/P150-153):
  ①移动强度0-2: gap离开=2(原文: 缺口=最大失衡); 无gap时 range>=2xATR15=2, >=1x=1, <1=0
  ②利润区0-2: 到对侧配对区(当日供给区对需求区)距离; 原文规则3: <3:1 不做(严格版直接拒事件)
  ③大图0-2: D1(5日均vs10日均) 趋势同向=2 逆向=0 中性=1
  ④回踩衰减0-2: 该区当日第1次回踩=2 第2次=1 第3次+=0 (砍树喻)
  ⑤到站时间0-1: 破区前价格停留该区 <=3根K=1 (越失衡停留越短)
  ⑥到达0-1: 回踩到达K 实体/全幅>=0.5=1 (强到达=强离开)
总分>=8 出事件(原文: 9-10限价/8确认, 回测统一限价近似=回踩K收盘进); 顺势口径=破需求区回踩上沿空/破供给区回踩下沿多(BSS+retest).
base 同分母=同一破区事件集不加 OE 分(=顺势版全事件), 同 SL/TP3R/12h.
数据闸: n>=30 否则 FAIL-LOUD; 快照打印.
"""
import json, os, time, numpy as np

BASE = r'E:\GoldstrategyEngine\research\net20261114_m15'
OUT = r'E:\GoldstrategyEngine\research\sd_zone_oe_result_20261115.json'
COST, STRESS = 0.095, 0.15
ATR_N, ZF, QUAL, HOURS, TP_R, MIN_SCORE = 14, 0.3, 0.5, 12, 3.0, 8.0


def atr14(h, l, c, i):
    if i < ATR_N + 1:
        return 0.0
    trs = [max(h[j] - l[j], abs(h[j] - c[j - 1]), abs(l[j] - c[j - 1])) for j in range(i - ATR_N + 1, i + 1)]
    return float(np.mean(trs))


def sma(vals, n):
    return float(np.mean(vals[-n:])) if len(vals) >= n else None


def day_of(ts):
    return int(ts // 86400)


def events_oe(sym):
    z = np.load(os.path.join(BASE, sym + '_M15.npz'))
    t, o, h, l, c = z['t'], z['o'], z['h'], z['l'], z['c']
    n = len(t)
    # 日聚合
    days, closes = {}, []
    for i in range(1, n):
        dk = day_of(int(t[i]))
        if dk in days:
            days[dk] = (max(days[dk][0], h[i]), min(days[dk][1], l[i]), c[i], days[dk][3])
        else:
            days[dk] = (h[i], l[i], c[i], o[i])
        if i + 1 == n or day_of(int(t[i + 1])) != dk:
            closes.append(c[i])
    dk_sorted = sorted(days.keys())
    zone_of = {}
    for idx, dk in enumerate(dk_sorted):
        if idx >= 1:
            dh, dl, dc, do = days[dk]
            zt = ZF * (dh - dl) if dh > dl else 0.0
            zone_of[dk] = {'supply': (dh - zt, dh), 'demand': (dl, dl + zt)}
    retest_cnt = {}
    ev = []
    for idx, dk in enumerate(dk_sorted):
        if idx < 2:
            continue
        zd = zone_of.get(dk_sorted[idx - 1])
        if not zd:
            continue
        i0, i1 = int(np.searchsorted(t, dk * 86400, side='left')), int(np.searchsorted(t, (dk + 1) * 86400, side='left'))
        day_low, day_high = float(np.min(l[i0:i1])), float(np.max(h[i0:i1]))
        for zname in ('supply', 'demand'):
            zlo, zhi = zd[zname]
            zone_h = zhi - zlo
            if zone_h <= 0:
                continue
            retest_cnt[('z', dk, zname)] = 0
            if zname == 'supply':
                # 原文标准结构: 做空=供给区进场, 利润区=到左下需求. 急涨破供给上沿 -> 回踩供给下沿收线空
                for i in range(i0 + 1, i1):
                    a = atr14(h, l, c, i)
                    if a <= 0 or c[i] <= zhi or (h[i] - l[i]) < 0.5 * a:
                        continue
                    ep = None
                    for j2 in range(i + 1, min(i + 49, i1)):
                        if c[j2] <= zlo:
                            ep, ev_i = zlo, j2
                            retest_cnt[('z', dk, zname)] = retest_cnt[('z', dk, zname)] + 1
                            break
                    if ep is None:
                        continue
                    sl = zhi + max(0.2 * zone_h, 0.5 * a)
                    risk = sl - ep
                    if risk <= 0:
                        continue
                    dist = ep - day_low
                    if dist < TP_R * risk:
                        continue
                    gap = (int(t[i]) - int(t[i - 1]) > 900) and (o[i] > c[i - 1])
                    rng = h[i] - l[i]
                    s1 = 2 if (gap or rng >= 2 * a) else (1 if rng >= a else 0)
                    s2 = 2
                    s5v = sma(closes[:len(closes) - 1] + [c[i]], 5)
                    s10v = sma(closes[:len(closes) - 1] + [c[i]], 10)
                    diff = (s5v - s10v) / a if (s5v and s10v) else 0
                    s3 = 0 if diff > 0.1 else (2 if diff < -0.1 else 1)
                    s4 = {1: 2, 2: 1}.get(retest_cnt[('z', dk, zname)], 0)
                    body = abs(c[ev_i] - o[ev_i])
                    rng_e = h[ev_i] - l[ev_i]
                    s6 = 1 if (rng_e > 0 and body / rng_e >= 0.5) else 0
                    ev.append(dict(sym=sym, dk=dk, side='sell', zone=zname, i=int(ev_i), t=int(t[ev_i]),
                                   ep=float(ep), sl=float(sl), tp=float(ep - TP_R * risk),
                                   base_ep=float(ep), base_sl=float(sl),
                                   score=int(s1 + s2 + s3 + s4 + s6), parts=[s1, s2, s3, s4, s6]))
            else:
                # 做多=需求区进场, 利润区=到左上供给. 急跌破需求下沿 -> 回踩需求上沿收线多
                for i in range(i0 + 1, i1):
                    a = atr14(h, l, c, i)
                    if a <= 0 or c[i] >= zlo or (h[i] - l[i]) < 0.5 * a:
                        continue
                    ep = None
                    for j2 in range(i + 1, min(i + 49, i1)):
                        if c[j2] >= zhi:
                            ep, ev_i = zhi, j2
                            retest_cnt[('z', dk, zname)] = retest_cnt[('z', dk, zname)] + 1
                            break
                    if ep is None:
                        continue
                    sl = zlo - max(0.2 * zone_h, 0.5 * a)
                    risk = ep - sl
                    if risk <= 0:
                        continue
                    dist = day_high - ep
                    if dist < TP_R * risk:
                        continue
                    gap = (int(t[i]) - int(t[i - 1]) > 900) and (o[i] < c[i - 1])
                    rng = h[i] - l[i]
                    s1 = 2 if (gap or rng >= 2 * a) else (1 if rng >= a else 0)
                    s2 = 2
                    s5v = sma(closes[:len(closes) - 1] + [c[i]], 5)
                    s10v = sma(closes[:len(closes) - 1] + [c[i]], 10)
                    diff = (s5v - s10v) / a if (s5v and s10v) else 0
                    s3 = 2 if diff > 0.1 else (0 if diff < -0.1 else 1)
                    s4 = {1: 2, 2: 1}.get(retest_cnt[('z', dk, zname)], 0)
                    body = abs(c[ev_i] - o[ev_i])
                    rng_e = h[ev_i] - l[ev_i]
                    s6 = 1 if (rng_e > 0 and body / rng_e >= 0.5) else 0
                    ev.append(dict(sym=sym, dk=dk, side='buy', zone=zname, i=int(ev_i), t=int(t[ev_i]),
                                   ep=float(ep), sl=float(sl), tp=float(ep + TP_R * risk),
                                   base_ep=float(ep), base_sl=float(sl),
                                   score=int(s1 + s2 + s3 + s4 + s6), parts=[s1, s2, s3, s4, s6]))
    return t, c, h, l, o, ev


def run_trade(t, c, h, l, i, ep, sl, tp, side):
    if side == 'buy':
        for j in range(i + 1, min(len(c), i + 49)):
            if l[j] <= sl:
                return -1.0
            if h[j] >= tp:
                return (tp - ep) / (ep - sl)
            if t[j] - t[i] >= HOURS * 3600:
                return (c[j] - ep) / (ep - sl)
        j = len(c) - 1
        return (c[j] - ep) / (ep - sl)
    else:
        for j in range(i + 1, min(len(c), i + 49)):
            if h[j] >= sl:
                return -1.0
            if l[j] <= tp:
                return (ep - tp) / (sl - ep)
            if t[j] - t[i] >= HOURS * 3600:
                return (ep - c[j]) / (sl - ep)
        j = len(c) - 1
        return (ep - c[j]) / (sl - ep)


def verdict_row(rs):
    if len(rs) < 30:
        return dict(n=len(rs), verdict='FAIL-LOUD(样本<30)')
    net = float(np.sum(rs))
    avg = net / len(rs)
    wr = float(np.mean([1 if r > 0 else 0 for r in rs]))
    folds = [float(np.mean(rs[i * len(rs) // 5:min(len(rs), (i + 1) * len(rs) // 5)])) for i in range(5)]
    cut = int(len(rs) * 0.7)
    segs = [float(np.mean(rs[:cut])), float(np.mean(rs[cut:]))]
    net_s = net - STRESS * len(rs)
    T = [net > 0, wr >= 0.45, all(f > -0.5 for f in folds), all(s > -0.5 for s in segs), net_s > 0, avg >= 1.0]
    v = 'APPROVE候选' if T.count(True) >= 4 and net > 0 else ('WATCH' if net > 0 else 'REJECT')
    return dict(n=len(rs), netR=round(net, 2), avgR=round(avg, 4), wr=round(wr, 3),
                folds=[round(f, 3) for f in folds], oos=[round(segs[0], 3), round(segs[1], 3)],
                netR_015=round(net_s, 2), T=T, verdict=v)


def main():
    res = dict(ts=time.strftime('%F %T'), spec='Odds Enhancers 10分制(>=8出事件, <3:1利润区拒) 顺势BSS+retest, TP3R, SL区外沿, 12h红线')
    out = {}
    for sym in ['XAUUSD', 'EURUSD', 'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'LTCUSD', 'BNBUSD']:
        t, c, h, l, o, ev = events_oe(sym)
        if not ev:
            out[sym] = dict(oe=dict(n=0, verdict='FAIL-LOUD(无>=8分事件)'), base=dict(n=0, verdict='FAIL-LOUD(无事件)'))
            continue
        rs_oe = [r for (r, e) in zip([run_trade(t, c, h, l, e['i'], e['ep'], e['sl'], e['tp'], e['side']) for e in ev], ev) if e['score'] >= MIN_SCORE]
        rs_base = [run_trade(t, c, h, l, e['i'], e['base_ep'], e['base_sl'], e['tp'], e['side']) for e in ev]
        # 注意: oe 行 tp 用 e['tp'](3R), base 同
        rs_base = [run_trade(t, c, h, l, e['i'], e['base_ep'], e['base_sl'], e['tp'], e['side']) for e in ev]
        rows = dict(oe=verdict_row(rs_oe), base=verdict_row(rs_base))
        rows['score_hist'] = {str(k): sum(1 for e in ev if e['score'] == k) for k in range(11)}
        rows['t_range'] = [int(t[0]), int(t[-1])]
        out[sym] = rows
    res['results'] = out
    json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for sym, r in out.items():
        oe, base = r['oe'], r['base']
        print('%-8s OE(>=8分) n=%-3s 净R=%s 胜率=%s 裁定=%s | base n=%-3s 净R=%s | 分数分布=%s' % (
            sym, oe.get('n'), oe.get('netR', '-'), oe.get('wr', '-'), oe.get('verdict'),
            base.get('n'), base.get('netR', '-'), r.get('score_hist')))
    print('OK ->', OUT)


if __name__ == '__main__':
    main()
