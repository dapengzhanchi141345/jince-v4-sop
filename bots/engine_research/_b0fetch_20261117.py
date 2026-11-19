# -*- coding: utf-8 -*-
"""_b0fetch_20261117.py — 30d B0_INVAL 事件集实读(MT5 3.13.12 通道, MT5只读 60137964)
产物: E:/GoldstrategyEngine/research/_b0data_20261117.json
内容: 逐事件(sym/side/vol/entry_ts/entry_price/sl/tp/out_ts/out_price/pnl_actual)
     + 逐品种 M15 bars(覆盖事件前后) + 数据有效性三闸(来源/快照时刻/新鲜度)
跑法: D:/workbuddy/binaries/python/versions/3.13.12/python.exe research/_b0fetch_20261117.py
"""
import os, sys, json, datetime as dt

os.environ["MT5_TERMINAL"] = r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe"
import MetaTrader5 as mt5

ROOT = "E:/GoldstrategyEngine"
OUT = os.path.join(ROOT, "research", "_b0data_20261117.json")
MAGIC = 30261103

t0 = dt.datetime(2026, 11, 9, 0, 0)   # UTC server time floor
t1 = dt.datetime(2026, 11, 17, 23, 59)

ok, info = mt5.initialize(), None
if not ok:
    print("INIT_FAIL", mt5.last_error())
    sys.exit(2)
acc = mt5.account_info()
if acc is None or acc.login != 60137964:
    print("ACCOUNT_MISMATCH", acc.login if acc else None)
    sys.exit(3)

deals = mt5.history_deals_get(t0, t1) or []
out_b0, in_by_pos = {}, {}
for d in deals:
    if getattr(d, "magic", 0) != MAGIC:
        continue
    entry = getattr(d, "entry", -1)
    cmt = getattr(d, "comment", "") or ""
    if "B0_INVAL" in cmt:
        out_b0[getattr(d, "position_id", 0)] = d
    if entry == 0:
        in_by_pos[getattr(d, "position_id", 0)] = d

orders = mt5.history_orders_get(t0, t1) or []
sltp = {}
for o in orders:
    if getattr(o, "magic", 0) == MAGIC and (getattr(o, "sl", 0) or getattr(o, "tp", 0)):
        p = getattr(o, "position_id", 0)
        if p:
            sltp[p] = (o.sl, o.tp)

events = []
symset = set()
for posid, od in out_b0.items():
    ind = in_by_pos.get(posid)
    sym = getattr(od, "symbol", None) or (getattr(ind, "symbol", "") if ind else "")
    if not sym:
        continue
    symset.add(sym)
    sl_, tp_ = sltp.get(posid, (0.0, 0.0))
    pnl = (getattr(od, "profit", 0.0) + getattr(od, "commission", 0.0) + getattr(od, "swap", 0.0))
    events.append({
        "pos": posid, "sym": sym,
        "side": "BUY" if ind is not None and getattr(ind, "type", -1) == 0 else "SELL",
        "vol": float(getattr(ind, "volume", 0.01) if ind else 0.01),
        "in_ts": int(getattr(ind, "time", 0)) if ind else None,
        "in_px": float(getattr(ind, "price", 0.0)) if ind else None,
        "out_ts": int(getattr(od, "time", 0)),
        "out_px": float(getattr(od, "price", 0.0)),
        "sl": float(sl_ or 0.0), "tp": float(tp_ or 0.0),
        "pnl_actual": round(float(pnl), 4),
    })
print("B0_OUT_deals:", len(out_b0), "with_IN:", sum(1 for e in events if e["in_px"]), "sl_known:", sum(1 for e in events if e["sl"] > 0))

# M15 per symbol: 老绑定 copy_rates 忽略 start_time 返回最近 N 根, 故拉 6000 根本地切片
# 窗口: [11-09 00:00, 11-15 00:00) UTC (覆盖全部 B0 事件 11-10~11-13 BJT + 18h 持有期)
import numpy as np
W0, W1 = 1762675200, 1763193600  # 2026-11-09T00:00Z, 2026-11-15T00:00Z
RAW_M15 = 15
bars = {}
for sym in sorted(symset):
    r = mt5.copy_rates_from_pos(sym, RAW_M15, 0, 6000) if hasattr(mt5, "copy_rates_from_pos") else None
    if r is None or len(r) == 0:
        bars[sym] = {"source": "MT5_LIVE_FAIL", "n": 0}
        print("M15_FAIL", sym, mt5.last_error())
        continue
    t = (r["time"].astype("int64") // 10**9).astype("int64")
    m = (t >= W0) & (t < W1)
    n_ok = int(m.sum())
    bars[sym] = {"source": "MT5_LIVE", "n": n_ok, "window_utc": [W0, W1],
                 "t": t[m].tolist(), "h": list(r["h"][m]), "l": list(r["l"][m]), "c": list(r["c"][m])}
    print("M15_OK", sym, n_ok, "first:", dt.datetime.utcfromtimestamp(int(t[m][0])) if n_ok else None,
          "last:", dt.datetime.utcfromtimestamp(int(t[m][-1])) if n_ok else None)
mt5.shutdown()

json.dump({
    "ts_unix": int(dt.datetime.now().timestamp()),
    "source": "MT5_LIVE_60137964",
    "mt5_version_note": "3.13.12 channel, entry 0=open/1=close, pnl=profit+commission+swap",
    "events": events, "bars": bars,
}, open(OUT, "w", encoding="utf-8"))
print("WROTE", OUT, "events:", len(events), "syms:", len(bars))
