# 22:35+ 美股批四步首跑: AVGO BUY_STOP + INTC BUY_LIMIT (magic 20261105, 事件日0.5x, 12h到期=11-07 10:20红线/03:55哨兜底)
import MetaTrader5 as mt5, json, time, os
from datetime import datetime
assert mt5.initialize(), mt5.last_error()

ORDERS = [
    dict(symbol="AVGO.NAS", type=mt5.ORDER_TYPE_BUY_STOP, price=308.5, sl=302.1, tp=318.0,
         volume=1.0, deviation=50, magic=20261105, comment="LX-AVGO-S4"),
    dict(symbol="INTC.NAS", type=mt5.ORDER_TYPE_BUY_LIMIT, price=54.8, sl=53.9, tp=56.15,
         volume=1.0, deviation=20, magic=20261105, comment="LX-INTC-S4"),
]
results = []
for o in ORDERS:
    tick = mt5.symbol_info_tick(o["symbol"])
    r = mt5.order_send({**o, "type_time": mt5.ORDER_TIME_GTC,
                       "type_filling": mt5.ORDER_FILLING_IOC})
    res = {"symbol": o["symbol"], "retcode": r.retcode, "comment": r.comment,
           "order": r.order, "req_price": o["price"],
           "tick": {"bid": tick.bid, "ask": tick.ask},
           "ts": time.strftime("%H:%M:%S"), "magic": o["magic"]}
    results.append(res)
    print(json.dumps(res, ensure_ascii=False))

# 留痕: discussion_log 四步 + prac log
dlg = r"E:/GoldstrategyEngine/data/discussion_log.jsonl"
now_be = datetime.now().strftime("%Y-%m-%d %H:%M")
entry = {"actor": "hermes", "evt": "orderflow_4step", "ts": int(time.time()), "beijing": now_be,
         "note": "机构订单流四步首跑(美股批22:35+ NFP冻结窗后, magic 20261105, 事件日0.5x): "
                 "AVGO 307.9 压20H高308.3(M15 UUUUDUDU回调不破, H1量分位P75=2354有放量) -> BUY_STOP 308.5 SL302.1(20H低) TP318(RR1.6); "
                 "INTC 54.96 钉M15密集区55.91/54.02下沿EMA20=54.93(吸筹支撑, 近8根UUDDUUDU回踩) -> BUY_LIMIT 54.8 SL53.9 TP56.15(RR1.5). "
                 "时段交叉: BJT23时我方DST大样本+3.0k正净(非deco亏时段口径), NFP后波动收敛, 量非低量转折 -> 无冲突放行. "
                 "12h到期红线=11-07 10:20, 03:55结算哨(usbatch_close_1107)兜底.",
         "orders": results}
with open(dlg, "a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
prac = r"E:/GoldstrategyEngine/data/prac_log.jsonl"
with open(prac, "a", encoding="utf-8") as f:
    for res in results:
        f.write(json.dumps({"ts": int(time.time()), "beijing": now_be, "action": "place_4step",
                            "detail": "%s retcode=%s order=%s magic=20261105" % (res["symbol"], res["retcode"], res["order"]),
                            "owner": "hermes"}, ensure_ascii=False) + "\n")
print("留痕完成")
mt5.shutdown()
