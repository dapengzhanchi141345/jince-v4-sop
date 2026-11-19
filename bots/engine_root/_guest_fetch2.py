# -*- coding: utf-8 -*-
"""自包含只读拉取: 拉 guest 终端 -> 循环登录到连上 -> 拉全量 -> 写 JSON -> 关.
铁律: 只读. 全程不 order_send / position_close / 任何交易动作.
"""
import MetaTrader5 as mt5, json, os, time, datetime, subprocess

DF = "E:/GoldstrategyEngine/_guest_mt5"
OUT = "E:/GoldstrategyEngine/_guest_analysis"
os.makedirs(OUT, exist_ok=True)
TARGET = 81223578
PWD = "abc321321D$"
SERVER = "ECMarkets-MT5-Live01"

def p(*a):
    print(" ".join(str(x) for x in a), flush=True)

# 1) 起一个常驻 guest 终端(独立 datafolder, 不碰引擎 20600)
subprocess.Popen([r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe",
                   r"-datafolder=E:\GoldstrategyEngine\_guest_mt5", "-name=GUEST"],
                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
p("已拉起 guest 终端, 等待初始化...")
time.sleep(20)

# 2) 连 + 循环登录到真正连上(余额非 0 才算成), 最多 6 分钟
connected = False
for i in range(40):
    mt5.initialize(data_folder=DF)
    ai = mt5.account_info()
    if ai and ai.login == TARGET and (ai.balance or 0) != 0:
        connected = True
        break
    if not (mt5.login(TARGET, password=PWD, server=SERVER, timeout=10000)):
        pass
    ai = mt5.account_info()
    if ai and ai.login == TARGET and (ai.balance or 0) != 0:
        connected = True
        break
    p(f"  第{i+1}次未连上 login={getattr(ai,'login',None)} err={mt5.last_error()} 重试")
    time.sleep(8)

if not connected:
    p("FATAL: 6 分钟仍未连上 81223578(余额非0), 终止")
    mt5.shutdown(); raise SystemExit(1)

ai = mt5.account_info()
p("已连上:", ai.login, "/", ai.server, "| 余额:", ai.balance, "| 净值:", ai.equity,
  "| 杠杆:", ai.leverage, "| 币种:", ai.currency, "| 可用:", ai.margin_free)

acct = {"login": ai.login, "server": ai.server, "currency": ai.currency,
        "leverage": ai.leverage, "balance": ai.balance, "equity": ai.equity,
        "profit": ai.profit, "margin": ai.margin, "margin_free": ai.margin_free,
        "trade_mode": getattr(ai, "trade_mode", None),
        "fetched_at": datetime.datetime.now().astimezone().isoformat()}
json.dump(acct, open(os.path.join(OUT, "account.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
p("account.json 已写")

# 3) 持仓 + 挂单(只读)
pos = mt5.positions_get() or []
json.dump([{"ticket": x.ticket, "symbol": x.symbol, "type": x.type, "volume": x.volume,
            "price_open": x.price_open, "sl": x.sl, "tp": x.tp, "price_current": x.price_current,
            "profit": x.profit, "magic": x.magic, "comment": x.comment,
            "time": datetime.datetime.fromtimestamp(x.time).isoformat()} for x in pos],
          open(os.path.join(OUT, "positions.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
p("持仓:", len(pos))
ordr = mt5.orders_get() or []
json.dump([{"ticket": x.ticket, "symbol": x.symbol, "type": x.type, "volume": x.volume,
            "price": x.price, "sl": x.sl, "tp": x.tp, "magic": x.magic, "comment": x.comment} for x in ordr],
          open(os.path.join(OUT, "orders.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
p("挂单:", len(ordr))

# 4) 全量成交流水(段拉, 断点续)
start = int(datetime.datetime(2018, 1, 1).timestamp())
end = int(time.time())
all_deals = []
cur = start
while cur < end:
    ce = min(cur + 86400 * 120, end)
    ds = mt5.history_deals_get(int(cur), int(ce))
    if ds is None:
        p("  deals 段失败, 重试", mt5.last_error()); time.sleep(3); continue
    if len(ds) == 0:
        cur = ce; continue
    all_deals.extend(ds)
    p("  deals 累计", len(all_deals), "至", datetime.datetime.fromtimestamp(ds[-1].time).strftime("%Y-%m"))
    cur = ds[-1].time
    if cur <= start: break
    time.sleep(0.2)
json.dump([{"ticket": d.ticket, "time": datetime.datetime.fromtimestamp(d.time).isoformat(),
            "entry": d.entry, "type": d.type, "symbol": d.symbol, "volume": d.volume,
            "price": d.price, "profit": d.profit, "swaps": d.swaps, "commission": d.commission,
            "reason": d.reason, "magic": d.magic, "comment": d.comment,
            "position_id": d.position_id} for d in all_deals],
          open(os.path.join(OUT, "deals.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
p("全量 deals:", len(all_deals))

# 5) 全量历史订单
all_orders = []
cur = start
while cur < end:
    ce = min(cur + 86400 * 120, end)
    oo = mt5.history_orders_get(int(cur), int(ce))
    if oo is None:
        time.sleep(3); continue
    if len(oo) == 0:
        cur = ce; continue
    all_orders.extend(oo)
    cur = oo[-1].time
    if cur <= start: break
    time.sleep(0.2)
json.dump([{"ticket": o.ticket, "time": datetime.datetime.fromtimestamp(o.time).isoformat(),
            "type": o.type, "state": o.state, "symbol": o.symbol, "volume": o.volume,
            "price": o.price, "sl": o.sl, "tp": o.tp, "magic": o.magic, "comment": o.comment}
           for o in all_orders],
          open(os.path.join(OUT, "hist_orders.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
p("全量 history orders:", len(all_orders))

mt5.shutdown()
p("全部拉取完成, guest 已关, 引擎不受影响. 输出目录:", OUT)
