# -*- coding: utf-8 -*-
"""slv2_sol_market_in_1117.py — SOL 赚钱格(全品种深优 4/6 OOS双正: SL0.8×ATR30 + TP2R +68.5净R) 21:00 BJT
[11-17 李令"全部按你赚钱的参数来执行, 深度优化"] 币go窗13-21UTC(21:00-05:00 BJT)开市
DEMO 60137964, 0.01 lot, D1空头同向空腿, 市价进(限价通道10015降级)
红线: 0.01 不加, 叠单去重, 12h 处置红线
"""
import json, datetime, os, time, sys, subprocess

BASE = r"E:/GoldstrategyEngine/data"
MAGIC = 20261104
WAVE = "v3fwd-slv2sol-20261117"
# [全品种深优 SOL 最优格] R=0.8×ATR30(0.4762)=0.38, TP3R=最优格(+84.2净R 4/6 OOS双正; TP2R +68.5同过线但净R低)
R_DIST = 0.38
TP_MULT = 3.0

def log_ledger(row):
    with open(os.path.join(BASE, "order_lifecycle.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    r = subprocess.run([sys.executable, "-c", "import mt5; mt5.initialize(); print(mt5.terminal_info().pid)"],
                       capture_output=True, text=True, timeout=30)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if "64" not in r.stdout and "32" not in r.stdout:
        print("MT5未连接, 尝试终端启动"); subprocess.run(["D:/MT5/terminal64.exe"], timeout=60)
        time.sleep(15)
    import MetaTrader5 as mt5
    if not mt5.initialize():
        print(f"MT5初始化失败({mt5.last_error()}), 跳过本轮"); sys.exit(1)
    t = mt5.symbol_info_tick("SOLUSD")
    if not t or t.ask <= 0:
        print("SOLUSD无行情, 跳过本轮"); mt5.shutdown(); sys.exit(0)
    now = datetime.datetime.now()
    fresh = (datetime.datetime.now() - datetime.datetime.fromtimestamp(t.time)).total_seconds() < 60
    if not fresh:
        print("tick不新鲜, 本轮跳过"); mt5.shutdown(); sys.exit(0)
    for p in mt5.positions_total():
        if p.magic == MAGIC and p.symbol == "SOLUSD":
            print("SOLUSD已有本magic仓, 去重跳过"); mt5.shutdown(); sys.exit(0)
    for o in mt5.orders_total():
        if o.magic == MAGIC and o.symbol == "SOLUSD" and o.type_filling is not None:
            print(f"SOLUSD已有挂单{o.ticket}, 去重跳过"); mt5.shutdown(); sys.exit(0)
    ftype = [i for i in mt5.symbol_info("SOLUSD").filling_mode_all if i in (0, 1, 2)][0]
    px = round(t.ask, 2)
    sl = round(px + R_DIST, 2)
    tp = round(px - TP_MULT * R_DIST, 2)
    r = mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "symbol": "SOLUSD", "volume": 0.01,
        "type": mt5.ORDER_TYPE_SELL, "magic": MAGIC, "comment": WAVE, "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": ftype, "deviation": 20, "position": 0, "sl": sl, "tp": tp})
    ok = r.retcode == 10009
    redline = (now + datetime.timedelta(hours=12)).strftime("%m-%d %H:%M")
    log_ledger({"ev": "place" if ok else "place_fail", "ts": ts, "sym": "SOLUSD", "side": "sell", "vol": 0.01,
        "price": px, "sl": sl, "tp": tp, "magic": MAGIC, "wave": WAVE, "params_ver": "deep_opt_20261117(SL0.8ATR30+TP3R赚钱格)",
        "ticket": (r.order if ok else None), "rc": r.retcode, "mode": "market_in", "actor": "slv2-sol-sentinel(李令'全部按赚钱参数执行')",
        "note": "全品种深优SOL最优格SL0.8/TP3R +84.2净R 4/6 OOS双正, 币go窗开市市价进",
        "redline_12h": redline, "live": True})
    print(f"SOL空腿: rc={r.retcode} ticket={getattr(r,'order',None)} @{px} SL{sl} TP{tp} {'OK' if ok else r.comment}")
    mt5.shutdown()
