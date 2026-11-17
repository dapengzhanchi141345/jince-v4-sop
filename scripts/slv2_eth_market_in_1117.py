#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""slv2 ETH 新止损策略 21:00 BJT 市价进场哨(一次性, 币系go窗13UTC):
ETH 空腿(李令11-17'立即执行新止损策略, 别的不动'):
  市价进 @go窗开, SL=entry+0.8×ATR30(7.8, v3网格base列), TP=entry-3R(sl_spec_v2: TP3R)
  离场层=GB1.5(WATCH, 引擎棘轮接线=rd工单sl_spec_v2_exit_layer_20261117, 本哨只管进场层)
  窗口外(非21:00-05:00 BJT)=跳过留痕; 预检: tick新鲜/无同magic重复/净值
台账: order_lifecycle.jsonl(place) + task_ledger.jsonl(redline_12h)
"""
import os, json, datetime

os.environ.setdefault("MT5_TERMINAL", r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe")
import MetaTrader5 as mt5

MAGIC = 20261104
WAVE = "v3fwd-slv2-20261117"
BASE = r"E:/GoldstrategyEngine/data"
# [11-17 李令"全部按你赚钱的参数来执行, 深度优化"] 全品种深优赚钱格: ETH SL0.8×ATR30/TP3R (+122.9净R 4/6 OOS双正)
# 宽损SL(2日高极值锚1865.1)已被全品种深优REJECT, 弃
R_DIST = 7.8  # 0.8×ATR30(9.73) 赚钱格同分母
TP_MULT = 3.0


def log_ledger(row):
    with open(os.path.join(BASE, "order_lifecycle.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    now = datetime.datetime.now()
    ts = now.strftime("%Y-%m-%d %H:%M:%S")
    hh = now.hour
    if not (hh >= 21 or hh < 5):
        print("SKIP: 不在币系go窗(13-21UTC), 留痕不执行")
        log_ledger({"ev": "wave_skip", "ts": ts, "sym": "ETHUSD", "wave": WAVE, "reason": "off_window", "actor": "slv2-eth-sentinel"})
        return
    assert mt5.initialize(), "mt5 init fail"
    t = mt5.symbol_info_tick("ETHUSD")
    fresh = bool(t.time) and abs(now.timestamp() - t.time) < 120
    si = mt5.symbol_info("ETHUSD")
    fm = si.filling_mode
    ftype = mt5.ORDER_FILLING_RETURN if fm & 4 else (mt5.ORDER_FILLING_IOC if fm & 2 else mt5.ORDER_FILLING_FOK)
    pos = [p for p in (mt5.positions_get() or []) if p.symbol == "ETHUSD" and p.type == 1 and p.magic == MAGIC and WAVE in str(getattr(p, "comment", ""))]
    orders = [o for o in (mt5.orders_get() or []) if o.symbol == "ETHUSD" and o.magic == MAGIC and WAVE in str(getattr(o, "comment", ""))]
    eq = mt5.account_info().equity
    print(f"预检: tick新鲜={fresh} ask={t.ask} 重复仓{len(pos)} 重复挂单{len(orders)} 净值={eq:.2f}")
    if pos or orders:
        print("已有同magic同波在途/持仓, 跳过(防叠单)"); mt5.shutdown(); return
    if not fresh:
        print("tick不新鲜, 本轮跳过"); mt5.shutdown(); return
    px = round(t.ask, 1)
    sl = round(px + R_DIST, 1)
    R = R_DIST
    tp = round(px - TP_MULT * R, 1)
    # [李令] 先别算风险, 不被风险束缚(撤风险帽)
    r = mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "symbol": "ETHUSD", "volume": 0.01,
        "type": mt5.ORDER_TYPE_SELL, "magic": MAGIC, "comment": WAVE, "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": ftype, "deviation": 20, "position": 0, "sl": sl, "tp": tp})
    ok = r.retcode == 10009
    redline = (now + datetime.timedelta(hours=12)).strftime("%m-%d %H:%M")
    log_ledger({"ev": "place" if ok else "place_fail", "ts": ts, "sym": "ETHUSD", "side": "sell", "vol": 0.01,
        "price": px, "sl": sl, "tp": tp, "magic": MAGIC, "wave": WAVE, "params_ver": "sl_spec_v2(TP3R+SL宽结构极值+GB1.5离场层)",
        "ticket": (r.order if ok else None), "rc": r.retcode, "mode": "market_in", "actor": "slv2-eth-sentinel(李令11-17立即执行新止损策略)",
        "note": "go窗开市价进; [李令'全部按赚钱参数执行': 全品种深优ETH SL0.8ATR30/TP3R格+122.9净R 4/6 OOS双正, 撤风险帽], GB1.5离场=引擎棘轮接线rd工单在案",
        "redline_12h": redline, "live": True})
    with open(os.path.join(BASE, "task_ledger.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": ts, "by": "slv2-eth-sentinel", "task": "ETH新策略空腿12h红线",
            "detail": "ticket=%s redline=%s 到期未平即强平" % ((r.order if ok else None), redline), "live": True}, ensure_ascii=False) + "\n")
    print("DONE ok=%s (市价进@%s SL%s TP%s)" % (ok, px, sl, tp))
    mt5.shutdown()


if __name__ == "__main__":
    main()
