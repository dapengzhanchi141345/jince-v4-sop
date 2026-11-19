"""第5轮: 供需区(Seiden标准结构) 时机修正变体 同分母五验 · 2026-11-15
基于 post_sl_analysis 假设(方向对, 时机/止损错)的两个修正:
 V2 止损外移: SL=ep±1.8×R4(原4轮风险的1.8倍), TP不变=3×R4口径(第4轮原TP), 12h红线
 V3 扫损确认后进场: 第4轮入场后价格触及原SL位, 不立即算损, 等下一根K收盘确认(向进场方向收)才以该收盘价为新进场点,
    新SL=原SL外再移0.5ATR(扫损深度), 若直接反向不回(12h)按新SL结算
数据闸: n>=30 否则 FAIL-LOUD; 快照打印.
"""
import json, os, time, pickle, numpy as np
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sd_zone_oe_20261115 as M

OUT = r'E:\GoldstrategyEngine\research\sd_zone_r5_result_20261115.json'
STRESS = 0.15


def atr14(h, l, c, i):
    return M.atr14(h, l, c, i)


def run_v2(t, c, h, l, e):
    """止损外移1.8x, TP=第4轮原TP"""
    ep, side, i = e['ep'], e['side'], e['i']
    risk4 = abs(e['sl'] - ep)
    if side == 'buy':
        sl = ep - 1.8 * risk4
        for j in range(i + 1, min(len(c), i + 49)):
            if l[j] <= sl:
                return -1.8
            if h[j] >= e['tp']:
                return (e['tp'] - ep) / (ep - sl)
            if t[j] - t[i] >= M.HOURS * 3600:
                return (c[j] - ep) / (ep - sl)
        return (c[-1] - ep) / (ep - sl)
    else:
        sl = ep + 1.8 * risk4
        for j in range(i + 1, min(len(c), i + 49)):
            if h[j] >= sl:
                return -1.8
            if l[j] <= e['tp']:
                return (ep - e['tp']) / (sl - ep)
            if t[j] - t[i] >= M.HOURS * 3600:
                return (c[j] - ep) / (ep - sl)
        return (c[-1] - ep) / (ep - sl)


def run_v3(t, c, h, l, o, e):
    """扫损确认后进场: 触及原SL后等下一根收盘确认(向进场方向)才进, 新SL=原SL外+0.5ATR"""
    ep, side, i = e['ep'], e['side'], e['i']
    sl4 = e['sl']
    a = atr14(h, l, c, i + 1)
    # 找触及原SL的K
    j_touch = None
    for j in range(i + 1, min(len(c), i + 49)):
        if side == 'buy' and l[j] <= sl4:
            j_touch = j
            break
        if side == 'sell' and h[j] >= sl4:
            j_touch = j
            break
    if j_touch is None:
        # 没扫损就到期/TP: 按第4轮结算
        return M.run_trade(t, c, h, l, i, ep, sl4, e['tp'], side)
    jn = j_touch + 1
    if jn >= min(len(c), i + 49):
        return -1.0 if side == 'buy' else -1.0
    # 确认: 下一根K向进场方向收
    ok = (c[jn] < o[jn]) if side == 'sell' else (c[jn] > o[jn])
    if not ok:
        # 未确认(收盘反转) = 不进场, 结算0
        return 0.0
    ep3 = c[jn]
    sl3 = sl4 - 0.5 * a if side == 'buy' else sl4 + 0.5 * a
    risk3 = abs(sl3 - ep3)
    if risk3 <= 0:
        return 0.0
    for j in range(jn + 1, min(len(c), i + 49)):
        if side == 'buy':
            if l[j] <= sl3:
                return -1.0
            if h[j] >= e['tp']:
                return (e['tp'] - ep3) / risk3
            if t[j] - t[i] >= M.HOURS * 3600:
                return (c[j] - ep3) / risk3
        else:
            if h[j] >= sl3:
                return -1.0
            if l[j] <= e['tp']:
                return (ep3 - e['tp']) / risk3
            if t[j] - t[i] >= M.HOURS * 3600:
                return (c[j] - ep3) / risk3
    return (c[min(len(c) - 1, i + 48)] - ep3) / risk3 if side == 'buy' else (ep3 - c[min(len(c) - 1, i + 48)]) / risk3


def verdict_row(rs, name):
    if len(rs) < 30:
        return dict(name=name, n=len(rs), verdict='FAIL-LOUD(<30)')
    net = float(np.sum(rs))
    avg = net / len(rs)
    wr = float(np.mean([1 if r > 0 else 0 for r in rs]))
    net_s = net - STRESS * len(rs)
    T = [net > 0, wr >= 0.45, net_s > 0]
    v = 'APPROVE候选' if all(T) else ('WATCH' if net > 0 else 'REJECT')
    return dict(name=name, n=len(rs), netR=round(net, 2), avgR=round(avg, 4), wr=round(wr, 3),
                netR_015=round(net_s, 2), verdict=v)


def main():
    out = {}
    for sym in ['XAUUSD', 'EURUSD', 'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'LTCUSD', 'BNBUSD']:
        pkl = os.path.join(M.BASE.replace('net20261114_m15', 'ev_cache'), sym + '.pkl')
        if os.path.exists(pkl):
            d = pickle.load(open(pkl, 'rb'))
            t, c, h, l, o, ev = d['t'], d['c'], d['h'], d['l'], d['o'], d['ev']
        else:
            t, c, h, l, o, ev = M.events_oe(sym)
        if not ev:
            out[sym] = dict(verdict='FAIL-LOUD(无事件)')
            continue
        r2 = [run_v2(t, c, h, l, e) for e in ev]
        r3 = [run_v3(t, c, h, l, o, e) for e in ev]
        row = dict(V2_止损外移=verdict_row(r2, 'V2'), V3_扫损确认=verdict_row(r3, 'V3'),
                   t_range=[int(t[0]), int(t[-1])])
        out[sym] = row
        print('%-8s V2(止损外移) n=%-4d 净R=%s 胜率=%s %s | V3(扫损确认) n=%-4d 净R=%s 胜率=%s %s' % (
            sym, row['V2_止损外移'].get('n'), row['V2_止损外移'].get('netR', '-'),
            row['V2_止损外移'].get('wr', '-'), row['V2_止损外移']['verdict'],
            row['V3_扫损确认'].get('n'), row['V3_扫损确认'].get('netR', '-'),
            row['V3_扫损确认'].get('wr', '-'), row['V3_扫损确认']['verdict']))
    json.dump(dict(ts=time.strftime('%F %T'),
                   spec='第5轮: V2止损外移1.8x / V3扫损确认后进场(收盘确认+SL再外移0.5ATR), 同分母=第4轮事件集, 12h红线',
                   results=out),
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('OK ->', OUT)


if __name__ == '__main__':
    main()
