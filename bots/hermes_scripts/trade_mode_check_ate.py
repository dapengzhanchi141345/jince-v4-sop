# ATE 实跑: 查 AVGO/INTC trade_mode, 全含多空位则输出 OK 否则 HOLD
import MetaTrader5 as mt5, sys
assert mt5.initialize(), mt5.last_error()
ok = 0
for sym in ["AVGO.NAS", "INTC.NAS"]:
    si = mt5.symbol_info(sym)
    ok |= si.trade_mode & 3
    print("%s trade_mode=%s" % (sym, si.trade_mode))
mt5.shutdown()
print("TRADE_MODE_OK" if ok else "TRADE_MODE_HOLD")
sys.exit(0)
