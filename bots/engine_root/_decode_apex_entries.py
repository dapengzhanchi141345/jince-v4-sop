# -*- coding: utf-8 -*-
"""
深度反推 Godking Apex Short v4.2 的【开单逻辑】。
方法：用隔离观测终端拉 XAUUSD 多周期 K 线，定位 5 笔空单的精确入场 H1 根，
逐根打印入场前导结构 + 入场 K 线形态，反推「进场点位」判定条件。
只读，不交易。
"""
import MetaTrader5 as mt5
import numpy as np, pandas as pd, json, os, time

EXE = r"E:/mt5_friend_observer/terminal64.exe"
SYMBOL = "XAUUSD"

# 5 笔空单入场时间(UTC秒) + 入场价（来自快照）
ENTRIES = [
    (1788172200, 4443.81),
    (1788177900, 4438.67),
    (1788196500, 4427.47),
    (1788207600, 4436.02),
    (1788219900, 4448.02),
]

def to_bj(uts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(uts + 8 * 3600))

def init():
    if not mt5.initialize(path=EXE, timeout=60000):
        # 尝试不带 path（系统已注册 terminal）
        if not mt5.initialize(timeout=60000):
            raise RuntimeError("INIT_FAIL " + str(mt5.last_error()))
    if not mt5.login(60129252, password="Aa141345$", server="TradeMaxGlobal-Demo"):
        raise RuntimeError("LOGIN_FAIL " + str(mt5.last_error()))

def fetch(tf, count):
    rates = mt5.copy_rates_from_pos(SYMBOL, tf, 0, count)
    if rates is None:
        return None
    df = pd.DataFrame(rates)
    df['time'] = df['time'].astype(int)
    return df

def main():
    init()
    # 拉足够历史：H1 近 600 根(25天) 足够覆盖 8/28~9/02
    h1 = fetch(mt5.TIMEFRAME_H1, 650)
    h4 = fetch(mt5.TIMEFRAME_H4, 200)
    d1 = fetch(mt5.TIMEFRAME_D1, 60)
    if h1 is None or h4 is None or d1 is None:
        raise RuntimeError("FETCH_FAIL")
    print("H1 bars:", len(h1), " range", to_bj(h1['time'].iloc[0]), "~", to_bj(h1['time'].iloc[-1]))
    print("H4 bars:", len(h4), " D1 bars:", len(d1))

    # index of entry time in h1
    out = {"entries": []}
    for et, ep in ENTRIES:
        # find h1 bar whose time <= et < time+3600  (entry executed during this bar's open->next)
        mask = (h1['time'] <= et) & (h1['time'] + 3600 > et)
        idxs = h1.index[mask]
        if len(idxs) == 0:
            # fallback: nearest before
            idxs = h1.index[h1['time'] <= et]
            if len(idxs) == 0:
                continue
            bi = idxs[-1]
        else:
            bi = idxs[-1]
        start = max(0, bi - 24)
        window = h1.iloc[start:bi + 4]  # 前24根 + 入场根 + 后3根
        rec = {
            "entry_beijing": to_bj(et),
            "entry_price": ep,
            "h1_window": [],
        }
        for r_i, row in window.iterrows():
            is_entry = (row['time'] <= et) and (row['time'] + 3600 > et)
            rec["h1_window"].append({
                "bj": to_bj(row['time']),
                "o": round(row['open'], 2),
                "h": round(row['high'], 2),
                "l": round(row['low'], 2),
                "c": round(row['close'], 2),
                "entry_bar": bool(is_entry),
            })
        out["entries"].append(rec)
        print("\n==== ENTRY", to_bj(et), "price", ep, "====")
        for w in rec["h1_window"]:
            tag = " <== ENTRY" if w["entry_bar"] else ""
            print(f"  {w['bj']}  O{w['o']:>7} H{w['h']:>7} L{w['l']:>7} C{w['c']:>7}{tag}")

    # H4 结构：入场前 20 根 H4
    print("\n==== H4 STRUCTURE (前 24 根 H4, 覆盖 8/28~9/02) ====")
    h4w = h4.iloc[-24:]
    for r_i, row in h4w.iterrows():
        print(f"  {to_bj(row['time'])}  O{row['open']:>7} H{row['high']:>7} L{row['low']:>7} C{row['close']:>7}")

    # D1 结构
    print("\n==== D1 STRUCTURE (前 12 根) ====")
    for r_i, row in d1.iloc[-12:].iterrows():
        print(f"  {to_bj(row['time'])}  O{row['open']:>7} H{row['high']:>7} L{row['low']:>7} C{row['close']:>7}")

    # 计算关键结构位（用于反推进场区/止损）
    h4c = h4['close'].values.astype(float)
    h4h = h4['high'].values.astype(float)
    h4l = h4['low'].values.astype(float)
    # 入场时段(8/31)前的最近摆动高点
    win = h4h[-40:]
    major_high = float(np.max(win))
    print("\n==== KEY LEVELS ====")
    print("  H4 窗口(近40根) 最高摆动高点 major_high =", round(major_high, 2))
    print("  入场区(5笔) = 4427~4448 ; 当前 SL = 4654.32 ; 前高失效位 4692.15(旧)")
    print("  8/30 破位大阴低点(结构需求) = 4445/4396 ; 反弹供给区上沿 = 4472(8/31 04:00 H4高)")

    with open("E:/GoldstrategyEngine/apex_entry_kline_decode.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print("\nSAVED apex_entry_kline_decode.json")
    mt5.shutdown()

if __name__ == "__main__":
    main()
