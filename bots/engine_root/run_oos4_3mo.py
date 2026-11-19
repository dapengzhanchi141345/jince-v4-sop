#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""L5 手动枪: 出徒 4 腿 OOS 池 × 近3个月 回测.
复用于引擎自己的策略注册表 (advanced_strategies) + simulate_signal + 宇宙配置,
但把数据切到「近 90 天」窗口, 独立出件 backtest_edge_3mo.json (不碰 01:30 枪读的 canonical).
确定性 Python, 0 LLM. 红线: 历史回测≠未来收益; 只产数据不碰实盘.
"""
import sys, os, json, time, datetime, threading
os.chdir(r"E:\GoldstrategyEngine")
sys.path.insert(0, r"E:\GoldstrategyEngine")

import numpy as np
import pandas as pd
import MetaTrader5 as mt5
import symbol_universe as su
import advanced_strategies as ast

ROOT = r"E:\GoldstrategyEngine"
DATA = ROOT + "/data"
BARS = 4320  # 3个月 ≈ 90天 H1 (24根/天), 给 4320 = 180天余量, 取「最近90天」切窗

# 用户指令 10-16: 4 条腿 + XAUUSD = 5 品种 × 全 9 策略 × 近 3 个月
OOS4 = ["CADJPY", "EURJPY", "EURNZD", "GBPCAD", "XAUUSD"]

# 引擎锁 (防双发 TIMECAP 教训: 与引擎本体共用一把内核锁)
import msvcrt as _m
_efd = os.open(os.path.join(DATA, "backtest_engine.lock"), os.O_CREAT | os.O_RDWR)
try:
    _m.locking(_efd, _m.LK_NBLCK, 1)
except OSError:
    print("[引擎锁] 已有引擎在跑, 本枪让位 exit 3(双发被拦)")
    os.close(_efd)
    sys.exit(3)

def get_rates_3mo(symbol, tf, days=90):
    """从最近端往回拉 近N天 的 K 线."""
    target = days * 24 if tf == mt5.TIMEFRAME_H1 else (days * 6 if tf == mt5.TIMEFRAME_H4 else days)
    frames = []
    total = 0
    # 从最旧拉满, 再尾部切最近 N 天
    frames_full = []
    pos = 0
    CAP = 6000
    while True:
        chunk = mt5.copy_rates_from_pos(symbol, tf, pos, CAP)
        if chunk is None or len(chunk) == 0:
            break
        frames_full.append(pd.DataFrame(chunk))
        total += len(chunk)
        if len(chunk) < CAP:
            break
        pos += len(chunk)
        if total >= CAP * 4:  # 够 3 个月就停 (省 IPC 时间)
            break
    if not frames_full:
        return None
    df = pd.concat(frames_full, ignore_index=True)
    df = df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    df["time_dt"] = pd.to_datetime(df["time"], unit="s")
    cutoff = df["time_dt"].max() - pd.Timedelta(days=days)
    df = df[df["time_dt"] >= cutoff].reset_index(drop=True)
    return df

def run_symbol_3mo(symbol, cfg, days=90):
    h1 = get_rates_3mo(symbol, mt5.TIMEFRAME_H1, days)
    if h1 is None or len(h1) < 100:
        return None, "H1数据不足(近3个月<100根)"
    h4 = get_rates_3mo(symbol, mt5.TIMEFRAME_H4, days)
    d1 = get_rates_3mo(symbol, mt5.TIMEFRAME_D1, days)
    if h4 is None or d1 is None:
        return None, "H4/D1缺失"
    # 复用引擎原函数 (同分母, 不重发明信号逻辑)
    import backtest_engine as BE
    # 引擎 backtest_symbol 内部用全局 get_rates, 这里换成我的 3mo 版 (monkey-patch, 仅限本进程)
    _og_h1, _og_h4, _og_d1 = BE.get_rates, None, None
    def _g(sym, tf, target=0):
        tmap = {mt5.TIMEFRAME_H1: "h1", mt5.TIMEFRAME_H4: "h4", mt5.TIMEFRAME_D1: "d1"}
        return _cache[tmap.get(tf, "h1")]
    _cache = {"h1": h1, "h4": h4, "d1": d1}
    BE.get_rates = _g
    try:
        res, note = BE.backtest_symbol(symbol, cfg)
    finally:
        BE.get_rates = _og_h1
    return res, note

def main():
    t0 = time.time()
    r = mt5.initialize()
    print("mt5.initialize =", r)
    overall = {}
    sym_summary = {}
    aborted = False
    for sym in OOS4:
        cfg = su.UNIVERSE.get(sym, {})
        if not cfg:
            sym_summary[sym] = {"note": "UNIVERSE缺配置", "best": None, "strats": {}}
            continue
        res, note = run_symbol_3mo(sym, cfg)
        if res is None:
            sym_summary[sym] = {"note": note, "best": None, "strats": {}}
            continue
        best = None
        for name, rr in res.items():
            if isinstance(rr, dict) and rr.get("n", 0) >= 20 and rr.get("pf", 0) >= 1.0:
                if best is None or rr["pf"] > best[1]["pf"]:
                    best = (name, rr)
        sym_summary[sym] = {"note": note, "best": best, "strats": res}
        b_txt = ("best=%s pf=%.3f n=%d wr=%.2f" % (best[0], best[1]["pf"], best[1]["n"], best[1]["wr"])) if best else "无过线腿(n>=20且pf>=1.0)"
        print("%s: %s" % (sym, b_txt))
    # 策略级汇总
    strat_acc = {s: {"n": 0, "gw": 0.0, "gl": 0.0, "wins": 0} for s in ast.ALL_STRATEGIES}
    for sym, d in sym_summary.items():
        for name, rr in (d.get("strats") or {}).items():
            if isinstance(rr, dict) and rr.get("n", 0) > 0:
                a = strat_acc[name]
                a["n"] += rr["n"]; a["wins"] += rr["wins"]; a["gw"] += rr["gw"]; a["gl"] += rr["gl"]
    for s, a in strat_acc.items():
        a["pf"] = round(a["gw"] / a["gl"], 3) if a["gl"] > 1e-9 else (float("inf") if a["gw"] > 0 else 0.0)
        a["wr"] = round(a["wins"] / a["n"], 3) if a["n"] else 0.0
    out = {
        "generated": datetime.datetime.now().isoformat(),
        "window_days": 90, "symbols_tested": len(OOS4), "pool": "OOS4",
        "elapsed_s": round(time.time() - t0, 1),
        "aborted_by_timecap": aborted,
        "strategy_overall": strat_acc, "per_symbol": sym_summary,
        "note": "L5 手动 3mo OOS4 枪, 确定性 Python, 0 LLM; 历史回测≠未来收益; 只产数据不碰实盘",
    }
    p = os.path.join(DATA, "backtest_5sym_3mo.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("=== 策略级整体 edge (近3个月 OOS4) ===")
    for s, a in strat_acc.items():
        print("  %-8s n=%-5d wr=%.2f pf=%s" % (s, a["n"], a["wr"], a["pf"]))
    print("产物:", p)
    try:
        _m.locking(_efd, _m.LK_UNLCK, 1)
    except OSError:
        pass
    os.close(_efd)

if __name__ == "__main__":
    main()
