
import MetaTrader5 as mt5, json, datetime
if not mt5.initialize():
    raise SystemExit  # 终端离线: 静默(看门狗管终端), 不刷屏
MAGIC = 30261106
LC = "E:/GoldstrategyEngine/data/order_lifecycle.jsonl"
def _now(): return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
def _lc(rec):
    with open(LC, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
# 轮值池第1轮: 空侧=系统净方向(NFP后利率压力), 多侧=中性对冲 -> 方向中性攒样
# (sym, side: 1=BUY 2=SELL, sl%, tp%)
POOL = [("BTCUSD", 2, 0.005, 0.015), ("ETHUSD", 2, 0.005, 0.015),
        ("SOLUSD", 1, 0.008, 0.020), ("ADAUSD", 1, 0.008, 0.020)]
held = {p.symbol for p in (mt5.positions_get() or []) if p.magic == MAGIC}
opened = []
for sym, side, slp, tpp in POOL:
    if sym in held:
        continue  # 幂等: 已有腿不重开(防叠单)
    si = mt5.symbol_info(sym)
    if not si or si.trade_mode != 1:
        continue  # 该品种仍close-only(博德逐个放开), 下轮15min自动补
    px = si.bid if side == 2 else si.ask
    sl = round(px * (1 + slp), si.digits) if side == 2 else round(px * (1 - slp), si.digits)
    tp = round(px * (1 + tpp), si.digits) if side == 1 else round(px * (1 - tpp), si.digits)
    r = mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": 0.01,
                        "type": mt5.ORDER_TYPE_SELL if side == 2 else mt5.ORDER_TYPE_BUY,
                        "price": px, "sl": sl, "tp": tp, "deviation": 20, "magic": MAGIC,
                        "comment": "obs4_%s_1108" % sym[:3], "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_IOC})
    if r.retcode in (10008, 10009, 10010):
        opened.append(sym)
        _lc({"ts": _now(), "sym": sym, "side": "SELL" if side == 2 else "BUY", "vol": 0.01,
             "magic": MAGIC, "open_px": px, "sl": sl, "tp": tp, "retcode": r.retcode,
             "deal": r.deal, "close_due": "开仓+12h(6h循环哨自动平+轮换)",
             "sentinel": "41112d6bfbc3(6h循环)+2a3f3ebcea82(15min放开即开)",
             "status": "open", "note": "4腿轮值池第1轮(空BTC/ETH+多SOL/ADA, 方向中性)"})
if opened:
    print("【4腿轮值池开单成功】close-only已放开: " + " ".join(opened) +
          " (未开出的下轮15min自动补)")
mt5.shutdown()
