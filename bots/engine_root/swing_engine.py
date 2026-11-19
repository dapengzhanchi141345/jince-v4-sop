"""
swing_engine.py — 独立波段策略引擎 (裸K + 供需原理 / Supply-Demand + Price Action)
=====================================================================================
设计原则 (Sam Seiden LRTB + 裸K确认, 与主 trader 完全独立):
  1. 结构:  5-bar pivot swing high/low → 市场结构
  2. 供需区: 反向 displacement 前的最后 consolidation (base) 即供需区
            Demand zone = 价格从 base 向上 displacement 离开
            Supply zone = 价格从 base 向下 displacement 离开
  3. 入场:  趋势方向回调至 zone (趋势 EMA 过滤) + 裸K反转确认 (吞没/锤子/内包突破)
  4. 止损:  zone 外沿 - buffer×ATR (严格结构止损)
  5. 止盈/管理: TP=对侧 swing, 移动 BE → 吊灯追踪 → 结构衰竭平仓 (让利润奔跑)
  6. 仓位:  单笔固定风险 % × equity / SL 距离 (动态手数)
  7. 进化:  Walk-Forward 随机搜索 (交易层参数), R-multiple 制衡量, OOS 验证

R-multiple 制: 每笔记录净 R (盈亏/初始风险), 组合质量由 expectancy/PF/maxDD 刻画.
本模块无 MT5 下单, 只做分析与回测 — 供 swing_bot.py 实盘调用.
"""

import json
import os
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

# ════════════════════════════════════════════════════════════════════
# 指标 (纯 numpy)
# ════════════════════════════════════════════════════════════════════

def atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder ATR"""
    n = len(c)
    out = np.zeros(n)
    if n < period + 1:
        return out
    tr = np.zeros(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    out[period - 1] = tr[1:period + 1].mean()
    for i in range(period, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def ema(x: np.ndarray, span: int) -> np.ndarray:
    """EMA (pandas-free)"""
    n = len(x)
    out = np.zeros(n)
    if n == 0:
        return out
    out[0] = x[0]
    alpha = 2.0 / (span + 1)
    for i in range(1, n):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


def find_pivots(h: np.ndarray, l: np.ndarray, k: int = 5) -> Tuple[np.ndarray, np.ndarray]:
    """返回 pivot high/low 索引数组 (5-bar 分形)"""
    n = len(h)
    ph, pl = [], []
    for i in range(k, n - k):
        if h[i] == max(h[i - k:i + k + 1]):
            ph.append(i)
        if l[i] == min(l[i - k:i + k + 1]):
            pl.append(i)
    return np.array(ph, dtype=np.int64), np.array(pl, dtype=np.int64)


# ════════════════════════════════════════════════════════════════════
# 供需区检测
# ════════════════════════════════════════════════════════════════════

class Zone:
    __slots__ = ("top", "bottom", "ztype", "born", "touch", "disp_i", "width", "disp_range")

    def __init__(self, top, bottom, ztype, born, disp_i, disp_range):
        self.top = top
        self.bottom = bottom
        self.ztype = ztype          # 'D' demand / 'S' supply
        self.born = born            # 形成 bar idx
        self.touch = 0
        self.disp_i = disp_i        # displacement bar idx
        self.width = top - bottom
        self.disp_range = disp_range


def scan_zones(o, h, l, c, a, cfg: dict) -> List[Zone]:
    """
    扫描全部供需区. cfg: pivot_k, cons_min, cons_max, disp_atr, zone_max_atr
    Demand : 一段 consolidation(base) 后出现向上 displacement → base 为需求区
    Supply : 对称
    """
    pivot_k = cfg.get("pivot_k", 5)
    cons_min = cfg.get("cons_min", 2)
    cons_max = cfg.get("cons_max", 15)
    disp_atr = cfg.get("disp_atr", 1.0)
    zone_max_atr = cfg.get("zone_max_atr", 1.6)
    tail_bars = cfg.get("zone_tail_bars", 3)   # 取 base 末端几根 bar 作 zone (紧贴触发点)
    n = len(c)
    zones: List[Zone] = []
    warm = pivot_k + 2

    for i in range(warm, n - 1):
        if a[i] <= 0:
            continue
        body = abs(c[i] - o[i])
        rng = h[i] - l[i]
        # ── 向上 displacement (需求启动) ──
        if c[i] > o[i] and rng >= disp_atr * a[i] and body >= 0.45 * rng:
            # 收集 i 之前的紧邻 base bars (低波动整理), 最多 cons_max 根
            j = i - 1
            base_idx = []
            while j >= 0 and (i - j) <= cons_max:
                rj = h[j] - l[j]
                bj = abs(c[j] - o[j])
                # 遇到明显反向/强 bar → base 到此为止 (该 bar 不纳入)
                if rj > 1.3 * a[i] and bj > 0.6 * rj:
                    break
                base_idx.append(j)
                j -= 1
            if len(base_idx) >= cons_min:
                # zone 只取最靠近 displacement 的 tail_bars 根 → 窄而贴近
                tb = base_idx[:tail_bars]
                top = max(h[k] for k in tb)
                bot = min(l[k] for k in tb)
                if (top - bot) <= zone_max_atr * a[i] and c[i] > top:
                    # demand: 收盘突破 base 顶 → 价格从上方离开
                    zones.append(Zone(top, bot, 'D', min(tb), i, rng / a[i]))
        # ── 向下 displacement (供应启动) ──
        elif c[i] < o[i] and rng >= disp_atr * a[i] and body >= 0.45 * rng:
            j = i - 1
            base_idx = []
            while j >= 0 and (i - j) <= cons_max:
                rj = h[j] - l[j]
                bj = abs(c[j] - o[j])
                if rj > 1.3 * a[i] and bj > 0.6 * rj:
                    break
                base_idx.append(j)
                j -= 1
            if len(base_idx) >= cons_min:
                tb = base_idx[:tail_bars]
                top = max(h[k] for k in tb)
                bot = min(l[k] for k in tb)
                if (top - bot) <= zone_max_atr * a[i] and c[i] < bot:
                    zones.append(Zone(top, bot, 'S', min(tb), i, rng / a[i]))
    return zones


def active_zones(zones: List[Zone], idx: int, max_age: int = 400, max_touch: int = 2,
                 a: Optional[np.ndarray] = None) -> List[Zone]:
    """在 bar idx 时刻仍有效的 zones (按新→旧排序)"""
    out = []
    for z in zones:
        if z.born >= idx:
            continue
        if idx - z.born > max_age:
            continue
        if z.touch >= max_touch + 1:   # touch>=3 失效
            continue
        # 价格已完全穿透 zone 对侧 → 失效 (结构被否定)
        out.append(z)
    out.sort(key=lambda z: -z.born)
    return out[:12]


# ════════════════════════════════════════════════════════════════════
# 交易模拟器 (R-multiple 制, 单品种)
# ════════════════════════════════════════════════════════════════════

class TradeRec:
    __slots__ = ("sym", "dir", "entry_i", "exit_i", "entry_px", "exit_px",
                 "sl", "tp", "risk", "net_r", "gross_r", "reason", "zone_type")

    def __init__(self, sym, direction, entry_i, entry_px, sl, tp, risk, zone_type):
        self.sym = sym
        self.dir = direction
        self.entry_i = entry_i
        self.exit_i = -1
        self.entry_px = entry_px
        self.sl = sl
        self.tp = tp
        self.risk = risk
        self.net_r = 0.0
        self.gross_r = 0.0
        self.reason = "open"
        self.zone_type = zone_type


def simulate(df: Dict[str, np.ndarray], zones: List[Zone], cfg: dict,
             cost_r: float = 0.02, equity: float = 10000.0) -> Tuple[List[TradeRec], Dict]:
    """
    逐 bar 模拟. df: o,h,l,c,t,a(ATR), emaf,emas.
    入场信号 (bar i 收盘确认, i+1 开盘执行):
      - 趋势过滤: emaf > emas (BUY) 且价格在 emas 上方
      - 价格本 bar 触及 demand zone (low <= z.top 且 close 收回 zone 内/上)
      - 裸K反转确认: bullish engulfing / hammer / 内包线向上突破
      - SL = z.bottom - buf*ATR; 风险 = entry - SL
      - TP候选 = 前方最近 pivot high; 若距离 < rr_min×risk 拒单
    管理 (每 bar): BE → 吊灯 trail → 结构衰竭平仓
    """
    o, h, l, c = df["o"], df["h"], df["l"], df["c"]
    a, emaf, emas = df["a"], df["emaf"], df["emas"]
    n = len(c)
    buf_atr = cfg.get("buf_atr", 0.25)
    rr_min = cfg.get("rr_min", 1.2)
    max_touch = cfg.get("zone_max_touch", 2)
    be_r = cfg.get("be_r", 1.0)
    trail_atr = cfg.get("trail_atr", 1.5)
    trail_start = cfg.get("trail_start", 1.6)
    tp_r = cfg.get("tp_r", 3.0)          # 固定 RR 止盈目标 (无前瞻)
    trend_need = cfg.get("trend_need", True)
    risk_pct = cfg.get("risk_pct", 0.01)
    max_age = cfg.get("zone_max_age", 400)

    trades: List[TradeRec] = []
    open_pos: List[TradeRec] = []
    eq = equity
    stats = {"n": 0, "wins": 0, "losses": 0, "gross_r": 0.0, "net_r": 0.0,
             "max_dd": 0.0, "peak_eq": equity}

    def _rejection(i, mode: str) -> Optional[str]:
        """裸K反转确认 (已收盘 bar i)"""
        if i < 1:
            return None
        body = c[i] - o[i]
        if mode == 'D':  # 需要看涨反转
            # 吞没看涨
            if c[i] > o[i] and o[i] <= c[i - 1] and c[i] >= o[i - 1] and (c[i] - o[i]) > 0.5 * (h[i] - l[i]):
                return "engulf"
            # 锤子
            rng = h[i] - l[i]
            if rng > 0 and (h[i] - max(c[i], o[i])) <= 0.25 * rng and (min(c[i], o[i]) - l[i]) >= 0.55 * rng \
                    and c[i] > o[i]:
                return "hammer"
            # 内包突破 (i-1 内包于 i-2, i 向上突破 i-1)
            if i >= 2:
                if h[i - 1] <= h[i - 2] and l[i - 1] >= l[i - 2] and c[i] > h[i - 1] and o[i] < l[i - 1]:
                    return "ib"
        else:  # 看跌反转
            if c[i] < o[i] and o[i] >= c[i - 1] and c[i] <= o[i - 1] and (o[i] - c[i]) > 0.5 * (h[i] - l[i]):
                return "engulf"
            rng = h[i] - l[i]
            if rng > 0 and (min(c[i], o[i]) - l[i]) <= 0.25 * rng and (h[i] - max(c[i], o[i])) >= 0.55 * rng \
                    and c[i] < o[i]:
                return "shooting"
            if i >= 2:
                if h[i - 1] <= h[i - 2] and l[i - 1] >= l[i - 2] and c[i] < l[i - 1] and o[i] > h[i - 1]:
                    return "ib"
        return None

    warm = max(60, 10)
    for i in range(warm, n - 1):
        # ── 1) 管理持仓 (intrabar SL/TP 触发 + BE + 吊灯追踪)
        for p in open_pos[:]:
            d = 1.0 if p.dir == 'BUY' else -1.0
            hit_sl = (l[i] <= p.sl) if d > 0 else (h[i] >= p.sl)
            hit_tp = (h[i] >= p.tp) if d > 0 else (l[i] <= p.tp)
            if hit_sl:
                p.exit_i, p.exit_px, p.reason = i, p.sl, "SL"
                r = -1.0
            elif hit_tp:
                p.exit_i, p.exit_px, p.reason = i, p.tp, "TP"
                r = (p.tp - p.entry_px) / p.risk if d > 0 else (p.entry_px - p.tp) / p.risk
            else:
                # BE 提升: 浮盈 ≥ be_r R → SL 移至入场 +0.1R
                if d > 0:
                    if p.reason in ("open", "BE") and c[i] >= p.entry_px + be_r * p.risk:
                        p.sl = p.entry_px + 0.1 * p.risk
                        p.reason = "BE"
                    # 吊灯追踪: 浮盈 ≥ trail_start R → SL = 峰值 - trail_atr×ATR
                    if c[i] >= p.entry_px + trail_start * p.risk:
                        new_sl = h[i] - trail_atr * a[i]
                        if new_sl > p.sl:
                            p.sl = new_sl
                            p.reason = "TRAIL"
                else:
                    if p.reason in ("open", "BE") and c[i] <= p.entry_px - be_r * p.risk:
                        p.sl = p.entry_px - 0.1 * p.risk
                        p.reason = "BE"
                    if c[i] <= p.entry_px - trail_start * p.risk:
                        new_sl = l[i] + trail_atr * a[i]
                        if p.sl == 0 or new_sl < p.sl:
                            p.sl = new_sl
                            p.reason = "TRAIL"
                continue
            gross = r
            net = r - cost_r
            p.net_r, p.gross_r = net, gross
            trades.append(p)
            open_pos.remove(p)
            eq *= (1.0 + risk_pct * net)
            if eq > stats["peak_eq"]:
                stats["peak_eq"] = eq
            dd = (stats["peak_eq"] - eq) / stats["peak_eq"]
            if dd > stats["max_dd"]:
                stats["max_dd"] = dd
            stats["net_r"] += net

        # ── 2) 新入场评估 (bar i 收盘, i+1 开盘执行)
        if open_pos:
            continue
        emaf_up = emaf[i] > emas[i]
        emaf_dn = emaf[i] < emas[i]
        d1up = df.get("d1up")
        d1_bull = (d1up is None) or bool(d1up[i])
        d1_bear = (d1up is None) or (not d1up[i])
        d1s = df.get("d1str")
        need_str = bool(cfg.get("need_d1str", False))
        d1_str_ok = (not need_str) or (d1s is not None and bool(d1s[i]))
        price_ok_buy = c[i] > emas[i] * 0.995  # 价格在慢线附近/上方
        price_ok_sell = c[i] < emas[i] * 1.005

        zs = active_zones(zones, i, max_age=max_age, max_touch=max_touch)
        for z in zs:
            if z.ztype == 'D' and (not trend_need or emaf_up) and d1_bull and price_ok_buy and d1_str_ok:
                if not (l[i] <= z.top and c[i] > z.bottom):
                    continue
                sig = _rejection(i, 'D')
                if not sig:
                    continue
                sl = z.bottom - buf_atr * a[i]
                risk = c[i + 1] - sl if i + 1 < n else 0
                if risk <= 0 or risk > cfg.get("risk_cap_atr", 2.2) * a[i]:
                    continue
                tp = c[i + 1] + tp_r * risk
                p = TradeRec("", 'BUY', i + 1, c[i + 1], sl, tp, risk, z.ztype)
                open_pos.append(p)
                stats["n"] += 1
                break
            elif z.ztype == 'S' and (not trend_need or emaf_dn) and d1_bear and price_ok_sell and d1_str_ok:
                if not (h[i] >= z.bottom and c[i] < z.top):
                    continue
                sig = _rejection(i, 'S')
                if not sig:
                    continue
                sl = z.top + buf_atr * a[i]
                risk = sl - c[i + 1] if i + 1 < n else 0
                if risk <= 0 or risk > cfg.get("risk_cap_atr", 2.2) * a[i]:
                    continue
                tp = c[i + 1] - tp_r * risk
                p = TradeRec("", 'SELL', i + 1, c[i + 1], sl, tp, risk, z.ztype)
                open_pos.append(p)
                stats["n"] += 1
                break

    # 收尾: 未平仓按最后价平 (标记 open)
    for p in open_pos:
        d = 1.0 if p.dir == 'BUY' else -1.0
        exit_px = c[-1]
        r = (exit_px - p.entry_px) / p.risk if d > 0 else (p.entry_px - exit_px) / p.risk
        p.exit_i, p.exit_px, p.reason = n - 1, exit_px, "EOD"
        p.gross_r = r
        p.net_r = r - cost_r
        trades.append(p)
        eq *= (1.0 + risk_pct * p.net_r)
        if eq > stats["peak_eq"]:
            stats["peak_eq"] = eq
        dd = (stats["peak_eq"] - eq) / stats["peak_eq"]
        if dd > stats["max_dd"]:
            stats["max_dd"] = dd
        stats["net_r"] += p.net_r

    # stats 汇总
    if trades:
        arr = np.array([t.net_r for t in trades])
        wins = arr[arr > 0]
        losses = arr[arr <= 0]
        stats["n"] = len(trades)
        stats["wins"] = int((arr > 0).sum())
        stats["losses"] = int((arr <= 0).sum())
        stats["gross_r"] = float(arr.sum())
        stats["net_r"] = float(arr.sum())
        stats["win_rate"] = float((arr > 0).mean())
        stats["avg_r"] = float(arr.mean())
        stats["pf"] = float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else (9.99 if len(wins) else 0.0)
        stats["max_dd"] = float(stats["max_dd"])
        stats["final_eq"] = float(eq)
    else:
        stats.update(win_rate=0.0, avg_r=0.0, pf=0.0, final_eq=equity)
    return trades, stats


# ════════════════════════════════════════════════════════════════════
# 数据装配
# ════════════════════════════════════════════════════════════════════

ZONE_DEFAULT = dict(pivot_k=5, cons_min=2, cons_max=15, disp_atr=1.0, zone_max_atr=1.6, zone_tail_bars=3)

TRADE_DEFAULT = dict(buf_atr=0.25, rr_min=1.2, zone_max_touch=2, be_r=1.0,
                     trail_atr=1.5, trail_start=1.6, tp_r=3.0,
                     trend_need=True, risk_pct=0.01, zone_max_age=400)

SEARCH_SPACE = {
    "rr_min": [1.0, 1.2],
    "zone_max_touch": [1, 2],
    "be_r": [0.8, 1.0, 1.5],
    "trail_atr": [1.0, 1.5, 2.0],
    "trail_start": [1.2, 1.6, 2.0],
    "tp_r": [2.0, 3.0, 4.0, 6.0],
    "buf_atr": [0.15, 0.25, 0.35],
}


def build_df(o, h, l, c, t, trend_cfg: dict = None, d1c: Optional[np.ndarray] = None,
             d1t: Optional[np.ndarray] = None, d1str: Optional[np.ndarray] = None) -> Dict[str, np.ndarray]:
    """d1c/d1t: D1 close 与时间戳 (可选) → 逐 H4 bar 映射 D1 EMA 方向闸
    d1str: 外部算好的逐 bar D1 趋势强度 bool (可选) → 额外强趋势闸"""
    tc = trend_cfg or {"ema_fast": 50, "ema_slow": 200}
    a = atr(h, l, c)
    emaf = ema(c, tc["ema_fast"])
    emas = ema(c, tc["ema_slow"])
    df = {"o": o, "h": h, "l": l, "c": c, "t": t, "a": a, "emaf": emaf, "emas": emas,
          "d1up": None, "d1str": None}
    if d1c is not None and len(d1c) > 60:
        e50 = ema(d1c, 50)
        e200 = ema(d1c, 200)
        d1up = e50 > e200
        idx = np.searchsorted(d1t, t, side="right") - 1
        idx = np.clip(idx, 0, len(d1c) - 1)
        df["d1up"] = d1up[idx]
        if d1str is not None:
            df["d1str"] = d1str[idx]
    return df


def evaluate(df: Dict[str, np.ndarray], zone_cfg: dict, trade_cfg: dict,
             cost_r: float = 0.02, equity: float = 10000.0, start_i: int = 0, end_i: int = None,
             zones: Optional[List[Zone]] = None):
    """若传入预扫 zones (全序列), 则按 start_i 过滤重用, 避免重复扫描"""
    n = len(df["c"])
    end_i = n if end_i is None else min(end_i, n)
    sub = {k: (v[start_i:end_i] if isinstance(v, np.ndarray) else v) for k, v in df.items()}
    if zones is None:
        zones_all = scan_zones(sub["o"], sub["h"], sub["l"], sub["c"], sub["a"], zone_cfg)
    else:
        # 平移全局坐标 → 窗口坐标 (born 可为负: 窗口开始前已形成的 zone, age 计算仍正确)
        zones_all = []
        for z in zones:
            if z.born < end_i:
                zones_all.append(Zone(z.top, z.bottom, z.ztype, z.born - start_i, z.disp_i - start_i, z.disp_range))
                zones_all[-1].touch = z.touch
    trades, stats = simulate(sub, zones_all, trade_cfg, cost_r=cost_r, equity=equity)
    return trades, stats


# ════════════════════════════════════════════════════════════════════
# Walk-Forward 自进化
# ════════════════════════════════════════════════════════════════════

def _fitness(stats: Dict) -> float:
    """适应度: 期望收益为正 + 盈利质量"""
    if stats["n"] < 10:
        return -1.0
    pf = min(stats.get("pf", 0), 5.0)
    avg = stats.get("avg_r", 0)
    wr = stats.get("win_rate", 0)
    if avg <= 0:
        return avg * stats["n"] * 0.1 - 2.0
    dd = max(stats.get("max_dd", 1.0), 0.05)
    return avg * stats["n"] * 0.5 + pf * 1.0 + wr * 2.0 - dd * 10.0


def evolve(df: Dict[str, np.ndarray], zone_cfg: dict, n_iters: int = 150, seed: int = 7,
           cost_r: float = 0.02, train_ratio: float = 0.6, val_ratio: float = 0.2,
           equity: float = 10000.0, min_trades: int = 25, progress=None) -> Dict:
    """
    三段式: train(旧60%) 搜索 → val(中20%) 稳健性 → 返回最优参数 (含 test 段 OOS 单独评测调用方做)
    """
    n = len(df["c"])
    t_end = int(n * train_ratio)
    v_end = int(n * (train_ratio + val_ratio))
    rng = np.random.default_rng(seed)
    # zone_cfg 固定 → zones 只扫一次 (全序列)
    zones_all = scan_zones(df["o"], df["h"], df["l"], df["c"], df["a"], zone_cfg)

    def _run(cfg, s, e):
        tr, st = evaluate(df, zone_cfg, cfg, cost_r=cost_r, equity=equity,
                          start_i=s, end_i=e, zones=zones_all)
        return tr, st

    best = None
    best_fit = -1e9
    hist = []
    # 1) 全局随机搜索 (交易层参数)
    keys = list(SEARCH_SPACE.keys())
    for it in range(n_iters):
        cfg = dict(TRADE_DEFAULT)
        for k in keys:
            cfg[k] = rng.choice(SEARCH_SPACE[k])
        tr, st = _run(cfg, 60, t_end)
        if st["n"] < min_trades:
            continue
        fit = _fitness(st)
        # val 段稳健性检查 (不直接参与选择, 防过拟合 train)
        _, stv = _run(cfg, t_end, v_end)
        if stv["n"] >= 8 and stv.get("avg_r", -1) < -0.05:
            fit -= 4.0  # val 段亏损惩罚
        if fit > best_fit:
            best_fit = fit
            best = dict(cfg)
        hist.append((fit, st["n"], st.get("pf", 0), st.get("avg_r", 0)))
        if progress and it % 50 == 0:
            progress(it, n_iters, best_fit, best)

    # 2) 局部精化 (对 best 每参数邻近微调)
    if best:
        for k in keys:
            cur = best[k]
            opts = SEARCH_SPACE[k]
            if cur in opts:
                cands = [cur]
                idx = opts.index(cur)
                if idx > 0:
                    cands.append(opts[idx - 1])
                if idx < len(opts) - 1:
                    cands.append(opts[idx + 1])
                for cv in cands:
                    c2 = dict(best)
                    c2[k] = cv
                    tr, st = _run(c2, 60, t_end)
                    if st["n"] < min_trades:
                        continue
                    f2 = _fitness(st)
                    if f2 > best_fit:
                        best_fit, best = f2, c2

    # 最终 OOS 报告 (test 段)
    oos = {"trades": [], "stats": {"n": 0, "avg_r": 0, "pf": 0, "win_rate": 0}}
    if best:
        tr_te, st_te = _run(best, v_end, n)
        oos = {"trades": tr_te, "stats": st_te}
    return {"best": best, "fit": best_fit, "oos": oos, "hist": hist}


# ════════════════════════════════════════════════════════════════════
# 成本模型
# ════════════════════════════════════════════════════════════════════

def spread_ticks(symbol: str, info=None, spread_map: dict = None) -> float:
    """估算每品种 round-trip 成本 (ticks 数). 用于 cost_r = spread_ticks / sl_ticks"""
    m = spread_map or {
        "XAUUSD": 35.0, "EURUSD": 12.0, "GBPUSD": 14.0, "AUDUSD": 11.0,
        "USDJPY": 12.0, "EURJPY": 20.0, "GBPJPY": 28.0, "CADJPY": 22.0,
        "AUDCHF": 16.0, "GBPCAD": 28.0, "CHFJPY": 22.0, "NZDUSD": 14.0,
        "AUDCAD": 20.0, "AUDNZD": 24.0, "USDCAD": 14.0, "EURGBP": 14.0,
        "USDCHF": 20.0, "EURCHF": 20.0, "GBPAUD": 30.0, "EURAUD": 26.0,
        "BTCUSD": 500.0, "ETHUSD": 2000.0,
    }
    if symbol in m:
        return m[symbol]
    if info is not None:
        try:
            return max(10.0, (info.spread / max(info.point, 1e-12)))
        except Exception:
            pass
    return 15.0


def typical_sl_ticks(symbol: str, atr_val: float, info=None) -> float:
    """典型 SL 距离 (ticks) = 1.0×ATR + buffer"""
    pt = info.point if info else (0.01 if symbol == "XAUUSD" else 0.00001)
    return max(20.0, (atr_val * 1.25) / pt)


def cost_r_estimate(symbol: str, atr_val: float, info=None) -> float:
    """成本/风险 比率估算"""
    st = spread_ticks(symbol, info)
    slt = typical_sl_ticks(symbol, atr_val, info)
    return min(0.12, st / slt)


# ════════════════════════════════════════════════════════════════════
# D1 major-zone 模式 (裸K供需波段 v2 — 主推)
#   zone 在 D1 检测 (强 displacement, 质量高) → H4 收盘入场
# ════════════════════════════════════════════════════════════════════

ZONE_D1_DEFAULT = dict(pivot_k=3, cons_min=2, cons_max=8, disp_atr=1.5,
                       zone_max_atr=3.0, zone_tail_bars=2)

TRADE_D1_DEFAULT = dict(TRADE_DEFAULT)


def build_d1_zones(od, hd, ld, cd, td, t_h4, zone_cfg: dict = None) -> List[Zone]:
    """D1 zone 检测 → 映射为 H4 bar 坐标的 Zone 列表 (全局坐标)"""
    zc = zone_cfg or ZONE_D1_DEFAULT
    ad = atr(hd, ld, cd)
    z_d1 = scan_zones(od, hd, ld, cd, ad, zc)
    mapped = []
    for z in z_d1:
        born_h4 = int(np.searchsorted(t_h4, td[max(z.born, 0)], side="right") - 1)
        if 0 <= born_h4 < len(t_h4):
            mapped.append(Zone(z.top, z.bottom, z.ztype, born_h4, born_h4, z.disp_range))
    return mapped


def evaluate_d1(df_h4: Dict[str, np.ndarray], od, hd, ld, cd, td,
                zone_cfg: dict = None, trade_cfg: dict = None,
                cost_r: float = 0.03, equity: float = 10000.0,
                start_i: int = 0, end_i: int = None):
    """D1-zone 模式评测. zone 用 D1 全序列检测并映射到 H4 坐标; 交易模拟在 H4."""
    n = len(df_h4["c"])
    end_i = n if end_i is None else min(end_i, n)
    zones_all = build_d1_zones(od, hd, ld, cd, td, df_h4["t"], zone_cfg)
    return evaluate(df_h4, {}, trade_cfg or {}, cost_r=cost_r, equity=equity,
                    start_i=start_i, end_i=end_i, zones=zones_all)


def evolve_d1(df_h4, od, hd, ld, cd, td, n_iters: int = 150, seed: int = 7,
              cost_r: float = 0.03, train_ratio: float = 0.5, val_ratio: float = 0.2,
              equity: float = 10000.0, min_trades: int = 12,
              zone_cfg: dict = None, trade_base: dict = None) -> Dict:
    """D1-zone 模式 Walk-Forward 进化"""
    zc = zone_cfg or ZONE_D1_DEFAULT
    base = trade_base or dict(TRADE_DEFAULT)
    # D1-zone 模式默认更宽的参数适配
    base.setdefault("risk_cap_atr", 6.0)
    base.setdefault("buf_atr", 0.5)
    n = len(df_h4["c"])
    t_end = int(n * train_ratio)
    v_end = int(n * (train_ratio + val_ratio))
    rng = np.random.default_rng(seed)
    # D1 zones 只构建一次, 全程复用 (全局 H4 坐标, evaluate 内自动平移)
    zones_all = build_d1_zones(od, hd, ld, cd, td, df_h4["t"], zc)

    def _run(cfg, s, e):
        return evaluate(df_h4, {}, cfg, cost_r=cost_r, equity=equity,
                        start_i=s, end_i=e, zones=zones_all)

    best, best_fit, hist = None, -1e9, []
    keys = list(SEARCH_SPACE.keys())
    for it in range(n_iters):
        cfg = dict(base)
        for k in keys:
            cfg[k] = rng.choice(SEARCH_SPACE[k])
        tr, st = _run(cfg, 60, t_end)
        if st["n"] < min_trades:
            continue
        fit = _fitness(st)
        _, stv = _run(cfg, t_end, v_end)
        if stv["n"] >= 5 and stv.get("avg_r", -1) < -0.05:
            fit -= 4.0
        if fit > best_fit:
            best_fit, best = fit, dict(cfg)
        hist.append((fit, st["n"], st.get("pf", 0), st.get("avg_r", 0)))
    # 局部精化
    if best:
        for k in keys:
            cur = best[k]
            opts = SEARCH_SPACE[k]
            if cur in opts:
                idx = opts.index(cur)
                for cand in ([cur] + (opts[max(0, idx - 1):idx + 2] if idx < len(opts) - 1 else [cur])):
                    if cand == cur:
                        continue
                    c2 = dict(best); c2[k] = cand
                    tr, st = _run(c2, 60, t_end)
                    if st["n"] < min_trades:
                        continue
                    f2 = _fitness(st)
                    if f2 > best_fit:
                        best_fit, best = f2, c2
    oos = {"trades": [], "stats": {"n": 0, "avg_r": 0, "pf": 0, "win_rate": 0}}
    if best:
        tr_te, st_te = _run(best, v_end, n)
        oos = {"trades": tr_te, "stats": st_te}
    return {"best": best, "fit": best_fit, "oos": oos, "hist": hist}
