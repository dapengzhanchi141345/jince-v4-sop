# -*- coding: utf-8 -*-
"""[rd 11-14 P1/E3 验批前置] MT5 只读回填 tf_cache M30+D1 (XAU/EUR + 币系6).
套路沿用 _jevo_tf_refresh_1111.py: 先写 tmp 再原子 replace; 对象属性用 getattr 候选列表.
红线: 只写 data/tf_cache/*.npz 缓存, 不碰闸源/挂单/仓位/REAL 30261104."""
import os, time, json
from datetime import datetime, timezone

import numpy as np
import MetaTrader5 as mt5

assert mt5.initialize(terminal=os.environ.get("MT5_TERMINAL") or None), "mt5 init failed"
acc = mt5.account_info()
print("connected account:", getattr(acc, "login", None), "data:", datetime.now(timezone.utc).strftime("%m-%d %H:%M UTC"))

cache = r"E:\GoldstrategyEngine\data\tf_cache"
os.makedirs(cache, exist_ok=True)
START = int(datetime(2025, 7, 1, tzinfo=timezone.utc).timestamp())


def tf_const(name):
    for attr in ("PERIOD_" + name, "TIMEFRAME_" + name):
        v = getattr(mt5, attr, None)
        if v is not None:
            return v
    return {"M30": 30, "H4": 16388, "D1": 16408}[name]


JOBS = [("XAUUSD", ["M30", "D1"]), ("EURUSD", ["M30", "D1"]),
        ("BTCUSD", ["M30", "D1"]), ("ETHUSD", ["M30", "D1"]), ("SOLUSD", ["M30", "D1"]),
        ("XRPUSD", ["M30", "D1"]), ("LTCUSD", ["M30", "D1"]), ("BNBUSD", ["M30", "D1"])]

report = {}
for sym, tfs in JOBS:
    for tf in tfs:
        key = f"{sym}_{tf}"
        path = os.path.join(cache, key + ".npz")
        rates = mt5.copy_rates_range(sym, tf_const(tf), START, int(time.time()))
        if rates is None:
            report[key] = {"status": "FETCH_FAILED", "detail": str(mt5.last_error())}
            print(sym, tf, "拉取失败:", mt5.last_error())
            continue
        new = {k: rates[k] for k in ("time", "high", "low", "close")}
        new = {k: v.astype(np.int64 if k == "time" else np.float64) for k, v in new.items()}
        old = {}
        if os.path.exists(path):
            try:
                z = np.load(path)
                for kk in ("t", "h", "l", "c"):
                    if kk in z:
                        old[kk] = z[kk].astype(np.int64 if kk == "t" else np.float64)
                z.close()
            except Exception:
                old = {}
        if old and "t" in old:
            m = dict(t=np.concatenate([old["t"], new["time"]]),
                     h=np.concatenate([old.get("h", np.zeros_like(new["time"])), new["high"]]),
                     l=np.concatenate([old.get("l", np.zeros_like(new["time"])), new["low"]]),
                     c=np.concatenate([old.get("c", np.zeros_like(new["time"])), new["close"]]))
            o = np.argsort(m["t"], kind="stable")
            keep = np.concatenate(([True], np.diff(m["t"][o]) > 0))
            m = {k: v[o][keep] for k, v in m.items()}
            out = {k: m[k] for k in ("t", "h", "l", "c")}
        else:
            out = {"t": new["time"], "h": new["high"], "l": new["low"], "c": new["close"]}
        last = datetime.fromtimestamp(int(out["t"][-1]), tz=timezone.utc).strftime("%m-%d %H:%M UTC")
        bars = len(out["t"])
        status = "OK"
        try:
            tmp = path + ".tmp"
            np.savez(tmp, **out)
            os.replace(tmp, path)
        except Exception:
            try:
                np.savez(path, **out)
                status = "OK_OVERWRITE"
            except Exception:
                status = "LOCKED"
        report[key] = {"status": status, "n": bars, "last": last}
        print(sym, tf, "bars=", bars, "last=", last, status)

mt5.shutdown()
okn = sum(1 for v in report.values() if v["status"].startswith("OK"))
with open(r"E:\GoldstrategyEngine\data\rd_batch_tf_refresh_20261114_report.json", "w", encoding="utf-8") as f:
    json.dump({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
               "account": getattr(acc, "login", None),
               "report": report}, f, ensure_ascii=False, indent=1)
print("MT5 回填完", okn, "/", len(report), "OK")
