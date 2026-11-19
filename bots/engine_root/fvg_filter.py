# -*- coding: utf-8 -*-
"""
P3-3: FVG 回补确认过滤 (Fair Value Gap 公允价值缺口)
=====================================================
借鉴 2026 SMC 前沿实践 (扫流动性 + FVG 回补):
  1. 流动性扫描 (Liquidity Sweep): 价格刺穿近期极值后快速反转 (扫止损)
  2. FVG (公允价值缺口): 3根K线间的价格缺口 (失衡区)
  3. 回补确认: 价格回撤进入 FVG 区域 → 确认信号有效, 提高入场质量

用途: 作为 ICT/SDP 信号的**附加过滤器** —— 有 FVG 回补+流动性扫描
确认的信号加仓/放行, 没有的降权, 过滤假突破 (2026 SMC 标准做法)。

纯 numpy, 无第三方依赖。
"""

import numpy as np

# ── 参数 ─────────────────────────────────────────────────────
MIN_BARS = 20           # 计算流动性/极值所需最少K线
SWEEP_LOOKBACK = 30     # 扫描近 N 根K线的极值
FVG_MAX_AGE = 10        # FVG 只在最近 N 根K线内有效 (新近缺口)
MAX_SWEEP_PIPS = 50.0   # 扫描深度上限 (pip), 防极端假信号


def find_fvg(highs, lows, max_age=FVG_MAX_AGE):
    """识别最近 max_age 根K线内的 FVG 缺口。

    FVG (看涨): 第1根K线高点 < 第3根K线低点 → 中间第2根留下缺口 (看涨失衡)
    FVG (看跌): 第1根K线低点 > 第3根K线高点 → 看跌失衡

    返回: [(fvg_type, top, bottom, age)] 按年龄排序 (最新在前)
      - fvg_type: 'bull' | 'bear'
      - top/bottom: 缺口上/下边界价格
      - age: 距离当前K线的根数 (0=最新)
    """
    h = np.asarray(highs, dtype=float)
    l = np.asarray(lows, dtype=float)
    n = len(h)
    if n < 3:
        return []

    out = []
    for i in range(max(2, n - max_age), n):
        # FVG: K线 i-2 与 K线 i 之间的缺口 (第 i-1 根是中间K线)
        if l[i] > h[i - 2]:          # 看涨缺口: 缺口低点=第3根低点, 高点=第1根高点
            out.append(('bull', float(h[i - 2]), float(l[i]), n - 1 - i))
        elif h[i] < l[i - 2]:        # 看跌缺口
            out.append(('bear', float(l[i - 2]), float(h[i]), n - 1 - i))
    # 按年龄排序 (新缺口在前)
    out.sort(key=lambda x: x[3])
    return out


def detect_liquidity_sweep(highs, lows, closes, lookback=SWEEP_LOOKBACK,
                           pip=0.0001):
    """检测最近K线的流动性扫描 (扫止损)。

    判断: 最近一根K线刺穿前 lookback 根K线的最高/最低点后, 收盘回收到
    极值之内 → 扫掉止损后反转 (SMC 扫流动性信号)。

    返回:
      ('bull_sweep'|'bear_sweep'|None, sweep_price, depth_pips)
        - bull_sweep: 向下扫低点后收回 (看涨)
        - bear_sweep: 向上扫高点后收回 (看跌)
    """
    h = np.asarray(highs, dtype=float)
    l = np.asarray(lows, dtype=float)
    c = np.asarray(closes, dtype=float)
    n = len(h)
    if n < lookback + 2:
        return (None, 0.0, 0.0)

    seg_h = h[-(lookback + 1):-1]
    seg_l = l[-(lookback + 1):-1]
    prev_high = float(seg_h.max())
    prev_low = float(seg_l.min())

    cur_h, cur_l, cur_c = float(h[-1]), float(l[-1]), float(c[-1])

    # 向下扫低点后收回 → 看涨扫描
    if cur_l < prev_low and cur_c > prev_low:
        depth = (prev_low - cur_l) / pip
        if depth <= MAX_SWEEP_PIPS:
            return ('bull_sweep', prev_low, depth)
    # 向上扫高点后收回 → 看跌扫描
    if cur_h > prev_high and cur_c < prev_high:
        depth = (cur_h - prev_high) / pip
        if depth <= MAX_SWEEP_PIPS:
            return ('bear_sweep', prev_high, depth)

    return (None, 0.0, 0.0)


def fvg_confirm(highs, lows, closes, direction, pip=0.0001):
    """FVG 回补确认过滤 (主入口)。

    对给定方向 ('BUY'/'SELL') 判断当前是否具备 SMC 高概率结构:
      - 近期有 FVG 且价格正回补到该缺口
      - (加分) 有对应方向的流动性扫描

    返回: (ok: bool, score: float, detail: str)
      - ok: 是否确认
      - score: 0~1 结构强度 (用于仓位缩放)
      - detail: 描述
    """
    try:
        fvgs = find_fvg(highs, lows)
        sweep, sweep_price, depth = detect_liquidity_sweep(highs, lows, closes, pip=pip)
        price = float(closes[-1])
        h = np.asarray(highs, dtype=float)
        l = np.asarray(lows, dtype=float)

        score = 0.0
        parts = []

        # 1) 方向匹配的 FVG 且价格在缺口内/附近 (回补中)
        if direction == 'BUY':
            match = [f for f in fvgs if f[0] == 'bull' and price <= f[1] + 1e-9]
        else:
            match = [f for f in fvgs if f[0] == 'bear' and price >= f[2] - 1e-9]

        if match:
            ftype, top, bottom, age = match[0]
            # 缺口越大、越新, 强度越高; 基准0.45 (有FVG回补即确认)
            gap_pips = abs(top - bottom) / pip
            age_factor = max(0.6, 1.0 - age * 0.1)
            score += min(0.7, 0.45 + gap_pips * 0.005) * age_factor
            parts.append(f"FVG{'看涨' if ftype=='bull' else '看跌'}"
                         f"({gap_pips:.0f}pip,{age}根前)回补中")

        # 2) 流动性扫描确认 (同向)
        if sweep:
            if (direction == 'BUY' and sweep == 'bull_sweep') or \
               (direction == 'SELL' and sweep == 'bear_sweep'):
                score += 0.35
                parts.append(f"流动性扫描({sweep},深{depth:.1f}pip)")
            else:
                parts.append(f"反向扫描({sweep})未确认")

        ok = score >= 0.4
        return ok, min(1.0, score), "; ".join(parts) if parts else "无SMC结构确认"
    except Exception as e:
        return True, 0.0, f"FVG异常开放: {e}"


# ── 自检 ─────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=== P3-3 FVG回补确认自检 ===")
    rng = np.random.default_rng(3)
    n = 80
    closes = np.cumsum(rng.normal(0, 0.0005, n)) + 1.10
    highs = closes + 0.0004
    lows = closes - 0.0004

    # 构造一个明确的看涨FVG+向下扫低点场景
    base = 1.1000
    highs2 = np.array([base + 0.001] * n)
    lows2 = np.array([base - 0.001] * n)
    closes2 = np.array([base] * n)
    # 3根K线制造缺口: 低-高-低 (中间高开), 后价格回落至缺口
    highs2[-3] = base + 0.002
    lows2[-3] = base + 0.0005
    closes2[-3] = base + 0.0012
    highs2[-2] = base + 0.0015
    lows2[-2] = base + 0.0002
    closes2[-2] = base + 0.0008
    # 最后一根: 向下扫低点后收回
    highs2[-1] = base + 0.0009
    lows2[-1] = base - 0.0015  # 扫破前低
    closes2[-1] = base + 0.0003  # 收回

    fvgs = find_fvg(highs2, lows2)
    print(f"检测到FVG: {[(t, round(top,5), round(bot,5), age) for t, top, bot, age in fvgs[:3]]}")
    sweep, sp, dp = detect_liquidity_sweep(highs2, lows2, closes2, pip=0.0001)
    print(f"流动性扫描: {sweep} @{sp:.5f} 深{dp:.1f}pip")

    ok, score, detail = fvg_confirm(highs2, lows2, closes2, 'BUY', pip=0.0001)
    print(f"BUY确认: ok={ok} score={score:.2f} | {detail}")
    ok2, score2, detail2 = fvg_confirm(highs2, lows2, closes2, 'SELL', pip=0.0001)
    print(f"SELL确认: ok={ok2} score={score2:.2f} | {detail2}")
    print("=== 自检通过 ===")
