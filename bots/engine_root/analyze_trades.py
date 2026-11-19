"""Analyze trade history and identify issues"""
import MetaTrader5 as mt5
from datetime import datetime

print("=" * 60)
print("GOLDSTRATEGY GUILD - TRADE ANALYSIS")
print("=" * 60)

mt5.initialize()
mt5.login(60043976, password="", server="TradeMaxGlobal-Demo")

# Account info
acct = mt5.account_info()
print(f"\nAccount: ${acct.balance:.2f} | Equity: ${acct.equity:.2f}")

# Open positions
pos = mt5.positions_get()
print(f"\n=== OPEN POSITIONS ({len(pos) if pos else 0}) ===")
if pos:
    for p in pos:
        tn = "BUY" if p.type==0 else "SELL"
        print(f"  {tn} {p.volume} {p.symbol}")
        print(f"    Entry: ${p.price_open:.2f}")
        print(f"    Now:   ${p.price_current:.2f}")
        print(f"    SL:    ${p.sl} | TP: ${p.tp}")
        print(f"    P/L:   ${p.profit:.2f}")
        print(f"    Ticket: {p.ticket} | Magic: {p.magic}")

# Today's deals
hist = mt5.history_deals_get(datetime(2026,7,4,0,0), datetime.now())
print(f"\n=== COMPLETED TRADES TODAY ({len(hist) if hist else 0}) ===")
if hist:
    total_profit = 0
    wins = 0
    losses = 0
    for h in hist:
        tn = "BUY" if h.type==0 else "SELL"
        print(f"  {tn} {h.volume} @ ${h.price:.2f} | P/L=${h.profit:.2f} | {h.comment}")
        total_profit += h.profit
        if h.profit > 0: wins += 1
        elif h.profit < 0: losses += 1
    print(f"\n  Summary: {wins}W / {losses}L | Total P/L: ${total_profit:.2f}")

# Key metrics
print(f"\n=== KEY METRICS ===")
print(f"  Balance: ${acct.balance:.2f}")
print(f"  Equity:  ${acct.equity:.2f}")
if pos:
    p = pos[0]
    print(f"  Open P/L: ${p.profit:.2f}")
    print(f"  Drawdown from entry: {((p.price_current-p.price_open)/p.price_open*100):.2f}%")
    print(f"  No SL set: {'YES - CRITICAL!' if p.sl==0.0 else 'OK'}")

mt5.shutdown()
print("\nDONE")
