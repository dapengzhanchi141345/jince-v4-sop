# -*- coding: utf-8 -*-
r"""币系茶歇峰触发探针 (确定性 0LLM, 00:30 BJT 哨用): BTC/ETH/SOL/XRP 24h 扫空位预计算。
规则(S4日偏空=只扫高空 + E1防追 + 3x点差地板 + RR>=2): 输出每品种 eligible 与挂单参数。
eligible=True 的才允许下 0.01 样本腿; 全 False = 今晚无单, 静默。
"""
import json
import time

import MetaTrader5 as mt5

WATCH = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"]
OUT = r"E:\GoldstrategyEngine\data\tea_time_probe.json"


def h1_atr(m15, n=14):
    trs = []
    for i in range(1, len(m15)):
        h, l, pc = m15[i]["high"], m15[i]["low"], m15[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    m15a = sum(trs[-n:]) / n
    return m15a * 2.4  # M15->H1 近似


def adx(m15):
    c, h, l = [r["close"] for r in m15], [r["high"] for r in m15], [r["low"] for r in m15]
    trs = [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(m15))]
    atr = sum(trs[-14:]) / 14
    if atr == 0:
        return 0.0
    plus_d, minus_d = [], []
    for i in range(1, len(m15)):
        plus_d.append(max(h[i] - h[i - 1], 0) if (h[i] - h[i - 1]) > (l[i - 1] - l[i]) else 0)
        minus_d.append((l[i - 1] - l[i]) if (l[i - 1] - l[i]) > (h[i] - h[i - 1]) else 0)
    sp = sum(plus_d[-14:]) / 14 / atr * 100
    sm = sum(minus_d[-14:]) / 14 / atr * 100
    return abs(sp - sm) / (sp + sm) * 100 if (sp + sm) else 0.0


def main():
    assert mt5.initialize(), "ATE init 失败"
    time.sleep(2)
    res = {"ts": time.strftime("%F %T"), "utc_h": round(time.gmtime().tm_hour + time.gmtime().tm_min / 60, 2), "symbols": {}}
    for s in WATCH:
        b = mt5.copy_rates_from_pos(s, mt5.TIMEFRAME_M15, 0, 400)
        if b is None or len(b) < 200:
            res["symbols"][s] = {"eligible": False, "why": "K线不足"}
            continue
        hi = max(x["high"] for x in b[-96:])
        lo = min(x["low"] for x in b[-96:])
        last = float(b[-1]["close"])
        d1 = mt5.copy_rates_from_pos(s, mt5.TIMEFRAME_D1, 0, 60)
        dc = [x["close"] for x in d1]
        e = sum(dc[:50]) / 50
        for x in dc[49:]:
            e = x * 2 / 51 + e * 49 / 51
        bear = last < e
        adxv = adx(b)
        atr_h = h1_atr(b)
        t = mt5.symbol_info_tick(s)
        spread = t.ask - t.bid
        sell_l = round(hi, 4)
        sl = round(hi + 0.5 * atr_h, 4)
        tp = round((hi + lo) / 2, 4)
        rr = (sell_l - tp) / (sl - sell_l)
        floor = (sl - sell_l) >= 3 * spread
        pos = (last - lo) / (hi - lo) * 100
        eligible = bear and adxv >= 40 and floor and rr >= 2.0 and pos < 70  # 日偏空+趋势+地板+RR+别贴顶(贴顶=已扫=追)
        res["symbols"][s] = {"eligible": int(eligible), "bear_d1": int(bear), "adx15": round(adxv, 1),
                             "hi24": hi, "lo24": lo, "last": last, "pos%": round(pos, 1),
                             "sell_limit": sell_l, "sl": sl, "tp": tp, "rr": round(rr, 2),
                             "spread": spread, "floor_pass": int(floor),
                             "why": "过S4/E1/地板/RR" if eligible else "未过(日偏多/无趋势/地板/RR/贴顶)"}
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    mt5.shutdown()


if __name__ == "__main__":
    main()
