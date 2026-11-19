# -*- coding: utf-8 -*-
"""jince_morning_report.py — 早间战报(李令'准备休息了, 一切交给你'): 11-18 07:30 BJT 一次哨
纯读: 持仓/平仓/净值/验尸/数据鲜度/参数官账本 -> 大白话多行报告, 原样投递给李(醒来第一眼).
"""
import json, os, datetime as dt

ROOT = "E:/GoldstrategyEngine"
BASE = os.path.join(ROOT, "data")
MAGICS = (30261106, 20261104)
LEGS = ("BTCUSD", "ETHUSD", "SOLUSD")


def main():
    import MetaTrader5 as mt5
    lines = ["【金策夜间战报 11-18 07:30】"]
    ok = mt5.initialize()
    if ok:
        acc = mt5.account_info()
        lines.append(f"净值 {acc.equity:.2f}")
        pos = [p for p in (mt5.positions_get() or ()) if p.symbol in LEGS and p.magic in MAGICS]
        lines.append(f"三腿持仓 {len(pos)}/3")
        for p in pos:
            lines.append(f"  {p.symbol} {'空' if p.type==1 else '多'} @{p.price_open} SL{p.sl} TP{p.tp} 浮{p.profit:+.2f} (单{p.ticket})")
        # 昨21:00后的平仓
        closed = [d for d in mt5.history_deals_get(
            dt.datetime(2026, 11, 17, 21, 0), dt.datetime.now())
            if d.symbol in LEGS and d.magic in MAGICS and d.entry == 1]
        for d in closed:
            lines.append(f"  已平 {d.symbol} {d.type}(rc {d.reason}) 盈 {d.profit:+.2f} 单{d.ticket}")
        mt5.shutdown()
    else:
        lines.append("MT5终端未连接(晨间报告降级: 只有台账)")
    # 台账摘要: 昨晚21点后的关键事件
    evs = []
    for ln in open(os.path.join(BASE, "order_lifecycle.jsonl"), encoding="utf-8"):
        try:
            r = json.loads(ln)
        except Exception:
            continue
        ts = str(r.get("ts", ""))
        if ts >= "2026-11-17 21:0" and r.get("ev") in ("place", "close", "skip_gowin", "place_fail", "miss_rootcause_fixed"):
            evs.append(f"  {ts[:16]} {r.get('ev')} {r.get('sym','')}")
    if evs:
        lines.append("台账事件(21:00后):")
        lines.extend(evs[-12:])
    st = os.path.join(BASE, "param_officer_state.json")
    if os.path.exists(st):
        d = json.load(open(st, encoding="utf-8"))
        lines.append(f"参数官: 不一致{len(d.get('issues',[]))}项 | OOS账本 {d.get('oos_closed',0)}/30")
    y = os.path.join(BASE, "postmortem_20261117.json")
    if os.path.exists(y):
        lines.append("验尸哨02:30已产报告(明细见文件)")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
