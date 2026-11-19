
import sys; sys.path.insert(0,"E:/GoldstrategyEngine"); sys.path.insert(0,"E:/GoldstrategyEngine/multi_agent/trading")
import MetaTrader5 as mt5
import weekly_forecaster as wf
mt5.initialize(); mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
for sym in ["BTCUSD","XAUUSD","SOLUSD"]:
    f = wf.from_mt5(sym)
    if f:
        print(f"[OK] {sym} state={f['state']}  下周带 [{f['next_lo']:.5g} ~ {f['next_hi']:.5g}]  "
              f"参照中值={f['ref_mid']:.5g}  周ATR={f['range_atr']:.5g}  "
              f"20周突破带[{f['dc_lo20']:.5g}~{f['dc_hi20']:.5g}]  前日高低{f['pvl']:.5g}~{f['pvh']:.5g}")
    else:
        print(f"[!] {sym} 预测返回None(数据不足/异常, fail-open)")
mt5.shutdown()
