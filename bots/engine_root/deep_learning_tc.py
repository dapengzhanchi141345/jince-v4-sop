"""
A.T.E. Deep Learning — 学习Trading Central分析范式
让系统像分析师一样思考: 趋势判断 → 关键价位 → 交易策略 → 报告输出
"""
import sys, os, json, warnings
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict
warnings.filterwarnings('ignore')

import MetaTrader5 as mt5
if not mt5.initialize(): mt5.initialize()
mt5.login(60043976, password="", server="TradeMaxGlobal-Demo")

BASE = r"E:\GoldstrategyEngine"
sys.path.insert(0, BASE)
DATA_DIR = os.path.join(BASE, "data")

# ═══ 品种列表 ═══
SYMBOLS = {
    "XAUUSD": {"name":"黄金 (Gold)",     "type":"Metals",    "digits":2},
    "BTCUSD": {"name":"比特币 (Bitcoin)", "type":"Crypto",    "digits":0},
    "ETHUSD": {"name":"以太坊 (Ethereum)", "type":"Crypto",    "digits":0},
    "EURUSD": {"name":"欧元 (Euro)",     "type":"Forex",     "digits":5},
    "GBPUSD": {"name":"英镑 (Pound)",    "type":"Forex",     "digits":5},
    "USDJPY": {"name":"美元/日元",       "type":"Forex",     "digits":3},
    "GBPJPY": {"name":"英镑/日元",       "type":"Forex",     "digits":3},
    "AUDUSD": {"name":"澳元 (AUD)",      "type":"Forex",     "digits":5},
}

# ═══ 指标引擎 ═══
def ema(v, p):
    r = np.full(len(v), np.nan); r[p-1] = np.mean(v[:p])
    a = 2/(p+1)
    for i in range(p, len(v)): r[i] = v[i]*a + r[i-1]*(1-a)
    return r

def atr(h, l, c, p=14):
    tr = np.maximum(h[1:]-l[1:], np.maximum(abs(h[1:]-c[:-1]), abs(l[1:]-c[:-1])))
    r = np.full(len(h), np.nan); r[p] = np.mean(tr[:p])
    for i in range(p+1, len(h)): r[i] = tr[i-1]/p + r[i-1]*(1-1/p)
    return pd.Series(r).ffill().fillna(np.mean(tr[:p])).values

def rsi(c, p=14):
    d = np.diff(c)
    g = np.where(d>0, d, 0); lo = np.where(d<0, -d, 0)
    ag = pd.Series(g).ewm(span=p).mean().values
    al = pd.Series(lo).ewm(span=p).mean().values
    rs = ag/(al+1e-10)
    return 100 - 100/(1+rs)

def pivot_points(h, l, c, window=20):
    ph = max(h[-window:]) if len(h)>=window else h[-1]
    pl = min(l[-window:]) if len(l)>=window else l[-1]
    pc = c[-1]
    pp = (ph+pl+pc)/3
    rng = ph-pl
    return {
        'PP': pp,
        'R1': pp+rng*0.5, 'R2': pp+rng, 'R3': pp+rng*1.5,
        'S1': pp-rng*0.5, 'S2': pp-rng, 'S3': pp-rng*1.5,
        'HL': ph, 'LL': pl, 'Range': rng
    }

def trend_votes(h1, h4, d1):
    """多时间框架趋势投票"""
    h1c = h1['close'].values; h4c = h4['close'].values; d1c = d1['close'].values
    
    e9 = ema(h1c, 9); e21 = ema(h1c, 21); e50 = ema(h1c, 50)
    h4_e21 = ema(h4c, 21); h4_e50 = ema(h4c, 50)
    d1_e21 = ema(d1c, 21); d1_e50 = ema(d1c, 50)
    
    price = float(h1c[-1])
    h1_up = price > e9[-1] > e21[-1]
    h4_up = float(h4c[-1]) > float(h4_e21[-1]) > float(h4_e50[-1])
    d1_up = float(d1c[-1]) > float(d1_e21[-1]) > float(d1_e50[-1])
    
    votes_up = (h1_up)*1 + (h4_up)*2 + (d1_up)*3
    votes_dn = (not h1_up)*1 + (not h4_up)*2 + (not d1_up)*3
    
    total = votes_up + votes_dn
    bias = 'BULLISH' if votes_up > votes_dn else 'BEARISH' if votes_dn > votes_up else 'SIDEWAYS'
    strength = abs(votes_up - votes_dn) / total
    
    if votes_up >= 5 and bias == 'BULLISH': direction = 'STRONGLY_BULLISH'
    elif votes_dn >= 5 and bias == 'BEARISH': direction = 'STRONGLY_BEARISH'
    elif votes_up >= 3: direction = 'BULLISH'
    elif votes_dn >= 3: direction = 'BEARISH'
    else: direction = 'SIDEWAYS'
    
    return direction, votes_up, votes_dn, h1_up, h4_up, d1_up

# ═══ Trading Central 模式学习 ═══
def learn_tc_pattern(symbol, cfg):
    """学习Trading Central的分析范式: 方向+目标+转折+支持"""
    
    # 加载数据
    for tf in [("H1", 16385), ("H4", 16388), ("D1", 16408)]:
        f = os.path.join(DATA_DIR, f"{symbol}_{tf[0]}.csv")
        if not os.path.exists(f):
            rates = mt5.copy_rates_range(symbol, tf[1], 
                int(datetime(2026, 1, 1).timestamp()), 
                int(datetime(2026, 7, 6).timestamp()))
            if rates is not None:
                df = pd.DataFrame(rates)
                df["time"] = pd.to_datetime(df["time"], unit="s")
                df.to_csv(f, index=False)
    
    h1 = pd.read_csv(os.path.join(DATA_DIR, f"{symbol}_H1.csv"), parse_dates=['time'])
    h4 = pd.read_csv(os.path.join(DATA_DIR, f"{symbol}_H4.csv"), parse_dates=['time'])
    d1 = pd.read_csv(os.path.join(DATA_DIR, f"{symbol}_D1.csv"), parse_dates=['time'])
    
    hc = h1['close'].values; hh = h1['high'].values; hl = h1['low'].values
    price = float(hc[-1])
    digits = cfg['digits']
    
    # 计算所有指标
    e9 = ema(hc, 9); e21 = ema(hc, 21); e50 = ema(hc, 50)
    atr_val = atr(hh, hl, hc)
    rsi_val = rsi(hc)
    pp = pivot_points(hh, hl, hc)
    trend_dir, vu, vd, h1_dir, h4_dir, d1_dir = trend_votes(h1, h4, d1)
    
    rsi_now = float(rsi_val[-1])
    adx = 24.6  # Simplified for demo
    
    # ═══ 学习到的Trading Central决策逻辑 ═══
    
    # Step 1: 确定方向(对应Trading Central的上升/下降箭头)
    if trend_dir in ('STRONGLY_BULLISH', 'BULLISH'):
        direction = '上涨'
        arrow = '▲'
    elif trend_dir in ('STRONGLY_BEARISH', 'BEARISH'):
        direction = '下跌'
        arrow = '▼'
    else:
        direction = '盘整'
        arrow = '→'
    
    # Step 2: 找出关键价位(对应Trading Central的转折位/目标位/支持位)
    if direction == '上涨':
        # 转折位 = 支撑区域, 目标位 = 阻力区域
        turn_point = pp['PP']  # Pivot Point as turning point
        target1 = pp['R1']
        target2 = pp['R2']
        support1 = pp['S1']
        support2 = pp['S2']
    elif direction == '下跌':
        turn_point = pp['PP']
        target1 = pp['S1']
        target2 = pp['S2']
        support1 = pp['R1']
        support2 = pp['R2']
    else:
        turn_point = price
        target1 = pp['PP']
        target2 = pp['PP'] + (pp['R1']-pp['PP']) if pp['R1'] > pp['PP'] else pp['PP']
        support1 = turn_point
        support2 = support1
    
    # Step 3: 制定交易策略(对应Trading Central的"在转折位之上做多, 之下做空")
    if direction == '上涨':
        strategy = f'在 {turn_point:,.{digits}f} 之上，{arrow}看涨，目标价位为 {target1:,.{digits}f}，然后为 {target2:,.{digits}f}。'
        alt_strategy = f'备选策略：在 {turn_point:,.{digits}f} 下，{arrow}看空，目标价位定在 {support1:,.{digits}f}，然后为 {support2:,.{digits}f}。'
    elif direction == '下跌':
        strategy = f'在 {turn_point:,.{digits}f} 之上，{arrow}看跌，目标价位为 {target1:,.{digits}f}，然后为 {target2:,.{digits}f}。'
        alt_strategy = f'备选策略：在 {turn_point:,.{digits}f} 下，{arrow}看涨，目标价位定在 {support1:,.{digits}f}，然后为 {support2:,.{digits}f}。'
    else:
        strategy = f'当前处于盘整阶段，建议观望。'
        alt_strategy = f'若突破 {pp["PP"]:,.{digits}f} 则重新评估趋势方向。'
    
    # Step 4: 技术点评(结合RSI等指标)
    if rsi_now > 70:
        tech_comment = f"RSI技术指标超买({rsi_now:.0f})，可能面临短期回调，但仍保持当前趋势方向。"
    elif rsi_now < 30:
        tech_comment = f"RSI技术指标超卖({rsi_now:.0f})，可能出现反弹修正，但不改变整体趋势。"
    else:
        if direction in ('上涨', '下跌'):
            tech_comment = f"RSI技术指标{direction=='上涨' and '看涨' or '偏空'}，有进一步向上趋势。"
        else:
            tech_comment = f"RSI技术指标中性({rsi_now:.0f})，市场处于多空平衡状态。"
    
    return {
        'symbol': str(symbol),
        'name': str(cfg['name']),
        'price': float(price),
        'direction': direction,
        'arrow': arrow,
        'turn_point': float(turn_point),
        'targets': [float(t) for t in [target1, target2]],
        'supports': [float(t) for t in [support1, support2]],
        'strategy': strategy,
        'alt_strategy': alt_strategy,
        'tech_comment': tech_comment,
        'rsi': float(rsi_now),
        'trend_votes_up': int(vu),
        'trend_votes_down': int(vd),
        'h1': 'UP' if h1_dir else 'DOWN',
        'h4': 'UP' if h4_dir else 'DOWN',
        'd1': 'UP' if d1_dir else 'DOWN',
        'overall': trend_dir,
    }

# ═══ 主流程 ═══
print("="*65)
print("  A.T.E. Deep Learning — 学习Trading Central分析范式")
print("="*65)

analyses = []
for sym, cfg in SYMBOLS.items():
    try:
        analysis = learn_tc_pattern(sym, cfg)
        analyses.append(analysis)
        print(f"  ✓ {sym}: {analysis['direction']} | 转折位 {analysis['turn_point']:,.{cfg['digits']}f} | RSI {analysis['rsi']:.0f}")
    except Exception as e:
        print(f"  ✗ {sym}: {e}")

# ═══ 格式化报告 ═══
print("\n" + "="*65)
print("  Trading Central 风格分析报告")
print("="*65)

for a in analyses:
    d = a['symbol'] in ['USDJPY','GBPJPY'] and 3 or 2
    print(f"\n{'─'*65}")
    print(f"  {a['name']} ({a['symbol']})")
    print(f"{'─'*65}")
    print(f"  价格: {a['price']:,.{d}}")
    print(f"  当日内趋势: {a['arrow']} 新一轮{a['direction']}")
    print(f"  转折位: {a['turn_point']:,.{d}}")
    print(f"  目标位: {a['targets'][0]:,.{d}}, {a['targets'][1]:,.{d}}")
    print(f"  交易策略:")
    print(f"    {a['strategy']}")
    print(f"    {a['alt_strategy']}")
    print(f"  技术点评: {a['tech_comment']}")
    print(f"  多TF趋势: H1={a['h1']} | H4={a['h4']} | D1={a['d1']}")

# 保存JSON用于后续ML训练
json_path = os.path.join(BASE, "data", "tc_learned_patterns.json")
with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(analyses, f, indent=2, ensure_ascii=False)

print(f"\n\n分析报告已保存到: {json_path}")
print(f"共分析了 {len(analyses)} 个品种")
print("学习模式已保存: Trading Central 决策树 → A.T.E. 自主交易系统")

mt5.shutdown()
