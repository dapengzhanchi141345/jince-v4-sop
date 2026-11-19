# -*- coding: utf-8 -*-
"""
VP V4.0 — 成交量Profile策略机构级升级
========================================
对标 Volume Profile量化研究标准

升级特性:
1. H1成交量数据接入
2. POC磁吸逻辑增强
3. LVN Zone Filtering
4. Value Area Rotation
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional


# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════
VP_BINS = 50
VP_VALUE_AREA = 0.70  # 价值区70%
VP_LVN_THRESHOLD = 0.15  # LVN阈值 (15% of max volume)
ADX_MIN = 20  # VP策略需要ADX>20才有效


# ═══════════════════════════════════════════════════════════════
# 基础指标
# ═══════════════════════════════════════════════════════════════

def _adx(h, l, c, p=14):
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


# ═══════════════════════════════════════════════════════════════
# V4.0 Volume Profile计算
# ═══════════════════════════════════════════════════════════════

def _compute_vp_profile(closes, highs, lows, volumes, end_idx, window=20, bins=VP_BINS):
    """计算成交量Profile"""
    lo = max(0, end_idx - window + 1)
    seg_closes = closes[lo:end_idx+1]
    seg_highs = highs[lo:end_idx+1]
    seg_lows = lows[lo:end_idx+1]
    seg_vols = volumes[lo:end_idx+1]

    if len(seg_closes) < 5:
        return None

    pmin = np.min(seg_lows)
    pmax = np.max(seg_highs)
    if pmax <= pmin:
        return None

    edges = np.linspace(pmin, pmax, bins+1)
    centers = (edges[:-1] + edges[1:])/2

    vol_bin = np.zeros(bins)
    for k in range(len(seg_closes)):
        b0 = np.searchsorted(edges, seg_lows[k], side='right')-1
        b1 = np.searchsorted(edges, seg_highs[k], side='left')
        b0 = max(0, min(bins-1, b0))
        b1 = max(0, min(bins-1, b1))
        if b1 < b0:
            b1 = b0
        n = b1 - b0 + 1
        vol_bin[b0:b1+1] += seg_vols[k] / n

    if vol_bin.sum() <= 0:
        return None

    # POC
    poc_idx = np.argmax(vol_bin)
    poc_price = centers[poc_idx]

    # 价值区 (70%)
    cum = vol_bin[poc_idx]
    lo_i, hi_i = poc_idx, poc_idx
    while cum < VP_VALUE_AREA * vol_bin.sum() and (lo_i > 0 or hi_i < bins-1):
        down = vol_bin[lo_i-1] if lo_i > 0 else -1
        up = vol_bin[hi_i+1] if hi_i < bins-1 else -1
        if up >= down and hi_i < bins-1:
            hi_i += 1; cum += vol_bin[hi_i]
        elif lo_i > 0:
            lo_i -= 1; cum += vol_bin[lo_i]
        else:
            break

    vah = edges[hi_i+1]
    val = edges[lo_i]

    # LVN区域
    max_vol = vol_bin[poc_idx]
    lvn_mask = vol_bin < VP_LVN_THRESHOLD * max_vol
    lvn_set = set(np.where(lvn_mask)[0].tolist())

    return {
        'poc': poc_price,
        'vah': vah,
        'val': val,
        'lvn': lvn_set,
        'centers': centers,
        'edges': edges,
        'volume': vol_bin
    }


# ═══════════════════════════════════════════════════════════════
# V4.0 主策略
# ═══════════════════════════════════════════════════════════════

def gen_vp_v4(h1, h4, d1, cfg) -> List[Dict]:
    """
    VP V4.0 — 机构级成交量Profile策略

    核心升级:
    1. H1成交量数据
    2. POC磁吸增强
    3. LVN Zone Filtering
    """
    hc = h1['close'].values.astype(float)
    hh = h1['high'].values.astype(float)
    hl = h1['low'].values.astype(float)

    # 成交量数据
    if 'tick_volume' in h1.columns:
        hvol = h1['tick_volume'].values.astype(float)
    elif 'volume' in h1.columns:
        hvol = h1['volume'].values.astype(float)
    else:
        hvol = np.ones(len(hc))  # 无成交量数据时默认

    adx_v = _adx(hh, hl, hc)
    lots = cfg.get('lot', 0.1)
    pip = float(cfg.get('pip', 0.0001))

    cache = {}
    sig = []

    for i in range(60, len(h1)):
        # ADX过滤
        if np.isnan(adx_v[i]) or adx_v[i] < ADX_MIN:
            continue

        # 计算Profile
        if i not in cache:
            cache[i] = _compute_vp_profile(hc, hh, hl, hvol, i)
        prof = cache[i]

        if prof is None:
            continue

        price = hc[i]
        if np.isnan(price) or price <= 0:
            continue

        poc = prof['poc']
        vah = prof['vah']
        val = prof['val']
        lvn = prof['lvn']
        centers = prof['centers']

        # 确定价格所在bin
        bin_idx = int(np.searchsorted(centers, price, side='right')-1)
        bin_idx = max(0, min(len(centers)-1, bin_idx))

        # LVN过滤
        if bin_idx in lvn:
            continue

        # 价值区边界缓冲
        buf = (vah - val) * 0.05 + pip

        prev = hc[i-1] if i > 0 else price

        # 价值区回测信号
        # 买入: 价格回到VAL边缘
        if prev < val and price >= val and abs(price - val) <= buf:
            sl = val - (vah - val) * 0.15
            tp = poc  # 目标POC
            if sl < price:
                sig.append({
                    'bar': i, 'side': 1, 'entry': price, 'sl': sl, 'tp': tp,
                    'regime': 'vp_val_retest', 'strat': 'VP', 'lot': lots,
                    'poc': poc, 'vah': vah, 'val': val,
                    'distance_to_poc': abs(price - poc) / price
                })

        # 卖出: 价格回到VAH边缘
        elif prev > vah and price <= vah and abs(price - vah) <= buf:
            sl = vah + (vah - val) * 0.15
            tp = poc
            if sl > price:
                sig.append({
                    'bar': i, 'side': -1, 'entry': price, 'sl': sl, 'tp': tp,
                    'regime': 'vp_vah_retest', 'strat': 'VP', 'lot': lots,
                    'poc': poc, 'vah': vah, 'val': val,
                    'distance_to_poc': abs(price - poc) / price
                })

        # POC磁吸: 价格远离POC时向POC回归
        elif abs(price - poc) / poc > 0.02:  # 偏离>2%
            if price < poc:
                # 低于POC，买入向POC回归
                sl = price - (poc - price) * 0.5
                tp = poc
                if sl < price:
                    sig.append({
                        'bar': i, 'side': 1, 'entry': price, 'sl': sl, 'tp': tp,
                        'regime': 'vp_poc_magnet', 'strat': 'VP', 'lot': lots,
                        'poc': poc, 'direction': 'below'
                    })
            else:
                # 高于POC，卖出向POC回归
                sl = price + (price - poc) * 0.5
                tp = poc
                if sl > price:
                    sig.append({
                        'bar': i, 'side': -1, 'entry': price, 'sl': sl, 'tp': tp,
                        'regime': 'vp_poc_magnet', 'strat': 'VP', 'lot': lots,
                        'poc': poc, 'direction': 'above'
                    })

    return sig


if __name__ == "__main__":
    print("=" * 70)
    print("VP V4.0 自检")
    print("=" * 70)

    np.random.seed(42)
    n = 500
    closes = [100.0]
    for i in range(1, n):
        trend = 0.005 * np.sin(i * 0.01)
        noise = np.random.randn() * 0.3
        closes.append(closes[-1] * (1 + trend + noise * 0.01))
    closes = np.array(closes)
    opens = closes + np.random.randn(n) * 0.05
    highs = np.maximum(closes, opens) + np.abs(np.random.randn(n)) * 0.2
    lows = np.minimum(closes, opens) - np.abs(np.random.randn(n)) * 0.2
    times = np.arange(n) * 3600
    volumes = np.random.randint(1000, 10000, n).astype(float)

    h1 = pd.DataFrame({
        'open': opens, 'high': highs, 'low': lows,
        'close': closes, 'time': times, 'tick_volume': volumes
    })
    h4 = pd.DataFrame({'open': opens[::4], 'high': highs[::4], 'low': lows[::4], 'close': closes[::4], 'time': times[::4]})
    d1 = pd.DataFrame({'open': opens[::20], 'high': highs[::20], 'low': lows[::20], 'close': closes[::20], 'time': times[::20]})

    cfg = {'pip': 0.01, 'lot': 0.1}

    sigs = gen_vp_v4(h1, h4, d1, cfg)
    print(f"\n生成信号: {len(sigs)} 个")
    if sigs:
        buys = [s for s in sigs if s['side'] == 1]
        sells = [s for s in sigs if s['side'] == -1]
        print(f"  买入: {len(buys)}, 卖出: {len(sells)}")
        regimes = {}
        for s in sigs:
            r = s['regime']
            regimes[r] = regimes.get(r, 0) + 1
        print(f"  市况分布: {regimes}")

    print("\n" + "=" * 70)
    print("✅ VP V4.0 自检完成")
    print("=" * 70)
