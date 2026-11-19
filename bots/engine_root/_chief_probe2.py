# -*- coding: utf-8 -*-
# 只读: 5仓的magic + 全量 vs magic=20260902 过滤差(坐实全链扫描为何漏读live腿)
import MetaTrader5 as mt5
PATH=r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe"
ok=mt5.initialize(PATH)
if not ok: print("init失败",mt5.last_error()); raise SystemExit
full=mt5.positions_get() or []
magic=mt5.positions_get(magic=20260902) or []
print("全量持仓=%d | magic=20260902 过滤=%d" % (len(full),len(magic)))
for p in full:
    print("  %s magic=%s %s%s | 开%.2f | 浮%.2f | 注释=%s" % (p.symbol,p.magic,"SELL" if p.type==0 else "BUY",p.volume,p.price_open,p.profit+p.swap,(p.comment or '')[:30]))
info=mt5.account_info()
print("equity=%.2f balance=%.2f 回撤=%.2f%%" % (info.equity,info.balance,abs((info.equity/info.balance-1)*100)))
mt5.shutdown()
