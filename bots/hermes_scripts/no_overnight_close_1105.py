#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策 22:15 禁隔夜强平执行器（风控官 11-05 L4 裁定②：账户级红线，人工不豁免）。

开仓 10:15-10:23 BJT = 02:15-02:23 UTC；hold_max_hours=12 → 14:15-14:23 UTC
= 22:15-22:23 BJT 到点必平。SL/TP 已触发的（已平）不在对象内。
IOC 市价平掉所有 magic=20261104 的未平持仓；平不掉的重试 3 次。
静默哨兵：全部已平/无仓 = 无输出（watchdog 模式）。
"""
import os
os.environ["PYTHONIOENCODING"] = "utf-8"
import sys, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

MAGIC = 20261104
LOG = "E:/GoldstrategyEngine/data/no_overnight_close_log.jsonl"
# 批次区分（18:5x 修正）：只强平"21:30 前开的持仓"（今晨 10:15-10:23 批，12h 到点 22:15）；
# 21:30 后新开的美股批（AVGO/INTC）豁免——它们有自己的 12h 期限到明日 09:3x（风控 14:2x 裁定③"两批独立期限"）
CUTOFF = int(time.mktime(time.strptime("2026-11-05", "%Y-%m-%d")) + 21 * 3600 + 30 * 60)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def main():
    import MetaTrader5 as mt5
    mt5.initialize()
    acc = mt5.account_info()
    if acc is None:
        print(f"[no_overnight] MT5 连接失败 rc={mt5.last_error()}")
        return 1
    positions = [p for p in (mt5.positions_get(None) or ()) if p.magic == MAGIC]
    exempted = []
    positions, exempted = ([p for p in positions if p.time < CUTOFF], [p for p in positions if p.time >= CUTOFF])
    if exempted:
        for p in exempted:
            print(f"[no_overnight] 豁免（21:30后新开, 自有12h期限）: {p.symbol} ticket={p.ticket} opened={time.strftime('%H:%M', time.localtime(p.time))}")
    if not positions:
        # 无仓（可能全被 SL/TP 触发了）= 无输出静默
        return 0
    closed, failed = [], []
    for p in positions:
        ok = False
        for attempt in range(3):
            tick = mt5.symbol_info_tick(p.symbol)
            price = tick.bid if (p.type == mt5.POSITION_TYPE_BUY and tick) else (tick.ask if tick else None)
            if price is None:
                time.sleep(3)
                continue
            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": p.ticket,
                "symbol": p.symbol,
                "volume": p.volume,
                "type": mt5.ORDER_TYPE_BUY if p.type == mt5.POSITION_TYPE_SELL else mt5.ORDER_TYPE_SELL,
                "price": price,
                "deviation": 50,
                "magic": MAGIC,
                "comment": "no_overnight_close_1105",
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            r = mt5.order_send(req)
            if r is not None and r.retcode == mt5.RETCODE_DONE:
                ok = True
                closed.append({"ticket": p.ticket, "symbol": p.symbol, "type": p.type, "vol": p.volume, "close_deal": r.deal})
                break
            time.sleep(3)
        if not ok:
            failed.append({"ticket": p.ticket, "symbol": p.symbol, "retcode": (r or {}).get("retcode") if r else None, "comment": (r or {}).get("comment") if r else None})
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": _now(), "eq": acc.equity, "closed": closed, "failed": failed,
                            "note": "L4 12h 禁隔夜强平 11-05 22:15 UTC14:15"}, ensure_ascii=False) + "\n")
    out = [f"[no_overnight] 强平 {len(closed)}/{len(positions)} 张:"]
    for c in closed:
        out.append(f"  ✓ {c['symbol']} {c['type']} vol={c['vol']} deal={c['close_deal']}")
    for fl in failed:
        out.append(f"  ✗ {fl['symbol']} ticket={fl['ticket']} retcode={fl['retcode']} {fl['comment']}")
    if not failed:
        out.append("全部平掉，无隔夜敞口 ✓")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
