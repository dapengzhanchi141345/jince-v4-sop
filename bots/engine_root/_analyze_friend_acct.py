"""
分析朋友账户 60129252 的 "Godking Apex Short v4.2" 波段策略。
只读：强制同步历史、拉多周期K线、反推进场时机结构。不交易、不修改。
"""
import MetaTrader5 as mt5
import json
import datetime
import time

EXE = "E:/mt5_friend_observer/terminal64.exe"
LOGIN = 60129252
PASSWORD = "Aa141345$"
SERVER = "TradeMaxGlobal-Demo"
OUT_JSON = "E:/GoldstrategyEngine/friend_acct_analysis.json"

POS_FIELDS = ["ticket","time","type","volume","price_open","sl","tp","price_current",
              "profit","swap","comment","magic","symbol"]

def pos_dict(p):
    return {f: getattr(p, f, None) for f in POS_FIELDS}

def main():
    if not mt5.initialize(path=EXE, timeout=90000):
        print("INIT_FAIL", mt5.last_error()); return
    if not mt5.login(LOGIN, password=PASSWORD, server=SERVER):
        print("LOGIN_FAIL", mt5.last_error()); mt5.shutdown(); return

    # 强制同步历史（多次重试，确保 broker 历史下载完成）
    now = datetime.datetime.now()
    from_d = now - datetime.timedelta(days=400)
    deals = []
    for attempt in range(4):
        d = mt5.history_deals_get(from_d, now) or []
        if d:
            deals = d
            break
        print(f"history sync attempt {attempt}: 0 deals, waiting...")
        time.sleep(4)
    orders = mt5.history_orders_get(from_d, now) or []
    print(f"DEALS={len(deals)} ORDERS={len(orders)}")

    # 当前持仓
    positions = [pos_dict(p) for p in (mt5.positions_get() or [])]
    sym = "XAUUSD"
    # 品种信息
    si = mt5.symbol_info(sym)
    sinfo = {k: getattr(si, k, None) for k in
             ['digits','point','spread','swap_long','swap_short','volume_min','volume_step','trade_mode']}
    tick = mt5.symbol_info_tick(sym)
    cur = tick.bid

    # 多周期K线
    def get_rates(tf, count):
        rates = mt5.copy_rates_from_pos(sym, tf, 0, count)
        if rates is None: return None
        return [{"time": int(r[0]), "open": r[1], "high": r[2], "low": r[3],
                 "close": r[4], "vol": r[5]} for r in rates]
    d1 = get_rates(mt5.TIMEFRAME_D1, 120)
    h4 = get_rates(mt5.TIMEFRAME_H4, 240)
    h1 = get_rates(mt5.TIMEFRAME_H1, 400)

    # 反推进场时机：对每个空头入场，找其前 N 根 H1 的摆动高点，判断是否接近局部顶
    def nearest_idx(rates, t):
        # rates 按时间升序；返回 <= t 的最后一根下标
        lo, hi = 0, len(rates)-1
        best = 0
        for i, r in enumerate(rates):
            if r["time"] <= t:
                best = i
            else:
                break
        return best

    entry_analysis = []
    for p in positions:
        et = int(p["time"])
        et_dt = datetime.datetime.utcfromtimestamp(et) + datetime.timedelta(hours=8)  # Beijing
        idx = nearest_idx(h1, et)
        # 前 24 根 H1 摆动高点
        window = h1[max(0, idx-48):idx+1]
        swing_high = max(r["high"] for r in window) if window else p["price_open"]
        swing_low = min(r["low"] for r in window) if window else p["price_open"]
        entry = p["price_open"]
        # 入场距摆动高点（空头应在高点附近）
        dist_to_swing_high = entry - swing_high  # 正=高于摆动高(不可能), 负=低于
        # 入场后 12 根 H1 的最低价（验证是否随后下跌）
        after = h1[idx+1:idx+13]
        low_after = min(r["low"] for r in after) if after else entry
        moved_after = low_after - entry  # 空头为负=下跌(好)
        # R 倍数（到 SL）
        sl = p["sl"]
        risk_pts = sl - entry  # 空头 SL 在上方
        r_mult_now = (entry - cur) / risk_pts if risk_pts else None
        entry_analysis.append({
            "ticket": p["ticket"],
            "entry_beijing": et_dt.strftime("%Y-%m-%d %H:%M"),
            "entry_utc": datetime.datetime.utcfromtimestamp(et).strftime("%Y-%m-%d %H:%M"),
            "entry_price": entry,
            "sl": sl,
            "sl_distance_pts": round(risk_pts, 2),
            "sl_distance_pct": round(risk_pts / entry * 100, 2),
            "swing_high_48h": round(swing_high, 2),
            "swing_low_48h": round(swing_low, 2),
            "entry_vs_swinghigh_pts": round(entry - swing_high, 2),
            "low_12h_after": round(low_after, 2),
            "moved_after_pts": round(moved_after, 2),
            "cur_price": cur,
            "floating_profit": p["profit"],
            "r_now": round(r_mult_now, 2) if r_mult_now else None,
            "holding_hours": round((int(time.time()) - et)/3600, 1),
        })

    # 历史平仓统计（若有）
    closed = []
    if deals:
        # 按 order 配对粗略统计
        for d in deals:
            closed.append({
                "ticket": d.ticket, "order": d.order, "time": datetime.datetime.utcfromtimestamp(int(d.time)).strftime("%Y-%m-%d %H:%M"),
                "type": d.type, "volume": d.volume, "price": d.price, "profit": d.profit,
                "symbol": d.symbol, "comment": d.comment, "magic": d.magic
            })

    result = {
        "captured_at_beijing": (datetime.datetime.now()+datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M"),
        "account_server": SERVER, "login": LOGIN,
        "symbol_info": sinfo,
        "current_bid": cur,
        "positions": positions,
        "entry_analysis": entry_analysis,
        "history_deals_total": len(deals),
        "closed_deals_sample": closed[:50],
        "d1_last10": (d1[-10:] if d1 else None),
        "h4_last30": (h4[-30:] if h4 else None),
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print("SAVED", OUT_JSON)
    # 终端摘要
    print("ENTRY ANALYSIS:")
    for e in entry_analysis:
        print(f"  #{e['ticket']} {e['entry_beijing']} entry={e['entry_price']} swingHi48h={e['swing_high_48h']} "
              f"entryVsSwingHi={e['entry_vs_swinghigh_pts']} movedAfter={e['moved_after_pts']} Rnow={e['r_now']} hold={e['holding_hours']}h")
    mt5.shutdown()

if __name__ == "__main__":
    main()
