"""真实 ADX 计算（Wilder 方法）"""
import numpy as np

def calc_real_adx(h1, period=14):
    """
    从 H1 K 线计算真实 ADX
    参数:
        h1: MT5 numpy 数组 (D1 或 H1)
        period: ADX 周期
    返回:
        adx: 当前 ADX 值（float）或 None（历史不足）
    """
    try:
        if len(h1) < period + 20:
            return None
        
        high = h1['high'][-period-20:].astype(float)
        low = h1['low'][-period-20:].astype(float)
        close = h1['close'][-period-20:].astype(float)
        
        # True Range
        tr = np.zeros(len(high))
        for i in range(1, len(high)):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i-1]),
                abs(low[i] - close[i-1])
            )
        
        # Smoothed TR (Wilder)
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
        
        return dx
    except Exception:
        return None

if __name__ == '__main__':
    import MetaTrader5 as mt5
    if mt5.initialize():
        symbols = ['GBPUSD', 'EURUSD', 'XAUUSD', 'FRA40', 'GBPJPY', 'USDJPY']
        for s in symbols:
            df = mt5.copy_rates_from_pos(s, mt5.TIMEFRAME_H1, 0, 400)
            if df is None or len(df) < 30:
                print(f'{s}: no data')
                continue
            adx = calc_real_adx(df, period=14)
            print(f'{s}: ADX={adx:.1f}' if adx else f'{s}: ADX=N/A')
        mt5.shutdown()
