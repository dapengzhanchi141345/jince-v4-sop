import mt5, time
from datetime import datetime, timezone, timedelta

def now(): return datetime.now(timezone(timedelta(hours=8))).strftime('%H:%M:%S')

print(f'[{now()}] MT5 预检开始')
for k in range(2):
    info = mt5.account_info()
    if info is None:
        print('  读失败:', mt5.last_error()); break
    pos = mt5.positions_get()
    ord_ = mt5.orders_get()
    print(f'  读{k+1}: equity={info.equity:.2f} bal={info.balance:.2f} positions={len(pos)} pending={len(ord_)}')
    time.sleep(2)

print('--- 品种名核验 ---')
for cand in ['AVGO','AVGO.NAS','AVGO_US','INTC','INTC.NAS','INTC_US']:
    s = mt5.symbol_info(cand)
    if s: print(f'  {cand}: 存在 bid={s.bid} ask={s.ask}')
    else: print(f'  {cand}: 不存在')

print('--- 挂单/持仓明细 ---')
for o in (mt5.orders_get() or []):
    print(f'  挂单: t={o.ticket} {o.symbol} px={o.price} magic={o.magic}')
for p in (mt5.positions_get() or []):
    print(f'  持仓: t={p.ticket} {p.symbol} {"BUY" if p.type==0 else "SELL"} lots={p.volume} open={p.price_open} magic={p.magic}')
