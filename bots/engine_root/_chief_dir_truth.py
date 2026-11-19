# -*- coding: utf-8 -*-
# 只读·方向判真: 用 server 端 p.profit 符号 + 现价 vs 开仓价 独立推真实方向, 不信任任何 label 映射.
# MT5 规范: POSITION_TYPE_BUY=0, POSITION_TYPE_SELL=1. 用 profit 符号交叉验证.
import MetaTrader5 as mt5, datetime
PATH=r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe"
ok=mt5.initialize(PATH)
if not ok: print("init失败",mt5.last_error()); raise SystemExit
info=mt5.account_info()
bal=info.balance; eq=info.equity
pos=mt5.positions_get() or []
print("=== 账户 %s | balance=%.2f equity=%.2f | 回撤自余额=%.2f%% | 活持仓=%d ==="%(info.login,bal,eq,abs((eq/bal-1)*100) if bal else 0,len(pos)))
tot=0.0
for p in pos:
    fl=p.profit+p.swap; tot+=fl
    tk=mt5.symbol_info_tick(p.symbol)
    bid=(tk.bid if tk else None); ask=(tk.ask if tk else None)
    op=p.price_open
    # 独立推方向: BUY在价涨时盈利; SELL在价跌时盈利
    nowpx = bid if bid else ask
    moved = (nowpx - op) if (nowpx and op) else None
    # profit>0: 若价涨->是BUY; 若价跌->是SELL. profit<0: 若价涨->是SELL; 若价跌->是BUY. profit==0 中性
    if fl>0:
        by_profit = "BUY" if (moved and moved>0) else "SELL"
    elif fl<0:
        by_profit = "SELL" if (moved and moved>0) else "BUY"
    else:
        by_profit = "flat?"
    # 按 MT5 规范: type 0=BUY 1=SELL
    by_type = "BUY" if p.type==0 else "SELL"
    agree = "一致" if by_profit==by_type else "★冲突★"
    print("  #%d %-8s raw_type=%s => 规范方向=%s | 盈亏反推=%s [%s] | 开@%.5f 现@%.5f 动%.5f | 浮%.2f magic=%s"%(
        p.ticket, p.symbol, p.type, by_type, by_profit, agree, op, nowpx or 0, (moved or 0), fl, p.magic))
print("=== 总浮=%.2f (正=净赚 负=净亏) | 5仓 raw_type 分布: %s ==="%(tot, {t:sum(1 for p in pos if p.type==t) for t in sorted({p.type for p in pos})}))
mt5.shutdown()
