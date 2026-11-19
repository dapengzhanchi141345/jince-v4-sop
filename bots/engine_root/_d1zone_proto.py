"""D1-zone + H4 入场 原型验证 (裸K供需波段 v2)"""
import MetaTrader5 as mt5
import numpy as np, time
from collections import Counter
import swing_engine as se
from swing_engine import Zone, scan_zones, build_df, simulate

def run(sym, cost_r=0.03):
    h4 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, 3000)
    d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 900)
    o4 = h4['open'].astype(float); h4a = h4['high'].astype(float); l4 = h4['low'].astype(float)
    c4 = h4['close'].astype(float); t4 = h4['time']
    od = d1['open'].astype(float); hd = d1['high'].astype(float); ld = d1['low'].astype(float)
    cd = d1['close'].astype(float); td = d1['time']
    df = build_df(o4, h4a, l4, c4, t4, d1c=cd, d1t=td)
    a4 = df['a']
    # D1 ATR
    ad = se.atr(hd, ld, cd)
    # D1 zone 检测 (质量高: 需要真实 displacement)
    zc_d1 = dict(pivot_k=3, cons_min=2, cons_max=8, disp_atr=1.5, zone_max_atr=3.0, zone_tail_bars=2)
    z_d1 = scan_zones(od, hd, ld, cd, ad, zc_d1)
    # 映射 D1 zone → H4 bar 坐标
    mapped = []
    for z in z_d1:
        # born: D1 bar open 时间在 H4 序列中对应的 index
        born_h4 = int(np.searchsorted(t4, td[z.born], side='right') - 1)
        if born_h4 < 0 or born_h4 >= len(t4):
            continue
        mapped.append(Zone(z.top, z.bottom, z.ztype, born_h4, born_h4, z.disp_range))
    # 用宽松 risk cap 的 trade cfg (D1 zone 深, SL 远)
    tc = dict(se.TRADE_DEFAULT, tp_r=1.5, buf_atr=0.5, trail_start=1.6, trail_atr=1.5,
              zone_max_age=2000, zone_max_touch=2, risk_cap_atr=6.0)
    tr, st = simulate(df, mapped, tc, cost_r=cost_r, equity=10000)
    return tr, st, len(mapped)

# 对 mapped zones 需要重新计时 (Age cap 2000 H4 ≈ 83天, D1 zone 应更长寿)

if __name__ == '__main__':
    mt5.initialize()
    for sym in ['XAUUSD', 'USDJPY', 'GBPUSD', 'EURUSD', 'AUDCHF']:
        t0 = time.time()
        tr, st, nz = run(sym)
        el = time.time() - t0
        tag = 'OK ' if st.get('avg_r', -9) > 0 else 'BAD'
        print(f'{tag}{sym}: zones(D1)={nz} n={st["n"]} avgR={st.get("avg_r",0):+.2f} PF={st.get("pf",0):.2f} WR={st.get("win_rate",0)*100:.0f}% DD={st.get("max_dd",0)*100:.0f}% ({el:.0f}s)')
        if tr:
            print('     出场:', Counter(x.reason for x in tr), '方向:', Counter(x.dir for x in tr))
    mt5.shutdown()
