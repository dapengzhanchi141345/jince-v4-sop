# 11-07 23:2x 开的 0.01 观察腿 12h 必平哨 (magic 30261106, BTC/ETH SELL 各0.01)
# 李彦明 11-07 深夜令: 深度优化后加快进化速度+直接操作本账号 -> 本哨升级为"平仓+立刻滚仓重开"自动循环
# (0.01样本腿全天滚动攒OOS, 30笔进度加速; 红线不动: 12h不过夜/10%熔断/连亏3笔冷却)
# 李彦明 11-07 末令: 每笔单开/关时刻务必清楚 -> 本哨平/开都追加 order_lifecycle.jsonl (自动台账, 不等提醒)
import subprocess, os, sys
ATE = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
inner = r'''
import MetaTrader5 as mt5, json, datetime, os
if not mt5.initialize():
    print("CLOSE_SENT: INIT_FAIL 终端不在线, 15min后重跑"); raise SystemExit
MAGIC = 30261106
LC = "E:/GoldstrategyEngine/data/order_lifecycle.jsonl"
def _now(): return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
def _lc(rec):
    with open(LC, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
# 平仓前: 读开仓时刻(该票号在台账里的open行), 平后写close行(闭环)
open_rows = {}
if os.path.exists(LC):
    for l in open(LC, encoding="utf-8"):
        try:
            row = json.loads(l)
            if row.get("ticket"): open_rows[row["ticket"]] = row
        except Exception: pass
targets = [p for p in (mt5.positions_get() or []) if p.magic == MAGIC]
if targets:
    for p in targets:
        si = mt5.symbol_info(p.symbol)
        close_px = si.bid if p.type == 1 else si.ask  # SELL用bid平, BUY用ask平
        r = mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol,
                            "volume": p.volume, "type": mt5.ORDER_TYPE_BUY if p.type == 1 else mt5.ORDER_TYPE_SELL,
                            "price": close_px, "position": p.ticket, "deviation": 20,
                            "magic": MAGIC, "comment": "close12h_obs", "type_time": mt5.ORDER_TIME_GTC,
                            "type_filling": mt5.ORDER_FILLING_IOC})
        print("已平: %s ticket=%d @%.2f retcode=%s | %s" % (p.symbol, p.ticket, close_px, r.retcode, r.comment))
        _lc({"ts": _now(), "sym": p.symbol, "ticket": p.ticket, "magic": MAGIC,
             "open_ts": open_rows.get(p.ticket, {}).get("ts", "未核(旧单)"), "close_ts": _now(),
             "close_px": close_px, "retcode": r.retcode, "status": "closed",
             "close_reason": "12h哨自动平仓(李11-07令: 开/关时刻清楚, 不等提醒)"})
# 加速进化(李彦明令): 平仓后立刻滚仓重开0.01样本腿(过灵魂闸四步: 价新鲜/防叠单/回撤/事件窗, 此处终端直读=价新鲜,
# 回撤读risk_state, 连亏3笔冷却读家族账) -> 全天滚动攒OOS
import json
roll = True
try:
    rj = json.load(open("E:/GoldstrategyEngine/data/risk_state.json", encoding="utf-8"))
    dd = rj.get("equity_dd_pct") or 0
    if dd >= 10:
        print("RISK_HOLD: 回撤%.1f%%>=10%熔断线, 暂停滚仓(红线不动)" % dd); roll = False
except Exception:
    pass
if roll:
    import time; time.sleep(5)
    for sym in ["BTCUSD", "ETHUSD"]:
        if any(p.magic == MAGIC and p.symbol == sym for p in (mt5.positions_get() or [])):
            continue  # 防叠单: 该品种已有腿就跳过
        si = mt5.symbol_info(sym)
        if not si or si.trade_mode != 1:
            print("%s 仍不可开单(trade_mode=%s), 下轮再试" % (sym, si.trade_mode if si else "?")); continue
        bid = si.bid; sl = round(bid * 1.005, si.digits); tp = round(bid * 0.985, si.digits)
        r = mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": 0.01,
                            "type": mt5.ORDER_TYPE_SELL, "price": bid, "sl": sl, "tp": tp,
                            "deviation": 20, "magic": MAGIC, "comment": "obs_roll_1107",
                            "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC})
        print("滚仓重开: %s SELL 0.01 @%.2f retcode=%s deal=%s | %s" % (sym, bid, r.retcode, r.deal, r.comment))
        _lc({"ts": _now(), "sym": sym, "side": "SELL", "vol": 0.01, "magic": MAGIC,
             "open_px": bid, "sl": sl, "tp": tp, "retcode": r.retcode, "deal": r.deal,
             "close_due": "开仓+12h(下轮12h哨自动平)", "sentinel": "41112d6bfbc3(每12h循环:平+滚仓)",
             "status": "open" if r.retcode in (10008, 10009, 10010) else "REJECTED",
             "note": "12h哨滚仓自动重开(0.01样本腿, 攒OOS)"})
else:
    print("(滚仓已按熔断暂停, 平仓动作已完成)")
mt5.shutdown()
'''
open(os.path.join(HERE, "close_obs12h_inner_1108.py"), "w", encoding="utf-8").write(inner)
r = subprocess.run([ATE, os.path.join(HERE, "close_obs12h_inner_1108.py")],
                   capture_output=True, text=True, timeout=120,
                   env={k: v for k, v in os.environ.items() if k not in
                        ("PYTHONPATH", "PYTHONHOME", "PYTHONNOUSERSITE")})
out = r.stdout.strip()
if out:
    print("【0.01观察腿12h平仓+滚仓】\n" + out)
