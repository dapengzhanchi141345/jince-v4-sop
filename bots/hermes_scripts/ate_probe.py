import MetaTrader5 as mt5
ok, err = mt5.initialize(15000), None
print("ATE probe:", ok, mt5.last_error())
mt5.shutdown()