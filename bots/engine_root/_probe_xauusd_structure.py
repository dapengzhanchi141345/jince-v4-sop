import MetaTrader5 as mt5, datetime
EXE="E:/mt5_friend_observer/terminal64.exe"
if not mt5.initialize(path=EXE, timeout=90000):
    print("INIT_FAIL", mt5.last_error()); raise SystemExit
if not mt5.login(60129252, password="Aa141345$", server="TradeMaxGlobal-Demo"):
    print("LOGIN_FAIL", mt5.last_error()); mt5.shutdown(); raise SystemExit
t=mt5.symbol_info_tick("XAUUSD")
si=mt5.symbol_info("XAUUSD")
print("TICK bid=",t.bid,"ask=",t.ask,"spread_pt=",si.spread,"swap_short=",si.swap_short)
for tf,name,n in [(mt5.TIMEFRAME_D1,"D1",12),(mt5.TIMEFRAME_H4,"H4",30),(mt5.TIMEFRAME_H1,"H1",40)]:
    r=mt5.copy_rates_from_pos("XAUUSD",tf,0,n)
    if r is None: print(name,"none"); continue
    hi=max(x['high'] for x in r); lo=min(x['low'] for x in r)
    print(f"{name} last{n}: high={hi:.2f} low={lo:.2f}  (SL4647.40 - high = {4647.40-hi:.2f})")
# ATR(14) D1 rough
r=mt5.copy_rates_from_pos("XAUUSD",mt5.TIMEFRAME_D1,0,20)
trs=[]
for i in range(1,len(r)):
    trs.append(max(r[i]['high']-r[i]['low'],abs(r[i]['high']-r[i-1]['close']),abs(r[i]['low']-r[i-1]['close'])))
print("D1 ATR14=",round(sum(trs[-14:])/14,2))
r4=mt5.copy_rates_from_pos("XAUUSD",mt5.TIMEFRAME_H4,0,20)
t4=[]
for i in range(1,len(r4)):
    t4.append(max(r4[i]['high']-r4[i]['low'],abs(r4[i]['high']-r4[i-1]['close']),abs(r4[i]['low']-r4[i-1]['close'])))
print("H4 ATR14=",round(sum(t4[-14:])/14,2))
# 自入场以来最高价(M5)
first_entry=1788172200
r5=mt5.copy_rates_from("XAUUSD",mt5.TIMEFRAME_M5,datetime.datetime.fromtimestamp(first_entry),400)
if r5 is not None and len(r5):
    print("since-1st-entry M5 max high=",round(max(x['high'] for x in r5),2),"min low=",round(min(x['low'] for x in r5),2),"bars=",len(r5))
mt5.shutdown()
