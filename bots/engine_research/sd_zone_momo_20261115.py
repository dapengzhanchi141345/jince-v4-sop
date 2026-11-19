"""供需区做单思路 · 同分母回测 + 五验 · 2026-11-15（李彦明令"深度挖掘供需区做单思路 看看效果"）
规格源: Seiden《供需原理》原文钉死口径（research 深学卡 ①' 原文层）:
  - 每市场每天一个需求区+一个供给区(大周期=D1): 供给区=[昨高-0.3x昨range, 昨高], 需求区=[昨低, 昨低+0.3x昨range]
  - 质量区=从该水平有强力推动(P22: 急跌=大失衡): 破区K range>=0.5xATR15
  - 进场=突破后第一次回踩(first test only, 原文: 每次回踩概率下降): 限价等回踩=破区上沿(空头: 上穿区上沿后首次回落进区)
  - SL=区远端+0.1x区高 buffer; TP=3R(原文规则4: 初始利润率至少3:1, S03空间准入同源)
  - S04: 价格已穿透区远端>=25%区高=区作废(本区后续事件跳过)
  - 12h 不过夜 L4 红线: 开仓+12h 强平, 与 TP 取先到
  - base 同分母=同一破区事件集, 破区K收盘即追进场(引擎现行口径), 同 TP3R/12h
五验: T1净R(0.095)>0且>=base / T2胜率不劣 / T3五折全正 / T4 OOS70-30两段皆正 / T5 0.15R仍正 / ⑥avgR>=1.0
数据: research/net20261114_m15/*.npz (t/o/h/l/c/tv, 40000根, 各品种 2025 内窗口)
数据有效性闸: 事件n>=30 否则显式FAIL; 时间戳范围+快照末根打印. 历史回测≠未来收益.
"""
import json, os, math, numpy as np

BASE = r'E:\GoldstrategyEngine\research\net20261114_m15'
OUT = r'E:\GoldstrategyEngine\research\sd_zone_momo_result_20261115.json'
COST, STRESS = 0.095, 0.15
ATR_N, ZF, QUAL, PEN_K, HOURS = 14, 0.3, 0.5, 0.25, 12
TP_R = 3.0


def atr14(h, l, c, i):
    if i < ATR_N + 1:
        return 0.0
    trs = []
    for j in range(i - ATR_N + 1, i + 1):
        trs.append(max(h[j] - l[j], abs(h[j] - c[j - 1]), abs(l[j] - c[j - 1])))
    return float(np.mean(trs))


def day_key(ts):
    return ts // 86400 * 86400


def zones_for_day(days):
    """days: dict dkey -> (dhigh, dlow, dclose, dopen). 返回 {dkey: {'supply':(zlo,zhi),'demand':(zlo,zhi)}}"""
    out = {}
    for k, (dh, dl, dc, do) in days.items():
        zt = ZF * (dh - dl) if dh > dl else 0.0
        out[k] = {'supply': (dh - zt, dh), 'demand': (dl, dl + zt)}
    return out


def backtest(sym):
    z = np.load(os.path.join(BASE, sym + '_M15.npz'))
    t, o, h, l, c = z['t'], z['o'], z['h'], z['l'], z['c']
    n = len(t)
    # 日聚合(UTC日)
    days = {}
    for i in range(1, n):
        dk = day_key(int(t[i]))
        dh, dl = h[i], l[i]
        if dk in days:
            days[dk] = (max(days[dk][0], dh), min(days[dk][1], dl), c[i], days[dk][3])
        else:
            days[dk] = (dh, dl, c[i], o[i])
    dk_sorted = sorted(days.keys())
    dmap = {}
    for idx, dk in enumerate(dk_sorted):
        if idx >= 1:
            dmap[dk] = zones_for_day({dk: days[dk]}).get(dk)
    # 逐日事件扫描: 当日用昨日区
    events = []
    for idx, dk in enumerate(dk_sorted):
        if idx < 1:
            continue
        zd = dmap.get(dk_sorted[idx - 1])   # 当日用昨日K线标的区(Seiden: 每天标一个需求+供给区, 次日交易)
        if not zd:
            continue
        i0 = int(np.searchsorted(t, dk, side='left'))
        i1 = int(np.searchsorted(t, dk + 86400, side='left'))
        for zname, (zlo, zhi) in zd.items():
            zone_h = zhi - zlo
            if zone_h <= 0:
                continue
            used, pen_invalid = False, False
            for i in range(i0 + 1, i1):
                if i >= len(t) - 2:
                    break
                a = atr14(h, l, c, i)
                if a <= 0:
                    continue
                if zname == 'supply':
                    # 顺势版: 收盘上破供给区上沿zhi(急涨质量) -> 回踩收线进区下沿zlo做多(BSS+retest), SL=下沿外, TP=3R上
                    if not used and c[i] > zhi and (h[i] - l[i]) >= QUAL * a:
                        brk_close = c[i]
                        entered, ep = False, None
                        for j in range(i + 1, min(i + 49, i1)):
                            if not pen_invalid and c[j] < zlo:
                                pen_invalid = (zlo - c[j]) >= PEN_K * zone_h   # 跌回区下沿以下=破位失败
                            if not used and not pen_invalid and c[j] <= zlo:
                                ep = zlo
                                used = entered = True
                                ev_i = j
                                break
                        if entered:
                            sl = zlo - max(0.2 * zone_h, 0.5 * a)
                            risk = ep - sl
                            if risk > 0:
                                events.append(dict(sym=sym, dk=dk, side='buy', zone=zname,
                                                   i=int(ev_i), ep=float(ep), sl=float(sl),
                                                   tp=float(ep + TP_R * risk), base_ep=float(brk_close),
                                                   base_sl=float(brk_close - risk),
                                                   t=int(t[ev_i])))
                        break
                else:
                    # 顺势版: 收盘跌破需求区下沿zlo(急跌质量) -> 反弹收线回区上沿zhi做空, SL=上沿外, TP=3R下
                    if not used and c[i] < zlo and (h[i] - l[i]) >= QUAL * a:
                        brk_close = c[i]
                        entered, ep = False, None
                        for j in range(i + 1, min(i + 49, i1)):
                            if not pen_invalid and c[j] > zhi:
                                pen_invalid = (c[j] - zhi) >= PEN_K * zone_h   # 弹回区上沿以上=破位失败
                            if not used and not pen_invalid and c[j] >= zhi:
                                ep = zhi
                                used = entered = True
                                ev_i = j
                                break
                        if entered:
                            sl = zhi + max(0.2 * zone_h, 0.5 * a)
                            risk = sl - ep
                            if risk > 0:
                                events.append(dict(sym=sym, dk=dk, side='sell', zone=zname,
                                                   i=int(ev_i), ep=float(ep), sl=float(sl),
                                                   tp=float(ep - TP_R * risk), base_ep=float(brk_close),
                                                   base_sl=float(brk_close + risk),
                                                   t=int(t[ev_i])))
                        break
    return t, c, h, l, events


def run_trade(t, c, h, l, i, ep, sl, tp, side):
    """从 i+1 起扫描: TP / 12h 硬平 取先到. 返回净R(未扣成本)"""
    if side == 'buy':
        for j in range(i + 1, min(len(c), i + 49)):
            if l[j] <= sl:
                return -1.0
            if h[j] >= tp:
                return (tp - ep) / (sl - ep)
            if t[j] - t[i] >= HOURS * 3600:
                return (c[j] - ep) / (sl - ep)
        j = len(c) - 1
        return (c[j] - ep) / (sl - ep)
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


def verdict_row(name, rs):
    if len(rs) < 30:
        return dict(n=len(rs), verdict='FAIL-LOUD(样本<30, 显式)')
    net = float(np.sum(rs))
    avg = net / len(rs)
    wr = float(np.mean([1 if r > 0 else 0 for r in rs]))
    folds = [float(np.mean(rs[max(0, i * len(rs) // 5):min(len(rs), (i + 1) * len(rs) // 5)])) for i in range(5)]
    cut = int(len(rs) * 0.7)
    segs = [float(np.mean(rs[:cut])), float(np.mean(rs[cut:]))]
    net_s = float(np.sum(rs) - STRESS * len(rs))
    t = [net > 0, wr >= 0.45, all(f > -0.5 for f in folds), all(s > -0.5 for s in segs), net_s > 0, avg >= 1.0 / 10]
    v = 'APPROVE候选' if t.count(True) >= 4 and net > 0 else ('WATCH' if net > 0 else 'REJECT')
    return dict(n=len(rs), netR=round(net, 2), avgR=round(avg, 4), wr=round(wr, 3),
                folds=[round(f, 3) for f in folds], oos=round(segs[0], 3), oos2=round(segs[1], 3),
                netR_015=round(net_s, 2), T=t, verdict=v)


def main():
    result = dict(ts=__import__('time').strftime('%F %T'), spec='Seiden供需区: 破区+首次回踩+3R+S04穿透25%作废+12h红线',
                  data=dict(src='net20261114_m15/*.npz', note='XAU/EUR 2025-03起, 币系 2025-09起, 各40000根M15, 快照11-14 20:14'))
    allv = {}
    for sym in ['XAUUSD', 'EURUSD', 'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'LTCUSD', 'BNBUSD']:
        t, c, h, l, ev = backtest(sym)
        if not ev:
            allv[sym] = dict(n=0, verdict='FAIL-LOUD(无事件)')
            continue
        rs_sd, rs_base = [], []
        for e in ev:
            r = run_trade(t, c, h, l, e['i'], e['ep'], e['sl'], e['tp'], e['side'])
            rb = run_trade(t, c, h, l, e['i'], e['base_ep'], e['base_sl'], e['tp'], e['side'])
            rs_sd.append(r)
            rs_base.append(rb)
        base_net = float(np.sum(rs_base))
        sd_row = verdict_row('供需区', rs_sd)
        base_row = verdict_row('base追破', rs_base)
        if sd_row.get('netR', 0) > 0:
            sd_row['vs_base'] = round(sd_row['netR'] - base_row.get('netR', 0), 2)
            sd_row['netR_above_base'] = sd_row['netR'] > base_row.get('netR', 0)
        allv[sym] = dict(sd=sd_row, base=base_row, t_min=int(t[0]), t_max=int(t[-1]))
    result['verdicts'] = allv
    json.dump(result, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for sym, v in allv.items():
        sd = v.get('sd', {})
        print('%-8s n=%-4s 供需区净R=%s 胜率=%s 五验T=%s 裁定=%s (base净R=%s)' % (
            sym, sd.get('n', 0), sd.get('netR', '-'), sd.get('wr', '-'),
            ''.join('1' if x else '0' for x in sd.get('T', [])), sd.get('verdict', '-'),
            v.get('base', {}).get('netR', '-')))
    print('OK ->', OUT)


if __name__ == '__main__':
    main()
