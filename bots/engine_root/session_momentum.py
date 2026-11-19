# -*- coding: utf-8 -*-
"""
P4-1: 时段动量策略 (Session Momentum)
======================================
基于 2026-08-26 研究发现的**时段方向性偏差** (服务器时区 = GMT+3):

  USDJPY 服务器h8 (伦敦开盘): 30d跌93% / 180d跌84%  → 做空
  EURUSD 服务器h9 (伦敦开盘): 30d涨77% / 180d涨64%  → 做多
  GBPUSD 服务器h8 (伦敦开盘): 30d跌83% / 180d跌79%  → 做空

核心逻辑:
  1. 服务器时间到达目标时段 (h8/h9 = 伦敦开盘) 且 H1 bar 为整点边界
  2. 价格未过度偏离 (过滤追高杀跌): 用 EMA21 偏离度过滤
  3. 顺时段方向开仓, SL = 1.5×ATR, TP = 2.0×风险
  4. 只在偏差>70%的稳定时段开仓 (不硬开)

独立于现有7策略 (SDP/ICT/VP/DIV/MR/TREND/BO), 提供新的 alpha 源。
时段偏差是多年统计行为 (伦敦开盘流动性涌入的方向性), 相对稳定。

纯 numpy, 无第三方依赖。
"""

import datetime
import numpy as np

# ── 时段策略配置: symbol -> (目标小时, 方向, 最小胜率, 最大偏离σ) ──
# 服务器时区 (TradeMaxGlobal = GMT+3). 仅收录 180天窗口胜率 ≥ 70% 的稳定组合.
SESSION_STRATEGY_MAP = {
    "USDJPY": {"hour": 8, "direction": "SELL", "min_wr": 0.70, "max_dev": 2.5},
    "GBPUSD": {"hour": 8, "direction": "SELL", "min_wr": 0.70, "max_dev": 2.5},
    "EURUSD": {"hour": 9, "direction": "BUY",  "min_wr": 0.70, "max_dev": 2.5},
}

FRESH_BARS_SESSION = 2   # 信号新鲜度: 当前bar/上一bar内
SL_ATR_MULT = 1.5        # SL = 1.5×ATR
TP_RR = 2.0              # TP = 2×风险


def _ema(arr, p=21):
    a = np.asarray(arr, dtype=float)
    if len(a) == 0:
        return np.array([])
    e = np.full(len(a), np.nan)
    k = 2.0 / (p + 1)
    e[0] = a[0]
    for i in range(1, len(a)):
        e[i] = a[i] * k + e[i - 1] * (1 - k)
    return e


def gen_session(h1, h4, d1, cfg):
    """时段动量信号生成器 (与 advanced_strategies 注册表兼容).

    h1: DataFrame(open/high/low/close/time); time 为服务器时间戳.
    返回: [{bar, side, entry, sl, tp, regime, strat}] 或 []
    """
    if h1 is None or len(h1) < 30:
        return []
    sym = str(cfg.get("name", ""))
    scfg = SESSION_STRATEGY_MAP.get(sym)
    if scfg is None:
        return []

    closes = h1['close'].values.astype(float)
    highs = h1['high'].values.astype(float)
    lows = h1['low'].values.astype(float)
    times = h1['time'].values

    n = len(closes)
    if n < 30:
        return []

    # 服务器小时 (时间戳转本地datetime → hour; 服务器=GMT+3 由broker设置,
    # 时间戳已含时区, 直接取 hour 即服务器小时)
    try:
        cur_hour = datetime.datetime.fromtimestamp(float(times[-1])).hour
    except Exception:
        return []

    # 目标时段检查: 当前bar 或 上一bar 处于目标小时 (h8 覆盖 8:00-8:59 bar)
    target = scfg["hour"]
    is_target = (cur_hour == target)
    if not is_target:
        # 允许上一bar在目标时段 (刚过整点)
        try:
            prev_hour = datetime.datetime.fromtimestamp(float(times[-2])).hour
            if prev_hour == target:
                is_target = True
        except Exception:
            pass
    if not is_target:
        return []

    direction = scfg["direction"]

    # ATR
    tr = np.zeros(n)
    tr[1:] = np.maximum(highs[1:] - lows[1:],
                        np.maximum(np.abs(highs[1:] - closes[:-1]),
                                   np.abs(lows[1:] - closes[:-1])))
    atr_v = np.full(n, np.nan)
    if n > 14:
        atr_v[14] = np.mean(tr[1:15])
        for i in range(15, n):
            atr_v[i] = tr[i] / 14 + atr_v[i - 1] * (13 / 14)
    atr_now = float(np.nan_to_num(atr_v[-1], nan=np.mean(tr[1:]))) if n > 15 else 0.0
    if atr_now <= 0:
        return []

    pip = float(cfg.get("pip", 0.0001) or 0.0001)
    price = float(closes[-1])

    # EMA21 偏离过滤 (防追高杀跌): |price-ema21| <= max_dev×ATR
    ema21 = _ema(closes, 21)
    if len(ema21) > 0 and not np.isnan(ema21[-1]):
        dev = abs(price - ema21[-1]) / (atr_now + 1e-12)
        if dev > scfg["max_dev"]:
            return []  # 过度偏离, 不追

    # 信号
    if direction == "BUY":
        side = 1
        sl = price - SL_ATR_MULT * atr_now
        tp = price + TP_RR * (price - sl)
    else:
        side = -1
        sl = price + SL_ATR_MULT * atr_now
        tp = price - TP_RR * (sl - price)

    sig = {
        "bar": n - 1,
        "side": side,
        "entry": price,
        "sl": float(sl),
        "tp": float(tp),
        "regime": f"session_h{target}",
        "strat": "SESSION",
        "lot": float(cfg.get("lot", 0.1)),
    }
    return [sig]


# ── 自检 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== P4-1 时段动量自检 ===")
    import pandas as pd
    # 构造模拟数据
    rng = np.random.default_rng(1)
    n = 100
    base = 150.0
    closes = np.cumsum(rng.normal(0, 0.001, n)) + base
    highs = closes + 0.002
    lows = closes - 0.002
    # 当前时间设为目标小时 (h8)
    now = datetime.datetime(2026, 8, 26, 8, 30)
    times = [now.timestamp() - (n - i) * 3600 for i in range(n)]
    df = pd.DataFrame({"open": closes, "high": highs, "low": lows,
                       "close": closes, "time": times})
    cfg = {"name": "USDJPY", "pip": 0.01, "lot": 0.1}
    sigs = gen_session(df, None, None, cfg)
    print(f"USDJPY h8 信号: {sigs}")
    assert len(sigs) == 1 and sigs[0]["side"] == -1, "应产出做空信号"
    print(f"  SL={sigs[0]['sl']:.3f} TP={sigs[0]['tp']:.3f} (做空: TP<entry<SL)")
    # 非目标时段应无信号
    now2 = datetime.datetime(2026, 8, 26, 14, 0)
    times2 = [now2.timestamp() - (n - i) * 3600 for i in range(n)]
    df2 = pd.DataFrame({"open": closes, "high": highs, "low": lows,
                        "close": closes, "time": times2})
    sigs2 = gen_session(df2, None, None, cfg)
    print(f"USDJPY h14 信号(应空): {sigs2}")
    assert len(sigs2) == 0, "非目标时段不应有信号"
    print("=== 自检通过 ===")
