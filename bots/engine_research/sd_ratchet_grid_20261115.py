# 锁利棘轮 × TP × 触发 × 回吐 网格回测 (SD E3S1 全品种 5769 单, L0 口径克隆)
# 结构: 区远沿限价进场, SL0=0.15x区宽, TP=tpmul*R, 12h超时
# 锁利: 浮盈>=trigger_R 起, 每3s tick 推 SL=open+lock_r*R (lock_r=peak_r-giveback_R, 只紧不松)
import sys, os, json, time, pickle, glob, itertools
import numpy as np
sys.path.insert(0, '.')
from sd_all_11rounds_20261115 import settle_grid, verdict, DATA

all_ev = {}
for pkl in glob.glob(os.path.join(DATA + '_ev', '*.pkl')):
    all_ev[os.path.basename(pkl)[:-4]] = pickle.load(open(pkl, 'rb'))

TICKS = 8  # 3s tick 近似 (M15 bar 内取8个采样点=插针近似)

def settle_ratchet(d, slc=0.15, tpmul=4.0, hours=12, trig=0.5, giveback=0.6, edge='far'):
    """带 L0 口径棘轮锁利的结算 (K线OHLC内模拟tick: 用 bar 内极值路径近似)"""
    out = []
    t, c, h, l, o, ev = d['t'], d['c'], d['h'], d['l'], d['o'], d['ev']
    for e in ev:
        ep, side, i = e['ep'], e['side'], e['i']
        zt = max(e['zh'], 1e-12)
        sl0 = ep + slc * zt if side == 'sell' else ep - slc * zt
        risk = abs(sl0 - ep)
        if risk <= 0:
            continue
        tp = ep - tpmul * risk if side == 'sell' else ep + tpmul * risk
        end = min(i + int(hours * 240), len(c))
        peak_r = 0.0
        sl = sl0
        r = None
        for j in range(i + 1, end):
            # bar 内路径近似: 先顺向(极值) 再逆向(插针), 顺向时更新峰值
            if side == 'sell':
                fav, unfav = l[j], h[j]
            else:
                fav, unfav = h[j], l[j]
            fav_r = (ep - fav) / risk if side == 'sell' else (fav - ep) / risk
            peak_r = max(peak_r, fav_r)
            if peak_r >= trig:
                lock_r = max(peak_r - giveback, 0.0)
                # [11-17口径修] sell=下移棘轮(SL 从上侧降到 entry 及更低=锁盈); buy=上移棘轮
                # 11-15 旧版两侧同用 ep+lock_r*risk = sell 侧符号反(亏损侧离场被记成锁盈, 23377R/98.9%WR 不可采信, 御史审计)
                sl = ep - lock_r * risk if side == 'sell' else ep + lock_r * risk
            if side == 'sell':
                hit_tp = fav <= tp
                hit_sl = unfav >= sl
                if hit_sl:  # [11-17口径修] 同 bar 双触= adverse 优先(防幽灵成交价: 旧版先判 TP 乐观计)
                    r = (ep - sl) / risk  # sl>ep=原止损-1R; sl<ep=锁盈出场+lock_r (统一符号公式)
                    break
                if hit_tp:
                    r = tpmul; break
            else:
                hit_tp = fav >= tp
                hit_sl = unfav <= sl
                if hit_sl:  # [11-17口径修] 同 bar 双触= adverse 优先(防幽灵成交价)
                    r = (sl - ep) / risk if sl >= ep else -1.0  # sl<ep=原止损-1R; sl>=ep=锁盈出场
                    break
                if hit_tp:
                    r = tpmul; break
        if r is None:
            last = c[end - 1]
            r = (ep - last) / risk if side == 'sell' else (last - ep) / risk
        out.append(r)
    return out

print('=== 27 组网格: 触发(0.3/0.5/0.7) × 回吐(0.4/0.6/0.8) × TP(3/4/5) ===')
results = []
for trig, gb, tp in itertools.product((0.3, 0.5, 0.7), (0.4, 0.6, 0.8), (3.0, 4.0, 5.0)):
    allr = []
    for sym, d in all_ev.items():
        allr += [r for r in settle_ratchet(d, slc=0.15, tpmul=tp, hours=12, trig=trig, giveback=gb) if r != 0]
    v = verdict(allr, 'grid')
    if 'netR' not in v:
        continue
    results.append(dict(trig=trig, giveback=gb, tp=tp, netR=v['netR'], wr=v['wr'], T=v['T']))
    print('  触发=%.1f 回吐=%.1f TP=%.0f: 净R=%-9s 胜率=%s%% 五验=%s/6 %s' % (
        trig, gb, tp, v['netR'], round(100 * v['wr'], 1), v['T'], v.get('verdict', '')))
results.sort(key=lambda x: -x['netR'])
best = results[0]
print('最优: 触发=%.1f 回吐=%.1f TP=%.0f 净R=%s 五验=%s/6' % (
    best['trig'], best['giveback'], best['tp'], best['netR'], best['T']))

# 最优组合邻域(稳健性)
print('=== 最优邻域± (稳健) ===')
for trig in (max(0.2, best['trig'] - 0.2), best['trig'], min(1.0, best['trig'] + 0.2)):
    for gb in (max(0.2, best['giveback'] - 0.2), best['giveback'], min(1.0, best['giveback'] + 0.2)):
        allr = []
        for sym, d in all_ev.items():
            allr += [r for r in settle_ratchet(d, slc=0.15, tpmul=best['tp'], hours=12, trig=trig, giveback=gb) if r != 0]
        v = verdict(allr, 'nb')
        print('  触发=%.1f 回吐=%.1f: 净R=%-9s 胜率=%s%% 五验=%s/6' % (
            trig, gb, v.get('netR', '-'), ('%.1f%%' % (100 * v['wr'])) if 'wr' in v else '-', v.get('T', '-')))

json.dump(dict(ts=time.strftime('%F %T'), grid=results, best=best),
          open('sd_ratchet_grid_20261115.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('OK -> sd_ratchet_grid_20261115.json')
