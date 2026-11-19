# 今晚观察腿(天天有单起点): 4步判断+挂单 0.01手 (magic 20261104, 12h到期哨另排)
import MetaTrader5 as mt5, time, json
import numpy as np
assert mt5.initialize(), mt5.last_error()
cands = [
    dict(sym="XAGUSD", bias=0),
    dict(sym="USDJPY", bias=0),
    dict(sym="EURUSD", bias=0),
    dict(sym="JPN225", bias=-1),
]
plans = []
for c in cands:
    sym = c["sym"]
    m15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 96)
    h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 24)
    tick = mt5.symbol_info_tick(sym)
    si = mt5.symbol_info(sym)
    if m15 is None or h1 is None or tick is None:
        print(sym, "SKIP 数据缺"); continue
    o, hc, c15, v15 = h1["open"], h1["close"], m15["close"], m15["tick_volume"]
    ema20 = float(np.mean(c15[-20:])); ema50 = float(np.mean(c15[-50:]))
    hh24 = float(np.max(h1["high"][-24:])); ll24 = float(np.min(h1["low"][-24:]))
    spread = tick.ask - tick.bid
    if si.trade_mode & 1:
        pass
    print("%s last=%.5g EMA20=%.5g EMA50=%.5g 24H高/低=%.5g/%.5g 量分位=%s spread=%.5g trade_mode=%s age_min=%.1f" % (
        sym, tick.bid, ema20, ema50, hh24, ll24, [int(x) for x in np.percentile(v15, [25,50,75])],
        spread, si.trade_mode, (time.time()-tick.time)/60 if tick.time else -1))
# 4步判: XAG 回踩EMA50+M15 U结构 做多; USDJPY 钉24H低点上方+回调不破 做多
for p in [dict(sym="XAGUSD", side=mt5.ORDER_TYPE_BUY_LIMIT, ref="EMA50回踩"),
          dict(sym="USDJPY", side=mt5.ORDER_TYPE_BUY_LIMIT, ref="24H低点上沿回踩")]:
    sym = p["sym"]
    m15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 96)
    h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 24)
    tick = mt5.symbol_info_tick(sym); si = mt5.symbol_info(sym)
    ema50 = float(np.mean(m15["close"][-50:]))
    hh24, ll24 = float(np.max(h1["high"][-24:])), float(np.min(h1["low"][-24:]))
    pt = si.point; dp = si.digits
    if sym == "XAGUSD":
        entry = round(float(np.mean(m15["close"][-10:])), dp)          # 近10根均值(密集区)
        sl = round(ll24 - 5*pt, dp); tp = round(entry + (entry-sl)*1.6, dp)
    else:
        entry = round(ll24 + 8*pt, dp)                                     # 24H低点上方8点回踩
        sl = round(ll24 - 10*pt, dp); tp = round(entry + (entry-sl)*1.6, dp)
    if entry >= tick.bid:  # BUY_LIMIT 合法=挂单价低于bid, 两品种同口径
        print(sym, "SKIP BUY_LIMIT 需挂单低于bid(%.5g>=bid %.5g)" % (entry, tick.bid)); continue
        print(sym, "SKIP 挂单价穿现价"); continue
    r = mt5.order_send({"symbol": sym, "action": mt5.TRADE_ACTION_DEAL,
        "type": p["side"], "volume": 0.01, "price": entry, "sl": sl, "tp": tp,
        "deviation": 30, "magic": 20261104, "comment": "LX-4step-obs",
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC})
    print(sym, "LX-4step-obs retcode:", r.retcode if r else None, mt5.last_error())
mt5.shutdown()
print("OK")
