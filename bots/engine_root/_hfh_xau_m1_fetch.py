# -*- coding: utf-8 -*-
"""拉 XAUUSD M1 K线缓存 (2026-09-02 ~ 2026-10-09), 供 ⑬ 黄飞日内节奏同分母回放.
只读 copy_rates, 拉完即 shutdown, 300s 时间护栏防 IPC 卡死.
运行: C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe E:/GoldstrategyEngine/_hfh_xau_m1_fetch.py
"""
import sys, os, json, time, datetime

ROOT = "E:/GoldstrategyEngine"
OUT = os.path.join(ROOT, "data", "_hfh_xau_m1_cache.json")

import MetaTrader5 as mt5

def main():
    if not mt5.initialize():
        print("INIT FAIL:", mt5.last_error())
        return 1
    t0 = time.time()
    start = datetime.datetime(2026, 9, 2)
    end = datetime.datetime(2026, 10, 10)
    all_rows = []
    cur = start
    while cur < end:
        nxt = cur + datetime.timedelta(days=7)
        rows = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_M1, cur, nxt)
        if rows is None or len(rows) == 0:
            print("EMPTY CHUNK at", cur, "err:", mt5.last_error())
            cur = nxt
            continue
        for r in rows:
            all_rows.append([int(r["time"]), float(r["open"]), float(r["high"]),
                             float(r["low"]), float(r["close"]), int(r["tick_volume"])])
        print("chunk", cur, "->", nxt, "bars:", len(rows), "total:", len(all_rows))
        if time.time() - t0 > 300:
            print("TIMECAP 300s, fail-open 出已有数据")
            break
        cur = nxt
    mt5.shutdown()
    meta = {"symbol": "XAUUSD", "tf": "M1",
            "from": start.isoformat(), "to": end.isoformat(),
            "bars": len(all_rows),
            "time_range": [int(all_rows[0][0]), int(all_rows[-1][0])] if all_rows else None,
            "generated": datetime.datetime.now().isoformat(),
            "note": "ate venv MT5只读拉取; 黄飞15014338在TradeMax, 本引擎TMGM价源仅作回放价路径近似(同源金), 2⑬回放扣2xpoint滑点"}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"meta": meta, "rows": all_rows}, open(OUT, "w"))
    print("SAVED", OUT, "bars:", len(all_rows), "elapsed_s:", round(time.time() - t0, 1))
    return 0

if __name__ == "__main__":
    sys.exit(main())
