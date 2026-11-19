import sys, json
try:
    import MetaTrader5 as mt5
except Exception as e:
    print(json.dumps({"error":"import_failed","detail":str(e)})); sys.exit(0)
out={"connect":False}
try:
    ok = mt5.initialize()
    out["connect"]=ok
    if not ok:
        print(json.dumps(out, ensure_ascii=False)); sys.exit(0)
    acc = mt5.account_info()
    out["account"]=acc.login if acc else None
    out["server"]=acc.server if acc else None
    out["balance"]=round(acc.balance,2) if acc else None
    out["equity"]=round(acc.equity,2) if acc else None
    out["trade_allowed"]=acc.trade_allowed if acc else None
    # 当前持仓
    pos = mt5.positions_get()
    out["positions"]=[]
    if pos:
        for p in pos:
            out["positions"].append({"symbol":p.symbol,"type":"BUY" if p.type==0 else "SELL","volume":round(p.volume,2),"open":round(p.price_open,5),"profit":round(p.profit,2),"sl":round(p.sl,5),"tp":round(p.tp,5),"ticket":p.ticket,"comment":p.comment})
    # 近2日成交
    from datetime import datetime, timedelta
    now = datetime.now()
    t2 = now - timedelta(days=2)
    deals = mt5.history_deals_get(t2, now)
    out["deals_2d_count"]=len(deals) if deals else 0
    out["deals"]=[]
    if deals:
        for d in sorted(deals, key=lambda x:x.time)[-25:]:
            out["deals"].append({"symbol":d.symbol,"type":("BUY" if d.type in (0,1) else "SELL"),"volume":round(d.volume,2),"price":round(d.price,5),"profit":round(d.profit,2),"time":d.time,"ticket":d.ticket,"magic":d.magic})
except Exception as e:
    out["error"]=str(e)
# 注意: 故意不调用 mt5.shutdown(), 以免断开 live 共享连接
print(json.dumps(out, ensure_ascii=False))
