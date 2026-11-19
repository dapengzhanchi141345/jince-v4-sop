# -*- coding: utf-8 -*-
"""consec_recount_mt5.py — @hermes 只读实读 MT5 deal 流, 给 L4 做 consec 重算底.
0 下单 0 撤单 0 挂单, 纯只读. 输出单行 JSON (ASCII, GBK 安全).
active-magic 白名单 = magic_registry.json existing_map_verified + EA 腿 20261103
退役/演练 = 20261102 (workbuddy 程序腿已撤销)
"""
import sys, json, datetime

# pylibs (MetaTrader5 .pyd) 走 env PYTHONPATH; 兜底这里手动补
sys.path.insert(0, r"E:\GoldstrategyEngine\pylibs")
import MetaTrader5 as mt5  # noqa: E402

ACTIVE = {20260901, 20260902, 20260903, 20260904, 20260708, 20261103}
RETIRED = {20261102}

def cls(m):
    if m in ACTIVE:
        return "active"
    if m in RETIRED:
        return "retired_drill"
    if m == 0:
        return "magic0_unknown"
    return "other_unknown"

def main():
    out = {"ok": False}
    if not mt5.initialize():
        out["error"] = "mt5.initialize() failed"
        print(json.dumps(out, ensure_ascii=True))
        return
    acc = mt5.account_info()
    if acc is None:
        out["error"] = f"account_info None init_err={mt5.last_error()}"
        print(json.dumps(out, ensure_ascii=True))
        return
    out["login"] = acc.login
    out["server"] = acc.server
    out["equity"] = acc.equity
    out["balance"] = acc.balance

    now = datetime.datetime.now()
    frm = now - datetime.timedelta(days=45)
    deals = mt5.history_deals_get(frm, now)
    out["n_deals_window"] = len(deals) if deals else 0
    if not deals:
        out["error"] = "no deals in window"
        print(json.dumps(out, ensure_ascii=True))
        return

    # numeric entry codes (stable across MetaTrader5 builds; older builds lack some attrs)
    DEAL_ENTRY_IN = 0
    DEAL_ENTRY_OUT = 1
    DEAL_ENTRY_INOUT = 2
    DEAL_ENTRY_BY = 3
    DEAL_ENTRY_OUT_BY = 4

    # position_id -> {magic (from IN), pnl (sum of OUT profit+swap+comm), close_time, symbol}
    pos = {}
    for d in deals:
        pid = getattr(d, "position_id", None) or getattr(d, "position", None) or 0
        magic = getattr(d, "magic", 0)
        if pid not in pos:
            pos[pid] = {"magic": None, "magic_in": None, "pnl": 0.0, "close_time": None, "symbol": None, "magics": set()}
        pos[pid]["magics"].add(magic)
        pos[pid]["symbol"] = d.symbol
        if d.entry == DEAL_ENTRY_IN:
            pos[pid]["magic_in"] = magic
        elif d.entry in (DEAL_ENTRY_OUT, DEAL_ENTRY_OUT_BY, DEAL_ENTRY_INOUT):
            pos[pid]["pnl"] += d.profit + d.swap + d.commission
            if pos[pid]["close_time"] is None or d.time > pos[pid]["close_time"]:
                pos[pid]["close_time"] = d.time
        # fallback magic from any deal if IN missing (partial window)
        if pos[pid]["magic_in"] is None:
            pos[pid]["magic_in"] = magic

    # realized closes = positions with a close_time
    closes = []
    for pid, p in pos.items():
        if p["close_time"] is not None:
            mag = p["magic_in"] if p["magic_in"] is not None else next(iter(p["magics"]), 0)
            closes.append({"pid": pid, "symbol": p["symbol"], "magic": mag, "cls": cls(mag),
                           "pnl": round(p["pnl"], 4), "close_t": p["close_time"]})
    closes.sort(key=lambda x: x["close_t"], reverse=True)  # most recent first

    def trailing_losses(seq):
        n = 0
        for c in seq:
            if c["pnl"] < 0:
                n += 1
            else:
                break
        return n

    all_consec = trailing_losses(closes)
    active_only = [c for c in closes if c["cls"] == "active"]
    active_consec = trailing_losses(active_only)
    retired_cnt = sum(1 for c in closes if c["cls"] == "retired_drill")
    active_cnt = len(active_only)

    out.update({
        "realized_close_positions": len(closes),
        "active_magic_closes": active_cnt,
        "retired_drill_closes": retired_cnt,
        "consec_losses_ALL": all_consec,
        "consec_losses_ACTIVE_ONLY": active_consec,
        "recent_closes_top12": closes[:12],
        "ts": now.isoformat(timespec="seconds"),
    })
    out["ok"] = True
    print(json.dumps(out, ensure_ascii=True, default=str))
    mt5.shutdown()

if __name__ == "__main__":
    main()
