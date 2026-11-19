# -*- coding: utf-8 -*-
r"""币系茶歇峰12h红线 close_obs 哨内层 (ATE 环境跑): 读 tea_tea_1115_orders.json registry,
逐单核: 未成交=撤单+order_lifecycle.jsonl留痕; 已成交=留痕移交既有管理; 已消失=留痕。
"""
import json, time, datetime
import MetaTrader5 as mt5

REG = r"E:\GoldstrategyEngine\data\tea_tea_1115_orders.json"
LC = r"E:\GoldstrategyEngine\data\order_lifecycle.jsonl"
MAGIC = 30261106


def now_s():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def lc(rec):
    with open(LC, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main():
    reg = json.load(open(REG, encoding="utf-8")).get("orders", [])
    if not reg:
        print("【币系茶歇12h红线close_obs哨】本批无成功挂单(全被拒/跳过), 哨空转。")
        return
    if not mt5.initialize():
        print("RED: MT5终端不在线, 12h红线撤单未执行! 未成交挂单将越过红线, 需5min自修复链+人工跟进。")
        raise SystemExit(1)
    time.sleep(2)
    print("【币系茶歇12h红线close_obs哨】共%d笔待核, magic=%d" % (len(reg), MAGIC))
    for o in reg:
        sym, tk = o["sym"], o.get("ticket")
        pending = [x for x in (mt5.orders_get() or [])
                   if x.magic == MAGIC and x.symbol == sym and x.order_type in
                   (mt5.ORDER_TYPE_SELL_LIMIT, mt5.ORDER_TYPE_BUY_LIMIT)]
        if pending:
            p = pending[0]
            r = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": p.identifier,
                                "magic": MAGIC, "comment": "close12h_obs"})
            ok = r is not None and r.retcode in (10008, 10009)
            print("%s: 12h未成交 -> 撤单%s (rc=%s %s), 留痕" % (
                sym, "成功" if ok else "失败", r.retcode if r else None, r.comment if r else ""))
            lc({"ts": now_s(), "op": "close", "type": "pending_cancel", "symbol": sym,
                "ticket": p.identifier, "magic": MAGIC, "order_px": o.get("order_px"),
                "sl": o.get("sl"), "tp": o.get("tp"), "retcode": r.retcode if r else None,
                "reason": "12h红线未成交, close_obs哨自动撤单(茶歇峰茶歇单不过夜纪律)"})
        else:
            since = int(time.time()) - 43200
            filled_deals = [d for d in (mt5.deals_get(since, None) or [])
                            if d.magic == MAGIC and d.symbol == sym and d.entry == mt5.DEAL_ENTRY_IN]
            pos = [p for p in (mt5.positions_get() or []) if p.magic == MAGIC and p.symbol == sym]
            if filled_deals or pos:
                print("%s: 12h内已成交(%d笔IN成交/活仓%d张), SL/TP在位, 移交既有12h强平+处置三件套管理" % (
                    sym, len(filled_deals), len(pos)))
                lc({"ts": now_s(), "op": "close_obs_filled", "type": "pending_filled", "symbol": sym,
                    "ticket": tk, "magic": MAGIC, "order_px": o.get("order_px"),
                    "sl": o.get("sl"), "tp": o.get("tp"),
                    "reason": "12h红线内已成交, close_obs哨销账; 活仓带SL/TP, 由既有处置三件套(12h强平/TP-SL/事件窗)管理"})
            else:
                print("%s: 订单已不存在(此前已撤/过期/他方处理), 无需动作, 留痕" % sym)
                lc({"ts": now_s(), "op": "close_obs_gone", "type": "pending_gone", "symbol": sym,
                    "ticket": tk, "magic": MAGIC, "order_px": o.get("order_px"),
                    "reason": "12h红线核时订单已不存在(无活仓无IN成交), close_obs哨销账留痕"})
    print("【close_obs哨收工】全部逐单留痕完毕。")
    mt5.shutdown()


if __name__ == "__main__":
    main()
