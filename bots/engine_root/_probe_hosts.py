import MetaTrader5 as mt5, json, datetime
mt5.initialize()
syms=["XAUUSD","EURUSD","DE30","EURTRY"]
P={"M15":mt5.TIMEFRAME_M15,"H1":mt5.TIMEFRAME_H1,"H4":mt5.TIMEFRAME_H4,"D1":mt5.TIMEFRAME_D1}
def ts(x): return datetime.datetime.utcfromtimestamp(int(x["time"])).strftime('%m-%d %H:%M')
out={}
for s in syms:
    if not mt5.symbol_select(s, True):
        out[s]={"err":"select_fail"}; continue
    tick=mt5.symbol_info_tick(s)
    d={"bid":float(tick.bid) if tick else None,"ask":float(tick.ask) if tick else None}
    for name in ["M15","H1","H4","D1"]:
        arr=mt5.copy_rates_from_pos(s,P[name],0,6)
        d[name]=[(ts(x),float(x["close"])) for x in list(arr)] if arr is not None and len(arr) else []
    out[s]=d
print(json.dumps(out,ensure_ascii=False))
mt5.shutdown()
