import json
import MetaTrader5 as mt5
ok=mt5.initialize()
ods=mt5.orders_get()
print("pending_count:", 0 if ods is None else len(ods))
if ods:
    for o in ods:
        try:
            d=o.__dict__
        except Exception:
            d={k:getattr(o,k) for k in dir(o) if not k.startswith('_')}
        keep={k:v for k,v in (d or {}).items() if k in ('ticket','symbol','type','volume','price','sl','tp','magic','comment','time')}
        print(json.dumps(keep,ensure_ascii=False,default=str))
