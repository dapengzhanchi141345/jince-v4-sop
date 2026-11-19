"""
只读探针（一次性）：找回 2026-09-08 ~ 2026-09-13 之间朋友账户 60129252 的成交。
重点：第3空篮平仓价/PnL、是否有新篮开/平、反推趋势退出逻辑。
绝不下单、绝不修改。仅用 E:/mt5_friend_observer 隔离终端。
"""
import MetaTrader5 as mt5
import datetime as dt
import time

EXE = "E:/mt5_friend_observer/terminal64.exe"
LOGIN = 60129252
PASSWORD = "Aa141345$"
SERVERS = ["TradeMaxGlobal-Demo", "123.56.129.232:443", "123.56.129.232:4433"]
SYM = "XAUUSD"

def srv2bj(epoch):
    return dt.datetime.utcfromtimestamp(epoch) + dt.timedelta(hours=5)

ok = False
for attempt in range(1, 5):
    if mt5.initialize(path=EXE, timeout=90000):
        ok = True
        break
    print(f"INIT_FAIL attempt {attempt}: {mt5.last_error()}")
    time.sleep(10)
if not ok:
    print("ALL_INIT_FAIL"); raise SystemExit

authorized = False
for srv in SERVERS:
    if mt5.login(LOGIN, password=PASSWORD, server=srv):
        authorized = True
        print("LOGIN_OK server=", srv)
        break
    print("LOGIN_FAIL", srv, mt5.last_error())
if not authorized:
    print("ALL_LOGIN_FAILED"); mt5.shutdown(); raise SystemExit

# 等终端把历史成交从服务器同步下来再查
print("waiting 25s for history sync ...")
time.sleep(25)

frm = dt.datetime(2026, 9, 8)
to  = dt.datetime(2026, 9, 13)
deals = mt5.history_deals_get(frm, to) or []
print(f"\n=== DEALS {len(deals)} (server {frm} ~ {to}) ===")

xau = [d for d in deals if d.symbol == SYM]
xau.sort(key=lambda d: d.time)
for d in xau:
    ttype = {0: "BUY", 1: "SELL"}.get(d.type, d.type)
    entry = {0: "IN ", 1: "OUT", 2: "INOUT"}.get(d.entry, d.entry)
    print(f"{srv2bj(d.time)} BJ | {ttype:4s} {entry} vol={d.volume} px={d.price:.2f} "
          f"pnl={d.profit:+7.2f} swap={d.swap:+6.2f} net={d.profit+d.swap:+7.2f} "
          f"magic={d.magic} cmt='{d.comment}'")

outs = [d for d in xau if d.entry in (1, 2)]
realized = sum(d.profit + d.swap for d in outs)
print(f"\n=== 缺口期已实现(平仓)净盈亏合计 = {realized:+.2f} (共 {len(outs)} 笔平仓) ===")

pos = mt5.positions_get(symbol=SYM) or []
print(f"\n=== 当前 XAUUSD 持仓 {len(pos)} ===")
for p in pos:
    print(f"tk={p.ticket} {p.type} vol={p.volume} open={p.price_open} sl={p.sl} tp={p.tp} "
          f"profit={p.profit:+7.2f} cmt='{p.comment}'")

# 全量历史成交数（验证 broker 是否清过历史）
all_deals = mt5.history_deals_get(dt.datetime(2025,1,1), dt.datetime(2026,12,31)) or []
print(f"\n=== 全量历史成交总数(2025~2026) = {len(all_deals)} ===")

acc = mt5.account_info()
print(f"\n=== 账户 === balance={acc.balance} equity={acc.equity} profit={acc.profit}")
mt5.shutdown()
