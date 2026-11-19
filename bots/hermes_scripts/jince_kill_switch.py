# -*- coding: utf-8 -*-
"""
jince_kill_switch.py — 金策一键急停 (独立 kill switch, 不走 bot 主循环)

用途: 紧急情况下, 一键撤掉 + 平掉本系统所有挂单/持仓, 并落审计。
设计铁律:
  1. 只碰【本系统 magic 白名单】的订单/持仓, 绝不误伤手工单/其它 EA 单。
  2. 默认 DRY-RUN: 只列出会撤/平哪些 + 估算影响, 不真动。加 --execute 才真执行。
  3. 平仓是释放风险 (降低敞口), 即便账号异常也允许放行 —— 所以这里【不】挂
     开仓那道 fail-closed 安全网关 (网关只拦开仓, 不拦平仓)。
  4. 全程写审计 data/kill_switch_audit.jsonl (撤/平了什么、retcode、时刻)。
  5. 用 MetaTrader5 库 attach 本机已登录终端 (只操作, 不 spawn/kill 终端)。

用法:
  python jince_kill_switch.py            # DRY-RUN: 只报告, 不真动 (推荐先跑这个)
  python jince_kill_switch.py --execute  # 真撤单+平仓 (仅在你明确要停手时用)
  python jince_kill_switch.py --execute --close-only   # 只平仓, 不撤挂单
  python jince_kill_switch.py --execute --cancel-only  # 只撤挂单, 不平持仓
"""
import sys, json, os, time
from datetime import datetime

try:
    import MetaTrader5 as mt5
except Exception as e:
    print("[kill-switch] 无法导入 MetaTrader5 库: %s" % e)
    sys.exit(2)

# 本系统全 magic 白名单 (从 E:/GoldstrategyEngine 全项目 grep 收敛, 2026-10-20 核实)
SYSTEM_MAGICS = {
    20260704, 20260705, 20260706, 20260707, 20260708, 20260710, 20260711, 20260712,
    20260901, 20260902, 20260903, 20260904,
    20261020, 20261021, 20261022,
}
AUDIT = r"E:/GoldstrategyEngine/data/kill_switch_audit.jsonl"
ENGINE_DIR = r"E:/GoldstrategyEngine"

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log_audit(rec):
    rec = {"ts": now_str(), "pid": os.getpid(), **rec}
    try:
        with open(AUDIT, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        print("[kill-switch] 审计写盘失败(不影响执行): %s" % e)

def list_system_orders():
    """只列本系统 magic 的挂单."""
    orders = mt5.orders_get() or []
    return [o for o in orders if o.magic in SYSTEM_MAGICS]

def list_system_positions():
    """只列本系统 magic 的持仓."""
    pos = mt5.positions_get() or []
    return [p for p in pos if p.magic in SYSTEM_MAGICS]

def cancel_one(order, dry):
    """撤一张挂单. 返回 (ok, reason)."""
    sym = order.symbol
    tick = mt5.symbol_info_tick(sym)
    if tick is None:
        return False, "无 tick"
    req = {
        "action": mt5.TRADE_ACTION_REMOVE,
        "order": order.ticket,
        "symbol": sym,
        "magic": order.magic,
        "comment": "kill_switch_cancel",
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    if dry:
        return True, "DRY(不真撤) %s #%d" % (sym, order.ticket)
    r = mt5.order_send(req)
    ok = bool(r) and r.retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_DONE_PARTIAL)
    return ok, ("retcode=%s" % getattr(r, "retcode", "?"))

def close_one(pos, dry):
    """平一张持仓. 返回 (ok, reason)."""
    sym = pos.symbol
    tick = mt5.symbol_info_tick(sym)
    info = mt5.symbol_info(sym)
    if tick is None or info is None:
        return False, "无 tick/info"
    if pos.type == mt5.POSITION_TYPE_BUY:
        ctype = mt5.ORDER_TYPE_SELL
        price = tick.bid
    else:
        ctype = mt5.ORDER_TYPE_BUY
        price = tick.ask
    price = round(price, info.digits)
    filling = mt5.ORDER_FILLING_IOC
    if info.filling_mode & mt5.ORDER_FILLING_FOK:
        filling = mt5.ORDER_FILLING_FOK
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": sym,
        "volume": float(pos.volume),
        "type": ctype,
        "position": pos.ticket,
        "price": price,
        "deviation": 50,
        "magic": pos.magic,
        "comment": "kill_switch_close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }
    if dry:
        return True, "DRY(不真平) %s #%d vol=%.2f" % (sym, pos.ticket, pos.volume)
    r = mt5.order_send(req)
    ok = bool(r) and r.retcode == mt5.TRADE_RETCODE_DONE
    return ok, ("retcode=%s" % getattr(r, "retcode", "?"))

def main():
    execute = "--execute" in sys.argv
    close_only = "--close-only" in sys.argv
    cancel_only = "--cancel-only" in sys.argv
    mode = "EXECUTE" if execute else "DRY-RUN"

    print("═" * 60)
    print("金策一键急停  [%s]" % mode)
    print("  终端 attach 走 MetaTrader5 库 (默认 datafolder), 不 spawn/kill 终端")
    print("═" * 60)

    ok_init = mt5.initialize()
    if not ok_init:
        print("[kill-switch] MT5 initialize 失败: %s" % (mt5.last_error(),))
        log_audit({"event": "init_fail", "detail": str(mt5.last_error())})
        sys.exit(3)

    acct = mt5.account_info()
    if acct is None:
        print("[kill-switch] 读不到账户信息, 为安全 fail-closed 不执行任何动作")
        log_audit({"event": "no_account", "detail": "account_info None"})
        mt5.shutdown()
        sys.exit(3)
    print("  终端账号: %s @ %s | 净值=%.2f | 持仓%s 挂单%s" % (
        acct.login, acct.server, acct.equity,
        len(mt5.positions_get() or []), len(mt5.orders_get() or [])))

    sys_orders = list_system_orders()
    sys_pos = list_system_positions()
    print("  本系统 magic 挂单: %d 张 | 本系统 magic 持仓: %d 张 (手工单不受影响)" % (len(sys_orders), len(sys_pos)))

    results = []
    # 撤挂单
    if not close_only and sys_orders:
        print("\n[撤挂单] %d 张:" % len(sys_orders))
        for o in sys_orders:
            ok, reason = cancel_one(o, dry=not execute)
            results.append({"op": "cancel", "ticket": o.ticket, "symbol": o.symbol,
                            "ok": ok, "reason": reason, "dry": not execute})
            print("   %s %s #%d -> %s" % ("✓" if ok else "✗", o.symbol, o.ticket, reason))
            time.sleep(0.2)
    elif close_only:
        print("\n[撤挂单] --close-only 跳过撤单")

    # 平持仓
    if not cancel_only and sys_pos:
        print("\n[平持仓] %d 张:" % len(sys_pos))
        for p in sys_pos:
            ok, reason = close_one(p, dry=not execute)
            results.append({"op": "close", "ticket": p.ticket, "symbol": p.symbol,
                            "ok": ok, "reason": reason, "dry": not execute})
            print("   %s %s #%d vol=%.2f -> %s" % ("✓" if ok else "✗", p.symbol, p.ticket, p.volume, reason))
            time.sleep(0.2)
    elif cancel_only:
        print("\n[平持仓] --cancel-only 跳过平仓")

    log_audit({"event": "kill_switch", "mode": mode,
               "cancelled": sum(1 for r in results if r["op"] == "cancel"),
               "closed": sum(1 for r in results if r["op"] == "close"),
               "all_ok": all(r["ok"] for r in results) if results else True,
               "account": acct.login, "server": acct.server, "equity": acct.equity})

    print("\n" + "═" * 60)
    if execute:
        print("已执行。审计: %s" % AUDIT)
        # 执行后复扫确认清零
        print("  复扫: 本系统挂单 %d / 持仓 %d (应=0, 若>0 说明有单没撤干净)" % (
            len(list_system_orders()), len(list_system_positions())))
    else:
        print("DRY-RUN 完成, 未真动任何单。确认无误后加 --execute 真执行。")
    print("═" * 60)
    mt5.shutdown()

if __name__ == "__main__":
    main()
