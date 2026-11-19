# Exness 233144570 深度统计
import json, datetime, collections

deals = json.load(open(r"E:\GoldstrategyEngine\data\exness_233144570_deals.json", encoding="utf-8"))

def num(s):
    if not s: return 0.0
    s = s.replace(' ','').replace(',','')
    neg = s.startswith('-') or s.startswith('(')
    s = s.lstrip('-(').rstrip(')')
    try: v = float(s)
    except: return 0.0
    return -v if neg else v

def dt(s):
    return datetime.datetime.strptime(s, "%Y.%m.%d %H:%M:%S")

# ---------- 1. 资金流 ----------
dep = wd = 0.0
dep_n = wd_n = 0
money = []
for d in deals:
    if d['type'] == 'balance' and d['comment']:
        c = d['comment']
        amt = abs(d['profit'])
        if c.startswith('D-'):
            dep += amt; dep_n += 1; money.append((d['time'], '入金', amt))
        elif c.startswith('W-'):
            wd += amt; wd_n += 1; money.append((d['time'], '出金', amt))
print(f"入金 {dep_n} 笔 合计 ${dep:.2f} | 出金 {wd_n} 笔 合计 ${wd:.2f}")
for m in money: print(' ', m[0], m[1], m[2])

# ---------- 2. 平仓单（trend=out 且 profit!=0 或 symbol 非空） ----------
closed = [d for d in deals if d['trend'] == 'out' and d['symbol'] and abs(d['profit']) > 0.001]
# 有的 out 单 profit=0（比如平0手？），另统计
outs_zero = [d for d in deals if d['trend'] == 'out' and d['symbol'] and abs(d['profit']) < 0.001]
wins = [d for d in closed if d['profit'] > 0]
losses = [d for d in closed if d['profit'] < 0]
wsum = sum(d['profit'] for d in wins); lsum = sum(d['profit'] for d in losses)
avgw = wsum/len(wins) if wins else 0; avgl = lsum/len(losses) if losses else 0
print(f"\n平仓成交 {len(closed)} 笔(赢 {len(wins)} 亏 {len(losses)} 零 {len(outs_zero)})")
print(f"胜率 {len(wins)/len(closed)*100:.1f}% | 赢单均 ${avgw:.2f} 亏单均 ${avgl:.2f} | 盈亏比 {abs(avgl/avgw) if avgw else 0:.2f}")
print(f"总盈利 ${wsum:.2f} 总亏损 ${lsum:.2f} 净 ${wsum+lsum:.2f}")
# 连亏
max_streak = cur = 0
for d in closed:
    cur = cur+1 if d['profit'] < 0 else 0
    max_streak = max(max_streak, cur)
print("最大连亏笔数:", max_streak)
# 最大单笔亏 / 赢
worst = min(closed, key=lambda d: d['profit']); best = max(closed, key=lambda d: d['profit'])
print("最大单笔亏:", worst['profit'], worst['time'], worst['symbol'], worst['volume'])
print("最大单笔赢:", best['profit'], best['time'], best['symbol'], best['volume'])
# 品种分布
sym = collections.Counter(d['symbol'] for d in closed)
print("品种分布:", dict(sym))
# 开仓时间范围
t0 = min(dt(d['time']) for d in closed); t1 = max(dt(d['time']) for d in closed)
print("平仓期:", t0, '→', t1, f" 共 {(t1-t0).days} 天")

# 按周分组盈亏
weekly = collections.defaultdict(float)
for d in closed:
    w = dt(d['time']).isocalendar()
    weekly[w[0]] += d['profit']
print("按周盈亏:", {f"W{k}": round(v,2) for k,v in sorted(weekly.items())})

# ---------- 3. 手续费/库存费 ----------
com = sum(d['commission'] for d in deals if d['type'] in ('buy','sell'))
fee = sum(d['fees'] for d in deals if d['type'] in ('buy','sell'))
sw = sum(d['swap'] for d in deals if d['type'] in ('buy','sell'))
print(f"\n手续费 ${com:.2f} 平台费 ${fee:.2f} 库存费 ${sw:.2f}")

# ---------- 4. 持仓开单行为：开仓方向分布、同方向堆叠 ----------
ins = [d for d in deals if d['trend'] == 'in' and d['symbol']]
buyin = [d for d in ins if d['type'] == 'buy']; sellin = [d for d in ins if d['type'] == 'sell']
print(f"\n开仓: 买单 {len(buyin)} 张 {sum(d['volume'] for d in buyin):.2f}手 | 卖单 {len(sellin)} 张 {sum(d['volume'] for d in sellin):.2f}手")
# 加仓检测：同一品种 10 分钟内同向开多单 = 加仓/堆叠
import collections
clusters = collections.defaultdict(list)
for d in ins:
    clusters[(d['symbol'], d['type'])].append(d)
stack_cnt = 0
for k, lst in clusters.items():
    lst.sort(key=lambda d: d['time'])
    for i in range(1, len(lst)):
        if (dt(lst[i]['time']) - dt(lst[i-1]['time'])).total_seconds() < 600:
            stack_cnt += 1
print("10分钟内同向二次开仓次数(堆叠):", stack_cnt)

# ---------- 5. 余额轨迹：用每条成交的 balance 建 equity curve, 算回撤 ----------
curve = [(dt(d['time']), d['balance']) for d in deals if d['balance']]
peak = -1e9; maxdd = 0; maxdd_pct = 0
base_invested = 1000
for t, b in curve:
    peak = max(peak, b)
    if peak > 0:
        dd = b - peak
        if dd < maxdd: maxdd = dd
        maxdd_pct = min(maxdd_pct, dd/peak)
print(f"\n余额轨迹峰值: ${peak:.2f} 最大回撤: ${maxdd:.2f} ({maxdd_pct*100:.1f}%)")
print(f"最终余额: ${curve[-1][1]:.2f}  累计入金 ${dep:.2f}  累计出金 ${wd:.2f}  净留存 ${dep-wd:.2f}")
# 最终净值对比
print("最后一笔成交余额:", curve[-1][1], curve[-1][0])
