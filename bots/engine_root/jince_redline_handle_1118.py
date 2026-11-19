# -*- coding: utf-8 -*-
"""jince_redline_handle_1118.py — 12h红线处置哨(李令'一切交给你'): 11-18 09:35 BJT 一次
规则(最小影响, 李彦明铁律): 三腿(BTC/ETH/SOL, magic 30261106/20261104)
- 已平(SL/TP) -> 只报结果
- 仍持 + 结构未破(空头腿: 现价未越24h高点区) -> 红线滚+12h(新决策点明21:35), 不动点位
- 仍持 + 结构破(现价越过24h高点=方向证伪) -> 市价平该腿(留痕, 报李)
时间闸: 仅在 2026-11-18 09:00-12:00 BJT 执行, 其余时间干跑=SKIP(防早误触).
"""
import json, os, sys, datetime as dt

ROOT = "E:/GoldstrategyEngine"
BASE = os.path.join(ROOT, "data")
MAGICS = (30261106, 20261104)
LEGS = ("BTCUSD", "ETHUSD", "SOLUSD")


def log(row):
    with open(os.path.join(BASE, "task_ledger.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    now = dt.datetime.now()
    in_win = ((now.strftime("%Y-%m-%d") == "2026-11-18" and 9 <= now.hour < 12)
              or os.environ.get("JINCE_REDLINE_FORCE") == "1")
    if not in_win:
        print(f"SKIP: 红线处置窗口(11-18 09:00-12:00或FORCE)外, 现 {now:%m-%d %H:%M}")
        return
    import MetaTrader5 as mt5
    assert mt5.initialize(), "mt5 init fail"
    lines = ["【12h红线处置 11-18 09:35】"]
    # 24h高点(结构锚): 用 M30 tf_cache npz 或 tick 前日 high 近似
    for sym in LEGS:
        pos = [p for p in (mt5.positions_get() or ()) if p.symbol == sym and p.magic in MAGICS]
        if not pos:
            lines.append(f"{sym}: 已了结(夜间SL/TP触发)")
            continue
        p = pos[0]
        hi = mt5.symbol_info_tick(sym)
        d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 3)
        anchor = float(max(r["high"] for r in d1[:2])) if d1 else None  # 近2日高点=空头结构
        broken = anchor is not None and p.price_open < anchor and float(hi.bid) > anchor
        if p.type == 1 and broken:  # 空头且价格越近2日高点=结构破
            r = mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": p.volume,
                "type": mt5.ORDER_TYPE_BUY, "magic": p.magic, "comment": "redline-struct-break-1118",
                "type_time": mt5.ORDER_TIME_GTC, "position": p.ticket, "deviation": 20})
            lines.append(f"{sym}: 结构破(价{hi.bid}>近2日高{anchor:.6g}) -> 市价平 rc={r.retcode}")
            log({"ev": "redline_struct_close", "ts": now.isoformat(), "sym": sym, "ticket": p.ticket,
                 "rc": r.retcode, "reason": "12h红线: 空头腿结构证伪(越近2日高点), 最小影响=平该腿", "live": True})
        else:
            new_rl = (now + dt.timedelta(hours=12)).strftime("%m-%d %H:%M")
            lines.append(f"{sym}: 结构未破, 浮{p.profit:+.2f} SL{p.sl} TP{p.tp} -> 红线滚至 {new_rl}(明21:35再判)")
            log({"ev": "redline_roll", "ts": now.isoformat(), "sym": sym, "ticket": p.ticket,
                 "new_redline": new_rl, "reason": "结构未破最小影响: 不动点位, 滚12h", "live": True})
    lines.append(f"净值 {mt5.account_info().equity:.2f}")
    print("\n".join(lines))
    mt5.shutdown()


if __name__ == "__main__":
    main()
