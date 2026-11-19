"""
可视化行情分析图表 — Trading Central风格
生成HTML报告，内嵌交互式K线图和技术指标
"""
import sys, os, json, warnings
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict
warnings.filterwarnings('ignore')

import MetaTrader5 as mt5
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec

if not mt5.initialize():
    mt5.initialize()
mt5.login(60043976, password="", server="TradeMaxGlobal-Demo")

BASE = r"E:\GoldstrategyEngine"
DATA_DIR = os.path.join(BASE, "data")

# ═══ 品种列表 ═══
SYMBOLS = {
    "XAUUSD": {"name":"黄金 (Gold)",     "digits":2, "color": "#FFD700"},
    "BTCUSD": {"name":"比特币 (Bitcoin)", "digits":0, "color": "#F7931A"},
    "ETHUSD": {"name":"以太坊 (Ethereum)", "digits":0, "color": "#627EEA"},
    "EURUSD": {"name":"欧元 (Euro)",     "digits":5, "color": "#003399"},
    "GBPUSD": {"name":"英镑 (Pound)",    "digits":5, "color": "#CF1020"},
    "USDJPY": {"name":"美元/日元",       "digits":3, "color": "#0066CC"},
    "GBPJPY": {"name":"英镑/日元",       "digits":3, "color": "#8B0000"},
    "AUDUSD": {"name":"澳元 (AUD)",      "digits":5, "color": "#008B45"},
}

def ema(v, p):
    r = np.full(len(v), np.nan); r[p-1] = np.mean(v[:p])
    a = 2/(p+1)
    for i in range(p, len(v)): r[i] = v[i]*a + r[i-1]*(1-a)
    return r

def atr_vals(h, l, c, p=14):
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

def macd_calc(c, fast=12, slow=26, signal=9):
    ef = ema(c, fast); es = ema(c, slow)
    line = ef - es
    sig = ema(line, signal)
    hist = line - sig
    return line, sig, hist

def pivot_points(h, l, c):
    ph = max(h[-20:]) if len(h)>=20 else h[-1]
    pl = min(l[-20:]) if len(l)>=20 else l[-1]
    pc = c[-1]
    pp = (ph+pl+pc)/3
    return {
        'PP': pp, 'R1': 2*pp-pl, 'S1': 2*pp-ph,
        'R2': pp+(ph-pl), 'S2': pp-(ph-pl),
        'HL': ph, 'LL': pl, 'Range': ph-pl
    }

# ═══ 画图 ═══
def plot_chart(symbol, sym_cfg):
    h1 = pd.read_csv(os.path.join(DATA_DIR, f"{symbol}_H1.csv"), parse_dates=['time'])
    
    hc = h1['close'].values; hh = h1['high'].values; hl = h1['low'].values
    h1_time = h1['time'].values
    
    e9 = ema(hc, 9); e21 = ema(hc, 21); e50 = ema(hc, 50)
    atr_val = atr_vals(hh, hl, hc)
    rsi_val = rsi(hc)
    macd_line, macd_sig, macd_hist = macd_calc(hc)
    pp = pivot_points(hh, hl, hc)
    
    # 只显示最近30天的数据
    last_n = min(500, len(hc))
    t = h1_time[-last_n:]
    c = hc[-last_n:]; h = hh[-last_n:]; l = hl[-last_n:]
    e9v = e9[-last_n:]; e21v = e21[-last_n:]; e50v = e50[-last_n:]
    atr = atr_val[-last_n:]; rsi_v = rsi_val[-last_n:]
    ml = macd_line[-last_n:]; ms = macd_sig[-last_n:]; mh = macd_hist[-last_n:]
    
    price = c[-1]
    digits = sym_cfg['digits']
    
    fig = plt.figure(figsize=(16, 10))
    gs = GridSpec(4, 1, height_ratios=[3, 1, 1, 0.5], hspace=0.1)
    
    # 1. K线图 + 均线
    ax1 = fig.add_subplot(gs[0])
    # 绘制蜡烛图（用折线图代替，节省代码）
    ax1.plot(t, c, color='black', linewidth=1.2, label='Price')
    ax1.fill_between(t, l, h, alpha=0.1, color=sym_cfg['color'])
    
    ax1.plot(t, e9v, color='#FF6B35', linewidth=1, label=f'EMA9 ({e9v[-1]:,.{digits}f})')
    ax1.plot(t, e21v, color='#4169E1', linewidth=1, label=f'EMA21 ({e21v[-1]:,.{digits}f})')
    ax1.plot(t, e50v, color='#9932CC', linewidth=1, label=f'EMA50 ({e50v[-1]:,.{digits}f})')
    
    # 关键价位线
    ax1.axhline(y=pp['PP'], color='gray', linestyle='--', alpha=0.5, label=f'PP ({pp["PP"]:,.{digits}f})')
    ax1.axhline(y=pp['R1'], color='green', linestyle=':', alpha=0.4, label=f'R1 ({pp["R1"]:,.{digits}f})')
    ax1.axhline(y=pp['S1'], color='red', linestyle=':', alpha=0.4, label=f'S1 ({pp["S1"]:,.{digits}f})')
    
    ax1.set_ylabel(f'Price ({sym_cfg["name"]})', fontsize=10)
    ax1.legend(loc='upper left', fontsize=8)
    ax1.grid(True, alpha=0.3)
    ax1.set_title(f'{sym_cfg["name"]} ({symbol}) — {datetime.now().strftime("%Y-%m-%d %H:%M")} CET', fontsize=12, fontweight='bold')
    
    # 2. ATR
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax2.plot(t, atr, color='orange', linewidth=0.8, alpha=0.7)
    ax2.fill_between(t, 0, atr, alpha=0.2, color='orange')
    ax2.set_ylabel('ATR(14)', fontsize=9)
    ax2.grid(True, alpha=0.3)
    
    # 3. RSI
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    ax3.plot(t, rsi_v, color='purple', linewidth=1)
    ax3.axhline(y=70, color='red', linestyle='--', alpha=0.5)
    ax3.axhline(y=30, color='green', linestyle='--', alpha=0.5)
    ax3.axhline(y=50, color='gray', linestyle='-', alpha=0.3)
    ax3.fill_between(t, 70, 100, alpha=0.1, color='red')
    ax3.fill_between(t, 0, 30, alpha=0.1, color='green')
    ax3.set_ylabel('RSI(14)', fontsize=9)
    ax3.set_ylim(0, 100)
    ax3.grid(True, alpha=0.3)
    
    # 4. MACD
    ax4 = fig.add_subplot(gs[3], sharex=ax1)
    ax4.plot(t, mh, color='blue', linewidth=0.8, label='MACD Hist')
    ax4.axhline(y=0, color='gray', linestyle='-', alpha=0.3)
    ax4.set_xlabel('Date', fontsize=9)
    ax4.set_ylabel('MACD', fontsize=9)
    ax4.legend(loc='upper left', fontsize=8)
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # 保存
    out = os.path.join(BASE, f"chart_{symbol}.png")
    plt.savefig(out, dpi=150, bbox_inches='tight')
    plt.close()
    return out

# ═══ 主流程 ═══
print("="*65)
print("  A.T.E. 可视化行情分析图表")
print("="*65)

chart_files = []
for sym, cfg in SYMBOLS.items():
    try:
        f = os.path.join(DATA_DIR, f"{sym}_H1.csv")
        if not os.path.exists(f):
            for tf_name, tf_mt5 in [("H1", 16385), ("H4", 16388), ("D1", 16408)]:
                f_full = os.path.join(DATA_DIR, f"{sym}_{tf_name}.csv")
                if not os.path.exists(f_full):
                    rates = mt5.copy_rates_range(sym, tf_mt5,
                        int(datetime(2026, 1, 1).timestamp()),
                        int(datetime(2026, 7, 6).timestamp()))
                    if rates is not None and len(rates) > 0:
                        df = pd.DataFrame(rates)
                        df["time"] = pd.to_datetime(df["time"], unit="s")
                        df.to_csv(f_full, index=False)
        
        chart_file = plot_chart(sym, cfg)
        chart_files.append(chart_file)
        print(f"  ✓ {sym} ({cfg['name']}) → {chart_file}")
    except Exception as e:
        print(f"  ✗ {sym}: {e}")

print(f"\n共生成 {len(chart_files)} 张图表")
print("保存在: E:\\GoldstrategyEngine\\chart_*.png")

mt5.shutdown()
