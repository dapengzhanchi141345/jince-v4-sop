"""查询MT5交易历史"""
import MetaTrader5 as mt5
from datetime import datetime

mt5.initialize(path=r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe")
mt5.login(60043976, password="", server="TradeMaxGlobal-Demo")

print("=== 当前持仓 ===")
for s in ["BTCUSD", "ETHUSD"]:
    pos = mt5.positions_get(symbol=s)
    if pos and len(pos) > 0:
        for p in pos:
            d = "BUY" if p.type == 0 else "SELL"
            print(f"  {s} {d} {p.volume} lot @ {p.price_open:.2f} SL={p.sl:.2f} TP={p.tp:.2f} Profit={p.profit:.2f}")
    else:
        print(f"  {s}: 无持仓")

print("\n=== 今日成交历史 (最近15笔) ===")
deals = mt5.history_deals_get(datetime(2026, 7, 4, 0, 0), datetime.now())
if deals:
    for d in reversed(deals[-15:]):
        direction = "BUY" if d.type == 0 else "SELL"
        print(f"  {d.time} | {d.symbol} | {direction} | {d.volume} lot | ${d.price:.2f} | Profit=${d.profit:.2f} | {d.comment}")
else:
    print("  无成交历史")

print(f"\n总成交: {len(deals) if deals else 0} 笔")

mt5.shutdown()
