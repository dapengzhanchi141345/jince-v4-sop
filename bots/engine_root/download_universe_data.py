# download_universe_data.py — 从 MT5 批量下载全宇宙可交易品种历史数据
"""
把 symbol_universe.UNIVERSE 中, 券商 MT5 实际提供的品种, 下载 H1/H4/D1 CSV 到 data/,
供 universe_backtest.py 离线回测 (覆盖全指数/外汇/加密/金属)。

用法:
    python download_universe_data.py           # 仅下载缺失的
    python download_universe_data.py --force    # 覆盖重下
依赖: 本机运行 MT5 终端 + 已装 MetaTrader5 + 已登录。
"""
import sys, os
from datetime import datetime
import pandas as pd
import symbol_universe as su

try:
    import MetaTrader5 as mt5
except Exception as e:
    print("未安装 MetaTrader5:", e); sys.exit(1)

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
os.makedirs(DATA_DIR, exist_ok=True)
TF = {'M15': 15, 'H1': 16385, 'H4': 16388, 'D1': 16408}

# 宇宙名 -> MT5 实际名 的别名表 (按券商调整)
ALIAS = {
    'SPX500': 'US500', 'DE30': 'GER40', 'JP225': 'JPN225', 'CHN50': 'CHI50',
    'TWN25': 'TWN', 'KOSPI200': 'KOSPI', 'SING30': 'SGP', 'CAN60': 'SPT',
    'BRA50': 'BRL', 'MEX35': 'MEX', 'IND50': 'IND', 'EU50': 'STOXX50',
    'ITA40': 'ITA40', 'ESP35': 'ESP35', 'NED25': 'NED25', 'SWI20': 'SWI20',
    'POR20': 'POR20', 'BEL20': 'BEL20', 'POL20': 'POL20', 'HUN30': 'BUX',
    'USDX': 'USDX', 'ORANGEJUICE': 'OJ', 'US10Y': 'US10YT', 'US05Y': 'US05YT',
    'US02Y': 'US02YT', 'DE10Y': 'DE10YT', 'UK10Y': 'GB10YT', 'JP10Y': 'JP10YT',
}

def resolve(u, alls):
    if u in alls:
        return u
    if (u + '.c') in alls:
        return u + '.c'
    if (u + '.r') in alls:
        return u + '.r'
    a = ALIAS.get(u)
    if a and a in alls:
        return a
    if a and (a + '.c') in alls:
        return a + '.c'
    return None

def main():
    force = '--force' in sys.argv
    if not mt5.initialize():
        print("MT5 初始化失败 (终端未运行/未登录):", mt5.last_error()); sys.exit(1)
    alls = set(s.name for s in mt5.symbols_get())
    start = int(datetime(2023, 1, 1).timestamp())
    end = int(datetime.now().timestamp())
    done = 0; skipped = 0; nomt5 = 0
    for u in su.UNIVERSE:
        m = resolve(u, alls)
        if not m:
            nomt5 += 1
            continue
        paths = {tf: os.path.join(DATA_DIR, f"{u}_{tf}.csv") for tf in ('H1', 'H4', 'D1')}
        if not force and all(os.path.exists(p) for p in paths.values()):
            skipped += 1
            continue
        try:
            mt5.symbol_select(m, True)
        except Exception:
            pass
        ok = True
        for tf_name, tf_mt5 in [('H1', TF['H1']), ('H4', TF['H4']), ('D1', TF['D1'])]:
            f = paths[tf_name]
            if (not force) and os.path.exists(f):
                continue
            rates = mt5.copy_rates_range(m, tf_mt5, start, end)
            if rates is None or len(rates) == 0:
                ok = False
                break
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df = df[['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']]
            df.to_csv(f, index=False)
        if ok:
            done += 1
            print(f"  ✓ {u} ({m}) 已下载 H1/H4/D1")
        else:
            print(f"  ✗ {u} ({m}) 无数据")
    mt5.shutdown()
    print(f"\n完成: 新下载 {done} | 已存在跳过 {skipped} | 券商无此品种 {nomt5} | 宇宙共 {len(su.UNIVERSE)}")

if __name__ == "__main__":
    main()
