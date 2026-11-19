"""V3.3 诊断：分析当前持仓、ADX 门槛影响、品种分层"""
import json, os, sys
from collections import defaultdict
from datetime import datetime

# ============ 1. 当前持仓 ============
sys.path.insert(0, 'E:/GoldstrategyEngine')
try:
    import MetaTrader5 as mt5
    if not mt5.initialize():
        print(f"MT5 init err: {mt5.last_error()}")
        mt5.shutdown()
        sys.exit(1)
except ImportError:
    print("MT5 not available, using journal only")
    mt5 = None

print("=" * 60)
print("【当前持仓】")
if mt5:
    positions = mt5.positions_get()
    if positions:
        for p in positions:
            print(f"  {p.symbol} {p.type} ticket={p.ticket} sl={p.sl:.4f} tp={p.tp:.4f} "
                  f"price={p.price_open:.4f} current={p.price_current:.4f} "
                  f"profit=${p.profit:.2f} vol={p.volume}")
    else:
        print("  无持仓")
    mt5.shutdown()

# ============ 2. Journal 按品种分层 + ADX 分布 ============
P = 'data/continuous_evolution/trade_journal.jsonl'
fills = {}; closes = []
for line in open(P, encoding='utf-8'):
    line = line.strip()
    if not line: continue
    try: r = json.loads(line)
    except: continue
    if r.get('type') == 'FILL': fills[r['ticket']] = r
    elif r.get('type') == 'CLOSE': closes.append(r)

def pnl(c):
    for k in ('pnl', 'profit', 'realized_pnl'):
        if isinstance(c.get(k), (int, float)): return float(c[k])
    f = fills.get(c.get('ticket'))
    if f and isinstance(c.get('price'), (int, float)) and isinstance(f.get('price'), (int, float)):
        d = 1 if str(f.get('direction', '')).upper() == 'BUY' else -1
        return d * (float(c['price']) - float(f['price']))
    return None

# 按品种分 ADX 层
by_symbol = defaultdict(lambda: {'pnl': [], 'adx': []})
for c in closes:
    f = fills.get(c.get('ticket'))
    if f is None: continue
    p = pnl(c)
    if p is None: continue
    sym = str(f.get('symbol', '?'))
    adx = float(f.get('adx', 0) or 0)
    by_symbol[sym]['pnl'].append(p)
    by_symbol[sym]['adx'].append(adx)

print(f"\n{'=' * 60}")
print(f"【品种 ADX 分布（基于全月已平仓）】")
print(f"{'品种':<12} {'n':>4} {'WR':>6} {'PF':>6} {'W/L':>6} {'avg_adx':>10} {'net':>8}")
print("-" * 60)

for sym, data in sorted(by_symbol.items(), key=lambda x: -sum(abs(p) for p in x[1]['pnl'])):
    pnls = data['pnl']; adxs = data['adx']
    if not pnls: continue
    n = len(pnls)
    gw = sum(x for x in pnls if x > 0)
    gl = -sum(x for x in pnls if x < 0)
    w = sum(1 for x in pnls if x > 0)
    pf = gw / gl if gl > 0 else None
    aw = gw / w if w else 0
    al = gl / (n - w) if (n - w) else 0
    wl = aw / abs(al) if al and al else None
    avg_adx = sum(adxs) / len(adxs) if adxs else 0
    print(f"{sym:<12} {n:>4} {round(w/n,2):>6} {round(pf,2) if pf else '---':>6} "
          f"{round(wl,2) if wl else '---':>6} {avg_adx:>10.1f} {round(gw-gl,1):>8}")

# ============ 3. ADX 分层 PF（找最优门槛）============
print(f"\n{'=' * 60}")
print(f"【ADX 门槛扫描：找最优 PF 的阈值】")
thresholds = [15, 18, 20, 22, 25, 28, 30, 35]
print(f"{'阈值':>6} {'n':>5} {'WR':>6} {'PF':>6} {'W/L':>6} {'net':>8}")
print("-" * 45)
for th in thresholds:
    kept = []
    for sym, data in by_symbol.items():
        for p, adx in zip(data['pnl'], data['adx']):
            if adx >= th:
                kept.append(p)
    if not kept: continue
    n = len(kept)
    gw = sum(x for x in kept if x > 0)
    gl = -sum(x for x in kept if x < 0)
    w = sum(1 for x in kept if x > 0)
    pf = gw / gl if gl > 0 else None
    aw = gw / w if w else 0
    al = gl / (n - w) if (n - w) else 0
    wl = aw / abs(al) if al and al else None
    print(f"{th:>6} {n:>5} {round(w/n,2):>6} {round(pf,2) if pf else '---':>6} "
          f"{round(wl,2) if wl else '---':>6} {round(gw-gl,1):>8}")

# ============ 4. 部署后（9-01）品种筛选 ============
print(f"\n{'=' * 60}")
print(f"【部署后（9-01）仅 1 笔平仓（FRA40）】")
recent_closes = []
for c in closes:
    ts = c.get('ts', '')
    if ts < '2026-09-01': continue
    f = fills.get(c.get('ticket'))
    if f is None: continue
    p = pnl(c)
    if p is None: continue
    recent_closes.append((f.get('symbol'), p, f.get('adx'), f.get('strategy')))

if recent_closes:
    for sym, p, adx, strat in recent_closes:
        print(f"  {sym} {strat} adx={adx:.1f} pnl=${p:.2f}")
else:
    print("  无平仓（V3.3 门槛可能导致无法开新仓）")

print("\n诊断完成")
