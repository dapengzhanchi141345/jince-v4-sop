# R8: 机构订单流四步流程数据底座 - AVGO/INTC H1/M15 实读 + 量能分位 + 近20笔tick方向
import MetaTrader5 as mt5, time
import numpy as np
assert mt5.initialize(), mt5.last_error()
for sym in ["AVGO.NAS", "INTC.NAS"]:
    h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 120)
    m15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 96)
    print("=== %s ===" % sym)
    for tf, arr in [("H1", h1), ("M15", m15)]:
        if arr is None or len(arr) == 0:
            print(tf, "FAIL", mt5.last_error()); continue
        o, c, h, l, v = arr["open"], arr["close"], arr["high"], arr["low"], arr["tick_volume"]
        last = c[-1]
        ema50 = float(np.mean(c[-50:]))
        ema20 = float(np.mean(c[-20:]))
        hh20, ll20 = float(np.max(h[-20:])), float(np.min(l[-20:]))
        # 量能分位(最近200根内)
        vp = np.percentile(v, [25, 50, 75])
        # 最近8根方向
        dir8 = "".join("U" if c[i] > o[i] else ("D" if c[i] < o[i] else "=") for i in range(len(c)-8, len(c)))
        print("%s last=%.4g EMA20=%.4g EMA50=%.4g 20H高/低=%.4g/%.4g 量分位P25/50/75=%s 近8根=%s" % (
            tf, last, ema20, ema50, hh20, ll20, [int(x) for x in vp], dir8))
    t = mt5.symbol_info_tick(sym)
    print("tick: bid=%.4g ask=%.4g spread=%.4g age_min=%.1f" % (t.bid, t.ask, t.ask-t.bid, (time.time()-t.time)/60 if t.time else -1))
    print()
mt5.shutdown()
print("OK")
