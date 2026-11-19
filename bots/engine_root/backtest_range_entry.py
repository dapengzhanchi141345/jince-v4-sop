"""P1-G 回测器: 验证区间模块 entry buffer 放大后的震荡市表现.

忠实复刻 guardian_executor.build_range_signal 的 entry 逻辑:
  - BB(period=15, std=1.5) on H1 close
  - ebuf 参数化: 原 = RANGE_ENTRY_BUFFER_PIPS(0.2)*pip (XAU=0.002, 比最小跳动0.01小→空集)
  - 本回测扫: ebuf = bb_w * RATIO (带宽比例), RATIO in [0.10,0.15,0.20,0.25]
  - 触发: price in [bb_up-ebuf, bb_up] -> SELL; price in [bb_dn, bb_dn+ebuf] -> BUY
  - 持仓: 未来 N_FUTURE 根, 先触 TP/SL 判盈亏; 未触用 N 根后收盘方向判
  - 仅 ADX < ADX_CEIL(35) 评估 (区间路由触发条件)
  - RR 硬校验 >= 2.0 (守双铁律)
无 RF/缠论/未来函数. 纯 numpy + MT5. 单品种独立进程 (规避历史 sklearn 崩溃, 虽本器不用).
"""
import sys
import argparse
import numpy as np
import MetaTrader5 as mt5
import continuous_evolution as ce

SYMBOLS = ['XAUUSD', 'EURUSD', 'GBPUSD']
TF = mt5.TIMEFRAME_H1
BARS = 3000
PERIOD = 15
STD = 1.5
KC_MULT = 1.5
SL_MULT_PIPS = 0.8          # RANGE_SL_BUFFER_PIPS
RATIOS = [0.10, 0.15, 0.20, 0.25]
N_FUTURE = 20
ADX_CEIL = 35
RR_MIN = 2.0


def get_rates(sym):
    if not mt5.initialize():
        raise RuntimeError("MT5 init failed")
    rates = mt5.copy_rates_from_pos(sym, TF, 0, BARS + PERIOD + N_FUTURE + 10)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"no rates for {sym}")
    close = np.array([r.close for r in rates], dtype=float)
    high = np.array([r.high for r in rates], dtype=float)
    low = np.array([r.low for r in rates], dtype=float)
    return close, high, low


def adx_arr(high, low, close):
    a = ce._adx(high, low, close)
    return a


def bb(close, i):
    w = close[i - PERIOD + 1:i + 1]
    ma = float(np.mean(w))
    sd = float(np.std(w))
    up = ma + STD * sd
    dn = ma - STD * sd
    return ma, up, dn


def first_touch(fh, fl, tp, sl, direction):
    for k in range(len(fh)):
        if direction == -1:
            if fl[k] <= tp:
                return 'TP'
            if fh[k] >= sl:
                return 'SL'
        else:
            if fh[k] >= tp:
                return 'TP'
            if fl[k] <= sl:
                return 'SL'
    return 'NONE'


def simulate(sym, ratio):
    close, high, low = get_rates(sym)
    a = adx_arr(high, low, close)
    n = len(close)
    pip = ce.SYMBOL_CONFIG[sym]['pip']
    slbuf = SL_MULT_PIPS * pip
    wins = losses = 0
    trades = 0
    pf_num = pf_den = 0.0
    for i in range(PERIOD + 5, n - N_FUTURE):
        if np.isnan(a[i]) or a[i] >= ADX_CEIL:
            continue
        ma, up, dn = bb(close, i)
        bb_w = up - dn
        if bb_w <= 0:
            continue
        ebuf = bb_w * ratio
        price = close[i]
        if up - ebuf <= price <= up:
            direction = -1
        elif dn <= price <= dn + ebuf:
            direction = 1
        else:
            continue
        mid = (up + dn) / 2.0
        if direction == -1:
            sl = up + slbuf
            tp = price - max((sl - price) * RR_MIN, price - mid)
        else:
            sl = dn - slbuf
            tp = price + max((price - sl) * RR_MIN, mid - price)
        sl_pts = abs(sl - price)
        tp_pts = abs(tp - price)
        if tp_pts / sl_pts < RR_MIN - 1e-6:
            continue
        # 未来 N 根判定
        fh = high[i + 1:i + 1 + N_FUTURE]
        fl = low[i + 1:i + 1 + N_FUTURE]
        res = first_touch(fh, fl, tp, sl, direction)
        if res == 'TP':
            win = True
        elif res == 'SL':
            win = False
        else:
            # 未触: 用 N 根后收盘相对 entry 方向
            close_n = close[i + N_FUTURE]
            if direction == -1:
                win = close_n < price
            else:
                win = close_n > price
        trades += 1
        if win:
            wins += 1
            pf_num += tp_pts
            pf_den += sl_pts
        else:
            losses += 1
            pf_num += sl_pts
            pf_den += tp_pts
    wr = wins / trades if trades else 0.0
    pf = (pf_num / pf_den) if pf_den > 0 else 0.0
    return trades, wr, pf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--symbol', default=None, help='single symbol (else all)')
    args = ap.parse_args()
    syms = [args.symbol] if args.symbol else SYMBOLS
    print(f"=== P1-G range entry backtest (TF=H1 BARS={BARS} ADX<{ADX_CEIL}) ===")
    for sym in syms:
        print(f"\n--- {sym} ---")
        for r in RATIOS:
            try:
                t, wr, pf = simulate(sym, r)
                tag = "OK" if (pf >= 1.0 and t >= 30) else "WEAK"
                print(f"  ratio={r:.2f}  trades={t:4d}  WR={wr*100:5.1f}%  PF={pf:.3f}  [{tag}]")
            except Exception as e:
                print(f"  ratio={r:.2f}  ERROR: {e}")


if __name__ == '__main__':
    main()
