# -*- coding: utf-8 -*-
import json, datetime as dt
import MetaTrader5 as mt5
out={}
ok=mt5.initialize()
out['connect']=bool(ok)
if not ok:
    out['err']=str(mt5.last_error()); print(json.dumps(out,ensure_ascii=False)); raise SystemExit
ai=mt5.account_info()
if ai:
    out['account']={'login':ai.login,'server':ai.server,'balance':round(ai.balance,2),
                    'equity':round(ai.equity,2),'profit':round(ai.profit,2),
                    'margin_free':round(ai.margin_free,2),'trade_allowed':ai.trade_allowed}
poss=mt5.positions_get() or []
out['positions']=[{'ticket':p.ticket,'symbol':p.symbol,'type':'BUY' if p.type==0 else 'SELL',
                   'volume':p.volume,'price_open':p.price_open,'sl':p.sl,'tp':p.tp,
                   'profit':round(p.profit,2),
                   'time':dt.datetime.fromtimestamp(p.time).strftime('%Y-%m-%d %H:%M:%S')} for p in poss]
now=dt.datetime.now(); frm=now-dt.timedelta(days=2)
deals=mt5.history_deals_get(frm,now) or []
dl=[]
for d in deals:
    if d.type in (0,1):
        dl.append({'ticket':d.ticket,'symbol':d.symbol,'type':'BUY' if d.type==0 else 'SELL',
                   'entry':d.entry,'volume':d.volume,'price':d.price,'profit':round(d.profit,2),
                   'commission':round(d.commission,2),'swap':round(d.swap,2),
                   'time':dt.datetime.fromtimestamp(d.time).strftime('%Y-%m-%d %H:%M:%S')})
out['deals_2d']=dl
out['deals_2d_count']=len(dl)
out['deals_2d_net']=round(sum(x['profit']+x['commission']+x['swap'] for x in dl),2)
# 7-day window
frm7=now-dt.timedelta(days=7)
d7=mt5.history_deals_get(frm7,now) or []
d7l=[x for x in d7 if x.type in (0,1)]
out['deals_7d_count']=len(d7l)
out['deals_7d_net']=round(sum(x.profit+x.commission+x.swap for x in d7l),2)
out['last_deal_7d']=(dt.datetime.fromtimestamp(max(x.time for x in d7l)).strftime('%Y-%m-%d %H:%M:%S') if d7l else None)
# ADX-ish: current H1 bars availability check per symbol
syms=['XAUUSD','BTCUSD','ETHUSD','EURUSD','GBPUSD','USDJPY','GBPJPY']
tk={}
for s in syms:
    t=mt5.symbol_info_tick(s)
    tk[s]= round(t.bid,3) if t else None
out['ticks']=tk
mt5.shutdown()
print(json.dumps(out,ensure_ascii=False,indent=1))
