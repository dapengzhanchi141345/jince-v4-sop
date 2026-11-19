# 机构订单流补判: BTC/ETH M15 扫掠三条件+吸收 (0.01观察腿交叉验证)
import MetaTrader5 as mt5
import numpy as np
if not mt5.initialize():
    print("INIT_FAIL:", mt5.last_error()); raise SystemExit
for sym in ["BTCUSD", "ETHUSD"]:
    b = mt5.copy_rates_from_pos(sym, 15, 0, 120)  # 48=PERIOD_M15 (本 build 无该常量)
    if b is None or len(b) < 30:
        print(sym, "M15不足"); continue
    lows = b["low"].astype(float); highs = b["high"].astype(float)
    closes = b["close"].astype(float); opens = b["open"].astype(float)
    vol = b["tick_volume"].astype(float)
    avg100 = vol[-min(100, len(vol)):].mean()
    now_px = mt5.symbol_info(sym).bid
    print("== %s M15 补判 (现=%.2f, 100根均量=%.0f, 共%d根) ==" % (sym, now_px, avg100, len(b)))
    for i in range(max(4, len(b) - 30), len(b) - 1):
        lo = min(lows[i - 3:i]); hi = max(highs[i - 3:i])
        if lows[i] < lo:
            broke_low, swing_pt = True, lo
        elif highs[i] > hi:
            broke_low, swing_pt = False, hi
        else:
            continue
        closed_back = closes[i] > swing_pt if broke_low else closes[i] < swing_pt
        vol_conf = vol[i] >= 1.2 * avg100
        if broke_low and closed_back and vol_conf:
            print("  [扫掠确认·底] bar#%d: 影线刺穿前低%.2f→收回%.2f, 量%.0f>=1.2x均量 -> 反转多信号(与我方空腿矛盾=空腿记中性样本)" % (i, swing_pt, closes[i], vol[i]))
        elif not broke_low and not closed_back and vol_conf:
            print("  [扫掠破位·顶] bar#%d: 影线刺穿前高%.2f未收回, 量确认 -> 顺势空(佐证我方空腿)" % (i, swing_pt))
        elif broke_low and not closed_back and vol_conf:
            print("  [扫掠破位·底] bar#%d: 刺穿前低%.2f未收回, 量确认 -> 顺势空(佐证我方空腿)" % (i, swing_pt))
    adv = (closes[-1] - opens[-5]) / max(opens[-5], 1e-9)
    if vol[-1] > 1.5 * avg100 and abs(adv) < 0.002:
        print("  [吸收信号] 末根放量但5根推进<0.2% -> 机构防守现位(方向不明=观察)")
    print("  近5根推进=%.3f%% 末根量/均量=%.2f" % (adv * 100, vol[-1] / avg100))
mt5.shutdown()
