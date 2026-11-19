"""近期(30天)实盘 PF 诊断 —— 用于验证"live 品种质量闸"的预期收益。只读。"""
import json, datetime as dt
import MetaTrader5 as mt5

ACC = 60043976
OUT = "E:/GoldstrategyEngine/live_pf_diagnosis_recent.json"
WINDOW_DAYS = 30

def main():
    if not mt5.initialize(timeout=30000):
        print("MT5 init FAIL:", mt5.last_error()); return
    acc = mt5.account_info()
    if acc is None or acc.login != ACC:
        print("账户不匹配"); mt5.shutdown(); return
    now = dt.datetime.now()
    start = now - dt.timedelta(days=WINDOW_DAYS)
    deals = mt5.history_deals_get(start, now)
    if deals is None:
        print("无成交"); mt5.shutdown(); return
    trades = {}
    for d in deals:
        if d.entry not in (mt5.DEAL_ENTRY_IN, mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT):
            continue
        pid = d.position_id
        t = trades.setdefault(pid, {"symbol": d.symbol, "magic": d.magic,
                                    "pnl": 0.0, "close": None})
        t["pnl"] += d.profit
        if d.entry in (mt5.DEAL_ENTRY_IN, mt5.DEAL_ENTRY_OUT):
            t["close"] = d.price
    closed = [t for t in trades.values() if t["close"] is not None and t["pnl"] != 0]
    def stats(rows):
        wins = [r["pnl"] for r in rows if r["pnl"] > 0]
        loss = [r["pnl"] for r in rows if r["pnl"] <= 0]
        n = len(rows); wr = len(wins)/n if n else 0
        gw = sum(wins); gl = -sum(loss)
        pf = (gw/gl) if gl else float("inf")
        aw = gw/len(wins) if wins else 0
        al = gl/len(loss) if loss else 0
        return {"n": n, "wr": round(wr,4), "pf": round(pf,3),
                "avg_win": round(aw,2), "avg_loss": round(al,2),
                "wl": round(aw/al,3) if al else float("inf")}
    rep = {"window_days": WINDOW_DAYS, "overall": stats(closed), "by_symbol": {}, "by_magic": {}}
    sm, mm = {}, {}
    for r in closed:
        sm.setdefault(r["symbol"], []).append(r)
        mm.setdefault(str(r["magic"]), []).append(r)
    for s, rows in sm.items(): rep["by_symbol"][s] = stats(rows)
    for m, rows in mm.items(): rep["by_magic"][m] = stats(rows)
    json.dump(rep, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    mt5.shutdown()
    o = rep["overall"]
    print(f"近期 {WINDOW_DAYS}天: n={o['n']} 胜率={o['wr']:.1%} PF={o['pf']} W/L={o['wl']}")
    print("按品种(PF升序):")
    for s, v in sorted(rep["by_symbol"].items(), key=lambda x: x[1]['pf']):
        print(f"  {s:9} n={v['n']:3} PF={v['pf']:.2f} wr={v['wr']:.0%} W/L={v['wl']}")
    print("按 magic:")
    for m, v in sorted(rep["by_magic"].items(), key=lambda x: x[1]['pf']):
        print(f"  {m:8} n={v['n']:3} PF={v['pf']:.2f} wr={v['wr']:.0%} W/L={v['wl']}")
    print(f"写入 {OUT}")
if __name__ == "__main__":
    main()
