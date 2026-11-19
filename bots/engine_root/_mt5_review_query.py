import sys, json, datetime as dt
import MetaTrader5 as mt5

out = {"ok": False, "error": None, "positions": [], "deals_last2d": []}
try:
    # initialize 安全：attach 到已登录 terminal64，不重启
    ini = mt5.initialize(timeout=8000)
    if not ini:
        out["error"] = f"initialize failed: {mt5.last_error()}"
        print(json.dumps(out))
        sys.exit(0)
    out["ok"] = True
    out["terminal"] = mt5.terminal_info()._asdict() if mt5.terminal_info() else None

    # 当前真实持仓
    pos = mt5.positions_get()
    if pos is not None:
        for p in pos:
            out["positions"].append({
                "symbol": p.symbol, "type": "BUY" if p.type == 0 else "SELL",
                "volume": round(p.volume, 2), "price_open": p.price_open,
                "sl": p.sl, "tp": p.tp, "profit": round(p.profit, 2),
                "magic": p.magic, "comment": p.comment,
                "time_open": dt.datetime.fromtimestamp(p.time).strftime("%Y-%m-%d %H:%M")
            })

    # 近 2 日成交 (deals)
    now = dt.datetime.now()
    from_t = now - dt.timedelta(days=2)
    deals = mt5.history_deals_get(from_t, now)
    if deals is not None:
        for d in deals:
            out["deals_last2d"].append({
                "symbol": d.symbol,
                "type": "BUY" if d.type % 2 == 0 else "SELL",
                "volume": round(d.volume, 2),
                "price": d.price,
                "profit": round(d.profit, 2),
                "magic": d.magic,
                "comment": d.comment,
                "time": dt.datetime.fromtimestamp(d.time).strftime("%Y-%m-%d %H:%M")
            })
    # 不调用 mt5.shutdown() —— 保留 live 共享连接
except Exception as e:
    out["error"] = f"{type(e).__name__}: {e}"
    print(json.dumps(out))
    sys.exit(0)

print(json.dumps(out, ensure_ascii=False))
