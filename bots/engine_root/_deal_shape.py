
import MetaTrader5 as mt5, json
assert mt5.initialize(), "init failed"
now = __import__("time").time()
d = mt5.history_deals_get(now-30*86400, now) or ()
print("30d deals:", len(d))
# 找带 V1b 的币系 deal（sym 在 6 币里 + 有 pnl）
six = {"BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD"}
coin = [x for x in d if getattr(x,"symbol","") in six]
print("6币 deals:", len(coin))
if coin:
    s = coin[-1]
    print("sample deal fields:", [a for a in ["ticket","symbol","entry","side","type","price","volume","profit","sl","tp","magic","comment","time"] if hasattr(s,a)])
    print("last deal:", {a: getattr(s,a) for a in ["symbol","entry","side","type","price","volume","profit","magic","comment"] if hasattr(s,a)})
# 找带 SL 的 V1b 开仓单（ORB leg 通常带 SL/TP）
o = mt5.history_orders_get(now-30*86400, now) or ()
co = [x for x in o if getattr(x,"symbol","") in six and getattr(x,"sl",0)>0]
print("6币开仓单带SL:", len(co))
if co:
    print("sample open order:", {a: getattr(co[-1],a) for a in ["symbol","type","price","sl","tp","volume","magic","comment"] if hasattr(co[-1],a)})
mt5.shutdown()
