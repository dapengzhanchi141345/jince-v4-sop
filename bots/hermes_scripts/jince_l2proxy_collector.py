# -*- coding: utf-8 -*-
r"""P2-2 L2数据源代理 · tick 采集器 (持久后台, 0LLM)
MT5 CFD 无真 L2 报价板, 顶配替代=高频 tick 流代理: 30s 采样 watchlist bid/ask/tick_volume
-> data/l2proxy_ticks.jsonl (追加, 50万行轮转), 供 HVN/LVN 区计算 (l2proxy_zones.py)。
pid 文件 data/l2proxy_collector.pid; 活体哨 30min 查 pid 存+最后行新鲜度(>5min=红报)。
启动: 本脚本直接跑(前台循环); --once 采样一轮即退(哨/自检用)。
"""
import json
import os
import time

import MetaTrader5 as mt5

WATCH = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "XAUUSD", "EURUSD", "GBPUSD", "US30"]
DATA = r"E:\GoldstrategyEngine\data"
OUT = os.path.join(DATA, "l2proxy_ticks.jsonl")
PIDF = os.path.join(DATA, "l2proxy_collector.pid")
ROTATE = 500_000


def count_lines():
    try:
        with open(OUT, "rb") as f:
            return sum(1 for _ in f)
    except FileNotFoundError:
        return 0


def sample_once():
    if not mt5.initialize():
        print("tick采样: ATE init 失败(%s)" % (mt5.last_error(),))
        return 0
    time.sleep(2)
    ts = time.strftime("%F %T")
    n = 0
    for s in WATCH:
        t = mt5.symbol_info_tick(s)
        if t is None or t.bid <= 0:
            continue
        v = getattr(t, "tick_volume", None)
        if v is None:
            v = getattr(t, "volume", 0)
        with open(OUT, "a", encoding="utf-8") as f:
            json.dump({"ts": ts, "sym": s, "bid": t.bid, "ask": t.ask, "v": int(v or 0)}, f, ensure_ascii=False)
            f.write("\n")
        n += 1
    if count_lines() > ROTATE:
        lines = open(OUT, encoding="utf-8", errors="replace").readlines()[-100000:]
        open(OUT, "w", encoding="utf-8").writelines(lines)
    mt5.shutdown()
    return n


def main():
    import sys
    if "--once" in sys.argv:
        print("采样一轮: %d 品种" % sample_once())
        return
    os.makedirs(DATA, exist_ok=True)
    open(PIDF, "w").write(str(os.getpid()))
    print("L2代理采集器启动 pid=%d watch=%s" % (os.getpid(), WATCH))
    while True:
        try:
            sample_once()
        except Exception as e:
            with open(OUT, "a", encoding="utf-8") as f:
                json.dump({"ts": time.strftime("%F %T"), "err": str(e)[:200]}, f)
                f.write("\n")
        time.sleep(30)


if __name__ == "__main__":
    main()
