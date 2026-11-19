
import MetaTrader5 as mt5, json, datetime, os
if not mt5.initialize():
    print("ROLL_SENT: 终端离线, 下轮再试"); raise SystemExit
MAGIC = 30261106
LC = "E:/GoldstrategyEngine/data/order_lifecycle.jsonl"
ST = "E:/GoldstrategyEngine/data/rotation_state.json"
def _now(): return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
def _lc(rec):
    with open(LC, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
st = {"round": 1}
if os.path.exists(ST):
    try: st = json.load(open(ST, encoding="utf-8"))
    except Exception: pass
targets = [p for p in (mt5.positions_get() or []) if p.magic == MAGIC]
open_rows = {}
if os.path.exists(LC):
    for l in open(LC, encoding="utf-8"):
        try:
            row = json.loads(l)
            if row.get("ticket"): open_rows[row["ticket"]] = row
        except Exception: pass
for p in targets:
    si = mt5.symbol_info(p.symbol)
    close_px = si.bid if p.type == 1 else si.ask
    r = mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol,
                        "volume": p.volume, "type": mt5.ORDER_TYPE_BUY if p.type == 1 else mt5.ORDER_TYPE_SELL,
                        "price": close_px, "position": p.ticket, "deviation": 20, "magic": MAGIC,
                        "comment": "close6h_roll", "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_IOC})
    print("已平: %s ticket=%d @%.4f retcode=%s | %s" % (p.symbol, p.ticket, close_px, r.retcode, r.comment))
    _lc({"ts": _now(), "sym": p.symbol, "ticket": p.ticket, "magic": MAGIC,
         "open_ts": open_rows.get(p.ticket, {}).get("ts", "未核"), "close_ts": _now(),
         "close_px": close_px, "retcode": r.retcode, "status": "closed",
         "close_reason": "6h滚动哨平仓(方向轮换 轮%s)" % st.get("round", 1)})
roll = True
try:
    rj = json.load(open("E:/GoldstrategyEngine/data/risk_state.json", encoding="utf-8"))
    dd = rj.get("equity_dd_pct") or 0
    if dd >= 10:
        print("RISK_HOLD: 回撤%.1f%%>=10%%熔断线, 暂停重开(红线不动)" % dd); roll = False
except Exception:
    pass
if roll:
    st["round"] = st.get("round", 1) % 2 + 1
    json.dump(st, open(ST, "w", encoding="utf-8"))
    inv = 1 if st["round"] % 2 == 1 else -1
    POOL = [("BTCUSD", 2, 0.005, 0.015), ("ETHUSD", 2, 0.005, 0.015),
            ("SOLUSD", 1, 0.008, 0.020), ("ADAUSD", 1, 0.008, 0.020)]
    newpool = [(s, (2 if s in ("SOLUSD","ADAUSD") else 1) if inv < 0 else d, sl, tp)
               for s, d, sl, tp in POOL]
    held = {p.symbol for p in (mt5.positions_get() or []) if p.magic == MAGIC}
    opened = []
    for sym, side, slp, tpp in newpool:
        if sym in held: continue
        si = mt5.symbol_info(sym)
        if not si or si.trade_mode != 1:
            print("%s 仍close-only, 本腿跳过(15min哨自动补)" % sym); continue
        px = si.bid if side == 2 else si.ask
        sl = round(px * (1 + slp), si.digits) if side == 2 else round(px * (1 - slp), si.digits)
        tp = round(px * (1 + tpp), si.digits) if side == 1 else round(px * (1 - tpp), si.digits)
        r = mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": 0.01,
                            "type": mt5.ORDER_TYPE_SELL if side == 2 else mt5.ORDER_TYPE_BUY,
                            "price": px, "sl": sl, "tp": tp, "deviation": 20, "magic": MAGIC,
                            "comment": "obs4_r%d" % st["round"], "type_time": mt5.ORDER_TIME_GTC,
                            "type_filling": mt5.ORDER_FILLING_IOC})
        print("轮%d重开: %s %s 0.01 @%.4f retcode=%s deal=%s | %s" %
              (st["round"], sym, "SELL" if side == 2 else "BUY", px, r.retcode, r.deal, r.comment))
        if r.retcode in (10008, 10009, 10010):
            opened.append(sym)
            _lc({"ts": _now(), "sym": sym, "side": "SELL" if side == 2 else "BUY", "vol": 0.01,
                 "magic": MAGIC, "open_px": px, "sl": sl, "tp": tp, "retcode": r.retcode,
                 "deal": r.deal, "round": st["round"],
                 "close_due": "开仓+12h(6h循环哨自动平+再轮换)",
                 "sentinel": "41112d6bfbc3(6h循环)", "status": "open",
                 "note": "6h滚动哨方向轮换(轮%d: %s)" % (st["round"], "空BTC/ETH+多SOL/ADA" if inv > 0 else "多BTC/ETH+空SOL/ADA")})
    if opened:
        print("【轮%d完成】重开: %s" % (st["round"], " ".join(opened)))
if not targets and not roll:
    print("(无在仓且熔断暂停)")
mt5.shutdown()
