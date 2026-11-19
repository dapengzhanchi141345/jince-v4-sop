# R1+R9: L1 tick 管道首跑 - copy_ticks_range 实读 + 落盘
import MetaTrader5 as mt5, time, sys
ok, err = mt5.initialize(), None
if not ok:
    print("[FAIL] mt5.initialize", mt5.last_error()); sys.exit(1)
sym = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"
from_t, to_t = int(time.time()) - 43200, int(time.time())  # 近12h
try:
    flags = mt5.TICKS_ALL
except AttributeError:
    flags = 1
ticks = mt5.copy_ticks_range(sym, from_t, to_t, flags)
print("ticks:", len(ticks) if ticks is not None else None, "err:", mt5.last_error())
if ticks is not None and len(ticks) > 0:
    import csv, os
    out = r"E:/GoldstrategyEngine/data/orderflow_ticks/%s_%s.csv" % (sym, time.strftime("%Y%m%d_%H%M"))
    with open(out, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["time","open","high","low","close","volume_tick"])
        n = 0
        for t in ticks:
            row = [int(t[0]), t[1], t[2], t[3], t[4], int(t[5])]
            w.writerow(row); n += 1
    print("落盘:", out, "rows:", n)
    print("首行:", ticks[0])
    print("尾行:", ticks[-1])
    print("样本中位量分位(前100):", sorted(t[5] for t in ticks[:100])[:3])
mt5.shutdown()
print("OK")
