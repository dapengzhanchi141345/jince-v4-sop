# -*- coding: utf-8 -*-
import MetaTrader5 as mt5, json, csv, sys, time
from datetime import datetime

ENGINE = r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe"
if not mt5.initialize(ENGINE):
    print("INIT_FAIL", mt5.last_error()); sys.exit(1)

acc = mt5.account_info()
print("attached:", acc.login if acc else None, "|", acc.server if acc else None, "|", acc.currency if acc else None)

# 1) 找对品种名
syms = [s.name for s in mt5.symbols_get() if s is not None]
xau = [s for s in syms if 'XAU' in s.upper() or 'GOLD' in s.upper()]
print("候选品种:", xau[:10] if xau else 'NONE, all=%s' % len(syms))
sym = xau[0] if xau else 'XAUUSD'
print("using symbol:", sym)

# 2) 服务器时间
svr = mt5.terminal_info()
print("server_time:", svr.time if svr else None, "timezone_offset:", svr.timezone if svr else None)

# 3) 拉 M5: 9/28 00:00 ~ 10/09 00:00 (服务器本地时间)
from datetime import datetime
t0 = datetime(2026,9,28,0,0)
t1 = datetime(2026,10,9,0,0)
import calendar
start = calendar.timegm(t0.utctimetuple())
end   = calendar.timegm(t1.utctimetuple())
rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, start, end)
print("copy_rates_range bars:", len(rates) if rates else 0, mt5.last_error() if not rates else '')

recs=[]
if rates:
    for r in rates:
        ts=time.gmtime(r["time"])
        recs.append({"t": datetime(*ts[:6]).strftime("%Y-%m-%d %H:%M"),
                     "o":round(float(r["open"]),2),"h":round(float(r["high"]),2),
                     "l":round(float(r["low"]),2),"c":round(float(r["close"]),2),
                     "v":int(r["tick_volume"])})
print("in-range M5 bars:", len(recs), (recs[0]["t"] if recs else '-'), '->', (recs[-1]["t"] if recs else '-'))
if recs:
    json.dump(recs, open(r"E:\workbuddy\xau_m5_0927_1008.json","w"), ensure_ascii=False)
    with open(r"E:\workbuddy\xau_m5_0927_1008.csv","w",newline="") as f:
        w=csv.writer(f); w.writerow(["time","open","high","low","close","tickvol"])
        for r in recs: w.writerow([r["t"],r["o"],r["h"],r["l"],r["c"],r["v"]])
    print("saved json+csv")
mt5.shutdown()
