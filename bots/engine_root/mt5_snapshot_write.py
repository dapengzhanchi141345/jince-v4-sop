# -*- coding: utf-8 -*-
"""
mt5_snapshot_write.py — 把活体 MT5 账户(60137964)实读结果写成看板快照
写: data/_tmp_mt5snap.json  (格式对齐 dashboard_gen._load_mt5_snap: 顶层 account + positions)

用途: 让看板「账户实况卡」显示的是当前 MT5 实盘, 不是 8 月旧快照。
由 auto_run_cycle.py 每 30min 全链调用一次 (fail-open: 失败不崩全链, 写 [!] 标记)。
也可手动跑: ate-python E:/GoldstrategyEngine/mt5_snapshot_write.py

GBK 安全: 本脚本 stdout 只打 [快照] 汉字 tag + 数字, 无 emoji / 无特殊符号。
"""
import os, json, time, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
SNAP = os.path.join(DATA, "_tmp_mt5snap.json")
ACCOUNT_ID = 60137964
PASSWORD = os.environ.get("MT5_PASS_60137964", "")
SERVER = "TradeMaxGlobal-Demo"

try:
    import MetaTrader5 as mt5
except Exception as e:
    print("[快照] MT5 库导入失败: %s" % str(e)[:60])
    mt5 = None


def _write_degraded_snap(reason):
    """写 degraded=True 快照 (fail-open): 看板卡片据此标"降级, 数据仅留痕", 不误报活体数字."""
    try:
        snap = {"account": None, "positions": [], "orders": [], "n_pos": 0, "n_orders": 0,
                "written_at": int(time.time()), "degraded": True, "errors": [reason]}
        tmp = SNAP + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, default=str)
        os.replace(tmp, SNAP)
        print("[快照] 已写降级快照: %s" % reason[:60])
    except Exception as e:
        print("[快照] 降级快照写入失败(fail-open): %s" % str(e)[:60])


def _f(obj, *keys):
    for k in keys:
        v = getattr(obj, k, None)
        if v is not None:
            return v
    return None


def main():
    # [2026-10-05 V13 根治·统一实读入口] 快照也走 mt5_live_read, 与节点/简报同一套实读;
    # 读不到活体时写 degraded=True 快照, 看板卡片看到 degraded 就标"降级, 仅留痕",
    # 绝不把旧数据当活体报出去. fail-open 不崩全链.
    global mt5
    if mt5 is None:
        try:
            import json as _j
            _snap = {"account": None, "positions": [], "orders": [], "n_pos": 0, "n_orders": 0,
                     "written_at": int(time.time()), "degraded": True,
                     "errors": ["MT5 库不可用, 快照降级"]}
            _tmp = SNAP + ".tmp"
            with open(_tmp, "w", encoding="utf-8") as f:
                _j.dump(_snap, f, ensure_ascii=False, default=str)
            os.replace(_tmp, SNAP)
            print("[快照] MT5 库不可用, 已写降级快照 (看板将标'降级')")
        except Exception as _e:
            print("[快照] fail-open 跳过: %s" % str(_e)[:80])
        return
    ok = mt5.initialize()
    if not ok:
        print("[快照] MT5 initialize 失败 (终端未起?)")
        _write_degraded_snap("initialize 失败 (终端未起?) %s" % str(mt5.last_error())[:60])
        return
    a = None
    # 已登录同账户则直接读; 否则显式登录
    cur = mt5.account_info()
    if cur is not None and getattr(cur, "login", None) == ACCOUNT_ID:
        a = cur
    else:
        if not mt5.login(ACCOUNT_ID, password=PASSWORD, server=SERVER):
            err = mt5.last_error()
            print("[快照] 登录失败 %s" % str(err)[:80])
            mt5.shutdown()
            return
        a = mt5.account_info()

    acct = {
        "login": _f(a, "login"), "server": _f(a, "server"),
        "currency": _f(a, "currency"), "name": _f(a, "name"),
        "balance": _f(a, "balance"), "equity": _f(a, "equity"),
        "profit": _f(a, "profit"), "margin": _f(a, "margin"),
        "margin_free": _f(a, "margin_free", "free_margin"),
        "margin_level": _f(a, "margin_level"), "leverage": _f(a, "leverage"),
        "trade_allowed": _f(a, "trade_allowed", "trading_allowed"),
        "trade_mode": _f(a, "trade_mode"),
    }
    positions = []
    for p in (mt5.positions_get() or []):
        positions.append({k: getattr(p, k, None) for k in
            ("ticket", "symbol", "type", "volume", "price_open", "price_current",
             "sl", "tp", "profit", "time", "comment")})
    orders = []
    for o in (mt5.orders_get() or []):
        orders.append({k: getattr(o, k, None) for k in
            ("ticket", "symbol", "type", "volume", "price", "sl", "tp", "time")})

    snap = {"account": acct, "positions": positions, "orders": orders,
            "n_pos": len(positions), "n_orders": len(orders),
            "written_at": int(time.time())}
    tmp = SNAP + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, default=str)
    os.replace(tmp, SNAP)
    mt5.shutdown()
    print("[快照] MT5 %s 净值=%.2f 余额=%.2f 持仓=%d 挂单=%d -> %s" % (
        acct.get("login"), acct.get("equity") or 0, acct.get("balance") or 0,
        len(positions), len(orders), os.path.basename(SNAP)))


if __name__ == "__main__":
    main()
