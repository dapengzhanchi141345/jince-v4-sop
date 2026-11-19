"""诊断用户实盘账户 60043976 的 PF 漏水点（只读，不改任何东西）。
目标：确认是 进场/退出/品种/策略 哪一层导致 PF<1.0。
"""
import json, datetime as dt
import MetaTrader5 as mt5

ACC = 60043976
OUT = "E:/GoldstrategyEngine/live_pf_diagnosis.json"

def main():
    if not mt5.initialize(timeout=30000):
        print("MT5 init FAIL:", mt5.last_error()); return
    # 只读确认账户
    acc = mt5.account_info()
    if acc is None or acc.login != ACC:
        print("账户不匹配:", acc.login if acc else None); mt5.shutdown(); return
    print(f"已连接账户 {acc.login}  server={acc.server}  余额={acc.balance:.2f} 净值={acc.equity:.2f}")

    now = dt.datetime.now()
    start = now - dt.timedelta(days=120)
    deals = mt5.history_deals_get(start, now)
    if deals is None:
        print("无成交历史"); mt5.shutdown(); return
    print(f"成交记录数: {len(deals)}")

    # 按 position_id 聚合每笔平仓 PnL
    trades = {}
    for d in deals:
        if d.entry not in (mt5.DEAL_ENTRY_IN, mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT):
            continue
        pid = d.position_id
        t = trades.setdefault(pid, {"symbol": d.symbol, "magic": d.magic,
                                    "pnl": 0.0, "commission": 0.0, "swap": 0.0,
                                    "vol": 0.0, "open": None, "close": None})
        t["pnl"] += d.profit
        t["commission"] += d.commission
        t["swap"] += d.swap
        t["vol"] = max(t["vol"], d.volume)
        if d.entry in (mt5.DEAL_ENTRY_IN, mt5.DEAL_ENTRY_OUT):
            if t["open"] is None: t["open"] = d.price
            t["close"] = d.price

    closed = [t for t in trades.values() if t["close"] is not None and t["pnl"] != 0]
    print(f"可聚合平仓笔数: {len(closed)}")

    def stats(rows):
        wins = [r["pnl"] for r in rows if r["pnl"] > 0]
        loss = [r["pnl"] for r in rows if r["pnl"] <= 0]
        n = len(rows)
        wr = len(wins)/n if n else 0
        gross_w = sum(wins); gross_l = -sum(loss)
        pf = (gross_w/gross_l) if gross_l else float("inf")
        avg_w = gross_w/len(wins) if wins else 0
        avg_l = gross_l/len(loss) if loss else 0
        wl = (avg_w/abs(avg_l)) if avg_l else float("inf")
        return {"n": n, "wr": round(wr,4), "gross_win": round(gross_w,2),
                "gross_loss": round(gross_l,2), "pf": round(pf,4),
                "avg_win": round(avg_w,2), "avg_loss": round(avg_l,2),
                "win_loss_ratio": round(wl,3)}

    rep = {"account": acc.login, "balance": round(acc.balance,2),
           "equity": round(acc.equity,2),
           "overall": stats(closed),
           "by_symbol": {}, "by_magic": {}}
    sym_map, mag_map = {}, {}
    for r in closed:
        sym_map.setdefault(r["symbol"], []).append(r)
        mag_map.setdefault(str(r["magic"]), []).append(r)
    for s, rows in sym_map.items():
        rep["by_symbol"][s] = stats(rows)
    for m, rows in mag_map.items():
        rep["by_magic"][m] = stats(rows)

    # 当前持仓
    pos = mt5.positions_get()
    rep["open_positions"] = len(pos) if pos else 0

    json.dump(rep, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    mt5.shutdown()
    o = rep["overall"]
    print(f"\n=== 总览 === n={o['n']} 胜率={o['wr']:.1%} PF={o['pf']} "
          f"avg_win={o['avg_win']} avg_loss={o['avg_loss']} W/L={o['win_loss_ratio']}")
    print("按品种:")
    for s, v in sorted(rep["by_symbol"].items(), key=lambda x: x[1]['pf']):
        print(f"  {s:8} n={v['n']:3} PF={v['pf']:.2f} wr={v['wr']:.0%} W/L={v['win_loss_ratio']}")
    print("按 magic(策略):")
    for m, v in sorted(rep["by_magic"].items(), key=lambda x: x[1]['pf']):
        print(f"  {m:8} n={v['n']:3} PF={v['pf']:.2f} wr={v['wr']:.0%} W/L={v['win_loss_ratio']}")
    print(f"\n写入 {OUT}")

if __name__ == "__main__":
    main()
