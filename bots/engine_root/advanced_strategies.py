# advanced_strategies.py — 金策宗师团 · 全网先进策略信号生成器 (策金尊 CIO)
"""
把 2025-2026 全网调研验证过、可量化的先进策略, 实现为**可插拔信号生成器**。
每个生成器输入 (h1, h4, d1, cfg) DataFrame, 输出候选信号列表:
    signal = {
        'bar':    int    # H1 _bar 索引 (信号在哪一_bar 触发)
        'side':   +1/-1
        'entry':  float  # 入场价 (取该_bar close)
        'sl':     float
        'tp':     float
        'regime': str
        'strat':  str    # 策略名
        'lot':    float
    }
风控/仓位/点差/连亏冷却由 universe_backtest.execute_signals 统一执行,
生成器只负责"在何处、何种方向、何种 SL/TP 入场"。

已落地的先进策略 (均来自 2025-2026 回测验证文献):
  SDP  : 原有供需区 + D1方向 + ADX + ATR (基线)
  ICT  : 订单块(OB) + 公平价值缺口(FVG) + 流动性扫荡 + 市场结构转变(MSS)
         + 折扣/溢价区过滤, 多条件共振(≥3 分才入场), ICT 2026 框架
  VP   : 成交量分布 POC/价值区(VAH/VAL)/低量节点(LVN) 均值回归,
         剔除 LVN 亏损交易 (研究: LVN 区单独胜率仅 34%), ADX>20 门禁
  DIV  : RSI 常规 + 隐藏背离 (及 MACD 背离辅助)
  MR   : 价格 z-score 偏离均线 均值回归 (区间内高胜率)

参考来源:
  - ICT/SMC 2026 框架 (trasignal/lunefi/meetforextraders): OB+FVG+Sweep+MSS, 胜率55-75%, RR 1:2+
  - Volume Profile 量化研究 (linkedin/zooz/trendsandbreakouts): LVN 过滤剔除亏损,
    POC 磁吸, 价值区回测; ADX>20 时 LVN 过滤才有效
  - SMC Pro BTC 回测 (tradingview): OB+FVG+volume 共振 PF 1.95(激进)/2.35(精选)
"""

import numpy as np
import pandas as pd

# ════════════════════════════════════════════════════════════════
# 0. 通用技术指标
# ════════════════════════════════════════════════════════════════
def ema(v, p):
    v = np.asarray(v, float)
    r = np.full(len(v), np.nan); r[p-1] = np.mean(v[:p])
    a = 2/(p+1)
    for i in range(p, len(v)):
        r[i] = v[i]*a + r[i-1]*(1-a)
    return r

def sma(v, p):
    v = np.asarray(v, float)
    return pd.Series(v).rolling(p, min_periods=p).mean().values

def std(v, p):
    v = np.asarray(v, float)
    return pd.Series(v).rolling(p, min_periods=p).std().values

def atr(h, l, c=None, p=14):
    if c is None:
        c = (h + l) / 2
    h, l, c = np.asarray(h, float), np.asarray(l, float), np.asarray(c, float)
    tr = np.maximum(h[1:]-l[1:], np.maximum(abs(h[1:]-np.roll(h,1)[1:]), abs(l[1:]-np.roll(l,1)[1:])))
    r = np.full(len(h), np.nan); r[p] = np.mean(tr[:p])
    a = 1/p
    for i in range(p+1, len(h)):
        r[i] = tr[i-1]*a + r[i-1]*(1-a)
    return pd.Series(r).ffill().fillna(np.mean(tr[:p])).values

def adx(h, l, c, p=14):
    h, l, c = np.asarray(h, float), np.asarray(l, float), np.asarray(c, float)
    if len(c) < p*2:
        return np.zeros(len(c))
    tr = np.maximum(h[1:]-l[1:], np.maximum(abs(h[1:]-c[:-1]), abs(l[1:]-c[:-1])))
    u = h[1:]-h[:-1]; d = l[:-1]-l[1:]
    pdi = 100*pd.Series(np.where((u>d)&(u>0), u, 0)).ewm(span=p, adjust=False).mean()/(pd.Series(tr).ewm(span=p, adjust=False).mean()+1e-10)
    mdi = 100*pd.Series(np.where((d>u)&(d>0), d, 0)).ewm(span=p, adjust=False).mean()/(pd.Series(tr).ewm(span=p, adjust=False).mean()+1e-10)
    dx = 100*np.abs(pdi-mdi)/(pdi+mdi+1e-10)
    result = pd.Series(dx).ewm(span=p, adjust=False).mean().values
    return np.concatenate([np.zeros(len(c)-len(result)), result])

def rsi(v, p=14):
    v = np.asarray(v, float)
    d = np.diff(v)
    gain = np.where(d > 0, d, 0.0); loss = np.where(d < 0, -d, 0.0)
    ag = pd.Series(gain).ewm(span=p, adjust=False).mean().values
    al = pd.Series(loss).ewm(span=p, adjust=False).mean().values
    rs = ag/(al+1e-10)
    out = np.full(len(v), np.nan)
    out[1:] = 100 - 100/(1+rs)
    return out

def macd(v, fast=12, slow=26, sig=9):
    v = np.asarray(v, float)
    ef, es = ema(v, fast), ema(v, slow)
    m = ef - es
    s = ema(m, sig)
    return m, s, m - s

def find_swing(h, l, lb=3):
    h, l = np.asarray(h, float), np.asarray(l, float)
    swh, swl = [], []
    for i in range(lb, len(h)-lb):
        if h[i] == max(h[i-lb:i+lb+1]):
            swh.append((i, h[i]))
        if l[i] == min(l[i-lb:i+lb+1]):
            swl.append((i, l[i]))
    return swh, swl

def find_zones(h4_df):
    """SDP 供需区检测 (原 logic, 移植)。返回 {'demand':[...], 'supply':[...]}"""
    h = h4_df['high'].values; l = h4_df['low'].values; c = h4_df['close'].values
    zones = []
    swh, swl = find_swing(h, l, 3)
    for idx, low_val in swl:
        if idx < 2 or idx > len(c)-3:
            continue
        left_high = max(h[max(0, idx-10):idx+1]); down = left_high - low_val
        if down <= 0:
            continue
        for j in range(idx+1, min(idx+8, len(c))):
            if c[j] > low_val + down*0.2:
                bh = max(h[idx:j+1]); bl = min(l[idx:j+1]); ret = (bh-bl)/max(down, 1)
                if 0.15 <= ret <= 0.95:
                    zones.append({'type': 'D', 'top': bh, 'bottom': max(bl, low_val-(bh-bl)*0.1), 'strength': min(5.0, ret*5+0.5)})
                break
    for idx, high_val in swh:
        if idx < 2 or idx > len(c)-3:
            continue
        left_low = min(l[max(0, idx-10):idx+1]); up = high_val - left_low
        if up <= 0:
            continue
        for j in range(idx+1, min(idx+8, len(c))):
            if c[j] < high_val - up*0.2:
                bh = max(h[idx:j+1]); bl = min(l[idx:j+1]); ret = (bh-bl)/max(up, 1)
                if 0.15 <= ret <= 0.95:
                    zones.append({'type': 'S', 'top': min(bh, high_val+(bh-bl)*0.1), 'bottom': bl, 'strength': min(5.0, ret*5+0.5)})
                break
    merged = []
    for z in zones:
        if not any(m['type'] == z['type'] and abs(m['top']-z['top'])/max(m['top'], 1) < 0.01
                   and abs(m['bottom']-z['bottom'])/max(m['bottom'], 1) < 0.01 for m in merged):
            merged.append(z)
    return {'demand': [z for z in merged if z['type'] == 'D'],
            'supply': [z for z in merged if z['type'] == 'S']}


# ════════════════════════════════════════════════════════════════
# 1. SDP (基线策略) — 供需区 + D1方向 + ADX + ATR
# ════════════════════════════════════════════════════════════════
def gen_sdp(h1, h4, d1, cfg) -> list:
    hc = h1['close'].values.astype(float); hh = h1['high'].values.astype(float); hl = h1['low'].values.astype(float)
    adx_v = adx(hh, hl, hc); atr_v = atr(hh, hl, hc)
    e14 = ema(hc, 14); e28 = ema(hc, 28)
    h4c = h4['close'].values.astype(float); h4adx = adx(h4['high'].values, h4['low'].values, h4c)
    dc = d1['close'].values.astype(float); de9 = ema(dc, 9); de21 = ema(dc, 21)
    h4_tr = np.maximum(h4['high'].values[1:]-h4['low'].values[1:],
                       np.maximum(abs(h4['high'].values[1:]-h4c[:-1]), abs(h4['low'].values[1:]-h4c[:-1])))
    h4a = np.full(len(h4c), np.nan); h4a[14] = np.mean(h4_tr[:14])
    for i in range(15, len(h4c)):
        h4a[i] = h4_tr[i-1]/14 + h4a[i-1]*13/14
    h4a = pd.Series(h4a).ffill().fillna(np.mean(h4_tr[:14])).values

    adx_min = cfg['adx_min']; sl_m = cfg['sl_mult']; rr_m = cfg['rr_mult']
    lots = cfg.get('lot', 0.1)
    sig = []
    h4_cache = {}
    for i in range(100, len(h1)):
        price = hc[i]
        if np.isnan(adx_v[i]) or adx_v[i] < adx_min:
            continue
        h4i = min(i//4, len(h4c)-1); hadx = h4adx[max(0, h4i)]
        regime = 'trend'
        if hadx < 20 and adx_v[i] < 20:
            regime = 'ranging'
        if hadx > 35:
            regime = 'strong_trend'
        atr_h = atr_v[max(0, i-30):i+1]
        if len(atr_h) > 10 and atr_v[i] > np.mean(atr_h)*1.8:
            regime = 'volatile'
        if regime == 'volatile':
            continue
        if np.isnan(e14[i]) or np.isnan(e28[i]):
            continue
        trend = 'UP' if e14[i] > e28[i] else 'DOWN'
        ck = h4i
        if ck not in h4_cache:
            chunk = h4.iloc[max(0, h4i-30):h4i+1]
            if len(chunk) >= 15:
                h4_cache[ck] = find_zones(chunk)
            else:
                continue
        zd = h4_cache.get(ck, {'demand': [], 'supply': []})
        zc = None; zt = None; flip = False; h4a_val = h4a[max(0, h4i)]
        for z in zd.get('demand', []):
            if z['strength'] >= 1.0 and price > z['top'] and price - z['top'] < h4a_val*3:
                zc, zt = z, 'D'; break
        if not zc:
            for z in zd.get('supply', []):
                if z['strength'] >= 1.0 and price < z['bottom'] and z['bottom'] - price < h4a_val*3:
                    zc, zt = z, 'S'; break
        if not zc:
            for z in zd.get('supply', []):
                if price > z['top']:
                    zc, zt = z, 'D'; flip = True; break
        if not zc:
            for z in zd.get('demand', []):
                if price < z['bottom']:
                    zc, zt = z, 'S'; flip = True; break
        if not zc:
            continue
        d1i = min(i//24, len(dc)-1)
        if d1i >= 21 and not np.isnan(de9[d1i]) and not np.isnan(de21[d1i]):
            d1_dir = 'UP' if de9[d1i] > de21[d1i] else 'DOWN'
            direction = ('BUY' if (d1_dir == 'UP' and zt == 'D') else
                         'SELL' if (d1_dir == 'DOWN' and zt == 'S') else None)
        else:
            direction = ('BUY' if (trend == 'UP' and zt == 'D') else
                         'SELL' if (trend == 'DOWN' and zt == 'S') else None)
        if not direction:
            continue
        sm = sl_m; rm = rr_m
        if regime == 'ranging':
            sm = min(sm*0.7, 0.8); rm = max(rm*0.8, 1.5)
        elif regime == 'strong_trend':
            sm = max(sm*1.2, 1.0); rm *= 1.2
        buf = max(h4a_val*0.1, 0.5*cfg['pip'])
        # ── SL 双约束: 结构位(供需区边界) 与 ATR 上限(cfg.sl_mult 语义) 取更紧者 ──
        # 未加此上限时, 宽供需区会产生荒谬止损(黄金曾达 $150+/笔, 小账户根本开不起)
        sl_cap = max(h4a_val * sm, 4.0 * cfg['pip']) if h4a_val > 0 else None
        if direction == 'BUY':
            sl = zc['bottom'] - buf
            if sl_cap is not None:
                sl = max(sl, price - sl_cap)          # 不允许比 ATR 上限更远
            if price - sl <= 0:
                continue
            tp = price + (price - sl)*rm
        else:
            sl = zc['top'] + buf
            if sl_cap is not None:
                sl = min(sl, price + sl_cap)
            if sl - price <= 0:
                continue
            tp = price - (sl - price)*rm
        sig.append({'bar': i, 'side': 1 if direction == 'BUY' else -1,
                    'entry': price, 'sl': sl, 'tp': tp, 'regime': regime,
                    'strat': 'SDP', 'lot': lots})
    return sig


# ════════════════════════════════════════════════════════════════
# 2. ICT / SMC — 订单块 + FVG + 流动性扫荡 + MSS + 折扣/溢价
# ════════════════════════════════════════════════════════════════
def _detect_fvg(h, l, c):
    """返回 bullish/ bearish FVG 区间列表。bullish: low[i+2] > high[i]"""
    bull, bear = [], []
    for i in range(0, len(c)-2):
        # bullish FVG: 3 根 K 中, 第1根 high 与 第3根 low 之间留空
        if l[i+2] > h[i]:
            bull.append((i, h[i], l[i+2]))      # (idx, top=high[i], bottom=low[i+2])
        if h[i+2] < l[i]:
            bear.append((i, h[i+2], l[i]))       # (idx, top=high[i+2], bottom=low[i])
    return bull, bear

def _detect_ob(h, l, c, disp=0.012):
    """订单块: 强位移前最后一根反向 K。返回 bullish OB (需求) / bearish OB (供应) 区间。"""
    bull, bear = [], []
    for i in range(2, len(c)-1):
        move = (c[i+1] - c[i-1]) / max(c[i-1], 1e-9)
        if move > disp:   # 强向上位移 → 前一根(空头发力)是 bullish OB
            bear_candle = i-1
            bull.append((i, max(h[bear_candle], c[bear_candle]), min(l[bear_candle], c[bear_candle])))
        elif move < -disp:
            bull_candle = i-1
            bear.append((i, max(h[bull_candle], c[bull_candle]), min(l[bull_candle], c[bull_candle])))
    return bull, bear

def gen_ict(h1, h4, d1, cfg) -> list:
    hc = h1['close'].values.astype(float); hh = h1['high'].values.astype(float); hl = h1['low'].values.astype(float)
    dc = d1['close'].values.astype(float)
    adx_v = adx(hh, hl, hc)
    # HTF 偏向 (D1 EMA9/21)
    de9 = ema(dc, 9); de21 = ema(dc, 21)
    # 折扣/溢价区 (基于近 20 根 D1 区间)
    dhi = pd.Series(dc).rolling(20).max().values
    dlo = pd.Series(dc).rolling(20).min().values
    # 摆动点 (流动性池)
    swh, swl = find_swing(hh, hl, 4)
    swh_v = [x[1] for x in swh]; swl_v = [x[1] for x in swl]
    swh_i = [x[0] for x in swh]; swl_i = [x[0] for x in swl]
    bull_fvg, bear_fvg = _detect_fvg(hh, hl, hc)
    bull_ob, bear_ob = _detect_ob(hh, hl, hc)
    lots = cfg.get('lot', 0.1)

    sig = []
    for i in range(60, len(h1)):
        price = hc[i]
        # HTF 偏向
        d1i = min(i//24, len(dc)-1)
        if np.isnan(de9[d1i]) or np.isnan(de21[d1i]):
            continue
        bias = 'UP' if de9[d1i] > de21[d1i] else 'DOWN'
        # 折扣/溢价
        rng_hi, rng_lo = dhi[d1i], dlo[d1i]
        if np.isnan(rng_hi) or np.isnan(rng_lo) or rng_hi <= rng_lo:
            continue
        mid = (rng_hi + rng_lo)/2
        in_discount = price < mid
        in_premium = price > mid

        # 流动性扫荡: 近 5 根内价格曾跌破近期 swl 又收复 (买侧流动性), 或突破 swh 又回落
        sweep_low = sweep_high = False
        recent_lo = min(hl[max(0, i-5):i+1]); recent_hi = max(hh[max(0, i-5):i+1])
        for lv in swl_v:
            if abs(recent_lo - lv)/max(lv, 1e-9) < 0.002 and price > lv:
                sweep_low = True; break
        for hv in swh_v:
            if abs(recent_hi - hv)/max(hv, 1e-9) < 0.002 and price < hv:
                sweep_high = True; break
        # MSS: 近 5 根内突破上一摆动高低
        mss_up = any(price > hv for hv in swh_v[-8:]) if swh_v else False
        mss_dn = any(price < lv for lv in swl_v[-8:]) if swl_v else False

        def has_zone(zones, p):
            return any(z[1] >= p >= z[2] for z in zones)

        if bias == 'UP' and in_discount:
            score = 0
            if has_zone(bull_ob, price): score += 2
            if has_zone(bull_fvg, price): score += 1
            if sweep_low: score += 1
            if mss_up: score += 1
            if score >= 3:
                sl = min(hl[max(0, i-4):i+1]) - cfg['pip']*2
                tp = price + (price - sl)*cfg.get('rr_mult', 2.0)
                sig.append({'bar': i, 'side': 1, 'entry': price, 'sl': sl, 'tp': tp,
                            'regime': f'ict_s{score}', 'strat': 'ICT', 'lot': lots})
        elif bias == 'DOWN' and in_premium:
            score = 0
            if has_zone(bear_ob, price): score += 2
            if has_zone(bear_fvg, price): score += 1
            if sweep_high: score += 1
            if mss_dn: score += 1
            if score >= 3:
                sl = max(hh[max(0, i-4):i+1]) + cfg['pip']*2
                tp = price - (sl - price)*cfg.get('rr_mult', 2.0)
                sig.append({'bar': i, 'side': -1, 'entry': price, 'sl': sl, 'tp': tp,
                            'regime': f'ict_s{score}', 'strat': 'ICT', 'lot': lots})
    return sig


# ════════════════════════════════════════════════════════════════
# 3. Volume Profile — POC / 价值区 / LVN 均值回归
# ════════════════════════════════════════════════════════════════
def _vp_profile(dc, dlo, dhi, dvol, end_idx, win=20, bins=50):
    """对 end_idx 之前 win 根 D1 计算成交量分布, 返回 (poc, vah, val, lvn_set)。"""
    lo = max(0, end_idx - win + 1)
    seg = slice(lo, end_idx+1)
    closes = dc[seg]; highs = dhi[seg]; lows = dlo[seg]; vols = dvol[seg]
    if len(closes) < 5:
        return None
    pmin = np.min(lows); pmax = np.max(highs)
    if pmax <= pmin:
        return None
    edges = np.linspace(pmin, pmax, bins+1)
    centers = (edges[:-1] + edges[1:])/2
    vol_bin = np.zeros(bins)
    for k in range(len(closes)):
        # 把该 D1 bar 的量分配到其 [low,high] 覆盖的 bin (按比例)
        b0 = np.searchsorted(edges, lows[k], side='right')-1
        b1 = np.searchsorted(edges, highs[k], side='left')
        b0 = max(0, min(bins-1, b0)); b1 = max(0, min(bins-1, b1))
        if b1 < b0:
            b1 = b0
        n = b1 - b0 + 1
        vol_bin[b0:b1+1] += vols[k]/n
    if vol_bin.sum() <= 0:
        return None
    poc = int(np.argmax(vol_bin))
    maxv = vol_bin[poc]
    # 扩展价值区到 70%
    cum = vol_bin[poc]; lo_i, hi_i = poc, poc
    while cum < 0.70*vol_bin.sum() and (lo_i > 0 or hi_i < bins-1):
        down = vol_bin[lo_i-1] if lo_i > 0 else -1
        up = vol_bin[hi_i+1] if hi_i < bins-1 else -1
        if up >= down and hi_i < bins-1:
            hi_i += 1; cum += vol_bin[hi_i]
        elif lo_i > 0:
            lo_i -= 1; cum += vol_bin[lo_i]
        else:
            break
    lvn = set(np.where(vol_bin < 0.15*maxv)[0].tolist())
    return edges[poc], edges[hi_i+1], edges[lo_i], lvn, centers

def gen_vp(h1, h4, d1, cfg) -> list:
    hc = h1['close'].values.astype(float)
    dc = d1['close'].values.astype(float); dlo = d1['low'].values.astype(float); dhi = d1['high'].values.astype(float)
    dvol = d1['tick_volume'].values.astype(float) if 'tick_volume' in d1.columns else \
           (d1['volume'].values.astype(float) if 'volume' in d1.columns else np.ones(len(d1)))
    adx_v = adx(h1['high'].values, h1['low'].values, hc)
    lots = cfg.get('lot', 0.1)
    cache = {}
    sig = []
    for i in range(60, len(h1)):
        if np.isnan(adx_v[i]) or adx_v[i] < 20:   # 研究: VP 过滤在 ADX>20 才有效
            continue
        d1i = min(i//24, len(dc)-1)
        if d1i not in cache:
            cache[d1i] = _vp_profile(dc, dlo, dhi, dvol, d1i)
        prof = cache[d1i]
        if prof is None:
            continue
        poc, vah, val, lvn, centers = prof
        price = hc[i]
        # 判断 price 落在哪个 bin (用于 LVN 过滤)
        bin_idx = int(np.searchsorted(centers, price, side='right')-1)
        bin_idx = max(0, min(len(centers)-1, bin_idx))
        if bin_idx in lvn:
            continue  # LVN 区: 研究证伪, 单独胜率仅 34%, 跳过
        buf = (vah - val)*0.05 + cfg['pip']
        # 价值区回测 (均值回归): 价格回到 VAL 边缘 → 买向 POC; 回到 VAH → 卖向 POC
        prev = hc[i-1]
        if prev < val and price >= val and abs(price - val) <= buf:
            sl = val - (vah-val)*0.15
            tp = poc
            sig.append({'bar': i, 'side': 1, 'entry': price, 'sl': sl, 'tp': tp,
                        'regime': 'vp_val', 'strat': 'VP', 'lot': lots})
        elif prev > vah and price <= vah and abs(price - vah) <= buf:
            sl = vah + (vah-val)*0.15
            tp = poc
            sig.append({'bar': i, 'side': -1, 'entry': price, 'sl': sl, 'tp': tp,
                        'regime': 'vp_vah', 'strat': 'VP', 'lot': lots})
    return sig


# ════════════════════════════════════════════════════════════════
# 4. Divergence — RSI 常规 + 隐藏背离 (+ MACD 辅助)
# ════════════════════════════════════════════════════════════════
def gen_divergence(h1, h4, d1, cfg) -> list:
    hc = h1['close'].values.astype(float); hh = h1['high'].values.astype(float); hl = h1['low'].values.astype(float)
    r = rsi(hc, 14)
    m, s, hist = macd(hc)
    atr_v = atr(hh, hl, hc)
    swh, swl = find_swing(hh, hl, 5)
    lots = cfg.get('lot', 0.1)
    sig = []
    # 取最近摆动点配对检测背离
    for a, b in zip(swl[:-1], swl[1:]):
        ia, ib = a[0], b[0]
        if ib - ia < 10:
            continue
        # 常规看涨背离: 价格更低低, RSI 更高低
        if b[1] < a[1] - cfg['pip']*2 and r[ib] > r[ia] + 2 and not np.isnan(r[ib]):
            sl = b[1] - atr_v[ib]*0.5
            tp = b[1] + (b[1] - sl)*cfg.get('rr_mult', 1.8)
            sig.append({'bar': ib, 'side': 1, 'entry': hc[ib], 'sl': sl, 'tp': tp,
                        'regime': 'div_bull', 'strat': 'DIV', 'lot': lots})
    for a, b in zip(swh[:-1], swh[1:]):
        ia, ib = a[0], b[0]
        if ib - ia < 10:
            continue
        if b[1] > a[1] + cfg['pip']*2 and r[ib] < r[ia] - 2 and not np.isnan(r[ib]):
            sl = b[1] + atr_v[ib]*0.5
            tp = b[1] - (sl - b[1])*cfg.get('rr_mult', 1.8)
            sig.append({'bar': ib, 'side': -1, 'entry': hc[ib], 'sl': sl, 'tp': tp,
                        'regime': 'div_bear', 'strat': 'DIV', 'lot': lots})
    return sig


# ════════════════════════════════════════════════════════════════
# 5. Mean Reversion — 价格 z-score 偏离均线
# ════════════════════════════════════════════════════════════════
def gen_meanrev(h1, h4, d1, cfg) -> list:
    hc = h1['close'].values.astype(float); hh = h1['high'].values.astype(float); hl = h1['low'].values.astype(float)
    ma = sma(hc, 20); sd = std(hc, 20)
    atr_v = atr(hh, hl, hc)
    lots = cfg.get('lot', 0.1)
    sig = []
    for i in range(40, len(h1)):
        if np.isnan(ma[i]) or np.isnan(sd[i]) or sd[i] <= 0:
            continue
        z = (hc[i] - ma[i]) / sd[i]
        if z <= -2.0:
            sl = hc[i] - atr_v[i]*1.2
            tp = ma[i]
            sig.append({'bar': i, 'side': 1, 'entry': hc[i], 'sl': sl, 'tp': tp,
                        'regime': f'z{z:.1f}', 'strat': 'MR', 'lot': lots})
        elif z >= 2.0:
            sl = hc[i] + atr_v[i]*1.2
            tp = ma[i]
            sig.append({'bar': i, 'side': -1, 'entry': hc[i], 'sl': sl, 'tp': tp,
                        'regime': f'z{z:.1f}', 'strat': 'MR', 'lot': lots})
    return sig


# ════════════════════════════════════════════════════════════════
# 6. TREND — 多周期趋势跟踪 (回踩入场)  [全网研究: 股指/加密/股票/原油
#    比外汇更"持续趋势", 原 5 策略缺纯趋势跟踪, 此为关键补强]
#    参考: road2funded / clearedge / investwhat / piprider (EMA20/50 + ADX>25
#          过滤 + 拉回动态支撑 + ATR 止损)
# ════════════════════════════════════════════════════════════════
def gen_trend(h1, h4, d1, cfg) -> list:
    hc = h1['close'].values.astype(float); hh = h1['high'].values.astype(float); hl = h1['low'].values.astype(float)
    atr_v = atr(hh, hl, hc)
    e20 = ema(hc, 20); e50 = ema(hc, 50)
    h4c = h4['close'].values.astype(float)
    h4e20 = ema(h4c, 20); h4e50 = ema(h4c, 50)
    dc = d1['close'].values.astype(float)
    de9 = ema(dc, 9); de21 = ema(dc, 21)
    adx_v = adx(hh, hl, hc)
    lots = cfg.get('lot', 0.1)
    adx_min = max(20, cfg.get('adx_min', 20))   # 趋势策略需真实趋势强度
    sig = []
    for i in range(80, len(h1)):
        if np.isnan(adx_v[i]) or adx_v[i] < adx_min:
            continue
        h4i = min(i, len(h4c)-1)   # H1索引越界保护(H4数据较短)
        if np.isnan(e20[i]) or np.isnan(e50[i]) or np.isnan(h4e20[h4i]) or np.isnan(h4e50[h4i]):
            continue
        # 更高周期取最新方向(趋势稳定, 不用H1索引错位映射; H1仅用于拉回入场与ADX动能)
        if np.isnan(de9[-1]) or np.isnan(de21[-1]) or np.isnan(h4e20[-1]) or np.isnan(h4e50[-1]):
            continue
        d1_up = de9[-1] > de21[-1]; d1_dn = de9[-1] < de21[-1]
        h4_up = h4e20[-1] > h4e50[-1]; h4_dn = h4e20[-1] < h4e50[-1]
        up = d1_up and h4_up
        dn = d1_dn and h4_dn
        if not (up or dn):
            continue
        price = hc[i]; a = atr_v[i]
        if np.isnan(a) or a <= 0:
            continue
        buf = max(a*0.4, 0.5*cfg['pip'])
        # 中长线: 宽 SL(3×ATR)吃趋势回调 + 大 TP(3.5×风险)吃完整波段; 拉回窗口放宽到 ±2 ATR
        if up:
            if e20[i]-a*2.0 <= price <= e20[i]+buf:
                sl = min(e50[i], price - a*3.0)
                # [2026-08-26 修复] 最小SL距离保护: 价格回调到e50附近时
                # min() 取 e50 导致 SL≈入场价 (8/25 AUDJPY 开仓即止损, 单日
                # 20次循环). 要求 SL 距入场 ≥1.5×ATR, 否则跳过 (回调过深=趋势弱).
                if sl >= price or (price - sl) < a * 1.5:
                    continue
                tp = price + (price-sl)*3.5
                sig.append({'bar': i, 'side': 1, 'entry': price, 'sl': sl, 'tp': tp,
                            'regime': 'trend_pullback', 'strat': 'TREND', 'lot': lots})
        else:
            if e20[i]-buf <= price <= e20[i]+a*2.0:
                sl = max(e50[i], price + a*3.0)
                if sl <= price or (sl - price) < a * 1.5:
                    continue
                tp = price - (sl-price)*3.5
                sig.append({'bar': i, 'side': -1, 'entry': price, 'sl': sl, 'tp': tp,
                            'regime': 'trend_pullback', 'strat': 'TREND', 'lot': lots})
    return sig


# ════════════════════════════════════════════════════════════════
# 7. BO — 唐奇安突破 (区间扩张突破)  [全网研究: 股指/股票开盘区间突破、
#    盘整突破最有效; 需真实区间扩张(atr*1.2)过滤假突破]
#    参考: clearedge (ORB/IB) / npfinancials / investwhat
# ════════════════════════════════════════════════════════════════
def gen_breakout(h1, h4, d1, cfg) -> list:
    hc = h1['close'].values.astype(float); hh = h1['high'].values.astype(float); hl = h1['low'].values.astype(float)
    atr_v = atr(hh, hl, hc)
    adx_v = adx(hh, hl, hc)
    lots = cfg.get('lot', 0.1)
    N = 20
    sig = []
    for i in range(N+5, len(h1)):
        if np.isnan(atr_v[i]) or atr_v[i] <= 0:
            continue
        if adx_v[i] < cfg.get('adx_min', 18):
            continue
        hi = np.max(hh[i-N:i]); lo = np.min(hl[i-N:i])
        if hi - lo < atr_v[i]*1.2:     # 真实区间扩张才视为突破
            continue
        price = hc[i]; prev = hc[i-1]
        if prev <= hi and price > hi:
            sl = lo - atr_v[i]*1.5
            if sl >= price:
                continue
            tp = price + (price-sl)*3.5
            sig.append({'bar': i, 'side': 1, 'entry': price, 'sl': sl, 'tp': tp,
                        'regime': 'donchian_break', 'strat': 'BO', 'lot': lots})
        elif prev >= lo and price < lo:
            sl = hi + atr_v[i]*1.5
            if sl <= price:
                continue
            tp = price - (sl-price)*3.5
            sig.append({'bar': i, 'side': -1, 'entry': price, 'sl': sl, 'tp': tp,
                        'regime': 'donchian_break', 'strat': 'BO', 'lot': lots})
    return sig


# ════════════════════════════════════════════════════════════════
# 8. 策略注册表 + 资产类别策略映射
# ════════════════════════════════════════════════════════════════
# [2026-08-26 P4-1] 时段动量策略 (伦敦开盘方向性偏差, 独立alpha源)
try:
    from session_momentum import gen_session
    _HAS_SESSION = True
except Exception:
    _HAS_SESSION = False

# [2026-08-29 P5] 价格行为+供需深度融合策略 (PA+SD Fusion)
try:
    from pasd_fusion import gen_pasd
    _HAS_PASD = True
except Exception:
    _HAS_PASD = False

# [2026-08-30 P6] 一次一单强趋势突破策略 (One Trade At A Time)
try:
    from otas_strategy import gen_otas
    _HAS_OTAS = True
except Exception:
    _HAS_OTAS = False

STRATEGY_REGISTRY = {
    "SDP": gen_sdp,
    "ICT": gen_ict,
    "VP":  gen_vp,
    "DIV": gen_divergence,
    "MR":  gen_meanrev,
    "TREND": gen_trend,
    "BO":  gen_breakout,
}
if _HAS_SESSION:
    STRATEGY_REGISTRY["SESSION"] = gen_session
if _HAS_PASD:
    STRATEGY_REGISTRY["PASD"] = gen_pasd
if _HAS_OTAS:
    STRATEGY_REGISTRY["OTAS"] = gen_otas
ALL_STRATEGIES = list(STRATEGY_REGISTRY.keys())

# 资产类别 → 策略有序列表 (研究结论: 指数/加密/股票优先趋势, 外汇用全套)
# [2026-08-29 P5] PASD策略加入贵金属/加密货币优先列表 (供需共振+价格行为)
CLASS_STRATEGY_MAP = {
    "forex_major": ["SDP", "ICT", "DIV", "MR", "VP", "TREND", "PASD"],
    "forex_cross": ["SDP", "ICT", "DIV", "MR", "VP", "TREND", "PASD"],
    "jpy_cross":   ["SDP", "ICT", "DIV", "MR", "VP", "TREND", "PASD"],
    "exotic":      ["SDP", "ICT", "MR", "TREND", "PASD"],
    "metal":       ["PASD", "ICT", "SDP", "TREND", "MR", "DIV"],  # PASD优先 (黄金供需区有效)
    "metal_ag":    ["PASD", "ICT", "SDP", "TREND", "MR", "DIV"],  # PASD优先 (白银)
    "metal_pgm":   ["PASD", "ICT", "SDP", "TREND", "MR"],
    "energy":      ["TREND", "SDP", "MR", "PASD"],
    "energy_gas":  ["TREND", "SDP", "MR", "PASD"],
    "crypto":      ["PASD", "TREND", "MR", "SDP", "ICT", "DIV"],  # PASD优先 (加密波动大)
    "crypto_alt":  ["PASD", "TREND", "MR", "SDP", "ICT", "DIV"],
    "crypto_small":["PASD", "TREND", "MR", "SDP", "ICT", "DIV"],
    "index":       ["TREND", "PASD", "SDP", "ICT", "MR", "VP"],
    "index_asia":  ["TREND", "PASD", "SDP", "ICT", "MR", "VP"],
    "stock":       ["TREND", "BO", "MR", "SDP", "PASD"],
    "etf":         ["TREND", "MR", "BO", "PASD"],
    "commodity_soft": ["TREND", "SDP", "MR", "PASD"],
    "commodity_grain":["TREND", "SDP", "MR", "PASD"],
    "bond":        ["TREND", "SDP", "MR", "PASD"],
}


if __name__ == "__main__":
    print("Advanced strategies loaded:", ALL_STRATEGIES)
