# -*- coding: utf-8 -*-
"""
apex_strategy_v5.py — Godking Apex Short (V5 落地版)
====================================================
来源: 只读观测朋友 MT5 账户 60129252 的 EA「Godking Apex Short v4.2」
      (见 docs/FRIEND_GODKING_APEX_LEARNING.md)，把其可观测机制迁移为
      GoldstrategyEngine 的标准策略模块。

朋友策略的 5 个硬事实 (我们严格复刻):
  1. 品种单一 -> 默认 XAUUSD(黄金)，但逻辑对空头波段品种通用。
  2. 方向单一偏空 -> Apex SHORT，只做空。
  3. Scale-in 分批建仓 -> 同一供给区最多 5 笔、间隔 >=3 根 H1。
  4. 无止盈 (TP=0) -> 吃趋势、靠追踪/反转退出 (回测用自定义退出模拟)。
  5. 共享硬止损 = 结构失效位(前高/摆动高点) -> 逻辑破产才离场。

进场逻辑 (Apex):
  - 用 H4 判定市场结构: 找「major high」(失效位) 与「local lower-high 供给区」。
  - 只在偏空上下文(价格低于 H4 长均线 或 摆动结构为 lower-high)才做空。
  - H1 上价格回抽进入供给区并形成拒绝线(上影/阴线)时，发出空头信号。
  - 同一供给区允许多笔 scale-in，摊薄择时误差。

信号契约: sig = {bar, side(-1), entry, sl, tp, strat}  (与 advanced_strategies 兼容)
  - entry: 供给区上沿附近(参考价)；回测实际取信号下一根 H1 开盘 - 点差。
  - sl:    结构失效位 (major high + buffer)。
  - tp:    0.0 (无固定止盈，趋势退出由 backtest_apex_v5 模拟)。
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional


# ═══════════════════════════════════════════════════════════════
# 配置 (可由 cfg 覆盖)
# ═══════════════════════════════════════════════════════════════
DEFAULT_CFG = {
    "apex_symbol": "XAUUSD",          # 聚焦品种
    "short_only": True,                # Apex Short
    "h4_struct_lookback": 240,         # H4 结构回溯(约 40 交易日)
    "zone_height_pts": 220,           # 供给区高度(价格点)，朋友回抽区 ~4430-4460 一带
    "zone_bottom_buffer": 30,         # 供给区下沿缓冲
    "invalidation_buffer": 60,        # 失效位缓冲(major high 上方)
    "max_scale_in": 5,                 # 单区最大分批笔数(对齐朋友 5 笔)
    "scale_in_gap_bars": 3,           # 相邻 signal 最小 H1 间隔
    "reject_wick_ratio": 0.45,        # 上影/实体 最小比(拒绝线判定)
    "trend_ema_fast": 20,
    "trend_ema_slow": 50,
    "min_bars": 60,                    # 最少 H1 数据
}


# ═══════════════════════════════════════════════════════════════
# 基础指标
# ═══════════════════════════════════════════════════════════════
def _ema(v, p):
    v = np.asarray(v, float)
    if len(v) < p:
        return np.full(len(v), np.nan)
    r = np.full(len(v), np.nan)
    r[p - 1] = np.mean(v[:p])
    a = 2 / (p + 1)
    for i in range(p, len(v)):
        r[i] = v[i] * a + r[i - 1] * (1 - a)
    return r


def _atr(h, l, c, p=14):
    h, l, c = np.asarray(h, float), np.asarray(l, float), np.asarray(c, float)
    if len(h) < p + 1:
        return np.full(len(h), np.nan)
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    r = np.full(len(h), np.nan)
    r[p] = np.mean(tr[:p])
    a = 1 / p
    for i in range(p + 1, len(h)):
        r[i] = tr[i - 1] * a + r[i - 1] * (1 - a)
    return pd.Series(r).ffill().fillna(np.nanmean(tr[:p])).values


def _swing_highs(h, l, lb=3):
    """返回 [(idx, price)] 摆动高点。"""
    h = np.asarray(h, float)
    swh = []
    for i in range(lb, len(h) - lb):
        if h[i] == max(h[i - lb:i + lb + 1]) and h[i] >= max(h[max(0, i - lb - 6):i]):
            swh.append((i, h[i]))
    return swh


def _swing_lows(h, l, lb=3):
    l = np.asarray(l, float)
    swl = []
    for i in range(lb, len(l) - lb):
        if l[i] == min(l[i - lb:i + lb + 1]) and l[i] <= min(l[max(0, i - lb - 6):i]):
            swl.append((i, l[i]))
    return swl


# ═══════════════════════════════════════════════════════════════
# 核心: 从 H4 抽取「失效位」与「当前供给区」
# ═══════════════════════════════════════════════════════════════
def _derive_structure(h4, cfg):
    """
    返回 dict (双向):
      invalidation   : 偏空失效位(major high + buffer)
      zone_top/bottom: 当前局部供给区(做空进场区)
      bearish_ctx    : bool, 偏空上下文
      demand_top/bottom: 当前局部需求区(做多进场区)
      bullish_ctx    : bool, 偏多上下文
      major_high/major_low: 结构极值
    """
    hi = h4['high'].values.astype(float)
    lo = h4['low'].values.astype(float)
    cl = h4['close'].values.astype(float)
    n = len(hi)
    if n < 30:
        return None

    lb = int(cfg.get("h4_struct_lookback", 240))
    lb = min(lb, n - 5)
    win_hi = hi[-lb:]
    win_lo = lo[-lb:]

    # major high / low = 窗口内极值摆动点 (失效位基准)
    swh = _swing_highs(win_hi, win_lo, lb=2)
    swl = _swing_lows(win_hi, win_lo, lb=2)
    major_high = max([p for _, p in swh]) if swh else np.max(win_hi)
    major_low = min([p for _, p in swl]) if swl else np.min(win_lo)
    inv_buf = float(cfg.get("invalidation_buffer", 60))
    invalidation = major_high + inv_buf                 # 空头失效位
    invalidation_low = major_low - inv_buf              # 多头失效位

    zone_height = float(cfg.get("zone_height_pts", 220))
    zbuf = float(cfg.get("zone_bottom_buffer", 30))

    # 局部 lower-high 供给区 (做空)
    recent_swh = [p for i, p in swh if i >= len(win_hi) - 40]
    if not recent_swh:
        recent_swh = [major_high]
    local_high = sorted(recent_swh)[-2] if len(recent_swh) >= 2 else recent_swh[-1]
    zone_top = local_high
    zone_bottom = local_high - zone_height - zbuf

    # 局部 higher-low 需求区 (做多, 镜像)
    recent_swln = [p for i, p in swl if i >= len(win_lo) - 40]
    if not recent_swln:
        recent_swln = [major_low]
    local_low = sorted(recent_swln)[0] if len(recent_swln) >= 2 else recent_swln[-1]
    demand_bottom = local_low
    demand_top = local_low + zone_height + zbuf

    # 上下文
    ema_slow = _ema(cl, int(cfg.get("trend_ema_slow", 50)))
    ema_fast = _ema(cl, int(cfg.get("trend_ema_fast", 20)))
    last_close = cl[-1]
    below_ema = (not np.isnan(ema_slow[-1])) and (last_close < ema_slow[-1])
    above_ema = (not np.isnan(ema_slow[-1])) and (last_close > ema_slow[-1])
    all_swh = _swing_highs(hi, lo, lb=3)
    all_swln = _swing_lows(hi, lo, lb=3)
    lower_high = False
    if len(all_swh) >= 2:
        s2 = [p for _, p in all_swh[-2:]]
        lower_high = s2[-1] < s2[-2]
    higher_low = False
    if len(all_swln) >= 2:
        s2 = [p for _, p in all_swln[-2:]]
        higher_low = s2[-1] > s2[-2]
    bearish_ctx = bool(below_ema or lower_high)
    bullish_ctx = bool(above_ema or higher_low)

    return {
        "invalidation": invalidation,
        "invalidation_low": invalidation_low,
        "zone_top": zone_top,
        "zone_bottom": zone_bottom,
        "demand_top": demand_top,
        "demand_bottom": demand_bottom,
        "bearish_ctx": bearish_ctx,
        "bullish_ctx": bullish_ctx,
        "major_high": major_high,
        "major_low": major_low,
        "local_high": local_high,
        "local_low": local_low,
    }


# ═══════════════════════════════════════════════════════════════
# H1 进场判定
# ═══════════════════════════════════════════════════════════════
def _is_rejection_bar(h1_row, cfg):
    """H1 出现上影拒绝线(做空): 上影 >= 实体*ratio 且收阴。"""
    o, h, l, c = h1_row['open'], h1_row['high'], h1_row['low'], h1_row['close']
    body = abs(c - o)
    upper = h - max(o, c)
    rng = (h - l)
    if rng <= 0:
        return False
    ratio = float(cfg.get("reject_wick_ratio", 0.45))
    return (upper >= ratio * body) and (c <= o) and (upper >= 0.35 * rng)


def _is_bullish_rejection_bar(h1_row, cfg):
    """H1 出现下影拒绝线(做多): 下影 >= 实体*ratio 且收阳。"""
    o, h, l, c = h1_row['open'], h1_row['high'], h1_row['low'], h1_row['close']
    body = abs(c - o)
    lower = min(o, c) - l
    rng = (h - l)
    if rng <= 0:
        return False
    ratio = float(cfg.get("reject_wick_ratio", 0.45))
    return (lower >= ratio * body) and (c >= o) and (lower >= 0.35 * rng)


def _emit_side(h1, struct, side, cfg, symbol):
    """
    单方向信号生成 (side=-1 空 / +1 多)。
    空头: 回抽供给区(zone_top/zone_bottom) + 上影拒绝 -> sl=invalidation
    多头: 回踩需求区(demand_top/demand_bottom) + 下影拒绝 -> sl=invalidation_low
    """
    if side < 0:
        zt = struct["zone_top"]; zb = struct["zone_bottom"]; inv = struct["invalidation"]
        in_zone = lambda i, hi, lo, cl: (hi[i] >= zb) and (hi[i] <= zt + 40) and (cl[i] <= zt)
        reject = _is_rejection_bar
        entry_ref = lambda i, hi: min(hi[i], zt)
        broke = lambda cl_i: cl_i >= inv
    else:
        zt = struct["demand_top"]; zb = struct["demand_bottom"]; inv = struct["invalidation_low"]
        in_zone = lambda i, hi, lo, cl: (lo[i] <= zt) and (lo[i] >= zb - 40) and (cl[i] >= zb)
        reject = _is_bullish_rejection_bar
        entry_ref = lambda i, lo: max(lo[i], zb)
        broke = lambda cl_i: cl_i <= inv

    max_scale = int(cfg.get("max_scale_in", 5))
    gap = int(cfg.get("scale_in_gap_bars", 3))
    scale_state = {}
    signals = []
    o = h1['open'].values.astype(float)
    hi = h1['high'].values.astype(float)
    lo = h1['low'].values.astype(float)
    cl = h1['close'].values.astype(float)
    n = len(hi)
    for i in range(n - 1):
        if not in_zone(i, hi, lo, cl):
            continue
        row = {'open': o[i], 'high': hi[i], 'low': lo[i], 'close': cl[i]}
        if not reject(row, cfg):
            continue
        if broke(cl[i]):
            continue
        zkey = (side, round(zt / 10.0))
        zs = scale_state.setdefault(zkey, {'count': 0, 'last': -999})
        if zs['count'] >= max_scale:
            continue
        if (i - zs['last']) < gap:
            continue
        er = entry_ref(i, hi) if side < 0 else entry_ref(i, lo)
        signals.append({
            "bar": int(i),
            "side": int(side),
            "entry": float(er),
            "sl": float(inv),
            "tp": 0.0,
            "strat": "APEX",
            "symbol": symbol,
            "meta": {
                "invalidation": float(inv),
                "zone_top": float(zt),
                "zone_bottom": float(zb),
                "major_high": float(struct["major_high"]),
                "major_low": float(struct["major_low"]),
                "side": int(side),
                "scale_idx": zs['count'] + 1,
            },
        })
        zs['count'] += 1
        zs['last'] = i
    return signals


def gen_apex(h1, h4, d1, cfg=None, symbol="XAUUSD"):
    """
    Apex V5 信号生成器。
    参数:
        h1/h4/d1: DataFrame(time,open,high,low,close,volume,spread) 已按时间升序
        cfg: 覆盖配置。bidirectional=True 时镜像做多(跌段做空/涨段做多)。
        symbol: 品种(聚焦 XAUUSD)
    返回: 信号列表, 每条 {bar, side(+1/-1), entry, sl, tp, strat}
    """
    if cfg is None:
        cfg = dict(DEFAULT_CFG)
    else:
        merged = dict(DEFAULT_CFG)
        merged.update(cfg)
        cfg = merged

    try:
        if h1 is None or len(h1) < int(cfg.get("min_bars", 60)) or h4 is None or len(h4) < 30:
            return []
        if d1 is not None and len(d1) < 10:
            d1 = None
    except Exception:
        return []

    # 聚焦品种保护: 非 XAUUSD 时跳过(先严守朋友原策略)
    if symbol and cfg.get("apex_symbol") and symbol != cfg.get("apex_symbol"):
        return []

    struct = _derive_structure(h4, cfg)
    if struct is None:
        return []

    bidir = bool(cfg.get("bidirectional", False))
    signals = []
    # 空头分支 (朋友原策略: Apex Short)
    if struct["bearish_ctx"]:
        signals += _emit_side(h1, struct, -1, cfg, symbol)
    # 多头分支 (仅双向模式: Apex Long, 镜像)
    if bidir and struct["bullish_ctx"]:
        signals += _emit_side(h1, struct, +1, cfg, symbol)
    return signals


# ═══════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("[APEX V5] module loaded. gen_apex(h1,h4,d1,cfg) ready.")
    print("Defaults:", DEFAULT_CFG)
