# -*- coding: utf-8 -*-
import os, time, json
import numpy as np
import MetaTrader5 as mt5
assert mt5.initialize(), "init failed"
now = int(time.time())
deals = mt5.history_deals_get(now-90*86400, now) or ()
# XAU 真实平仓 4 笔详情
xau = [d for d in deals if d.symbol=="XAUUSD" and d.entry in (1,3) and abs(d.profit or 0)>1e-6]
print("XAUUSD 真实平仓 %d 笔:" % len(xau))
for d in xau:
    print("  ticket=%d  entry=%s  profit=$%.2f  comment=%r  time=%s  volume=%s" % (
        d.ticket, {0:"IN",1:"OUT",2:"INOUT",3:"OUT_BY"}.get(d.entry,d.entry),
        d.profit or 0, (d.comment or "")[:40],
        time.strftime("%Y-%m-%d %H:%M", time.gmtime(d.time)), d.volume))
# 是否带 SL 的老批次 (无 SL = R 不可回填, 只能金额 PF)
# 找 XAU 开仓单 magic/comment
o = mt5.history_orders_get(now-90*86400, now) or ()
xo = [x for x in o if x.symbol=="XAUUSD"]
print("XAU 开仓单 %d: magic 集合=%s  带SL=%d" % (len(xo), sorted(set(x.magic for x in xo)), sum(1 for x in xo if x.sl and x.sl>0)))
for x in xo[:6]:
    print("   type=%s magic=%s sl=%s comment=%r" % (x.type, x.magic, x.sl, (x.comment or "")[:30]))
mt5.shutdown()
