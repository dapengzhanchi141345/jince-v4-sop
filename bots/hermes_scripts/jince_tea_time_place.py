# -*- coding: utf-8 -*-
r"""币系茶歇峰挂单脚本 (ATE 环境跑): 读 tea_time_probe.json, eligible 币按 rr 降序取前2,
挂 SELL_LIMIT 0.01 样本腿(magic 30261106), 挂前逐币复验(现价<24h区间70%位置+日偏空仍成立+E1防追),
每笔成功写 order_lifecycle.jsonl open_pending 行 + 写 12h 哨 registry(tea_tea_1115_orders.json)。
"""
import json, time, datetime
import MetaTrader5 as mt5

PROBE = r"E:\GoldstrategyEngine\data\tea_time_probe.json"
REG = r"E:\GoldstrategyEngine\data\tea_tea_1115_orders.json"
LC = r"E:\GoldstrategyEngine\data\order_lifecycle.jsonl"
MAGIC = 30261106
VOL = 0.01


def now_bjt():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main():
    probe = json.load(open(PROBE, encoding="utf-8"))
    pt = datetime.datetime.strptime(probe["ts"], "%Y-%m-%d %H:%M:%S")
    age_min = (datetime.datetime.now() - pt).total_seconds() / 60
    assert age_min <= 10, f"数据有效性闸FAIL: 探针ts龄{age_min:.1f}min>10min, 禁挂单"
    elig = [(s, v) for s, v in probe["symbols"].items() if v.get("eligible") == 1 and v.get("sell_limit")]
    elig.sort(key=lambda kv: -kv[1]["rr"])
    top2 = elig[:2]  # E3 同族上限2腿
    print(f"探针ts={probe['ts']} 龄{age_min:.1f}min 闸PASS | eligible={len(elig)} 取前2={[s for s, _ in top2]}")

    assert mt5.initialize(), "ATE init 失败(终端不在线)"
    time.sleep(2)
    results = []
    placed_ts = now_bjt()
    close_due = (datetime.datetime.now() + datetime.timedelta(hours=12)).strftime("%Y-%m-%d %H:%M")
    for sym, v in top2:
        sell_l, sl, tp, rr = v["sell_limit"], v["sl"], v["tp"], v["rr"]
        # 挂前复验(实读, 不吃探针旧值): 24h区间位置<70% + 日偏空仍成立 + E1防追(ask未上穿挂点)
        m15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 400)
        hi = max(x["high"] for x in m15[-96:])
        lo = min(x["low"] for x in m15[-96:])
        last = float(m15[-1]["close"])
        d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 60)
        dc = [x["close"] for x in d1]
        e = sum(dc[:50]) / 50
        for x in dc[49:]:
            e = x * 2 / 51 + e * 49 / 51
        bear = last < e
        pos = (last - lo) / (hi - lo) * 100 if hi > lo else 99.0
        tick = mt5.symbol_info_tick(sym)
        ask = tick.ask if tick else 0.0
        skip = None
        if not bear:
            skip = "复验FAIL: 日偏空不再成立(现价已上穿50日EMA族), 跳过该币"
        elif pos >= 70:
            skip = f"复验FAIL: 现价处于24h区间{pos:.1f}%位置>=70%(已上扫, 追高), 跳过该币"
        elif ask >= sell_l:
            skip = f"E1防追: 现价ask {ask:.4f} 已上穿挂点 {sell_l}, 跳过该币"
        si = mt5.symbol_info(sym)
        if si and si.trade_mode != 1:
            skip = f"trade_mode={si.trade_mode}(不可开单), 跳过该币(5min自修复链盯)"
        if skip:
            results.append({"sym": sym, "status": "SKIP", "reason": skip,
                            "fresh_pos%": round(pos, 1), "fresh_bear": int(bear), "last": last})
            print("SKIP " + sym + ": " + skip)
            continue
        step = si.volume_step if si else 0.01
        vol = round(VOL / step) * step if step else VOL
        digits = si.digits if si else 2
        req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": vol,
               "type": mt5.ORDER_TYPE_SELL_LIMIT, "price": round(sell_l, digits),
               "sl": round(sl, digits), "tp": round(tp, digits), "deviation": 20,
               "magic": MAGIC, "comment": "tea_peak_1115",
               "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_FOK}
        r = mt5.order_send(req)
        if r is None or r.retcode not in (10008, 10009):
            r2 = mt5.order_send({**req, "type_filling": mt5.ORDER_FILLING_IOC})
            if r2 is not None:
                r = r2
        ok = r is not None and r.retcode in (10008, 10009)
        row = {"ts": now_bjt(), "op": "open_pending", "symbol": sym, "magic": MAGIC,
               "side": "SELL_LIMIT", "vol": vol, "order_px": round(sell_l, digits),
               "sl": round(sl, digits), "tp": round(tp, digits), "rr": rr,
               "retcode": r.retcode if r else None,
               "status": "pending" if ok else "REJECTED"}
        if ok:
            row["ticket"] = r.order
            row["close_due"] = close_due
            row["reason"] = ("币系茶歇峰(16-17UTC)24h扫空位: S4日偏空+E1防追+3x点差地板+RR>=2, "
                              "按RR降序取前2(E3同族币系上限2腿, 0.01样本腿), 12h红线close_obs哨未成交即撤")
            results.append({"sym": sym, "status": "PLACED", "ticket": r.order,
                            "retcode": r.retcode, "order_px": round(sell_l, digits),
                            "sl": round(sl, digits), "tp": round(tp, digits), "rr": rr,
                            "vol": vol, "magic": MAGIC, "placed_ts": placed_ts,
                            "close_due": close_due, "fresh_pos%": round(pos, 1),
                            "fresh_bear": int(bear)})
            print("PLACED " + sym + " SELL_LIMIT " + str(vol) + " @ " + str(round(sell_l, digits)) +
                  " SL " + str(round(sl, digits)) + " TP " + str(round(tp, digits)) +
                  f" RR {rr} ticket={r.order} 12h红线={close_due}")
        else:
            row["reason"] = f"挂单被拒 rc={r.retcode if r else None} {r.comment if r else 'init失败'}, 交1108自修复链5min哨重试"
            results.append({"sym": sym, "status": "REJECTED", "retcode": r.retcode if r else None,
                            "comment": r.comment if r else None,
                            "order_px": round(sell_l, digits), "sl": round(sl, digits),
                            "tp": round(tp, digits), "rr": rr})
            print("REJECTED " + sym + " rc=" + str(r.retcode if r else None) + " " + (r.comment if r else ""))
        with open(LC, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        time.sleep(2)
    reg = [x for x in results if x["status"] == "PLACED"]
    json.dump({"ts": placed_ts, "close_due": close_due,
               "orders": [{k: x.get(k) for k in ("sym", "ticket", "order_px", "sl", "tp", "magic", "rr")} for x in reg]},
              open(REG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"results": results, "registry": REG, "close_due": close_due}, ensure_ascii=False, indent=1))
    mt5.shutdown()


if __name__ == "__main__":
    main()
