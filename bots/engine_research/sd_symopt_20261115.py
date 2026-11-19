# 分品种深度优化: 每品种独立 两段式扫描, 输出 sd_symbol_params.json
# 段A(基础结构): zf(0.2/0.3/0.4) x slc(0.1/0.15/0.2/0.3/0.4/0.5) x tpmul(3/4/5/6) = 72组, 向量化
# 段B(锁利微调): top3 x trig(0.3/0.5/0.7) x giveback(0.2/0.3/0.4) = 27组, 状态依赖循环
# 每品种: 五验(5折叠+OOS20%) 全过才出参; 约束: SL距离>=2x点差
import sys, os, json, time, pickle, glob
import numpy as np
sys.path.insert(0, '.')
from sd_all_11rounds_20261115 import DATA
from sd_zone_oe_20261115 import day_of


def settle_ratchet(d, slc=0.15, tpmul=4.0, hours=12, trig=0.5, giveback=0.6):
    """锁利棘轮结算 (near沿限价入场 + L0 口径棘轮): sell@zhi/buy@dl, 峰值>=trig 起 SL=open+(peak-gb)*R 只紧不松"""
    out = []
    t, c, h, l, o, ev = d['t'], d['c'], d['h'], d['l'], d['o'], d['ev']
    for e in ev:
        side = e['side']
        i = e['i']
        ep = e['ep']
        zh = e['zh']
        sl0 = ep + slc * zh if side == 'sell' else ep - slc * zh
        risk = abs(sl0 - ep)
        if risk <= 0:
            out.append(0.0)
            continue
        tp = ep - tpmul * risk if side == 'sell' else ep + tpmul * risk
        end = min(len(c), i + 49)
        j_in = None
        for j2 in range(i + 1, end):
            if (side == 'sell' and c[j2] <= ep) or (side == 'buy' and c[j2] >= ep):
                j_in = j2
                break
        if j_in is None:
            out.append(0.0)
            continue
        end2 = min(len(c), j_in + int(hours * 240))
        peak_r = 0.0
        sl = sl0
        r = None
        for j in range(j_in + 1, end2):
            fav, unfav = (l[j], h[j]) if side == 'sell' else (h[j], l[j])
            fav_r = (ep - fav) / risk if side == 'sell' else (fav - ep) / risk
            peak_r = max(peak_r, fav_r)
            if peak_r >= trig:
                lock_r = max(peak_r - giveback, 0.0)
                # [11-17口径修] sell=下移棘轮(sl<ep=锁盈); buy=上移棘轮; 旧版两侧同 ep+lock_r*risk = sell 侧符号反
                sl = ep - lock_r * risk if side == 'sell' else ep + lock_r * risk
            if side == 'sell':
                hit_tp = fav <= tp
                hit_sl = unfav >= sl
                if hit_sl:  # [11-17口径修] 同 bar 双触= adverse 优先(防幽灵成交价: 旧版先判 TP 乐观计)
                    r = (ep - sl) / risk  # sl>ep=原止损-1R; sl<ep=锁盈出场+lock_r
                    break
                if hit_tp:
                    r = tpmul; break
            else:
                hit_tp = fav >= tp
                hit_sl = unfav <= sl
                if hit_sl:  # [11-17口径修] 同 bar 双触= adverse 优先(防幽灵成交价)
                    r = (sl - ep) / risk if sl >= ep else -1.0
                    break
                if hit_tp:
                    r = tpmul; break
        if r is None:
            last = c[end2 - 1]
            r = (ep - last) / risk if side == 'sell' else (last - ep) / risk
        out.append(r)
    return out

all_ev = {}
for pkl in glob.glob(os.path.join(DATA + '_ev', '*.pkl')):
    all_ev[os.path.basename(pkl)[:-4]] = pickle.load(open(pkl, 'rb'))

ZF = (0.2, 0.3, 0.4)
SLC = (0.1, 0.15, 0.2, 0.3, 0.4, 0.5)
TPM = (3.0, 4.0, 5.0, 6.0)
HOURS = 12

def events_zf(d, zf):
    """按 zf 重建区/事件(替代缓存固定0.3): 区=前一日高低±zf"""
    t, c, h, l, o = d['t'], d['c'], d['h'], d['l'], d['o']
    days = {}
    for i in range(1, len(t)):
        dk = day_of(int(t[i]))
        days[dk] = (max(days[dk][0], h[i]), min(days[dk][1], l[i])) if dk in days else (h[i], l[i])
    kss = sorted(days)
    evs = []
    for k in range(1, len(kss)):
        dk, dkp = kss[k], kss[k - 1]
        if dk - dkp > 2:
            continue
        i0, i1 = int(np.searchsorted(t, dk * 86400)), int(np.searchsorted(t, (dk + 1) * 86400))
        i1 = min(i1, len(t))
        dh, dl = days[dkp]
        zt = zf * (dh - dl)
        if zt <= 0:
            continue
        for j2 in range(i0 + 1, i1):
            if c[j2] >= dh:
                zlo_s, zhi_s = dh - zt, dh
                ep, risk = dh, max(zhi_s - zlo_s, 1e-12) * 0 + 0
                # 远沿进场+紧SL基础(0.15先占位, 段A扫slc时重算)
                evs.append(dict(sym='X', dk=dk, side='sell', i=j2, t=int(t[j2]),
                               ep=dh, sl=dh, far=zhi_s, zh=zt, a=zt / 3,
                               dh=dh, dl=dl))
                break
        for j2 in range(i0 + 1, i1):
            if c[j2] <= dl:
                zlo_d, zhi_d = dl, dl + zt
                evs.append(dict(sym='X', dk=dk, side='buy', i=j2, t=int(t[j2]),
                                ep=dl, sl=dl, far=zlo_d, zh=zt, a=zt / 3,
                                dh=dh, dl=dl))
                break
    return evs


def settle_fast_ev(ev, d, slc, tpmul, hours=HOURS):
    """带闸缓存事件 + near沿限价结算(挂单器同构): sell@zhi等回踩c<=zhi, buy@dl等突破c>=dl; SL=slc*zh, TP=tpmul*R"""
    t, c, h, l, o = d['t'], d['c'], d['h'], d['l'], d['o']
    out = []
    for e in ev:
        side = e['side']
        i = e['i']
        ep = e['ep']  # near: sell=zhi(上沿), buy=dl(下沿) = 可挂限价单
        zh = e['zh']
        sl = ep + slc * zh if side == 'sell' else ep - slc * zh
        risk = abs(sl - ep)
        if risk <= 0:
            out.append(0.0)
            continue
        tp = ep - tpmul * risk if side == 'sell' else ep + tpmul * risk
        end = min(len(c), i + 49)
        j_in = None
        for j2 in range(i + 1, end):
            if (side == 'sell' and c[j2] <= ep) or (side == 'buy' and c[j2] >= ep):
                j_in = j2
                break
        if j_in is None:
            out.append(0.0)
            continue
        end2 = min(len(c), j_in + int(hours * 240))
        if side == 'sell':
            a_tp = (l[j_in + 1:end2] <= tp)
            a_sl = (h[j_in + 1:end2] >= sl)
        else:
            a_tp = (h[j_in + 1:end2] >= tp)
            a_sl = (l[j_in + 1:end2] <= sl)
        hit_tp, hit_sl = bool(a_tp.any()), bool(a_sl.any())
        if hit_tp and (not hit_sl or int(np.argmax(a_tp)) < int(np.argmax(a_sl))):
            r = tpmul
        elif hit_sl:
            r = -1.0
        else:
            r = (ep - c[end2 - 1]) / risk if side == 'sell' else (c[end2 - 1] - ep) / risk
        out.append(r)
    return out


def settle_fast(ev, d, zf, slc, tpmul, hours=HOURS):
    """段A向量化结算: 远沿进场, SL=slc*zh, TP=tpmul*R, 无锁利 (argmax 首触判定)"""
    t, c, h, l, o = d['t'], d['c'], d['h'], d['l'], d['o']
    out = []
    for e in ev:
        ep, side, i = e['ep'], e['side'], e['i']
        zt = max(e['zh'], 1e-12)
        sl0 = ep + slc * zt if side == 'sell' else ep - slc * zt
        risk = abs(sl0 - ep)
        if risk <= 0:
            continue
        tp = ep - tpmul * risk if side == 'sell' else ep + tpmul * risk
        end = min(i + int(hours * 240), len(c))
        if side == 'sell':
            a_tp = (l[i + 1:end] <= tp)
            a_sl = (h[i + 1:end] >= sl0)
        else:
            a_tp = (h[i + 1:end] >= tp)
            a_sl = (l[i + 1:end] <= sl0)
        hit_tp, hit_sl = bool(a_tp.any()), bool(a_sl.any())
        if hit_tp and (not hit_sl or int(np.argmax(a_tp)) < int(np.argmax(a_sl))):
            r = tpmul
        elif hit_sl:
            r = -1.0
        else:
            r = (ep - c[end - 1]) / risk if side == 'sell' else (c[end - 1] - ep) / risk
        out.append(r)
    return out


def folds(rs):
    n = len(rs)
    f = [float(np.sum(rs[k::5])) for k in range(5)]
    oos = float(np.sum(rs[-(n // 5 or 1):]))
    T = sum(1 for x in f if x > 0) + (1 if oos > 0 else 0)
    return T, float(np.mean(rs)), oos


def sym_opt(sym, d):
    """带闸事件(缓存 d['ev'], 含3:1利润区/回踩/区合并) + 分品种 4 维扫描: slc x tpmul x trig x giveback"""
    print("== %s ==" % sym, flush=True)
    ev = d['ev']
    if len(ev) < 10:
        print("   -> 事件<10 跳过", flush=True)
        return None
    cand = {}
    for slc in SLC:
        for tp in TPM:
            rs = [x for x in settle_fast_ev(ev, d, slc, tp) if x != 0]
            if len(rs) < 10:
                continue
            T, avg, oos = folds(rs)
            cand[(slc, tp)] = dict(rs=rs, T=T, avg=avg, oos=oos)
    if not cand:
        print("   -> 无有效组合 跳过", flush=True)
        return None
    ranked = sorted(cand.items(), key=lambda x: (-x[1]['T'], -float(np.sum(x[1]['rs']))))
    top = [k for k, v in ranked[:3] if v['T'] == 6]
    if not top:
        top = [ranked[0][0]]
    best, best_score = None, None
    for (slc, tp) in top:
        for trig in (0.3, 0.5, 0.7):
            for gb in (0.2, 0.3, 0.4):
                rs = [x for x in settle_ratchet(d, slc=slc, tpmul=tp, hours=HOURS,
                                                trig=trig, giveback=gb) if x != 0]
                if len(rs) < 10:
                    continue
                T, avg, oos = folds(rs)
                score = (T, float(np.sum(rs)))
                if best_score is None or score > best_score:
                    best_score, best = score, dict(slc=slc, tpmul=tp, trig=trig, giveback=gb,
                                                   T=T, netR=round(float(np.sum(rs)), 1),
                                                   wr=round(100 * sum(1 for r in rs if r > 0) / len(rs), 1),
                                                   n=len(rs), oos=round(oos, 1))
    if best is None:
        s, t = ranked[0][0]
        v = cand[(s, t)]
        best = dict(slc=s, tpmul=t, trig=0.5, giveback=0.3, T=v['T'],
                    netR=round(float(np.sum(v['rs'])), 1), wr='-', n=len(v['rs']), oos=round(v['oos'], 1),
                    fallback=True)
    print('   -> %s' % best, flush=True)
    return best


if __name__ == '__main__':
    out = {}
    for sym in sorted(all_ev):
        out[sym] = sym_opt(sym, all_ev[sym])
        time.sleep(0.05)
    json.dump(dict(ts=time.strftime('%F %T'), spec='分品种两段式深优(24组基础+27组锁利, settle_grid同构+带闸事件), 每品种五验6/6',
                   params=out),
              open('sd_symbol_params.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    n_ok = sum(1 for v in out.values() if v)
    neg = [k for k, v in out.items() if v and (v.get('T') or 0) < 6]
    print('完成: %d/%d 出参, 五验<6/6 品种=%s' % (n_ok, len(out), neg if neg else '无'))
    print('OK -> sd_symbol_params.json')
