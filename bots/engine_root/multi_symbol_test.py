"""
多品种回测 — XAUUSD + 虚拟货币 + 货币对
下载数据 → 跑回测 → 对比报告
"""
import sys, os, json, warnings, time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
warnings.filterwarnings('ignore')

import MetaTrader5 as mt5
if not mt5.initialize():
    mt5.shutdown()
    mt5.initialize()
mt5.login(60043976, password="", server="TradeMaxGlobal-Demo")

BASE = r"E:\GoldstrategyEngine"
DATA_DIR = os.path.join(BASE, "data")
os.makedirs(DATA_DIR, exist_ok=True)
sys.path.insert(0, BASE)

# ═══ 品种列表 ═══
SYMBOLS = {
    "XAUUSD": {
        "type":"metal",     "name":"黄金",    "session":(15,24),
        "adx_min":22, "sl_mult":1.5, "rr_mult":2.5,
        "lots":0.10, "max_daily":6, "cool_5l":True,
        # 黄金特点: 高波动, 大ATR, 趋势持续性强
        "regime_adjust": {"ranging": {"sl_factor":0.8, "rr_factor":1.8}, "strong_trend":{"sl_factor":2.0, "rr_factor":3.0}}
    },
    "BTCUSD": {
        "type":"crypto",    "name":"比特币",  "session":(0,23),
        "adx_min":16, "sl_mult":1.2, "rr_mult":2.0,
        "lots":0.01, "max_daily":8, "cool_5l":False,
        # 比特币特点: 24小时交易, 高趋势性, 滑点大
        "regime_adjust": {"ranging": {"sl_factor":0.7, "rr_factor":1.5}, "strong_trend":{"sl_factor":1.5, "rr_factor":2.5}}
    },
    "ETHUSD": {
        "type":"crypto",    "name":"以太坊",  "session":(0,23),
        "adx_min":18, "sl_mult":1.3, "rr_mult":2.0,
        "lots":0.05, "max_daily":8, "cool_5l":False,
        # 以太坊: 类似BTC但流动性差一些
        "regime_adjust": {"ranging": {"sl_factor":0.75, "rr_factor":1.6}, "strong_trend":{"sl_factor":1.6, "rr_factor":2.6}}
    },
    "EURUSD": {
        "type":"forex",     "name":"欧元",    "session":(0,23),
        "adx_min":12, "sl_mult":0.8, "rr_mult":2.0,
        "lots":1.0, "max_daily":10, "cool_5l":False,
        # 外汇: 低波动, 高流动性, 趋势弱但持续
        "regime_adjust": {"ranging": {"sl_factor":0.5, "rr_factor":1.5}, "strong_trend":{"sl_factor":1.2, "rr_factor":2.5}}
    },
    "GBPUSD": {
        "type":"forex",     "name":"英镑",    "session":(0,23),
        "adx_min":12, "sl_mult":0.8, "rr_mult":2.0,
        "lots":1.0, "max_daily":10, "cool_5l":False,
        "regime_adjust": {"ranging": {"sl_factor":0.5, "rr_factor":1.5}, "strong_trend":{"sl_factor":1.2, "rr_factor":2.5}}
    },
    "USDJPY": {
        "type":"forex",     "name":"美元/日元","session":(0,23),
        "adx_min":12, "sl_mult":0.5, "rr_mult":2.0,
        "lots":1.0, "max_daily":10, "cool_5l":False,
        "regime_adjust": {"ranging": {"sl_factor":0.4, "rr_factor":1.5}, "strong_trend":{"sl_factor":1.0, "rr_factor":2.5}}
    },
    "GBPJPY": {
        "type":"cross",     "name":"英镑/日元","session":(0,23),
        "adx_min":16, "sl_mult":1.0, "rr_mult":2.2,
        "lots":0.5, "max_daily":6, "cool_5l":False,
        # 交叉盘: 比主流外汇波动大, 趋势性好
        "regime_adjust": {"ranging": {"sl_factor":0.6, "rr_factor":1.8}, "strong_trend":{"sl_factor":1.4, "rr_factor":2.8}}
    },
}

# ═══ 指标 ═══
def ema(v, p):
    r = np.full(len(v), np.nan); r[p-1] = np.mean(v[:p])
    a=2/(p+1)
    for i in range(p, len(v)): r[i]=v[i]*a+r[i-1]*(1-a)
    return r

def atr(h, l, p=14):
    tr = np.maximum(h[1:]-l[1:], np.maximum(abs(h[1:]-np.roll(h,1)[1:]), abs(l[1:]-np.roll(l,1)[1:])))
    r = np.full(len(h), np.nan); r[p]=np.mean(tr[:p])
    a=1/p
    for i in range(p+1, len(h)): r[i]=tr[i-1]*a+r[i-1]*(1-a)
    return pd.Series(r).ffill().fillna(np.mean(tr[:p])).values

def adx(h, l, c, p=14):
    if len(c) < p*2: return np.zeros(len(c))
    tr = np.maximum(h[1:]-l[1:], np.maximum(abs(h[1:]-c[:-1]), abs(l[1:]-c[:-1])))
    u=h[1:]-h[:-1]; d=l[:-1]-l[1:]
    pdi = 100*pd.Series(np.where((u>d)&(u>0),u,0)).ewm(span=p).mean()/(pd.Series(tr).ewm(span=p).mean()+1e-10)
    mdi = 100*pd.Series(np.where((d>u)&(d>0),d,0)).ewm(span=p).mean()/(pd.Series(tr).ewm(span=p).mean()+1e-10)
    dx = 100*np.abs(pdi-mdi)/(pdi+mdi+1e-10)
    result = pd.Series(dx).ewm(span=p).mean().values
    return np.concatenate([np.zeros(len(c)-len(result)), result])

def find_swing(h, l, lb=3):
    swh, swl = [], []
    for i in range(lb, len(h)-lb):
        if h[i] == max(h[i-lb:i+lb+1]): swh.append((i, h[i]))
        if l[i] == min(l[i-lb:i+lb+1]): swl.append((i, l[i]))
    return swh, swl

def find_zones(h4_df):
    h = h4_df['high'].values; l = h4_df['low'].values; c = h4_df['close'].values
    zones = []
    swh, swl = find_swing(h, l, 3)
    for idx, low_val in swl:
        if idx < 2 or idx > len(c)-3: continue
        left_high = max(h[max(0,idx-10):idx+1]); down = left_high - low_val
        if down <= 0: continue
        for j in range(idx+1, min(idx+8, len(c))):
            if c[j] > low_val + down*0.2:
                bh = max(h[idx:j+1]); bl = min(l[idx:j+1]); ret = (bh-bl)/max(down,1)
                if 0.15 <= ret <= 0.95:
                    zones.append({'type':'D','top':bh,'bottom':max(bl,low_val-(bh-bl)*0.1),'strength':min(5.0,ret*5+0.5)})
                break
    for idx, high_val in swh:
        if idx < 2 or idx > len(c)-3: continue
        left_low = min(l[max(0,idx-10):idx+1]); up = high_val - left_low
        if up <= 0: continue
        for j in range(idx+1, min(idx+8, len(c))):
            if c[j] < high_val - up*0.2:
                bh = max(h[idx:j+1]); bl = min(l[idx:j+1]); ret = (bh-bl)/max(up,1)
                if 0.15 <= ret <= 0.95:
                    zones.append({'type':'S','top':min(bh,high_val+(bh-bl)*0.1),'bottom':bl,'strength':min(5.0,ret*5+0.5)})
                break
    merged = []
    for z in zones:
        dup = any(m['type']==z['type'] and abs(m['top']-z['top'])/max(m['top'],1)<0.01 and abs(m['bottom']-z['bottom'])/max(m['bottom'],1)<0.01 for m in merged)
        if not dup: merged.append(z)
    return {'demand':[z for z in merged if z['type']=='D'],'supply':[z for z in merged if z['type']=='S']}

# ═══ 数据下载 ═══
def download_data(sym):
    for tf, tf_name, tf_mt5 in [("H1","H1",16385), ("H4","H4",16388), ("D1","D1",16408)]:
        f = os.path.join(DATA_DIR, f"{sym}_{tf_name}.csv")
        if os.path.exists(f): continue
        rates = mt5.copy_rates_range(sym, tf_mt5, int(datetime(2025,7,1).timestamp()), int(datetime(2026,7,1).timestamp()))
        if rates is not None and len(rates) > 0:
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            df.to_csv(f, index=False)
            print(f"  {sym} {tf_name}: {len(df)} bars")

# ═══ 回测 (每个品种用独立参数) ═══
def run_backtest(sym, cfg):
    h1 = pd.read_csv(os.path.join(DATA_DIR, f"{sym}_H1.csv"), parse_dates=['time'])
    h4 = pd.read_csv(os.path.join(DATA_DIR, f"{sym}_H4.csv"), parse_dates=['time'])
    d1 = pd.read_csv(os.path.join(DATA_DIR, f"{sym}_D1.csv"), parse_dates=['time'])
    
    hc = h1['close'].values; hh = h1['high'].values; hl = h1['low'].values
    ht = h1['time'].values; vols = h1['tick_volume'].values if 'tick_volume' in h1.columns else None
    
    adx_v = adx(hh, hl, hc); atr_v = atr(hh, hl)
    e14 = ema(hc, 14); e28 = ema(hc, 28)
    h4c = h4['close'].values; h4adx = adx(h4['high'].values, h4['low'].values, h4c)
    dc = d1['close'].values; de9 = ema(dc, 9); de21 = ema(dc, 21)
    
    # H4 ATR
    h4_tr = np.maximum(h4['high'].values[1:]-h4['low'].values[1:], 
                       np.maximum(abs(h4['high'].values[1:]-h4c[:-1]), abs(h4['low'].values[1:]-h4c[:-1])))
    h4a = np.full(len(h4c), np.nan); h4a[14] = np.mean(h4_tr[:14])
    for i in range(15, len(h4c)): h4a[i] = h4_tr[i-1]/14 + h4a[i-1]*13/14
    h4a = pd.Series(h4a).ffill().fillna(np.mean(h4_tr[:14])).values
    
    trades = []; pos = None; bal = 10000.0; daily_t = 0; last_d = None; cool_until = None; consec_l = 0
    h4_cache = {}; last_signal_time = None
    
    adx_min = cfg['adx_min']; sl_m = cfg['sl_mult']; rr_m = cfg['rr_mult']
    lots = cfg.get('lots', 0.10); max_daily = cfg.get('max_daily', 8)
    cool_5l = cfg.get('cool_5l', False)
    regime_adj = cfg.get('regime_adjust', {})
    ss, se = cfg['session']
    
    # 品种特性因子: 交易成本/滑点
    spread_cost = {"XAUUSD": 0.30, "BTCUSD": 0.50, "ETHUSD": 0.30, "EURUSD": 0.05, "GBPUSD": 0.06, "USDJPY": 0.04, "GBPJPY": 0.08}[sym]
    
    for i in range(100, len(h1)):
        bt = pd.Timestamp(ht[i]); price = hc[i]; bh = hh[i]; bl = hl[i]
        cd = bt.date()
        if last_d != cd: last_d = cd; daily_t = 0
        if cool_until and bt < cool_until: continue
        
        if pos:
            # 品种特定止损止盈检查 — 含spread成本
            hit_sl = (pos['side']==1 and bl<=(pos['sl']+spread_cost)) or (pos['side']==-1 and bh>=(pos['tp']-spread_cost))
            hit_tp = (pos['side']==1 and bh>=(pos['tp']-spread_cost)) or (pos['side']==-1 and bl<=(pos['sl']+spread_cost))
            if hit_sl or hit_tp:
                ep = pos['sl'] if hit_sl else pos['tp']
                profit = (ep-pos['entry'])*pos['side']*0.01*100 - spread_cost
                trades.append({
                    'symbol':sym, 'profit':round(profit,2), 'result':'WIN' if profit>0 else 'LOSS',
                    'holding_bars':i-pos['signal_bar'],
                    'entry':round(pos['entry'],2), 'exit':round(ep,2),
                    'sl':round(pos['sl'],2), 'tp':round(pos['tp'],2),
                    'adx':round(adx_v[i],1), 'regime':regime, 'trend':pos['trend'],
                    'lot_size':lots
                })
                bal += profit
                if profit < 0:
                    consec_l += 1
                    if consec_l >= 5 and cool_5l: cool_until = bt+timedelta(hours=24)
                    elif consec_l >= 3: cool_until = bt+timedelta(hours=4)
                    else: cool_until = bt+timedelta(minutes=30)
                else: consec_l = 0
                pos = None; continue
            else: continue
        
        if daily_t >= max_daily: continue
        if not (ss <= bt.hour < se): continue
        if np.isnan(adx_v[i]) or adx_v[i] < adx_min: continue
        
        h4i = min(i//4, len(h4c)-1); hadx = h4adx[max(0,h4i)]
        regime = 'trend'
        if hadx < 20 and adx_v[i] < 20: regime = 'ranging'
        if hadx > 35: regime = 'strong_trend'
        atr_h = atr_v[max(0,i-30):i+1]
        if len(atr_h)>10 and atr_v[i] > np.mean(atr_h)*1.8: regime = 'volatile'
        if regime == 'volatile': continue
        
        if np.isnan(e14[i]) or np.isnan(e28[i]): continue
        trend = 'UP' if e14[i] > e28[i] else 'DOWN'
        
        # H4供需区
        ck = h4i
        if ck not in h4_cache:
            chunk = h4.iloc[max(0,h4i-30):h4i+1]
            if len(chunk) >= 15: h4_cache[ck] = find_zones(chunk)
            else: continue
        zd = h4_cache.get(ck, {'demand':[],'supply':[]})
        
        zc=None; zt=None; flip=False; h4a_val = h4a[max(0,h4i)]
        for z in zd.get('demand',[]):
            if z['strength']>=1.0 and price>z['top'] and price-z['top']<h4a_val*3: zc,zt=z,'D'; break
        if not zc:
            for z in zd.get('supply',[]):
                if z['strength']>=1.0 and price<z['bottom'] and z['bottom']-price<h4a_val*3: zc,zt=z,'S'; break
        if not zc:
            for z in zd.get('supply',[]):
                if price>z['top']: zc,zt=z,'D'; flip=True; break
        if not zc:
            for z in zd.get('demand',[]):
                if price<z['bottom']: zc,zt=z,'S'; flip=True; break
        if not zc: continue
        
        # D1方向
        d1i = min(i//24, len(dc)-1)
        if d1i >= 21 and not np.isnan(de9[d1i]) and not np.isnan(de21[d1i]):
            d1_dir = 'UP' if de9[d1i] > de21[d1i] else 'DOWN'
            direction = 'BUY' if d1_dir=='UP' and zt=='D' else 'SELL' if d1_dir=='DOWN' and zt=='S' else None
        else: direction = 'BUY' if trend=='UP' and zt=='D' else 'SELL' if trend=='DOWN' and zt=='S' else None
        if not direction: continue
        
        sm=sl_m; rm=rr_m
        if regime == 'ranging': sm=min(sm*0.7,0.8); rm=max(rm*0.8,1.5)
        elif regime == 'strong_trend': sm=max(sm*1.2,1.0); rm*=1.2
        buf = max(h4a_val*0.1, 0.5)
        if direction == 'BUY': sl=zc['bottom']-buf; tp=price+(price-sl)*rm
        else: sl=zc['top']+buf; tp=price-(sl-price)*rm
        
        pos = {
            'side':1 if direction=='BUY' else -1,
            'entry':price, 'sl':sl, 'tp':tp,
            'signal_bar':i, 'trend':trend, 'lot_size':lots
        }
        daily_t += 1; last_signal_time = bt
    
    if pos:
        profit = (hc[-1]-pos['entry'])*pos['side']*0.01*100 - spread_cost
        trades.append({'profit':round(profit,2),'result':'WIN' if profit>0 else 'LOSS'})
        bal += profit
    
    return trades, bal

# ═══ 报告 ═══
def calc_stats(trades, bal, initial=10000):
    closed = [t for t in trades if t.get('result','') in ('WIN','LOSS')]
    if not closed: return {'trades':0,'error':'no trades'}
    wins = [t for t in closed if t['profit']>0]
    losses = [t for t in closed if t['profit']<0]
    total = sum(t['profit'] for t in closed)
    wr = len(wins)/len(closed)*100
    avg_w = np.mean([t['profit'] for t in wins]) if wins else 0
    avg_l = abs(np.mean([t['profit'] for t in losses])) if losses else 0
    pf = sum(t['profit'] for t in wins)/max(abs(sum(t['profit'] for t in losses)),1) if wins and losses else 0
    return {'trades':len(closed),'wins':len(wins),'losses':len(losses),'wr':round(wr,1),
            'pnl':round(total,2),'avg_w':round(avg_w,2),'avg_l':round(avg_l,2),'pf':round(pf,2),
            'final':round(bal,2),'ret':round(total/initial*100,2)}


# ═══ MAIN ═══
print("="*65)
print("  A.T.E. 多品种回测 — 黄金/虚拟货币/外汇")
print("="*65)

# 1. 下载/检查数据
print("\n[Phase 1] 数据检查...")
for sym, cfg in SYMBOLS.items():
    for tf in ['H1','H4','D1']:
        f = os.path.join(DATA_DIR, f"{sym}_{tf}.csv")
        if not os.path.exists(f):
            print(f"下载 {sym}...")
            download_data(sym)
            break

# 2. 各品种回测
print("\n[Phase 2] 回测...")
results = {}
for sym, cfg in SYMBOLS.items():
    try:
        trades, bal = run_backtest(sym, cfg)
        stats = calc_stats(trades, bal, initial=10000)
        results[sym] = {'stats': stats, 'trades': trades, 'config': cfg}
        cn = cfg['name']
        print(f"  {sym} ({cn:7s}): {int(stats.get('trades',0)):3d}笔 | 胜率{stats.get('wr',0):5.1f}% | PnL${stats.get('pnl',0):7.0f}")
    except Exception as e:
        print(f"  {sym}({cfg['name']}): FAILED - {e}")

# 3. 对比报告
print("\n" + "="*65)
print("  ★ 多品种回测对比报告")
print("="*65)
print(f"\n{'品种':<10} {'类型':<8} {'笔数':<6} {'胜率':<7} {'盈亏':<10} {'PF':<6} {'平均盈':<8} {'平均亏':<8} {'收益率':<8}")
print("-"*70)
for sym, cfg in SYMBOLS.items():
    r = results.get(sym, {})
    if r.get('stats',{}).get('error'):
        print(f"{sym:<10} {cfg['type']:<8} {'ERR':<6} {r['stats']['error']:<20}")
    else:
        s = r.get('stats',{})
        print(f"{sym:<10} {cfg['type']:<8} {s.get('trades',0):<6d} {s.get('wr',0):<6.1f}% ${s.get('pnl',0):<7.2f} "
              f"{s.get('pf',0):<6.2f} ${s.get('avg_w',0):<6.2f} ${s.get('avg_l',0):<6.2f} {s.get('ret',0):<7.2f}%")

# 汇总
metal = [r for s,r in results.items() if results[s]['config']['type']=='metal']
crypto = [r for s,r in results.items() if results[s]['config']['type']=='crypto']
forex = [r for s,r in results.items() if results[s]['config']['type'] in ('forex','cross')]

print("\n" + "="*65)
print("  品种差异化报告")
print("="*65)
print(f"{'品种':<10s} {'类型':<10s} {'笔数':>5s} {'胜率':>7s} {'PnL':>9s} {'PF':>6s} {'赢均':>7s} {'亏均':>7s} {'持仓K线':>9s}")
print("-"*78)
for sym in results:
    r = results[sym]
    s = r['stats']
    cfg = r['config']
    cn = cfg['name']
    if s.get('error'):
        print(f"{sym:<10s} {cfg['type']:<10s} {'ERR':>5s} {s['error']:<20s}")
        continue
    avg_w = s.get('avg_w', 0)
    avg_l = s.get('avg_l', 0)
    wr = s.get('wr', 0)
    pnl = s.get('pnl', 0)
    pf = s.get('pf', 0)
    td = s.get('trades', 0)
    avg_w = s.get('avg_w', 0)
    avg_l = s.get('avg_l', 0)
    avg_hold = 0
    ts = r['trades']
    if ts:
        holds = [t.get('holding_bars', 0) for t in ts if 'holding_bars' in t]
        if holds: avg_hold = sum(holds)/len(holds)
    print(f"{sym:<10} {cfg['type']:<10} {td:>5d} {wr:>7.1f}% ${pnl:>8.0f} {pf:>6.2f} ${avg_w:>6.0f} ${abs(avg_l):>6.0f} {avg_hold:>9.0f}")

print("\n" + "="*65)
print("  品种差异化参数总结")
print("="*65)
for sym in results:
    cfg = results[sym]['config']
    s = results[sym]['stats']
    if s.get('error'): continue
    for sym, cfg in SYMBOLS.items():
        if sym not in results: continue
        r = results[sym]
        s = r['stats']
        cn = cfg['name']
        if s.get('error'): continue
        print(f"\n{sym} ({cn}):")
        print(f"  参数: ADX>={cfg['adx_min']} | SL={cfg['sl_mult']}ATR | RR={cfg['rr_mult']} | Lot={cfg['lots']}")
        print(f"  时段: {cfg['session'][0]:02d}:00-{cfg['session'][1]:02d}:00 UTC")
        print(f"  每日上限: {cfg['max_daily']}笔 | 5连败冷却: {'是' if cfg['cool_5l'] else '否'}")
        print(f"  结果: {s['trades']}笔, 胜率{s['wr']}%, PnL ${s['pnl']:.0f}, PF={s['pf']:.2f}")

print("\n" + "="*65)
print("  类别汇总")
print("="*65)
print(f"{'类别':<10s} {'品种数':>5s} {'总交易':>7s} {'平均胜率':>9s} {'总盈亏':>10s} {'平均PF':>7s}")
print("-"*55)
for cat_name, cat_results in [("贵金属", metal), ("虚拟货币", crypto), ("外汇", forex)]:
    if cat_results:
        total_t = sum(r.get('trades',0) for r in cat_results)
        avg_wr = np.mean([r.get('wr',0) for r in cat_results if r.get('wr',0)])
        total_pnl = sum(r.get('pnl',0) for r in cat_results)
        avg_pf = np.mean([r.get('pf',0) for r in cat_results if r.get('pf',0) > 0])
        print(f"{cat_name:<10s} {len(cat_results):>5d} {total_t:>7d} {avg_wr:>8.1f}% ${total_pnl:>9.0f} {avg_pf:>7.2f}")

print("="*65)
mt5.shutdown()
