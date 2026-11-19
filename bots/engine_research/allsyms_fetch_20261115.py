# 全品种清单探测 + M15 可取性 (只读, 60137964 模拟户)
import os, sys, json
os.environ.setdefault("MT5_TERMINAL", r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe")
os.environ.setdefault("MT5_LOGIN", "60137964")
import MetaTrader5 as mt5
import numpy as np

ok = mt5.initialize()
if not ok:
    print("INIT FAIL", mt5.last_error()); sys.exit(1)
acct = mt5.account_info()
print("account:", acct.login, "trade_allowed:", mt5.terminal_info().trade_allowed)
syms = mt5.symbols_get() or []
print("symbols_total:", mt5.symbols_total(), "got:", len(syms))
# 分类筛选: 主流 G10 外汇 + 贵金属 + 股指 + 币系 (排除 exotic/指数碎片/股票)
FX = ["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCHF","NZDUSD","USDCAD","EURGBP","EURJPY","GBPJPY","AUDJPY","USDIDR","XAGUSD","XAUUSD","XPTUSD"]
IDX = ["US500","US30","NAS100","GER40","JPN225","UK100","AUS200","HK50","SIXH"]
CR = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD","DOGEUSD","ADAUSD","AVAXUSD"]
WANT = []
have = set(s.name for s in syms)
# TMGM 命名可能带点: 试 直接名 / 名.后缀
alt = {}
for s in syms:
    base = s.name.split('.')[0]
    alt.setdefault(base, []).append(s.name)
for w in FX + IDX + CR:
    if w in have:
        WANT.append(w)
    elif w in alt:
        WANT.append(alt[w][0])
    else:
        # 常见别名
        for cand in [w + "i", w + ".c", "c" + w, w + "c", "o" + w, w + "m"]:
            if cand in have:
                WANT.append(cand); break
print("want list (%d):" % len(WANT), WANT)
out = []
for w in WANT:
    if not mt5.symbol_select(w, True):
        print("%s select FAIL %s" % (w, mt5.last_error())); continue
    rates = mt5.copy_rates_from_pos(w, 15, 0, 40000)
    if rates is None or len(rates) == 0:
        print("%s EMPTY %s" % (w, mt5.last_error())); continue
    d = rates
    arr = dict(t=np.asarray(d["time"], dtype="int64"), o=np.asarray(d["open"], dtype="float64"),
               h=np.asarray(d["high"], dtype="float64"), l=np.asarray(d["low"], dtype="float64"),
               c=np.asarray(d["close"], dtype="float64"), tv=np.asarray(d["tick_volume"].astype(float)))
    import datetime as dt
    import glob, os as o2
    o2.makedirs(r"E:\GoldstrategyEngine\research\allsyms_m15", exist_ok=True)
    p = r"E:\GoldstrategyEngine\research\allsyms_m15\%s_M15.npz" % w
    np.savez(p, **arr)
    t0 = dt.datetime.utcfromtimestamp(int(arr["t"][0]))
    t1 = dt.datetime.utcfromtimestamp(int(arr["t"][-1]))
    out.append(dict(sym=w, n=len(arr["t"]), t0=str(t0), t1=str(t1)))
    print("%-10s %d bars %s -> %s UTC" % (w, len(arr["t"]), t0, t1), flush=True)
mt5.shutdown()
print("DONE", len(out), "symbols ->", r"E:\GoldstrategyEngine\research\allsyms_m15")
