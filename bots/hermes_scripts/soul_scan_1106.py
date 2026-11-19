# 灵魂全品种扫描: 核心52品种 x H1/M15 量能+流动性池+密集区+扫损形态 -> 赚钱点位候选
import MetaTrader5 as mt5, time, json
import numpy as np
assert mt5.initialize(), mt5.last_error()
CORE = ["XAUUSD","XAGUSD","EURUSD","USDJPY","GBPUSD","GBPJPY","AUDUSD","NZDUSD","USDCAD","CHFJPY","EURGBP",
        "BTCUSD","ETHUSD","BCHUSD","XRPUSD","LTCUSD","SOLUSD","XLMUSD","DOTUSD","UNIUSD","XBRUSD","XPTUSD",
        "JPN225","GER40","US30","NAS100","AVGO.NAS","INTC.NAS","AMD.NAS","NFLX.NAS","META.NAS","COIN.NAS","JD.NAS","US500"]
out = []
for sym in CORE:
    si = mt5.symbol_info(sym)
    if si is None: continue
    m15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 96)
    h1  = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 48)
    t = mt5.symbol_info_tick(sym)
    if m15 is None or h1 is None or t is None or len(m15) < 96: continue
    bid, o15, c15, h15, l15, v15 = t.bid, m15["open"], m15["close"], m15["high"], m15["low"], m15["tick_volume"]
    h48, l48, v48 = h1["high"], h1["low"], h1["tick_volume"]
    # 流动性池: 等低(48H内>=3次触及) / 等高
    lows_u = np.unique(np.round(l48, 4))
    pool_low = [float(x) for x in lows_u if (np.round(l48,4) == np.round(x,4)).sum() >= 3 and x < bid]
    highs_u = np.unique(np.round(h48, 4))
    pool_high = [float(x) for x in highs_u if (np.round(h48,4)==np.round(x,4)).sum() >= 3 and x > bid]
    # 密集区: M15量分位 top 区域的价区间中值
    q90 = float(np.percentile(v15, 90))
    dense_zone = None
    if q90 > 0:
        idx = np.argsort(v15)[-max(1,int(0.1*len(v15))):]
        dense_zone = float(np.median(np.concatenate([o15[idx], c15[idx]])))
    # 扫损: 近12根H1 下影线穿 48H 低后收回(多头扫损=买) / 上影线穿高后收回(空头扫损=卖)
    sweep_bull = bool(l48[-1] < np.min(l48[-13:-1]) and c15[-1] > np.min(l48[-13:-1]))
    sweep_bear = bool(h48[-1] > np.max(h48[-13:-1]) and c15[-1] < np.max(h48[-13:-1]))
    ema50_15 = float(np.mean(c15[-50:]))
    rec = dict(sym=sym, bid=round(bid,4),
        buy_zones=sorted(pool_high, reverse=True)[:2],   # 上方量密集=回调进多参考(密集区上方)
        sell_zones=sorted(pool_low, reverse=True)[:2],
        dense_zone=round(dense_zone,4) if dense_zone else None,
        ema50_m15=round(ema50_15,4), sweep_bull=bool(sweep_bull), sweep_bear=bool(sweep_bear),
        vol_p90=float(q90), trade_mode=si.trade_mode)
    out.append(rec)
mt5.shutdown()
# 输出: 有信号(扫损/池/密集区)的 top 品种
scored = []
for r in out:
    s = 0
    if r["sweep_bull"]: s += 3   # 扫损多头=机构扫流动性后反向
    if r["sweep_bear"]: s += 3
    if r["dense_zone"]: s += 1
    if r["buy_zones"]: s += 1
    if r["sell_zones"]: s += 1
    scored.append((s, r))
scored.sort(key=lambda x: -x[0])
print("=== 灵魂扫描: 信号强度 top (核心 %d 品种) ===" % len(CORE))
for s, r in scored[:12]:
    if s == 0: continue
    print("%-9s 强度%d | 现=%.4g 扫多=%s 扫空=%s 密集区=%s 买参考(上方池)=%s 卖参考(下方池)=%s" % (
        r["sym"], s, r["bid"], r["sweep_bull"], r["sweep_bear"], r["dense_zone"], r["buy_zones"], r["sell_zones"]))
json.dump(out, open(r"E:/GoldstrategyEngine/data/orderflow_soul_scan_1107.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("全量落盘: E:/GoldstrategyEngine/data/orderflow_soul_scan_1107.json (%d 品种)" % len(out))
