"""
只读探针：朋友账户 60129252 方向翻转 + 篮子SL锚点定标
1) 用远期边界补查历史成交/订单（找回多单入场 deal）
2) 取 XAUUSD D1/H4/H1 ATR，检验 SL≈3xATR 假设
3) 找入场前的结构低点，检验 SL 是否锚定 swing low
绝不下单、绝不修改。仅使用 E:/mt5_friend_observer 隔离终端。
"""
import MetaTrader5 as mt5
import datetime as dt

EXE = "E:/mt5_friend_observer/terminal64.exe"
LOGIN = 60129252
PASSWORD = "Aa141345$"
SERVER = "TradeMaxGlobal-Demo"
SYM = "XAUUSD"

def srv2bj(epoch):
    return dt.datetime.utcfromtimestamp(epoch) + dt.timedelta(hours=5)

if not mt5.initialize(path=EXE, timeout=90000):
    print("INIT_FAIL", mt5.last_error()); raise SystemExit
if not mt5.login(LOGIN, password=PASSWORD, server=SERVER):
    print("LOGIN_FAIL", mt5.last_error()); mt5.shutdown(); raise SystemExit
print("LOGIN_OK")

# ── 1. 补查成交（边界推到远期） ──
frm = dt.datetime(2026, 8, 25)
to = dt.datetime(2026, 9, 10)
deals = mt5.history_deals_get(frm, to) or []
print(f"\n=== DEALS {len(deals)} (2026-08-25 ~ 09-10) ===")
for d in deals:
    if d.symbol != SYM:
        continue
    ttype = {0: "BUY", 1: "SELL"}.get(d.type, d.type)
    entry = {0: "IN ", 1: "OUT", 2: "INOUT"}.get(d.entry, d.entry)
    print(f"{srv2bj(d.time)} BJ | {ttype:4s} {entry} vol={d.volume} px={d.price:.2f} "
          f"pnl={d.profit:+7.2f} swap={d.swap:+5.2f} magic={d.magic} cmt='{d.comment}'")

orders = mt5.history_orders_get(frm, to) or []
print(f"\n=== ORDERS {len(orders)} ===")
for o in orders:
    print(f"{srv2bj(o.time_setup)} BJ | tk={o.ticket} type={o.type} state={o.state} "
          f"vol={o.volume_initial} sl={o.sl} tp={o.tp} cmt='{o.comment}'")

# ── 2. ATR ──
print("\n=== ATR ===")


def atr(tf, n=14, label=""):
    r = mt5.copy_rates_from_pos(SYM, tf, 0, n + 60)
    if r is None or len(r) < n + 2:
        print(f"{label}: no data"); return None
    trs = []
    for i in range(1, len(r)):
        h, l, pc = r[i]['high'], r[i]['low'], r[i - 1]['close']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    a = sum(trs[-n:]) / n
    print(f"ATR({label},{n}) = {a:.2f}   x2={a*2:.1f}  x2.5={a*2.5:.1f}  x3={a*3:.1f}  x3.5={a*3.5:.1f}")
    return a


atr(mt5.TIMEFRAME_D1, 14, "D1")
atr(mt5.TIMEFRAME_H4, 14, "H4")
atr(mt5.TIMEFRAME_H1, 14, "H1")

# ── 3. 结构低点 / 价格路径 ──
POS_SL = 4061.92
LONG1_T = 1788381300   # 多单1 开仓(server epoch)
LONG1_PX = 4368.33
print("\n=== 多单入场前后 结构 / SL 锚点检验 ===")
print(f"多单1 入场 {srv2bj(LONG1_T)} BJ @ {LONG1_PX}   共享SL={POS_SL}  距入场 {POS_SL-LONG1_PX:+.2f}")

for tf, lab, look in ((mt5.TIMEFRAME_D1, "D1", 40), (mt5.TIMEFRAME_H4, "H4", 90), (mt5.TIMEFRAME_H1, "H1", 200)):
    r = mt5.copy_rates_from_pos(SYM, tf, 0, look)
    if r is None:
        continue
    pre = [b for b in r if b['time'] <= LONG1_T]
    if not pre:
        continue
    for w in (10, 20, 30, 50, 100):
        seg = pre[-w:]
        if len(seg) < w:
            continue
        lo = min(b['low'] for b in seg)
        hi = max(b['high'] for b in seg)
        print(f"  {lab} 前{w:3d}根: low={lo:.2f} (SL-low={POS_SL-lo:+7.2f})  high={hi:.2f}")

tick = mt5.symbol_info_tick(SYM)
si = mt5.symbol_info(SYM)
print(f"\n现价 bid={tick.bid} ask={tick.ask}  spread={(tick.ask-tick.bid):.2f}")
print(f"swap_long={si.swap_long} swap_short={si.swap_short} swap_mode={si.swap_mode}")
mt5.shutdown()
