# -*- coding: utf-8 -*-
"""
P5: 长线趋势策略 (D1 唐奇安通道突破)
=====================================
基于 2026-08-28 数据研究 (8年回测):

  ETHUSD +178.2% (53%) ⭐
  XAUUSD +74.8% (55%) ⭐
  NAS100 +49.5% / US500 +42.8% ✅
  外汇品种全部负收益 → 排除

核心逻辑:
  1. D1 收盘突破 20日高点 → 做多 (趋势启动)
  2. D1 收盘跌破 20日低点 → 做空 (趋势启动)
  3. SL = 3×ATR (跌破趋势结构), 最长持有 90 天
  4. 出场: 反向突破 或 超时

与日内系统 (H1) 完全独立, 互补不同时间尺度 alpha。
参数经稳健性验证: 窗口20-30 / SL2-4ATR / 持有60-120天 全正收益。
"""

import datetime
import json
import os
import time

import numpy as np
import pandas as pd

# ── 配置 ──
LONGTERM_SYMBOLS = ["XAUUSD", "ETHUSD", "NAS100", "US500"]
LOOKBACK = 20          # 唐奇安通道窗口 (日)
SL_ATR_MULT = 3.0      # SL = 3×ATR
MAX_HOLD_DAYS = 90     # 最长持有
MIN_RISK_PCT = 2.5     # 单笔风险% (与系统一致)
MAX_LONGTERM_POS = 2   # 最多同时2个长线仓
MAGIC_PREFIX = "LT"    # 标记长线仓

# 状态文件 (避免重复开仓/记录已开信号)
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "data", "longterm_state.json")


def _ema(a, p):
    a = np.asarray(a, dtype=float)
    e = np.full(len(a), np.nan)
    k = 2.0 / (p + 1)
    if len(a) > 0:
        e[0] = a[0]
    for i in range(1, len(a)):
        e[i] = a[i] * k + (e[i - 1] if not np.isnan(e[i - 1]) else a[i]) * (1 - k)
    return e


def donchian_signal(mt5, symbol):
    """D1 唐奇安突破信号: 返回 ('BUY'/'SELL'/None, 详情)"""
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 100)
    if rates is None or len(rates) < 40:
        return None, "D1数据不足"
    df = pd.DataFrame(rates)
    h = df['high'].values.astype(float)
    l = df['low'].values.astype(float)
    c = df['close'].values.astype(float)
    n = len(c)

    # ATR(14)
    tr = np.maximum(h[1:] - l[1:],
                    np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    atr = np.full(n, np.nan)
    if len(tr) > 14:
        atr[14] = np.mean(tr[:14])
        for i in range(15, n):
            atr[i] = tr[i - 1] / 14 + atr[i - 1] * 13 / 14
    atr_now = atr[-1]
    if np.isnan(atr_now) or atr_now <= 0:
        return None, "ATR无效"

    # 唐奇安通道 (shift 1: 不含当前bar, 用昨日通道)
    hh = pd.Series(h).rolling(LOOKBACK).max().shift(1).values
    ll = pd.Series(l).rolling(LOOKBACK).min().shift(1).values
    if np.isnan(hh[-1]) or np.isnan(ll[-1]):
        return None, "通道未就绪"

    cur = c[-1]
    # 趋势过滤器: EMA50 方向 (只做顺势突破, 避免逆势假突破)
    e50 = _ema(c, 50)
    trend_up = (not np.isnan(e50[-1])) and cur > e50[-1]
    trend_dn = (not np.isnan(e50[-1])) and cur < e50[-1]

    if cur > hh[-1] and trend_up:
        sl = cur - SL_ATR_MULT * atr_now
        tp = None  # 趋势跟踪, 由出场规则管理
        return "BUY", {"entry": cur, "sl": sl, "atr": atr_now,
                       "hh": hh[-1], "ll": ll[-1], "trend": "up"}
    elif cur < ll[-1] and trend_dn:
        sl = cur + SL_ATR_MULT * atr_now
        return "SELL", {"entry": cur, "sl": sl, "atr": atr_now,
                        "hh": hh[-1], "ll": ll[-1], "trend": "dn"}
    return None, f"通道内 (hh={hh[-1]:.1f} ll={ll[-1]:.1f} cur={cur:.1f})"


def _load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"signaled": {}, "opened": {}}


def _save_state(st):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def check_exit(mt5, symbol, position):
    """长线持仓出场检查: 反向突破或超时"""
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 40)
    if rates is None or len(rates) < 25:
        return False, "数据不足"
    df = pd.DataFrame(rates)
    h = df['high'].values.astype(float)
    l = df['low'].values.astype(float)
    c = df['close'].values.astype(float)
    hh = pd.Series(h).rolling(LOOKBACK).max().shift(1).values
    ll = pd.Series(l).rolling(LOOKBACK).min().shift(1).values

    is_buy = position.type == 0
    cur = c[-1]
    if is_buy and cur < ll[-1]:
        return True, f"跌破20日低 {ll[-1]:.1f}, 多头离场"
    if (not is_buy) and cur > hh[-1]:
        return True, f"突破20日高 {hh[-1]:.1f}, 空头离场"

    # 超时
    hold_days = (datetime.datetime.now().timestamp() - float(position.time)) / 86400
    if hold_days > MAX_HOLD_DAYS:
        return True, f"持有{hold_days:.0f}天超时, 离场"
    return False, "持有中"


def scan_longterm(mt5, equity):
    """长线策略主入口: 返回 [(proposal, reason)] 或 []"""
    from symbol_universe import UNIVERSE, build_full_universe
    st = _load_state()
    out = []
    today = datetime.date.today().isoformat()

    # 清理过期状态
    st['signaled'] = {k: v for k, v in st['signaled'].items()
                      if v == today}
    _save_state(st)

    # 当前长线持仓数
    try:
        positions = mt5.positions_get() or []
        lt_pos = [p for p in positions if p.comment.startswith(MAGIC_PREFIX)]
        existing_syms = {p.symbol for p in lt_pos}
    except Exception:
        lt_pos = []
        existing_syms = set()

    if len(lt_pos) >= MAX_LONGTERM_POS:
        # 已满仓: 只做出场检查
        for p in lt_pos:
            exit_now, reason = check_exit(mt5, p.symbol, p)
            if exit_now:
                out.append(("EXIT", p.ticket, p.symbol, reason))
        return out

    # 扫描信号
    for sym in LONGTERM_SYMBOLS:
        if sym in existing_syms:
            continue
        if st['signaled'].get(sym) == today:
            continue  # 今日已评估过
        sig, info = donchian_signal(mt5, sym)
        st['signaled'][sym] = today
        if sig in ("BUY", "SELL"):
            cfg = UNIVERSE.get(sym) or {}
            pip = float(cfg.get('pip', 0.0001) or 0.0001)
            pip_usd = float(cfg.get('pip_usd', 1.0) or 1.0)
            sl_pts = abs(info['sl'] - info['entry']) / pip
            if sl_pts <= 0:
                continue
            # 仓位: 按单笔风险
            lot = (equity * MIN_RISK_PCT / 100.0) / (sl_pts * pip_usd)
            lot = max(0.01, min(1.0, round(lot, 2)))
            proposal = {
                "symbol": sym,
                "direction": sig,
                "entry": float(info['entry']),
                "sl": float(info['sl']),
                "sl_pts": round(sl_pts, 2),
                "lot": lot,
                "strategy": "LONGTERM",
                "comment": f"{MAGIC_PREFIX}.{sym}",
                "regime": "d1_donchian",
            }
            out.append(("OPEN", proposal, f"{sig} 突破20日通道 "
                       f"趋势={info['trend']} SL={info['sl']:.1f}"))
    _save_state(st)
    return out
