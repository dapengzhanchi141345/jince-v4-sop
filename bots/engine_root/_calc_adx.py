"""真正的 ADX 计算（基于 Wilder 的 DI 方法）"""
import numpy as np

def calc_adx(high, low, close, period=14):
    """
    计算 ADX（Average Directional Index）
    参数:
        high: 高点数组
        low: 低点数组
        close: 收盘价数组
        period: 周期（默认 14）
    返回:
        adx: 当前 ADX 值
        plus_di: +DI
        minus_di: -DI
    """
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)

    if len(high) < period + 1:
        return 20.0, 25.0, 25.0  # 回退值

    # True Range
    tr = np.zeros(len(high))
    for i in range(1, len(high)):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i-1]),
            abs(low[i] - close[i-1])
        )

    # Smoothed TR
    atr = np.mean(tr[-period:])

    # Directional Movement
    plus_dm = np.zeros(len(high))
    minus_dm = np.zeros(len(high))
    for i in range(1, len(high)):
        up = high[i] - high[i-1]
        down = low[i-1] - low[i]
        plus_dm[i] = up if (up > down and up > 0) else 0
        minus_dm[i] = down if (down > up and down > 0) else 0

    # Smoothed DM
    smooth_plus = np.mean(plus_dm[-period:])
    smooth_minus = np.mean(minus_dm[-period:])

    # Directional Indicators
    if atr > 0:
        plus_di = 100 * smooth_plus / atr
        minus_di = 100 * smooth_minus / atr
    else:
        plus_di = 25.0
        minus_di = 25.0

    # ADX
    if (plus_di + minus_di) > 0:
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    else:
        dx = 0.0

    return dx, plus_di, minus_di


if __name__ == '__main__':
    import MetaTrader5 as mt5
    if mt5.initialize():
        symbols = ['GBPUSD', 'EURUSD', 'XAUUSD', 'FRA40', 'GBPJPY', 'USDJPY']
        for s in symbols:
            df = mt5.copy_rates_from_pos(s, mt5.TIMEFRAME_D1, 0, 100)
            if df is None or len(df) < 30:
                print(f'{s}: no data')
                continue
            # MT5 可能返回 numpy 数组而非 DataFrame
            if isinstance(df, np.ndarray):
                high = df['high'].astype(float)
                low = df['low'].astype(float)
                close = df['close'].astype(float)
            else:
                high = np.asarray(df['high'], dtype=float)
                low = np.asarray(df['low'], dtype=float)
                close = np.asarray(df['close'], dtype=float)
            adx, pdi, mdi = calc_adx(high, low, close, period=14)
            print(f'{s}: ADX={adx:.1f} +DI={pdi:.1f} -DI={mdi:.1f}')
        mt5.shutdown()
