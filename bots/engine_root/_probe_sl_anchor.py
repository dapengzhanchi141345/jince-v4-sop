"""只读探针：反推 Godking Apex Short v4.2 的 SL 锚定规则。
不下单、不改单，只读 rates。SL 观测序列：4692.15 -> 4654.00 -> 4647.40 -> 4606.67
"""
import MetaTrader5 as mt5, datetime

EXE = "E:/mt5_friend_observer/terminal64.exe"
SL_NOW = 4606.67
SL_HIST = [(  "22:02(9/1)", 4448.02), ]  # 占位, 主要用 SL_NOW

if not mt5.initialize(path=EXE, timeout=90000):
    print("INIT_FAIL", mt5.last_error()); raise SystemExit
if not mt5.login(60129252, password="Aa141345$", server="TradeMaxGlobal-Demo"):
    print("LOGIN_FAIL", mt5.last_error()); mt5.shutdown(); raise SystemExit

tick = mt5.symbol_info_tick("XAUUSD")
print("BID", tick.bid, "ASK", tick.ask)

TFS = [(mt5.TIMEFRAME_M15, "M15"), (mt5.TIMEFRAME_M30, "M30"),
       (mt5.TIMEFRAME_H1, "H1"), (mt5.TIMEFRAME_H4, "H4"), (mt5.TIMEFRAME_D1, "D1")]

print("\n=== 滚动最高价窗口 vs 当前SL %.2f ===" % SL_NOW)
best = []
for tf, name in TFS:
    r = mt5.copy_rates_from_pos("XAUUSD", tf, 0, 220)
    if r is None or len(r) < 10:
        continue
    for n in (5, 8, 10, 12, 14, 15, 20, 24, 30, 40, 48, 50, 60, 72, 96, 120, 150, 200):
        if n > len(r):
            continue
        hi = max(x['high'] for x in r[-n:])
        diff = SL_NOW - hi
        best.append((abs(diff), name, n, hi, diff))
best.sort()
for a, name, n, hi, diff in best[:12]:
    print(f"  {name:3s} last{n:<4d} high={hi:8.2f}  SL-high={diff:+8.2f}")

print("\n=== ATR 倍数检查 (SL - bid = %.2f) ===" % (SL_NOW - tick.bid))
for tf, name, per in [(mt5.TIMEFRAME_H1, "H1", 14), (mt5.TIMEFRAME_H4, "H4", 14), (mt5.TIMEFRAME_D1, "D1", 14)]:
    r = mt5.copy_rates_from_pos("XAUUSD", tf, 0, per + 6)
    trs = [max(r[i]['high'] - r[i]['low'], abs(r[i]['high'] - r[i-1]['close']), abs(r[i]['low'] - r[i-1]['close'])) for i in range(1, len(r))]
    atr = sum(trs[-per:]) / per
    print(f"  {name} ATR{per}={atr:8.2f}   (SL-bid)/ATR = {(SL_NOW-tick.bid)/atr:5.2f}")

print("\n=== 自首单以来价格路径 (H1) ===")
first_entry = 1788172200
r = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_H1, 0, 300)
seg = [x for x in r if x['time'] >= first_entry]
if seg:
    hh = max(x['high'] for x in seg); ll = min(x['low'] for x in seg)
    hh_t = [x for x in seg if x['high'] == hh][0]['time']
    ll_t = [x for x in seg if x['low'] == ll][0]['time']
    print(f"  bars={len(seg)} 最高={hh:.2f} @ {datetime.datetime.utcfromtimestamp(hh_t)}  最低={ll:.2f} @ {datetime.datetime.utcfromtimestamp(ll_t)}")
    print(f"  SL_NOW - 期间最高 = {SL_NOW-hh:+.2f}   SL_NOW - 期间最低 = {SL_NOW-ll:+.2f}")
    # 最近 N 根 H1 高点序列, 看 SL 台阶
    print("  最近12根H1 (time / high / low / close):")
    for x in seg[-12:]:
        print("   ", datetime.datetime.utcfromtimestamp(x['time']), f"{x['high']:.2f} {x['low']:.2f} {x['close']:.2f}")
mt5.shutdown()
