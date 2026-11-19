"""扫损后走势验证 + 事件缓存(第5轮复用) · 2026-11-15
修复: 上一版 print 行 %% 格式化崩在写盘前. 本版每品种算完即时 print, 事件 pickle 缓存.
数据闸: 快照打印; n>=30 才下结论(扫损子集按实际数量报).
"""
import json, os, time, pickle, sys, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sd_zone_oe_20261115 as M

CACHE = r'E:\GoldstrategyEngine\research\ev_cache'
OUT = r'E:\GoldstrategyEngine\research\post_sl_analysis_20261115.json'
HORIZON = 48


def analyze(sym):
    t, c, h, l, o, ev = M.events_oe(sym)
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, sym + '.pkl'), 'wb') as f:
        pickle.dump(dict(t=t, c=c, h=h, l=l, o=o, ev=ev), f)
    mfe_after, mae_after, tp_late = [], [], 0
    n_stop, n_win, n_tmo = 0, 0, 0
    R_list, TP_range_list = [], []
    for e in ev:
        ep, sl, tp, side, i = e['ep'], e['sl'], e['tp'], e['side'], e['i']
        risk = abs(sl - ep)
        R_list.append(risk)
        j_sl = None
        for j in range(i + 1, min(len(c), i + 49)):
            if side == 'buy' and l[j] <= sl:
                j_sl = j
                break
            if side == 'sell' and h[j] >= sl:
                j_sl = j
                break
        if j_sl is None:
            hit_tp = False
            for j in range(i + 1, min(len(c), i + 49)):
                if side == 'buy' and h[j] >= tp:
                    hit_tp = True
                    break
                if side == 'sell' and l[j] <= tp:
                    hit_tp = True
                    break
            if hit_tp:
                n_win += 1
            else:
                n_tmo += 1
            continue
        n_stop += 1
        end = min(len(c), j_sl + HORIZON + 1)
        if side == 'sell':
            mfe = max((ep - c[j_sl:end].min()), 0)
            maed = max((c[j_sl:end].max() - ep), 0)
            tp_late += int(l[j_sl:end].min() <= tp)
        else:
            mfe = max((c[j_sl:end].max() - ep), 0)
            maed = max((ep - l[j_sl:end].min()), 0)
            tp_late += int(h[j_sl:end].max() >= tp)
        mfe_after.append(mfe / risk)
        mae_after.append(maed / risk)
        TP_range_list.append(abs(tp - ep) / risk)
    row = dict(n_ev=len(ev), n_stop=n_stop, n_win=n_win, n_tmo=n_tmo,
               mfe_after_R=round(float(np.mean(mfe_after)), 3) if mfe_after else None,
               mae_after_R=round(float(np.mean(mae_after)), 3) if mae_after else None,
               tp_late_pct=round(100 * tp_late / max(n_stop, 1), 1),
               tp_R=round(float(np.mean(TP_range_list)), 2) if TP_range_list else None,
               t_range=[int(t[0]), int(t[-1])])
    return row


def main():
    out = {}
    for sym in ['XAUUSD', 'EURUSD', 'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'LTCUSD', 'BNBUSD']:
        t0 = time.time()
        row = analyze(sym)
        out[sym] = row
        print('[%s] 事件=%d 扫损=%d 胜=%d 到期=%d | 扫损后12h: 顺向=%sR 逆向=%sR 再摸原TP=%s%% TP口径=%sR (%.0fs)' % (
            sym, row['n_ev'], row['n_stop'], row['n_win'], row['n_tmo'],
            row['mfe_after_R'], row['mae_after_R'], row['tp_late_pct'], row['tp_R'], time.time() - t0), flush=True)
    json.dump(dict(ts=time.strftime('%F %T'),
                   spec='扫损后12h走势验证(第4轮Seiden标准结构事件) — 顺向>逆向 & 再摸TP占比高 = 方向对时机错',
                   results=out),
              open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('OK ->', OUT, flush=True)


if __name__ == '__main__':
    main()
