# -*- coding: utf-8 -*-
"""@hermes 只读「练习轮」= 完整自检实读 (0 下单 0 撤单 0 挂单, 纯读, 不动账户).
每跑一次 = 1 轮练习, 把实数追加进 _hermes_practice_log.jsonl (供 08:30 简报「练习量行」计数).
练习腿: 不吃 exp_r 总闸、0 开新仓、3 闸 (日亏10%/品种日3单/连亏3笔24h) 一律不动.
输出单行 JSON (ASCII, GBK 安全, 无 emoji). 退出码 0=成功.
"""
import sys, os, json, datetime

sys.path.insert(0, r"E:\GoldstrategyEngine\pylibs")
try:
    import MetaTrader5 as mt5
except Exception as e:
    print(json.dumps({"ok": False, "error": "import_mt5_failed: %s" % e}, ensure_ascii=True))
    sys.exit(2)

GATE = r"C:\Users\Administrator\AppData\Roaming\MetaQuotes\Terminal\7643C0B96C7AD5841307C9E1EB0B9252\MQL5\Files\jince_gate.json"
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_hermes_practice_log.jsonl")
# 哪条"腿"产出的这轮 (默认=hermes 自动循环腿; L4 独立复核腿跑时传 env HERMES_PRACTICE_LEG=L4-recheck)
LEG = os.environ.get("HERMES_PRACTICE_LEG", "hermes-loop")

ACTIVE = {20260901, 20260902, 20260903, 20260904, 20260708, 20261103}
RETIRED = {20261102}


def gate_read():
    out = {"present": False}
    try:
        mtime = os.path.getmtime(GATE)
        with open(GATE, "r", encoding="utf-8") as f:
            g = json.load(f)
        age_s = int(datetime.datetime.now().timestamp() - mtime)
        out.update({"present": True, "exp_r": g.get("exp_r"),
                    "updated": g.get("updated"), "writer_age_s": age_s,
                    "fail_closed": (g.get("exp_r", 0) <= 0.1)})
    except Exception as e:
        out["error"] = "gate_read_failed: %s" % e
    return out


def consec_recount(deals):
    DEAL_IN, DEAL_OUT, DEAL_INOUT, DEAL_BY, DEAL_OUT_BY = 0, 1, 2, 3, 4
    pos = {}
    for d in deals or []:
        pid = getattr(d, "position_id", None) or getattr(d, "position", None) or 0
        magic = getattr(d, "magic", 0)
        p = pos.setdefault(pid, {"magic_in": None, "pnl": 0.0, "close_t": None, "magics": set()})
        p["magics"].add(magic)
        if d.entry == DEAL_IN:
            p["magic_in"] = magic
        elif d.entry in (DEAL_OUT, DEAL_OUT_BY, DEAL_INOUT):
            p["pnl"] += d.profit + d.swap + d.commission
            if p["close_t"] is None or d.time > p["close_t"]:
                p["close_t"] = d.time
        if p["magic_in"] is None:
            p["magic_in"] = magic

    def cls(m):
        if m in ACTIVE:
            return "active"
        if m in RETIRED:
            return "retired_drill"
        return "other"

    closes = []
    for pid, p in pos.items():
        if p["close_t"] is not None:
            mag = p["magic_in"] if p["magic_in"] is not None else next(iter(p["magics"]), 0)
            closes.append({"mag": mag, "cls": cls(mag), "pnl": round(p["pnl"], 4), "t": p["close_t"]})
    closes.sort(key=lambda x: x["t"], reverse=True)

    def trailing(seq):
        n = 0
        for c in seq:
            if c["pnl"] < 0:
                n += 1
            else:
                break
        return n

    all_c = trailing(closes)
    act_c = trailing([c for c in closes if c["cls"] == "active"])
    return {"consec_ALL": all_c, "consec_ACTIVE": act_c,
            "n_realized": len(closes),
            "n_active_closes": sum(1 for c in closes if c["cls"] == "active"),
            "n_retired_closes": sum(1 for c in closes if c["cls"] == "retired_drill")}


def main():
    out = {"ok": False, "ts": datetime.datetime.now().isoformat(timespec="seconds"), "leg": LEG}
    if not mt5.initialize():
        out["error"] = "mt5.init_failed err=%s" % (mt5.last_error(),)
        print(json.dumps(out, ensure_ascii=True))
        sys.exit(1)
    acc = mt5.account_info()
    if acc is None:
        out["error"] = "account_info None err=%s" % (mt5.last_error(),)
        mt5.shutdown()
        print(json.dumps(out, ensure_ascii=True))
        sys.exit(1)
    positions = mt5.positions_get() or []
    orders = mt5.orders_get() or []
    now = datetime.datetime.now()
    deals = mt5.history_deals_get(now - datetime.timedelta(days=45), now)
    out.update({
        "login": acc.login, "server": acc.server,
        "equity": acc.equity, "balance": acc.balance,
        "n_positions": len(positions), "n_pending_orders": len(orders),
        "positions_sym": [p.symbol for p in positions][:20],
        "pending_sym": [o.symbol for o in orders][:20],
        "gate": gate_read(),
        "consec": consec_recount(deals),
        "n_deals_window": len(deals) if deals else 0,
    })
    out["ok"] = True
    line = json.dumps(out, ensure_ascii=True, default=str)
    # append to practice log (countable for the 08:30 "practice-volume" line)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        out["logged"] = True
    except Exception as e:
        out["log_error"] = str(e)
    print(line)
    mt5.shutdown()
    sys.exit(0)


if __name__ == "__main__":
    main()
