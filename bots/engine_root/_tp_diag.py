import numpy as np, datetime, sys
sys.path.insert(0, "E:/GoldstrategyEngine")
src = open("E:/GoldstrategyEngine/_trailing_protocols.py", encoding="utf-8").read().replace('if __name__ ==', 'if False and __name__ ==')
ns = {}
exec(compile(src, "_tp", "exec"), ns)

M, D = ns["load"]("BTCUSD")
t = M["t"]
print("M30 span days:", int((t[-1]-t[0])/86400), "bars:", len(t))
print("M30 first:", datetime.datetime.utcfromtimestamp(t[0]))
print("M30 last:", datetime.datetime.utcfromtimestamp(t[-1]))
d = D["t"]
print("D1 span days:", int((d[-1]-d[0])/86400), "bars:", len(d))
print("D1 first:", datetime.datetime.utcfromtimestamp(d[0]))
print("D1 last:", datetime.datetime.utcfromtimestamp(d[-1]))
b = ns["stream_events"](M, D)
s = ns["stream_events_sell"](M, D)
print("BUY fills:", len(b), "SELL fills:", len(s))
if b:
    print("first buy ts:", datetime.datetime.utcfromtimestamp(b[0]["ts"]))
    print("last  buy ts:", datetime.datetime.utcfromtimestamp(b[-1]["ts"]))
