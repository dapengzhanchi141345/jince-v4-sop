
# -*- coding: utf-8 -*-
"""新账号 60137964 连接探针: 验证 MT5 连通 + 账户状态, 输出快照."""
import json, os, time, datetime
import MetaTrader5 as mt5

ACCOUNT_ID = 60137964
PASSWORD = ""
SERVER = "TradeMaxGlobal-Demo"
OUT = "E:/GoldstrategyEngine/data/_review_mt5_60137964.json"

def main():
    if not mt5.initialize():
        print("MT5 initialize 失败:", mt5.last_error())
        return
    # 登录
    login = mt5.login(ACCOUNT_ID, password=PASSWORD, server=SERVER)
    err = mt5.last_error()
    print("login ok:", login, " err:", err)
    info = mt5.account_info()
    if not info:
        print("account_info 失败:", mt5.last_error())
        return
    acct = {
        "login": info.login, "server": info.server,
        "currency": info.currency,
        "balance": float(info.balance), "equity": float(info.equity),
        "margin": float(info.margin), "free_margin": float(info.margin_free),
        "leverage": info.leverage, "trade_mode": info.trade_mode,
        "trade_allowed": bool(info.trade_allowed),
    }
    # 持仓
    pos = []
    for p in (mt5.positions_get() or []):
        pos.append({
            "ticket": p.ticket, "symbol": p.symbol,
            "type": "BUY" if p.type==0 else "SELL",
            "volume": float(p.volume), "price_open": float(p.price_open),
            "sl": float(p.sl), "tp": float(p.tp), "profit": float(p.profit),
        })
    # 最近成交
    deals = []
    now = int(time.time())
    for d in (mt5.history_deals_get(now-86400, now) or [])[:30]:
        deals.append({"symbol": d.symbol, "entry": d.entry, "profit": float(d.profit),
                     "time": datetime.datetime.fromtimestamp(d.time).isoformat(),
                     "comment": str(d.comment)})
    snap = {"generated": time.time(), "account": acct, "positions": pos,
            "recent_deals_24h": deals, "n_pos": len(pos), "n_deals": len(deals)}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(snap, open(OUT,"w",encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    print("余额:", acct["balance"], "净值:", acct["equity"], "杠杆:", acct["leverage"],
          "货币:", acct["currency"], "持仓:", len(pos))
    print("trade_mode:", acct["trade_mode"], "(0=real,1=demo) trade_allowed:", acct["trade_allowed"])
    if pos:
        for p in pos[:10]:
            print(f"  {p['symbol']} {p['type']} {p['volume']} @ {p['price_open']} PnL={p['profit']:+.2f}")
    mt5.shutdown()

if __name__ == "__main__":
    main()
