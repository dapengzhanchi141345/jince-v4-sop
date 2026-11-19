# R1修正+R8数据底座: tick字段纠正 + AVGO/INTC拉取
import MetaTrader5 as mt5, time, csv
import numpy as np
assert mt5.initialize(), mt5.last_error()
for sym in ["XAUUSD", "AVGO.NAS", "INTC.NAS"]:
    ticks = mt5.copy_ticks_range(sym, int(time.time())-43200, int(time.time()), 1)
    if ticks is None or len(ticks) == 0:
        print(sym, "FAIL", mt5.last_error()); continue
    n = len(ticks)
    vols = sorted(int(t[6]) for t in ticks)
    q = np.percentile(vols, [10, 25, 50, 75, 90])
    out = r"E:/GoldstrategyEngine/data/orderflow_ticks/%s_%s.csv" % (sym.replace(".", "_"), time.strftime("%Y%m%d_%H%M"))
    with open(out, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["time_s","open","high","low","close","vol_tick","spread","time_ms"])
        for t in ticks:
            w.writerow([int(t[0]), t[1], t[2], t[3], t[4], int(t[6]), t[7], int(t[5])])
    print(sym, "ticks:", n, "量分位P10/25/50/75/90:", [int(x) for x in q], "| 落盘:", out)
mt5.shutdown()
print("OK")
