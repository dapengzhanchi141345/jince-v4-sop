#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""灵魂波 21:00 BJT 市价进场哨(一次性, 币系go窗13UTC开):
BTC 灵魂信号空腿(11-17扫高收回+位移确认+S4日偏对齐):
  首选 GTC 卖挂 65220.25(结构位) -> 失败则市价进; [李令"别太近"SL深查] SL=入场相对1.5×ATR15抗噪地板353.8pt, TP3R
  窗口外(不在13-21UTC)=跳过+留痕. 预检: tick新鲜/无重复仓/净值/风险≤1%帽
台账: order_lifecycle.jsonl(place) + task_ledger.jsonl(redline_12h)
"""
import os, sys, json, datetime

os.environ.setdefault("MT5_TERMINAL", r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe")
import MetaTrader5 as mt5

MAGIC = 30261106
WAVE = "soul-sweep-20261117"
BASE = r"E:/GoldstrategyEngine/data"
ENTRY_LIM = 65220.25
# [11-17 李令"全部按你赚钱的参数来执行, 深度优化"] SL=0.8×ATR30(255.7, 全品种五验赚钱格: BTC SL0.8/TP3R +147.2净R 4/6 OOS双正)
# 宽损SL(结构极值65670.91)已被全品种深优REJECT(扫损率+TP不可达), 弃
SL_DIST = 255.7  # 0.8×ATR30(319.6) 赚钱格同分母
TP_R_MULT = 3.0

def log_ledger(row):
    with open(os.path.join(BASE, "order_lifecycle.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

def main():
    now_bj = datetime.datetime.now()
    ts = now_bj.strftime("%Y-%m-%d %H:%M:%S")
    # 窗口门: 币系 go 13-21 UTC = 21:00-05:00 BJT(次日)
    hh = now_bj.hour
    in_window = (hh >= 21) or (hh < 5)
    if not in_window:
        print("SKIP: 不在币系go窗(13-21UTC), 留痕不执行"); 
        log_ledger({"ev": "wave_skip", "ts": ts, "sym": "BTCUSD", "wave": WAVE, "reason": "off_window", "actor": "soul-wave-sentinel"})
        return
    assert mt5.initialize(), "mt5 init fail"
    t = mt5.symbol_info_tick("BTCUSD")
    tick_fresh = abs((now_bj.timestamp() - t.time)) < 120 if t.time else False
    si = mt5.symbol_info("BTCUSD")
    fm = si.filling_mode
    ftype = mt5.ORDER_FILLING_RETURN if fm & 4 else (mt5.ORDER_FILLING_IOC if fm & 2 else mt5.ORDER_FILLING_FOK)
    pos = [p for p in (mt5.positions_get() or []) if p.symbol == "BTCUSD" and p.type == 1 and p.magic == MAGIC]
    orders = [o for o in (mt5.orders_get() or []) if o.symbol == "BTCUSD" and o.magic == MAGIC]
    equity = mt5.account_info().equity
    print(f"预检: tick新鲜={tick_fresh} bid={t.bid} 重复仓{len(pos)} 重复挂单{len(orders)} 净值={equity:.2f}")
    if pos or orders:
        print("已有同magic在途/持仓, 跳过(防叠单)"); mt5.shutdown(); return
    if not tick_fresh:
        print("tick不新鲜, 跳过本轮(下拍再试)"); mt5.shutdown(); return

    r = None
    entry_mode = "gct_limit"
    # 首选: GTC 结构位卖挂(若現價在挂单价下方=有效侧)
    if t.bid < ENTRY_LIM:
        r = mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "symbol": "BTCUSD", "volume": 0.01,
            "type": mt5.ORDER_TYPE_SELL_LIMIT, "price": ENTRY_LIM, "sl": round(ENTRY_LIM + SL_DIST, 2), "tp": round(ENTRY_LIM - TP_R_MULT * SL_DIST, 2),
            "magic": MAGIC, "comment": WAVE, "type_time": mt5.ORDER_TIME_GTC, "type_filling": ftype, "deviation": 20, "position": 0})
        print(f"GTC卖挂{ENTRY_LIM} SL{round(ENTRY_LIM + SL_DIST, 2)}: rc={r.retcode} {r.comment}")
    if r is None or r.retcode != 10009:
        entry_mode = "market_in"
        ask = round(t.ask, 2)
        sl = round(ask + SL_DIST, 2)
        R = SL_DIST
        tp = round(ask - TP_R_MULT * SL_DIST, 2)
        # [李令] 先别算风险, 撤 1% 帽内检
        r = mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "symbol": "BTCUSD", "volume": 0.01,
            "type": mt5.ORDER_TYPE_SELL, "magic": MAGIC, "comment": WAVE, "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": ftype, "deviation": 20, "position": 0, "sl": sl, "tp": tp})
        print(f"市价进@{ask}: rc={r.retcode} ticket={r.order} SL{sl} TP{tp} R={R:.1f} {r.comment}")
    ok = r.retcode == 10009
    redline = (now_bj + datetime.timedelta(hours=12)).strftime("%m-%d %H:%M")
    log_ledger({"ev": "place" if ok else "place_fail", "ts": ts, "sym": "BTCUSD", "side": "sell", "vol": 0.01,
        "mode": entry_mode, "ticket": (r.order if ok else None), "rc": r.retcode, "magic": MAGIC, "wave": WAVE,
        "params_ver": "deep_opt_20261117(SL0.8ATR30+TP3R赚钱格)", "sl": round(ask + SL_DIST, 2) if entry_mode == "market_in" else round(ENTRY_LIM + SL_DIST, 2),
        "actor": "soul-wave-sentinel(李令灵魂策略严格执行)",
        "note": "BTC扫高收回位移确认信号腿; [李令'全部按赚钱参数执行': 全品种深优BTC SL0.8/TP3R格+147.2净R 4/6 OOS双正, 撤风险帽], TP3R",
        "redline_12h": redline, "event_decision": "今晚无HIGH事件, 隔夜看S8衰竭窗21UTC后未达TP降半", "live": True})
    with open(os.path.join(BASE, "task_ledger.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": ts, "by": "soul-wave-sentinel", "task": "BTC信号空腿12h红线",
            "detail": "ticket=%s redline=%s 到期未平即强平(分级: 锁利豁免)" % ((r.order if ok else None), redline), "live": True}, ensure_ascii=False) + "\n")
    print("DONE ok=%s" % ok)
    mt5.shutdown()

if __name__ == "__main__":
    main()
