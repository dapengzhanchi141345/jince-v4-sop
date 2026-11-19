"""
v10.4 自进化回测引擎 — 3轮迭代
流程: 回测 → 分析失败/成功模式 → 调参 → 回测 → 分析 → 调参 → 回测 → 报告
"""
import sys, os, json, warnings, copy
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
warnings.filterwarnings('ignore')

BASE = r"E:\GoldstrategyEngine"
DATA_DIR = os.path.join(BASE, "data")
OUT_DIR = os.path.join(BASE, "data", "evolution")
os.makedirs(OUT_DIR, exist_ok=True)

# ═══════════════════════════════════════════════
# Part 1: 核心函数
# ═══════════════════════════════════════════════
def ema(vals, p):
    r = np.full(len(vals), np.nan)
    r[p-1] = np.mean(vals[:p])
    a = 2/(p+1)
    for i in range(p, len(vals)):
        r[i] = vals[i]*a + r[i-1]*(1-a)
    return r

def atr(h, l, c, p=14):
    tr = np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1])))
    r = np.full(len(h), np.nan)
    r[p] = np.mean(tr[:p])
    a = 1/p
    for i in range(p+1, len(h)):
        r[i] = tr[i-1]*a + r[i-1]*(1-a)
    return pd.Series(r).ffill().fillna(np.mean(tr[:p])).values

def adx(h, l, c, p=14):
    if len(c) < p*2: return np.zeros(len(c))
    tr = np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1])))
    u, d = h[1:]-h[:-1], l[:-1]-l[1:]
    pdi = 100*pd.Series(np.where((u>d)&(u>0),u,0)).ewm(span=p).mean()/(pd.Series(tr).ewm(span=p).mean()+1e-10)
    mdi = 100*pd.Series(np.where((d>u)&(d>0),d,0)).ewm(span=p).mean()/(pd.Series(tr).ewm(span=p).mean()+1e-10)
    dx = 100*np.abs(pdi-mdi)/(pdi+mdi+1e-10)
    result = pd.Series(dx).ewm(span=p).mean().values
    return np.concatenate([np.zeros(len(c)-len(result)), result])

# ═══════════════════════════════════════════════
# Part 2: 供需区检测
# ═══════════════════════════════════════════════
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
        left_high = max(h[max(0,idx-10):idx+1])
        down = left_high - low_val
        if down <= 0: continue
        for j in range(idx+1, min(idx+8, len(c))):
            if c[j] > low_val + down*0.2:
                bh = max(h[idx:j+1]); bl = min(l[idx:j+1])
                ret = (bh-bl)/down if down > 0 else 0
                if 0.15 <= ret <= 0.95:
                    zones.append({'type':'D','top':bh,'bottom':max(bl,low_val-(bh-bl)*0.1),
                                 'strength':min(5.0,ret*5+0.5),'fresh':(len(c)-idx)<=20})
                break
    for idx, high_val in swh:
        if idx < 2 or idx > len(c)-3: continue
        left_low = min(l[max(0,idx-10):idx+1])
        up = high_val - left_low
        if up <= 0: continue
        for j in range(idx+1, min(idx+8, len(c))):
            if c[j] < high_val - up*0.2:
                bh = max(h[idx:j+1]); bl = min(l[idx:j+1])
                ret = (bh-bl)/up if up > 0 else 0
                if 0.15 <= ret <= 0.95:
                    zones.append({'type':'S','top':min(bh,high_val+(bh-bl)*0.1),'bottom':bl,
                                 'strength':min(5.0,ret*5+0.5),'fresh':(len(c)-idx)<=20})
                break
    # 去重
    merged = []
    for z in zones:
        dup = False
        for m in merged:
            if m['type']==z['type'] and abs(m['top']-z['top'])/max(m['top'],1)<0.01 and \
               abs(m['bottom']-z['bottom'])/max(m['bottom'],1)<0.01:
                m['strength'] = max(m['strength'],z['strength']); dup = True; break
        if not dup: merged.append(z)
    return {'demand':[z for z in merged if z['type']=='D'],'supply':[z for z in merged if z['type']=='S']}

# ═══════════════════════════════════════════════
# Part 3: 回测引擎 (参数化)
# ═══════════════════════════════════════════════
DEFAULT_PARAMS = {
    'adx_min': 22,
    'zone_str_min': 1.2,
    'sl_mult': 1.5,
    'rr_mult': 2.5,
    'ema_fast': 14,
    'ema_slow': 28,
    'session_start': 15,
    'session_end': 24,
    'd1_filter': True,
    'max_trades_day': 8,
    'lot_size': 0.01,
    'initial_balance': 10000,
}

def run_backtest(h1_df, h4_df, d1_df, params=None, verbose=False):
    if params is None: params = DEFAULT_PARAMS
    h1 = h1_df.copy(); h4 = h4_df.copy()
    hc = h1['close'].values; hh = h1['high'].values; hl = h1['low'].values
    ht = h1['time'].values
    
    adx_v = adx(hh, hl, hc); atr_v = atr(hh, hl, hc)
    e_fast = ema(hc, params['ema_fast'])
    e_slow = ema(hc, params['ema_slow'])
    
    h4c = h4['close'].values; h4adx = adx(h4['high'].values, h4['low'].values, h4c)
    h4_tr = np.maximum(h4['high'].values[1:]-h4['low'].values[1:],
                       np.maximum(np.abs(h4['high'].values[1:]-h4c[:-1]),
                                  np.abs(h4['low'].values[1:]-h4c[:-1])))
    h4_atr = np.full(len(h4c), np.nan)
    h4_atr[14] = np.mean(h4_tr[:14])
    for i in range(15, len(h4c)): h4_atr[i] = h4_tr[i-1]/14 + h4_atr[i-1]*13/14
    h4_atr = pd.Series(h4_atr).ffill().fillna(np.mean(h4_tr[:14])).values
    
    dc = d1_df['close'].values
    de9 = ema(dc, 9) if params['d1_filter'] else None
    de21 = ema(dc, 21) if params['d1_filter'] else None
    
    trades = []; pos = None; bal = float(params['initial_balance'])
    eq = [bal]; daily_t = 0; last_d = None; consec_l = 0; cool_until = None
    h4_zone_cache = {}
    
    for i in range(100, len(h1)):
        bt = pd.Timestamp(ht[i]); price = hc[i]; bh = hh[i]; bl = hl[i]
        cd = bt.date()
        if last_d != cd: daily_t = 0; last_d = cd
        
        # 冷却
        if cool_until and bt < cool_until: eq.append(bal); continue
        
        # 持仓管理
        if pos:
            hit_sl = (pos['side']==1 and bl<=pos['sl']) or (pos['side']==-1 and bh>=pos['sl'])
            hit_tp = (pos['side']==1 and bh>=pos['tp']) or (pos['side']==-1 and bl<=pos['tp'])
            reason = 'SL' if hit_sl else 'TP' if hit_tp else ''
            if hit_sl or hit_tp:
                ep = pos['sl'] if hit_sl else pos['tp']
                profit = (ep-pos['entry'])*pos['side']*params['lot_size']*100
                trades.append({'open_time':pos['ot'].strftime('%Y-%m-%d %H:%M'),
                    'close_time':bt.strftime('%Y-%m-%d %H:%M'),'direction':'BUY' if pos['side']==1 else 'SELL',
                    'entry':round(pos['entry'],2),'exit':round(ep,2),'profit':round(profit,2),
                    'result':'WIN' if profit>0 else 'LOSS','reason':reason,'regime':pos.get('regime',''),
                    'adx_at_entry':round(pos.get('adx',0),1),'trend_at_entry':pos.get('trend','')})
                bal += profit
                if profit < 0:
                    consec_l += 1
                    if consec_l >= 5: cool_until = bt + timedelta(hours=24)
                    elif consec_l >= 3: cool_until = bt + timedelta(hours=4)
                    elif consec_l >= 2: cool_until = bt + timedelta(minutes=30)
                else: consec_l = 0
                pos = None; eq.append(bal); continue
            else: eq.append(bal); continue
        
        # 新信号
        if daily_t >= params['max_trades_day']: eq.append(bal); continue
        if not (params['session_start'] <= bt.hour < params['session_end']): eq.append(bal); continue
        if np.isnan(adx_v[i]) or adx_v[i] < params['adx_min']: eq.append(bal); continue
        
        # 市场状态
        h4i = min(i//4, len(h4c)-1)
        hadx = h4adx[max(0,h4i)]; h4a = h4_atr[max(0,h4i)]
        regime = 'trend'
        if hadx < 20 and adx_v[i] < 20: regime = 'ranging'
        if hadx > 35: regime = 'strong_trend'
        atr_h = atr_v[max(0,i-30):i+1]
        if len(atr_h)>10 and atr_v[i] > np.mean(atr_h)*1.8: regime = 'volatile'
        if regime == 'volatile': eq.append(bal); continue
        
        if np.isnan(e_fast[i]) or np.isnan(e_slow[i]): eq.append(bal); continue
        trend = 'UP' if e_fast[i] > e_slow[i] else 'DOWN'
        
        # H4供需区
        ck = h4i
        if ck not in h4_zone_cache:
            chunk = h4.iloc[max(0,h4i-30):h4i+1]
            if len(chunk) >= 15: h4_zone_cache[ck] = find_zones(chunk)
            else: eq.append(bal); continue
        zd = h4_zone_cache.get(ck, {'demand':[],'supply':[]})
        
        zc = None; zt = None; flip = False
        for z in zd.get('demand',[]):
            if z['strength']>=params['zone_str_min'] and price>z['top'] and price-z['top']<h4a*3:
                zc,zt=z,'D'; break
        if not zc:
            for z in zd.get('supply',[]):
                if z['strength']>=params['zone_str_min'] and price<z['bottom'] and z['bottom']-price<h4a*3:
                    zc,zt=z,'S'; break
        if not zc:
            for z in zd.get('supply',[]):
                if price>z['top']: zc,zt=z,'D'; flip=True; break
        if not zc:
            for z in zd.get('demand',[]):
                if price<z['bottom']: zc,zt=z,'S'; flip=True; break
        if not zc: eq.append(bal); continue
        
        # D1方向
        if params['d1_filter'] and de9 is not None and de21 is not None:
            d1i = min(i//24, len(dc)-1)
            if d1i >= 21 and not np.isnan(de9[d1i]) and not np.isnan(de21[d1i]):
                d1_dir = 'UP' if de9[d1i] > de21[d1i] else 'DOWN'
            else: d1_dir = trend
            direction = 'BUY' if d1_dir=='UP' and zt=='D' else 'SELL' if d1_dir=='DOWN' and zt=='S' else None
        else:
            direction = 'BUY' if trend=='UP' and zt=='D' else 'SELL' if trend=='DOWN' and zt=='S' else None
        if not direction: eq.append(bal); continue
        
        # SL/TP
        sm = params['sl_mult']; rm = params['rr_mult']
        if regime == 'ranging': sm = min(sm*0.7, 0.8); rm = max(rm*0.8, 1.5)
        elif regime == 'strong_trend': sm = max(sm*1.2, 1.0); rm *= 1.2
        
        buf = max(h4a*0.1, 0.5)
        if direction == 'BUY': sl = zc['bottom'] - buf; tp = price + (price-sl)*rm
        else: sl = zc['top'] + buf; tp = price - (sl-price)*rm
        
        pos = {'side':1 if direction=='BUY' else -1, 'entry':price, 'sl':sl, 'tp':tp,
               'ot':bt, 'regime':regime, 'adx':adx_v[i], 'trend':trend}
        daily_t += 1; eq.append(bal)
    
    if pos:
        profit = (hc[-1]-pos['entry'])*pos['side']*params['lot_size']*100
        trades.append({'open_time':pos['ot'].strftime('%Y-%m-%d %H:%M'),
            'close_time':pd.Timestamp(ht[-1]).strftime('%Y-%m-%d %H:%M'),
            'direction':'BUY' if pos['side']==1 else 'SELL',
            'entry':round(pos['entry'],2),'exit':round(hc[-1],2),
            'profit':round(profit,2),'result':'WIN' if profit>0 else 'LOSS','reason':'回测结束',
            'regime':pos.get('regime',''),'adx_at_entry':round(pos.get('adx',0),1),
            'trend_at_entry':pos.get('trend','')})
        bal += profit
    
    return trades, bal, np.array(eq)

# ═══════════════════════════════════════════════
# Part 4: 分析引擎 — 从交易中学习
# ═══════════════════════════════════════════════
def analyze_trades(trades, params):
    """分析交易数据 → 输出智能进化建议"""
    closed = [t for t in trades if t.get('result','') in ('WIN','LOSS')]
    if not closed: return {}, [{'msg':'无交易数据','action':'skip'}]
    
    wins = [t for t in closed if t['profit']>0]
    losses = [t for t in closed if t['profit']<0]
    total_pnl = sum(t['profit'] for t in closed)
    wr = len(wins)/len(closed)*100
    n = len(closed)
    
    recos = []
    
    # ─── 规则1: 交易频率是否足够? ───
    if n < 20:
        # 交易太少, 应该放宽条件
        if params['adx_min'] > 20:
            recos.append({'param':'adx_min','current':params['adx_min'],
                         'suggested':max(20, params['adx_min']-5),
                         'reason':f'仅{n}笔交易/年, 太少, 放宽ADX≥{max(20,params["adx_min"]-5)}以获取更多信号',
                         'confidence':'high'})
        if params['zone_str_min'] > 1.0:
            recos.append({'param':'zone_str_min','current':params['zone_str_min'],
                         'suggested':max(1.0, params['zone_str_min']-0.2),
                         'reason':f'放宽区强度阈值以增加交易机会',
                         'confidence':'high'})
    # ─── 规则2: 交易足够但亏损 ───
    elif total_pnl < 0:
        # 亏损时的调整
        avg_loss = abs(np.mean([t['profit'] for t in losses])) if losses else 0
        avg_win = np.mean([t['profit'] for t in wins]) if wins else 0
        
        if avg_win < avg_loss * 1.5:
            recos.append({'param':'rr_mult','current':params['rr_mult'],
                         'suggested':round(params['rr_mult']+0.5,1),
                         'reason':f'盈亏比不足, 提高RR从{params["rr_mult"]}→{round(params["rr_mult"]+0.5,1)}',
                         'confidence':'high'})
        if wr < 35:
            recos.append({'param':'adx_min','current':params['adx_min'],
                         'suggested':min(30, params['adx_min']+3),
                         'reason':f'胜率{wr}%过低, 提高ADX≥{min(30,params["adx_min"]+3)}',
                         'confidence':'medium'})
    # ─── 规则3: 盈利状态 ───
    else:
        pf = sum(t['profit'] for t in wins) / max(abs(sum(t['profit'] for t in losses)), 1)
        if n >= 20:
            # 已经不错, 微调
            if pf < 1.8:
                recos.append({'param':'rr_mult','current':params['rr_mult'],
                             'suggested':round(params['rr_mult']+0.3,1),
                             'reason':f'盈利但PF={pf}偏低, 微调提升RR',
                             'confidence':'low'})
        else:
            # 盈利但交易少, 尝试适当放宽获取更多信号
            recos.append({'param':'adx_min','current':params['adx_min'],
                         'suggested':max(18, params['adx_min']-3),
                         'reason':f'盈利但仅{n}笔, 放宽ADX≥{max(18,params["adx_min"]-3)}以获取更多信号',
                         'confidence':'medium'})
    
    if not recos:
        recos.append({'param':'none','current':'','suggested':'',
                     'reason':f'当前{n}笔交易, 表现稳定, 无需调整',
                     'confidence':'none'})
    
    # 市场状态分解
    regime_stats = defaultdict(lambda: {'t':0,'w':0,'p':0})
    for t in closed:
        r = t.get('regime','?')
        regime_stats[r]['t'] += 1; regime_stats[r]['p'] += t['profit']
        if t['profit']>0: regime_stats[r]['w'] += 1
    
    return {
        'total_trades': n, 'wins': len(wins), 'losses': len(losses),
        'win_rate': round(wr,1), 'total_pnl': round(total_pnl,2),
        'regime_stats': {k:{'trades':v['t'],'wr':round(v['w']/v['t']*100,1) if v['t']>0 else 0,
                            'pnl':round(v['p'],2)} for k,v in regime_stats.items()},
    }, recos

def apply_recommendations(params, recos, iteration):
    new_params = copy.deepcopy(params)
    log = []
    for r in recos:
        p = r['param']
        if p == 'adx_min':
            old = new_params[p]
            new_params[p] = int(r['suggested'])
            log.append(f"  → ADX_MIN {old}→{new_params[p]} | {r['reason']} [{r['confidence']}]")
        elif p == 'zone_str_min':
            old = new_params[p]
            new_params[p] = round(r['suggested'], 1)
            log.append(f"  → ZONE_STR {old}→{new_params[p]} | {r['reason']} [{r['confidence']}]")
        elif p == 'rr_mult':
            old = new_params[p]
            new_params[p] = round(r['suggested'], 1)
            log.append(f"  → RR_MULT {old}→{new_params[p]} | {r['reason']} [{r['confidence']}]")
        elif p == 'sl_mult':
            old = new_params[p]
            new_params[p] = round(r['suggested'], 1)
            log.append(f"  → SL_MULT {old}→{new_params[p]} | {r['reason']} [{r['confidence']}]")
    if not log:
        log.append('  本轮回测表现稳定, 维持参数不变')
    return new_params, log

# ═══════════════════════════════════════════════
# Part 5: 报告
# ═══════════════════════════════════════════════
def full_report(trades, balance, equity, initial, label=''):
    closed = [t for t in trades if t.get('result','') in ('WIN','LOSS')]
    if not closed: return {}
    
    wins = [t for t in closed if t['profit']>0]
    losses = [t for t in closed if t['profit']<0]
    total = sum(t['profit'] for t in closed)
    wr = len(wins)/len(closed)*100
    
    avg_w = np.mean([t['profit'] for t in wins]) if wins else 0
    avg_l = abs(np.mean([t['profit'] for t in losses])) if losses else 0
    gp = sum(t['profit'] for t in wins) if wins else 0
    gl = abs(sum(t['profit'] for t in losses)) if losses else 0
    pf = gp/gl if gl>0 else float('inf')
    
    peak = equity[0]; mdd = 0
    for e in equity:
        if e > peak: peak = e
        mdd = max(mdd, (peak-e)/peak*100)
    
    rets = np.diff(equity)/(equity[:-1]+1e-10)
    sh = np.mean(rets)/np.std(rets)*np.sqrt(365*24) if len(rets)>1 and np.std(rets)>0 else 0
    rp = total/initial*100
    cm = rp/mdd if mdd>0 else 0
    
    cw=cl=mw=ml=0
    for t in closed:
        if t['profit']>0: cw+=1; cl=0
        else: cl+=1; cw=0
        mw=max(mw,cw); ml=max(ml,cl)
    
    return {'label':label,'trades':len(closed),'wins':len(wins),'losses':len(losses),
            'wr':round(wr,1),'pnl':round(total,2),'avg_w':round(avg_w,2),'avg_l':round(avg_l,2),
            'pf':round(pf,2),'sharpe':round(sh,2),'calmar':round(cm,2),'mdd':round(mdd,2),
            'max_cons_w':mw,'max_cons_l':ml,'final_bal':round(initial+total,2),'ret':round(rp,2)}

# ═══════════════════════════════════════════════
# MAIN: 自进化管道
# ═══════════════════════════════════════════════
def run_evolution_pipeline(rounds=3):
    # 加载数据
    h1 = pd.read_csv(os.path.join(DATA_DIR,'XAUUSD_H1.csv'), parse_dates=['time'])
    h4 = pd.read_csv(os.path.join(DATA_DIR,'XAUUSD_H4.csv'), parse_dates=['time'])
    d1 = pd.read_csv(os.path.join(DATA_DIR,'XAUUSD_D1.csv'), parse_dates=['time'])
    print(f'数据: H1={len(h1)} H4={len(h4)} D1={len(d1)}')
    
    params = dict(DEFAULT_PARAMS)
    results = []
    all_logs = []
    
    for rnd in range(1, rounds+1):
        print(f'\n{"="*60}')
        print(f'  第 {rnd} 轮 回测 | 参数: ADX≥{params["adx_min"]} ZS≥{params["zone_str_min"]} '
              f'SLx{params["sl_mult"]} RRx{params["rr_mult"]}')
        print(f'{"="*60}')
        
        trades, bal, eq = run_backtest(h1, h4, d1, params)
        r = full_report(trades, bal, eq, params['initial_balance'], f'Round {rnd}')
        results.append(r)
        
        print(f'  交易: {r["trades"]}笔 | 胜率: {r["wr"]}% | PnL: ${r["pnl"]} | '
              f'PF: {r["pf"]} | Sharpe: {r["sharpe"]} | MDD: {r["mdd"]}%')
        
        # 分析进化
        if rnd < rounds:
            analysis, recos = analyze_trades(trades, params)
            new_params, logs = apply_recommendations(params, recos, rnd)
            params = new_params
            all_logs.extend(logs)
            for l in logs: print(l)
        
        # 保存中间结果
        pd.DataFrame(trades).to_csv(os.path.join(OUT_DIR, f'trades_r{rnd}.csv'), index=False)
        with open(os.path.join(OUT_DIR, f'params_r{rnd}.json'), 'w') as f:
            json.dump(params, f, indent=2)
    
    # 最终报告
    print(f'\n{"="*60}')
    print(f'  ★ 自进化回测最终报告')
    print(f'{"="*60}')
    print(f'\n{"轮次":<8} {"交易数":<8} {"胜率":<8} {"盈亏":<12} {"PF":<8} {"夏普":<8} {"回撤":<8} {"收益率":<8}')
    print('-'*68)
    for r in results:
        print(f'{r["label"]:<8} {r["trades"]:<8} {r["wr"]:<7.1f}% ${r["pnl"]:<8.2f} {r["pf"]:<8.2f} '
              f'{r["sharpe"]:<8.2f} {r["mdd"]:<7.2f}% {r["ret"]:<7.2f}%')
    
    # 对比
    r1, r_last = results[0], results[-1]
    print(f'\n▶ 进化效果:')
    imp_pnl = ((r_last['pnl'] - r1['pnl']) / abs(r1['pnl']) * 100) if r1['pnl'] != 0 else 0
    imp_wr = r_last['wr'] - r1['wr']
    imp_pf = r_last['pf'] - r1['pf']
    imp_mdd = r1['mdd'] - r_last['mdd']
    
    print(f'  PnL: ${r1["pnl"]} → ${r_last["pnl"]} ({imp_pnl:+.0f}%)')
    print(f'  胜率: {r1["wr"]}% → {r_last["wr"]}% ({imp_wr:+.1f}pp)')
    print(f'  盈亏比: {r1["pf"]} → {r_last["pf"]} ({imp_pf:+.2f})')
    print(f'  回撤: {r1["mdd"]}% → {r_last["mdd"]}% ({imp_mdd:+.1f}pp)')
    print(f'  夏普: {r1["sharpe"]} → {r_last["sharpe"]}')
    
    if imp_pnl > 0:
        print(f'  ✅ 系统自我进化成功! PnL提升{imp_pnl:.0f}%')
    else:
        print(f'  ⚠️ 本轮进化未提升收益, 但记录了交易经验')
    
    # 保存最终参数
    with open(os.path.join(OUT_DIR, 'final_params.json'), 'w') as f:
        json.dump(params, f, indent=2)
    print(f'\n最终参数已保存: {os.path.join(OUT_DIR, "final_params.json")}')
    
    # 保存汇总
    with open(os.path.join(OUT_DIR, 'evolution_report.json'), 'w') as f:
        json.dump({'results':results,'logs':all_logs,'final_params':params}, f, indent=2)
    print(f'进化报告已保存')
    
    return results, params, all_logs

if __name__ == '__main__':
    print('='*65)
    print('  v10.4 自进化回测引擎')
    print('  3轮: 回测→分析→调参→回测→分析→调参→回测')
    print('='*65)
    results, final_params, logs = run_evolution_pipeline(rounds=5)
