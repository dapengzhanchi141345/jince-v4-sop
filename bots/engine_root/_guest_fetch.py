# -*- coding: utf-8 -*-
"""客户实盘账户 只读数据拉取 (EC Markets 81223578)
铁律: 只读。不 order_send / position_close / 任何交易动作。
输出: E:/GoldstrategyEngine/_guest_analysis/{account,positions,orders,deals,hist_orders}.json
"""
import MetaTrader5 as mt5, json, os, time, datetime

DF = "E:/GoldstrategyEngine/_guest_mt5"
OUT = "E:/GoldstrategyEngine/_guest_analysis"
os.makedirs(OUT, exist_ok=True)
TARGET = 81223578
PWD = "abc321321D$"

log = []
def p(*a):
    msg = " ".join(str(x) for x in a)
    log.append(msg)
    print(msg)

ok = mt5.initialize(data_folder=DF)
p("guest init:", ok, "| last_error:", mt5.last_error())
if not ok:
    p("FATAL: init 失败, 终止")
    raise SystemExit(1)

# 确认/登录
for attempt in range(3):
    ai = mt5.account_info()
    if ai is not None and ai.login == TARGET:
        p("attempt", attempt, "已连上:", ai.login, "/", ai.server)
        break
    p("attempt", attempt, "未连上, 试 login...")
    r = mt5.login(TARGET, password=PWD, server="ECMarkets-MT5-Live01", timeout=15000)
    p("  login:", r, "| err:", mt5.last_error())
    time.sleep(6)

ai = mt5.account_info()
if ai is None:
    p("FATAL: account_info 空, 连不上, 终止")
    mt5.shutdown(); raise SystemExit(1)

# trade_mode: 0=REAL, 1=DEMO (meta库常量)
mode = getattr(ai, "trade_mode", None)
p("账户:", ai.login, "/", ai.server, "| 币种:", ai.currency, "| 杠杆:", ai.leverage,
  "| 余额:", ai.balance, "| 净值:", ai.equity, "| 浮盈:", ai.profit,
  "| 占用保证金:", ai.margin, "| 可用:", ai.margin_free,
  "| trade_mode:", mode, "(0=实盘REAL, 1=模拟DEMO)")

acct = {"login": ai.login, "server": ai.server, "currency": ai.currency,
        "leverage": ai.leverage, "balance": ai.balance, "equity": ai.equity,
        "profit": ai.profit, "margin": ai.margin, "margin_free": ai.margin_free,
        "trade_mode": mode, "fetched_at": datetime.datetime.now().astimezone().isoformat()}
json.dump(acct, open(os.path.join(OUT, "account.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# 持仓
pos = mt5.positions_get() or []
p("当前持仓数:", len(pos))
pos_json = [{"ticket": x.ticket, "symbol": x.symbol, "type": x.type, "volume": x.volume,
             "price_open": x.price_open, "sl": x.sl, "tp": x.tp, "price_current": x.price_current,
             "profit": x.profit, "magic": x.magic, "comment": x.comment,
             "time": datetime.datetime.fromtimestamp(x.time).isoformat()} for x in pos]
json.dump(pos_json, open(os.path.join(OUT, "positions.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# 挂单
ordr = mt5.orders_get() or []
p("当前挂单数:", len(ordr))
ord_json = [{"ticket": x.ticket, "symbol": x.symbol, "type": x.type, "volume": x.volume,
             "price": x.price, "sl": x.sl, "tp": x.tp, "magic": x.magic, "comment": x.comment,
             "time": datetime.datetime.fromtimestamp(x.time).isoformat()} for x in ordr]
json.dump(ord_json, open(os.path.join(OUT, "orders.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# 全量成交流水 (deals) — 从 2020 拉到现在, 分段拉防超时
start = datetime.datetime(2020, 1, 1).timestamp()
end = time.time()
all_deals = []
cur = start
while cur < end:
    chunk_end = min(cur + 86400 * 180, end)  # 每次 180 天
    ds = mt5.history_deals_get(int(cur), int(chunk_end))
    if ds is None:
        p("  deals 段拉取失败 cur=", cur, mt5.last_error()); time.sleep(2); continue
    if len(ds) == 0:
        cur = chunk_end; continue
    all_deals.extend(ds)
    p("  deals 累计:", len(all_deals), "last time:", datetime.datetime.fromtimestamp(ds[-1].time).strftime("%Y-%m-%d"))
    cur = ds[-1].time
    if cur <= start: break
    time.sleep(0.3)

p("全量 deals:", len(all_deals))
deals_json = [{"ticket": d.ticket, "time": datetime.datetime.fromtimestamp(d.time).isoformat(),
               "entry": d.entry, "type": d.type, "symbol": d.symbol, "volume": d.volume,
               "price": d.price, "profit": d.profit, "swaps": d.swaps, "commission": d.commission,
               "reason": d.reason, "magic": d.magic, "comment": d.comment,
               "order": d.order, "position_id": d.position_id} for d in all_deals]
json.dump(deals_json, open(os.path.join(OUT, "deals.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# 全量历史订单 (含挂单/撤销记录)
all_orders = []
cur = start
while cur < end:
    chunk_end = min(cur + 86400 * 180, end)
    os_ = mt5.history_orders_get(int(cur), int(chunk_end))
    if os_ is None:
        time.sleep(2); continue
    if len(os_) == 0:
        cur = chunk_end; continue
    all_orders.extend(os_)
    cur = os_[-1].time
    if cur <= start: break
    time.sleep(0.3)
p("全量 history orders:", len(all_orders))
ojson = [{"ticket": o.ticket, "time": datetime.datetime.fromtimestamp(o.time).isoformat(),
          "type": o.type, "state": o.state, "symbol": o.symbol, "volume": o.volume,
          "price": o.price, "sl": o.sl, "tp": o.tp, "magic": o.magic, "comment": o.comment} for o in all_orders]
json.dump(ojson, open(os.path.join(OUT, "hist_orders.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# 品种列表
syms = mt5.symbols_get() or []
json.dump([s.name for s in syms], open(os.path.join(OUT, "symbols.txt"), "w", encoding="utf-8"))

mt5.shutdown()
p("拉取完成, guest 终端已关闭, 引擎不受影响")
p("输出:", OUT)
