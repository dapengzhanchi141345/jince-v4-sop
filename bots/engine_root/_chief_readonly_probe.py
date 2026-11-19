# -*- coding: utf-8 -*-
# 只读探针: terminal64 账户 60137964 实盘持仓/equity. 纯读, 不撤仓不下单.
import MetaTrader5 as mt5
PATH = r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe"
ok = mt5.initialize(PATH)
if not ok:
    print("initialize 失败", mt5.last_error()); mt5.shutdown(); raise SystemExit
# 空密码=靠 terminal 已预登录; 若需显式 login 再试
info = mt5.account_info()
print("登录账户 =", info.login if info else None, "| SERVER =", info.server if info else None,
      "| EQUITY =", round(info.equity,2) if info else None, "| BALANCE =", round(info.balance,2) if info else None)
if info is None:
    ok2 = mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
    print("显式 login =", ok2, mt5.last_error())
    info = mt5.account_info()
pos = mt5.positions_get() or []
print("=== 实盘持仓 %d 仓 ===" % len(pos))
tot = 0.0
for p in pos:
    fl = p.profit + p.swap
    tot += fl
    tk = mt5.symbol_info_tick(p.symbol)
    now = (tk.bid if (tk and p.type==1) else (tk.ask if tk else 0)) or p.price_open
    print("%s | %s | %s手 | 开@%.2f | 浮%.2f | SL/TP=[%.0f/%.0f]" % (
        p.symbol, "SELL" if p.type==0 else "BUY", p.volume, p.price_open, fl, p.sl, p.tp))
bal = info.balance if info else 0; eq = info.equity if info else 0
print("=== 总浮 %.2f | equity=%.2f | 回撤=%.2f%% ===" % (tot, eq, abs((eq/bal-1)*100) if bal else 0))
mt5.shutdown()
