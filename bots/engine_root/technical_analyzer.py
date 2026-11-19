"""
通用行情分析报告引擎 v2.0 — Trading Central Daily+Weekly 双框架版
自动生成 TC 风格 Technical Summary（日线+周线双时间框架）
支持: XAUUSD, BTCUSD, ETHUSD, EURUSD, GBPUSD, USDJPY, GBPJPY, AUDUSD, NZDUSD
v2.0 新增: W1周线分析 / D&W矛盾检测 / TC四级关键位系统 / 趋势线算法
"""
import sys, os, json, warnings
import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict
warnings.filterwarnings('ignore')

import MetaTrader5 as mt5

# ═══ 深度学习优化器 (盘感神经网络, 可选加载) ═══
def _safe_probe_dl():
    """在子进程中探测 deep_learning_optimizer 是否可安全导入。
    该模块导入阶段可能触发段错误(segfault), 而 Python 的 try/except 无法捕获段错误。
    用子进程隔离: 若子进程异常退出(含段错误), 主引擎永不导入该模块, 保证『只分析、不崩溃』。"""
    import subprocess
    _probe = ("from deep_learning_optimizer import DLOptimizer, _enc_bias, MODEL_PATH; "
              "print('DL_OK', MODEL_PATH)")
    try:
        _r = subprocess.run([sys.executable, "-c", _probe],
                            capture_output=True, text=True, timeout=30)
        return _r.returncode == 0 and "DL_OK" in _r.stdout
    except Exception:
        return False

HAS_DL = _safe_probe_dl()
if HAS_DL:
    try:
        from deep_learning_optimizer import DLOptimizer, _enc_bias, MODEL_PATH
    except Exception as _e:
        DLOptimizer = None
        _enc_bias = None
        HAS_DL = False
        print(f"  [提示] 深度学习模块导入失败: {_e}")
else:
    DLOptimizer = None
    _enc_bias = None
    print("  [提示] 深度学习模块不可用(导入会段错误/缺失), 已安全跳过。")

# ═══ 初始化 ═══
if not mt5.initialize():
    # MT5 终端未运行 / 初始化失败 → 按指令记录错误后直接结束，不重试、不等待、不轮询
    print("✗ MT5 初始化失败：终端未运行或无法连接。按指令结束，不重试/不等待/不轮询。")
    sys.exit(1)
mt5.login(60043976, password="", server="TradeMaxGlobal-Demo")

BASE = r"E:\GoldstrategyEngine"
sys.path.insert(0, BASE)
DATA_DIR = os.path.join(BASE, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ═══ 品种列表 ═══
SYMBOLS = {
    "XAUUSD":   {"name":"黄金 (Gold)",     "type":"Metals",    "digits":2, "lot_step":0.01},
    "BTCUSD":   {"name":"比特币 (Bitcoin)", "type":"Crypto",    "digits":0, "lot_step":0.01},
    "ETHUSD":   {"name":"以太坊 (Ethereum)", "type":"Crypto",    "digits":0, "lot_step":0.05},
    "EURUSD":   {"name":"欧元 (Euro)",     "type":"Forex",     "digits":5, "lot_step":0.01},
    "GBPUSD":   {"name":"英镑 (Pound)",    "type":"Forex",     "digits":5, "lot_step":0.01},
    "USDJPY":   {"name":"美元/日元 (USD/JPY)", "type":"Forex", "digits":3, "lot_step":0.01},
    "GBPJPY":   {"name":"英镑/日元 (GBP/JPY)", "type":"Forex", "digits":3, "lot_step":0.01},
    "AUDUSD":   {"name":"澳元 (AUD)",      "type":"Forex",     "digits":5, "lot_step":0.01},
}

# ═══ 原始数据质量清洗 (MT5 拉取后第一道防线) ═══
def _clean_ohlc(df):
    """清洗 MT5 原始 OHLC:
       - 非数值 / 0 / 负值 → 视为缺失 → 前向填充(再后向补)
       - high < low 异常 → 用 low 修正
       目的: 防止异常 bar 导致 EMA / ATR / MACD 整链 NaN (报告出现 +nan 的根因)
    """
    df = df.copy()
    for col in ('open', 'high', 'low', 'close'):
        df[col] = pd.to_numeric(df[col], errors='coerce')
        df[col] = df[col].mask(df[col] <= 0)
        df[col] = df[col].ffill().bfill()
    bad = df['high'] < df['low']
    if bad.any():
        df.loc[bad, 'high'] = df.loc[bad, 'low']
    return df

# ═══ 指标计算 ═══
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
    g = np.where(d>0, d, 0); l = np.where(d<0, -d, 0)
    ag = pd.Series(g).ewm(span=p).mean().values
    al = pd.Series(l).ewm(span=p).mean().values
    rs = ag/(al+1e-10)
    return 100 - 100/(1+rs)

def bollinger(c, p=20, k=2):
    mid = pd.Series(c).rolling(p).mean().values
    std = pd.Series(c).rolling(p).std().values
    return mid - k*std, mid, mid + k*std

def macd(c, fast=12, slow=26, signal=9):
    ef = ema(c, fast); es = ema(c, slow)
    line = ef - es
    sig = ema(line, signal)
    hist = line - sig
    return line, sig, hist

def adx_calc(h, l, c, p=14):
    tr = np.maximum(h[1:]-l[1:], np.maximum(abs(h[1:]-c[:-1]), abs(l[1:]-c[:-1])))
    u = h[1:]-h[:-1]; d = l[:-1]-l[1:]
    pdi = 100*pd.Series(np.where((u>d)&(u>0),u,0)).ewm(span=p).mean()/(pd.Series(tr).ewm(span=p).mean()+1e-10)
    mdi = 100*pd.Series(np.where((d>u)&(d>0),d,0)).ewm(span=p).mean()/(pd.Series(tr).ewm(span=p).mean()+1e-10)
    dx = 100*np.abs(pdi-mdi)/(pdi+mdi+1e-10)
    result = pd.Series(dx).ewm(span=p).mean().values
    return np.concatenate([np.zeros(len(c)-len(result)), result]), pdi.values, mdi.values

# ═══ 支撑阻力位 ═══
def pivot_points(h, l, c):
    """经典pivot点"""
    ph = max(h[-5:]) if len(h)>=5 else h[-1]
    pl = min(l[-5:]) if len(l)>=5 else l[-1]
    pc = c[-1]
    pp = (ph+pl+pc)/3
    r1 = 2*pp-pl; s1 = 2*pp-ph
    r2 = pp+(ph-pl); s2 = pp-(ph-pl)
    r3 = ph+2*(pp-pl); s3 = pl-2*(ph-pl)
    return {'PP':pp,'R1':r1,'S1':s1,'R2':r2,'S2':s2,'R3':r3,'S3':s3,
            'HL':ph,'LL':pl,'Range':ph-pl}

def recent_swings(c, h, l, window=5):
    """近期高低点"""
    swings = []
    for i in range(window, len(c)-window):
        if h[i] == max(h[i-window:i+window+1]):
            swings.append(('Resistance', i, h[i]))
        if l[i] == min(l[i-window:i+window+1]):
            swings.append(('Support', i, l[i]))
    # 最近的5个显著位
    swings = sorted(swings, key=lambda x: abs(len(c)-x[1]))[:10]
    return swings

# ═══ 趋势判断 ═══
def trend_analysis(h1, h4, d1):
    """多时间框架趋势分析"""
    c1 = h1['close'].values; h_h1 = h1['high'].values; l_h1 = h1['low'].values
    
    e9 = ema(c1, 9); e21 = ema(c1, 21); e50 = ema(c1, 50)
    ma20 = pd.Series(c1).rolling(20).mean().values
    
    # H1趋势
    price = float(c1[-1])
    h1_e9 = float(e9[-1]); h1_e21 = float(e21[-1]); h1_e50 = float(e50[-1])
    h1_ma20_val = float(ma20[-1])
    h1_direction = 'UP' if price > h1_e9 and h1_e9 > h1_e21 else ('DOWN' if price < h1_e9 and h1_e9 < h1_e21 else 'SIDEWAYS')
    h1_ma20 = 'ABOVE' if price > h1_ma20_val else 'BELOW'
    
    # H4趋势
    h4c = h4['close'].values
    h4_e21 = ema(h4c, 21); h4_e50 = ema(h4c, 50)
    h4_price = float(h4c[-1]); h4_e21_val = float(h4_e21[-1]); h4_e50_val = float(h4_e50[-1])
    h4_direction = 'UP' if h4_price > h4_e21_val > h4_e50_val else ('DOWN' if h4_price < h4_e21_val < h4_e50_val else 'SIDEWAYS')
    
    # D1趋势
    d1c = d1['close'].values
    d1_e21 = ema(d1c, 21); d1_e50 = ema(d1c, 50)
    d1_price = float(d1c[-1]); d1_e21_val = float(d1_e21[-1]); d1_e50_val = float(d1_e50[-1])
    d1_direction = 'UP' if d1_price > d1_e21_val > d1_e50_val else ('DOWN' if d1_price < d1_e21_val < d1_e50_val else 'SIDEWAYS')
    
    # 综合趋势
    votes = {'UP':0, 'DOWN':0}
    if h1_direction == 'UP': votes['UP'] += 1
    elif h1_direction == 'DOWN': votes['DOWN'] += 1
    if h4_direction == 'UP': votes['UP'] += 2  # 权重更高
    elif h4_direction == 'DOWN': votes['DOWN'] += 2
    if d1_direction == 'UP': votes['UP'] += 3  # 最高权重
    elif d1_direction == 'DOWN': votes['DOWN'] += 3
    
    total_vote = votes['UP'] + votes['DOWN']
    if total_vote == 0:
        # H1/H4/D1 三周期均为 SIDEWAYS → 无多空投票, 避免除零; 判为中性
        overall = 'SIDEWAYS'
    else:
        overall = 'STRONGLY_BULLISH' if votes['UP']/total_vote > 0.75 else \
                  ('BULLISH' if votes['UP'] > votes['DOWN'] else \
                   ('STRONGLY_BEARISH' if votes['DOWN']/total_vote > 0.75 else 'BEARISH'))
    
    return {
        'h1': h1_direction, 'h4': h4_direction, 'd1': d1_direction,
        'overall': overall, 'votes_up': votes['UP'], 'votes_down': votes['DOWN'],
        'e9': float(e9[-1]), 'e21': float(e21[-1]), 'e50': float(e50[-1]), 'ma20': float(ma20[-1])
    }

# ═══ 周线趋势分析 ═══
def weekly_trend_analysis(w1):
    """周线级别趋势判断(Trading Central Weekly Chart 方法论)"""
    wc = w1['close'].values
    w_h = w1['high'].values; w_l = w1['low'].values
    
    we21 = ema(wc, 21); we50 = ema(wc, 50)
    w_price = float(wc[-1])
    we21v = float(we21[-1]); we50v = float(we50[-1])
    
    # 周线MA排列
    if w_price > we21v > we50v:
        w_dir = 'BULLISH'
        w_strength = 'Strongly Bullish' if (w_price - we50v) / we50v > 0.05 else 'Bullish'
    elif w_price < we21v < we50v:
        w_dir = 'BEARISH'
        w_strength = 'Strongly Bearish' if (we50v - w_price) / we50v > 0.05 else 'Bearish'
    else:
        w_dir = 'SIDEWAYS'
        w_strength = 'Neutral'
    
    # 周线RSI
    w_rsi = rsi(wc)
    wrsi_val = float(w_rsi[-1])
    
    # 周线关键位(更宽的swing window)
    w_swings = recent_swings(wc, w_h, w_l, window=3)
    w_resistance = sorted([s[2] for s in w_swings if s[0]=='Resistance' and s[2] > w_price], reverse=True)[:3]
    w_support = sorted([s[2] for s in w_swings if s[0]=='Support' and s[2] < w_price])[:3]
    
    # 周线Pivot
    wp = pivot_points(w_h, w_l, wc)
    
    return {
        'direction': w_dir, 'strength': w_strength,
        'price': round(w_price, 2),
        'ema21': round(we21v, 5), 'ema50': round(we50v, 5),
        'rsi': round(wrsi_val, 1),
        'resistance': w_resistance, 'support': w_support,
        'pivot': round(wp['PP'], 5),
    }

# ═══ D/W 双框架矛盾检测 ═══
def detect_dw_conflict(daily_dir, weekly_dir):
    """判断日线和周线方向是否一致 — TC方法论核心过滤器"""
    d = daily_dir.upper(); w = weekly_dir.upper()
    bull = ('BULLISH', 'STRONGLY_BULLISH')
    bear = ('BEARISH', 'STRONGLY_BEARISH')
    
    d_bull = d in bull; d_bear = d in bear
    w_bull = w in bull; w_bear = w in bear
    
    if d_bull and w_bull:
        return "AGREE_BULLISH", "日周双重看多 → 高确信度做多信号", 1.0
    elif d_bear and w_bear:
        return "AGREE_BEARISH", "日周双重看空 → 高确信度做空信号", 1.0
    elif d_bull and w_bear:
        return "CONFLICT_D_VS_W", "日线多但周线空 → 日线反弹是周线下跌途中的回调，不追多", 0.3
    elif d_bear and w_bull:
        return "CONFLICT_D_VS_W", "日线空但周线多 → 日线下跌是周线上涨途中的回调，不追空", 0.3
    else:
        return "NEUTRAL", "一方或双方为震荡，方向不明确", 0.5

# ═══ TC 四级关键位系统 ═══
def tc_key_levels(price, pivots, swings, adx, trend_dir):
    """仿 Trading Central 四级关键位: 🔴红阻/🔵蓝转/⚫黑参/🟢绿支"""
    # 从swing中分离阻力/支撑
    res_all = sorted([s[2] for s in swings if s[0] == 'Resistance'], reverse=True)
    sup_all = sorted([s[2] for s in swings if s[0] == 'Support'])
    
    is_bull = trend_dir.upper() in ('BULLISH', 'STRONGLY_BULLISH')
    
    # 红色强阻力(最远上方2个)
    red_res = [r for r in res_all if r > price][:2]
    if not red_res:
        red_res = [round(pivots['R2'], 4), round(pivots['R1'], 4)]
    
    # 蓝色转折位(最近价格的一个)
    blue_pivot = price
    if res_all:
        nearest_res = min(res_all, key=lambda x: abs(x - price))
        if abs(nearest_res - price) / price < 0.01:
            blue_pivot = nearest_res
    elif sup_all:
        nearest_sup = min(sup_all, key=lambda x: abs(x - price))
        if abs(nearest_sup - price) / price < 0.01:
            blue_pivot = nearest_sup
    
    # 黑色参考位(Pivot Point)
    black_ref = pivots['PP']
    
    # 绿色强支撑(最远下方2个) — 如果看多是目标位，如果看空是止损参考
    green_sup = [s for s in sup_all if s < price][-2:]
    if not green_sup:
        # 价格跌破所有近期摆动低点(如黄金创新低)时过滤结果为空 → 回退到 pivot 支撑位, 避免 support_green 为空
        green_sup = [round(pivots['S1'], 4), round(pivots['S2'], 4)]
    
    # 目标位(TC惯例：绿的最远端=目标)
    target = green_sup[-1] if green_sup else (pivots['S3'] if is_bull else pivots['R3'])
    
    return {
        'resistance_strong_red': [round(r, 4) for r in red_res],
        'pivot_blue': round(blue_pivot, 4),
        'reference_black': round(black_ref, 4),
        'support_green': [round(s, 4) for s in green_sup],
        'target': round(target, 4),
    }

# ═══ 生成技术分析摘要 ═══
def generate_technical_summary(symbol, sym_cfg):
    """为单个品种生成 Trading Central 风格的 Technical Summary"""
    
    # 下载数据(每次都拉最新K线, 保证每小时重算有效, 不依赖缓存CSV)
    tf_map = {"H1": 16385, "H4": 16388, "D1": 16408, "W1": 32769}
    bars   = {"H1": 400,   "H4": 400,   "D1": 300,  "W1": 120}  # 周线120根≈2年+
    frames = {}
    for tf_name, tf_mt5 in tf_map.items():
        rates = mt5.copy_rates_from_pos(symbol, tf_mt5, 0, bars[tf_name])
        if rates is None or len(rates) == 0:
            if tf_name == "W1":
                # 周线某些品种可能不可用(如加密货币在部分broker无周线), 跳过不中断
                continue
            raise RuntimeError(f"MT5 数据获取失败: {symbol} {tf_name}")
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = _clean_ohlc(df)          # ⚠ 数据清洗: 异常 bar → 指标 NaN 防线
        frames[tf_name] = df
    h1 = frames["H1"]; h4 = frames["H4"]; d1 = frames["D1"]
    w1 = frames.get("W1")  # 周线可能为None
    
    hc = h1['close'].values; hh = h1['high'].values; hl = h1['low'].values
    price = hc[-1]
    digits = sym_cfg['digits']
    
    # 计算指标
    e9 = ema(hc, 9); e21 = ema(hc, 21); e50 = ema(hc, 50)
    ma20 = pd.Series(hc).rolling(20).mean().values
    atr_val = atr_vals(hh, hl, hc)
    rsi_val = rsi(hc)
    bb_lower, bb_mid, bb_upper = bollinger(hc)
    macd_line, macd_sig, macd_hist = macd(hc)
    adx_val, pdi_val, mdi_val = adx_calc(hh, hl, hc)
    pp = pivot_points(hh, hl, hc)
    trend = trend_analysis(h1, h4, d1)
    swings = recent_swings(hc, hh, hl)
    
    # ── v2.0: 周线分析 + D/W双框架 ──
    weekly = None; dw_status = None; dw_note = None; dw_confidence = 0.5
    if w1 is not None and len(w1) > 20:
        weekly = weekly_trend_analysis(w1)
        dw_status, dw_note, dw_confidence = detect_dw_conflict(trend['overall'], weekly['direction'])
    
    # TC 四级关键位
    tc_levels = tc_key_levels(price, pp, swings, float(adx_val[-1]), trend['overall'])
    
    # 当前值
    price = float(hc[-1])
    cur_rsi = float(rsi_val[-1])
    cur_adx = float(adx_val[-1])
    cur_macd = float(np.nan_to_num(macd_line[-1]))
    _mh_last = macd_hist[-1] if len(macd_hist) >= 1 else 0.0
    _mh_5 = macd_hist[-5] if len(macd_hist) > 5 else _mh_last
    cur_macd_hist_last = float(np.nan_to_num(_mh_last))
    cur_macd_hist_5 = float(np.nan_to_num(_mh_5))
    cur_bb_pos = float((price - bb_lower[-1]) / (bb_upper[-1] - bb_lower[-1] + 1e-10))
    
    digits = sym_cfg['digits']
    e9v = float(e9[-1]); e21v = float(e21[-1]); e50v = float(e50[-1]); ma20v = float(ma20[-1])
    
    # ═══ 判断 ═══
    
    # 1. 趋势
    if trend['overall'] in ('STRONGLY_BULLISH', 'BULLISH'):
        bias = "BULLISH"
        bias_strength = "Strongly Bullish" if trend['overall'] == 'STRONGLY_BULLISH' else "Bullish"
    elif trend['overall'] in ('STRONGLY_BEARISH', 'BEARISH'):
        bias = "BEARISH"
        bias_strength = "Strongly Bearish" if trend['overall'] == 'STRONGLY_BEARISH' else "Bearish"
    else:
        bias = "SIDEWAYS"
        bias_strength = "Neutral"
    
    # 2. 动能
    momentum = 'NEUTRAL'
    if cur_rsi > 65: momentum = 'OVERBOUGHT'
    elif cur_rsi > 55: momentum = 'BULLISH_MOMENTUM'
    elif cur_rsi < 35: momentum = 'OVERSOLD'
    elif cur_rsi < 45: momentum = 'BEARISH_MOMENTUM'
    
    # 3. 波动率
    volatility = 'NORMAL'
    if cur_adx > 40: volatility = 'VERY_HIGH'
    elif cur_adx > 25: volatility = 'HIGH'
    elif cur_adx < 15: volatility = 'LOW'
    
    # 4. 布林带位置
    bb_position = 'MIDDLE'
    if cur_bb_pos > 0.8: bb_position = 'NEAR_UPPER'
    elif cur_bb_pos > 0.6: bb_position = 'UPPER_HALF'
    elif cur_bb_pos > 0.4: bb_position = 'MIDDLE'
    elif cur_bb_pos > 0.2: bb_position = 'LOWER_HALF'
    else: bb_position = 'NEAR_LOWER'
    
    # 5. MACD
    macd_signal = 'NEUTRAL'
    if cur_macd > 0 and cur_macd_hist_last > cur_macd_hist_5: macd_signal = 'BULLISH_CROSS'
    elif cur_macd < 0 and cur_macd_hist_last < cur_macd_hist_5: macd_signal = 'BEARISH_CROSS'
    elif cur_macd > 0: macd_signal = 'BULLISH_DIVERGENCE'
    elif cur_macd < 0: macd_signal = 'BEARISH_DIVERGENCE'
    
    # 6. 关键价位
    support_levels = sorted([pp['S1'], pp['S2'], pp['S3']], reverse=True)[:3]
    resistance_levels = sorted([pp['R1'], pp['R2'], pp['R3']])[:3]
    
    # 加入近期swing点
    for stype, idx, val in swings:
        if stype == 'Support' and val < price:
            if val not in support_levels: support_levels.append(val)
            support_levels = sorted(set(support_levels), reverse=True)[:3]
        elif stype == 'Resistance' and val > price:
            if val not in resistance_levels: resistance_levels.append(val)
            resistance_levels = sorted(set(resistance_levels))[:3]
    
    # 7. 综合评分 (-10到+10)
    score = 0
    if bias == 'BULLISH': score += 2
    elif bias == 'BEARISH': score -= 2
    if momentum in ('OVERBOUGHT'): score -= 1
    elif momentum in ('OVERSOLD'): score += 1
    elif momentum == 'BULLISH_MOMENTUM': score += 1
    elif momentum == 'BEARISH_MOMENTUM': score -= 1
    if macd_signal in ('BULLISH_CROSS', 'BULLISH_DIVERGENCE'): score += 1
    elif macd_signal in ('BEARISH_CROSS', 'BEARISH_DIVERGENCE'): score -= 1
    if bb_position == 'NEAR_LOWER': score += 0.5
    elif bb_position == 'NEAR_UPPER': score -= 0.5
    
    # 8. 生成结论
    if score >= 4: recommendation = "STRONG BUY"
    elif score >= 2: recommendation = "BUY"
    elif score >= 0.5: recommendation = "NEAR BUY"
    elif score >= -0.5: recommendation = "NEUTRAL"
    elif score >= -2: recommendation = "NEAR SELL"
    elif score >= -4: recommendation = "SELL"
    else: recommendation = "STRONG SELL"
    
    # ═══ 输出报告 ═══
    # 安全显示: 防止关键位列表为空时 'N/A' 被当作浮点格式化导致整段报告崩溃(曾致 XAUUSD/AUDUSD 被静默丢弃)
    _res_red_disp = f"{tc_levels['resistance_strong_red'][0]:,.{digits}f}" if tc_levels['resistance_strong_red'] else "N/A"
    _sup_grn_disp = f"{tc_levels['support_green'][0]:,.{digits}f}" if tc_levels['support_green'] else "N/A"
    now = datetime.now().astimezone()
    now_str = now.strftime("%A, %B %d, %Y %H:%M %Z")
    
    report = f"""
╔══════════════════════════════════════════════════════════════════╗
║               TECHNICAL ANALYSIS REPORT                         ║
║               技术分析每日报告                                    ║
╚══════════════════════════════════════════════════════════════════╝

  Report Date: {now_str}
  Provider: A.T.E. (Autonomous Trading Engine) v2.0-DW
  Data Source: MetaTrader 5 (TradeMaxGlobal-Demo)

{'='*65}
  {sym_cfg['name']} ({symbol})
{'='*65}

  Price:        {price:,.{digits}f}
  Daily Change: {'+' if float(np.diff(hc)[-2]) > 0 else ''}{float(np.diff(hc)[-1]):,.{digits}f} ({float(np.diff(hc)[-1])/float(hc[-2])*100:+.2f}%)

  ─────────────────────────────────────────────────────
  MARKET REGIME ANALYSIS
  ─────────────────────────────────────────────────────

  Trend Bias:        {bias_strength}
  Timeframe Votes:   H1={trend['h1']} | H4={trend['h4']} | D1={trend['d1']}
  Overall Score:     {trend['votes_up']:+} UP / {trend['votes_down']:+} DOWN

  Momentum:          {momentum}
  RSI(14):           {cur_rsi:.1f} {'⟶ OVERSOLD' if cur_rsi < 35 else '⟶ OVERBOUGHT' if cur_rsi > 65 else '⟶ Neutral Zone'}
  ADX(14):           {cur_adx:.1f} {'⟶ Strong Trend' if cur_adx > 25 else '⟶ Weak Trend'}
  Volatility:        {volatility}
  
  Bollinger Position: {bb_position} ({cur_bb_pos*100:.0f}%)
  MACD Signal:       {macd_signal}
  MACD Line:         {cur_macd:+.5f}
  MACD Histogram:    {float(macd_hist[-1]):+.5f}
  
  ─────────────────────────────────────────────────────
  KEY LEVELS (TC 4-Tier System)
  ─────────────────────────────────────────────────────

  🔴 Strong Resistance: {_res_red_disp}
                     {'  ' + str(tc_levels['resistance_strong_red'][1]) if len(tc_levels['resistance_strong_red']) > 1 else ''}
  🔵 Pivot/Current:   {tc_levels['pivot_blue']:,.{digits}f}
  ⚫ Reference:        {tc_levels['reference_black']:,.{digits}f}
  🟢 Strong Support:  {_sup_grn_disp}
                     {'  ' + str(tc_levels['support_green'][1]) if len(tc_levels['support_green']) > 1 else ''}
  🎯 TC Target:       {tc_levels['target']:,.{digits}f}

  ─────────────────────────────────────────────────────
  DUAL TIMEFRAME (D/W) ANALYSIS ★ v2.0
  ─────────────────────────────────────────────────────

  Daily Direction:   {bias_strength} ({trend['overall']})
""" + (f"""
  Weekly Direction:  {weekly['strength']} ({weekly['direction']})
  Weekly RSI(14):     {weekly['rsi']:.1f}
  Weekly Price:      {weekly['price']:,.{digits}f}
  W EMA21/50:       {weekly['ema21']:,.{digits}f} / {weekly['ema50']:,.{digits}f}
""" if weekly else """
  Weekly:            N/A (W1 data unavailable)
""") + f"""
  D/W Status:        {dw_status or 'N/A'}
  D/W Confidence:    {(dw_confidence*100):.0f}%{' ✅ HIGH' if dw_confidence >= 0.9 else ' ⚠️ LOW — reduce size' if dw_confidence <= 0.3 else ''}
  D/W Note:          {dw_note or 'N/A'}

  ─────────────────────────────────────────────────────
  MOVING AVERAGES
  ─────────────────────────────────────────────────────

  EMA 9:         {e9v:,.{digits}f}  {'← Price ABOVE ▲' if price > e9v else '← Price BELOW ▼'}
  EMA 21:        {e21v:,.{digits}f}  {'← Price ABOVE ▲' if price > e21v else '← Price BELOW ▼'}
  EMA 50:        {e50v:,.{digits}f}  {'← Price ABOVE ▲' if price > e50v else '← Price BELOW ▼'}
  MA 20:         {ma20v:,.{digits}f}  {'← Price ABOVE ▲' if price > ma20v else '← Price BELOW ▼'}
  BB Upper (20): {float(bb_upper[-1]):,.{digits}f}
  BB Middle:     {float(bb_mid[-1]):,.{digits}f}
  BB Lower (20): {float(bb_lower[-1]):,.{digits}f}
  
  ─────────────────────────────────────────────────────
  RECOMMENDATION
  ─────────────────────────────────────────────────────

  Score:         {score:+.1f} / 10
  Action:        {recommendation}

  Interpretation:
"""
    
    # 添加解读
    interpretations = {
        "STRONG BUY": f"  → 多头强势, 多头排列清晰,  momentum强劲。考虑做多, SL设在{support_levels[0]:,.{digits}f}下方。",
        "BUY": f"  → 偏向多头, D1/H4趋势向上。可在回调至{support_levels[0]:,.{digits}f}附近入场做多。",
        "NEAR BUY": f"  → 轻微偏多, 需等待确认信号。关注价格能否站稳{pp['PP']:,.{digits}f}上方。",
        "NEUTRAL": f"  → 多空平衡, 观望为主。等待价格突破{resistance_levels[0]:,.{digits}f}或跌破{support_levels[0]:,.{digits}f}。",
        "NEAR SELL": f"  → 轻微偏空, 需等待确认信号。关注价格能否跌破{pp['PP']:,.{digits}f}下方。",
        "SELL": f"  → 偏向空头, D1/H4趋势向下。可在反弹至{resistance_levels[0]:,.{digits}f}附近入场做空。",
        "STRONG SELL": f"  → 空头强势, 空头排列清晰, momentum疲软。考虑做空, SL设在{resistance_levels[0]:,.{digits}f}上方。",
    }
    report += interpretations.get(recommendation, "") + "\n\n"
    
    return report, {
        'symbol': symbol,
        'price': round(price, digits),
        'bias': bias_strength,
        'momentum': momentum,
        'recommendation': recommendation,
        'score': round(score, 1),
        'rsi': round(cur_rsi, 1),
        'adx': round(cur_adx, 1),
        'support': [round(s, digits) for s in support_levels],
        'resistance': [round(r, digits) for r in resistance_levels],
        'pivot': round(pp['PP'], digits),
        # v2.0 D/W dual timeframe
        'weekly_direction': weekly['direction'] if weekly else None,
        'weekly_strength': weekly['strength'] if weekly else None,
        'weekly_rsi': weekly.get('rsi') if weekly else None,
        'dw_status': dw_status,
        'dw_confidence': round(dw_confidence, 2),
        'dw_note': dw_note,
        # TC 4-tier key levels
        'tc_target': tc_levels['target'],
        'tc_resistance_red': tc_levels['resistance_strong_red'],
        'tc_support_green': tc_levels['support_green'],
    }

# ═══ Trading Central 共识(外部分析师观点, 用于交叉验证) ═══
def load_tc_consensus():
    """加载 Trading Central / 职业分析师共识, 作为引擎自分析的外部裁判"""
    f = os.path.join(BASE, "tc_consensus.json")
    if os.path.exists(f):
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                return json.load(fh)
        except Exception:
            pass
    return {}

def normalize_bias(b):
    """把任意表述归一到 BULLISH / BEARISH / SIDEWAYS"""
    b = (b or "").upper()
    if "BULL" in b: return "BULLISH"
    if "BEAR" in b: return "BEARISH"
    if b in ("BUY", "LONG", "看多", "多"): return "BULLISH"
    if b in ("SELL", "SHORT", "看空", "空"): return "BEARISH"
    return "SIDEWAYS"

def _tc_age_days(updated_at):
    """TC 共识快照距今天数; 无日期返回 None"""
    if not updated_at:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            d = datetime.strptime(str(updated_at), fmt).date()
            return (datetime.now().date() - d).days
        except ValueError:
            continue
    return None

def build_market_state(summaries, tc_consensus):
    """生成机器可读 market_state.json — EA / Python 大脑直接读取以调整参数"""
    symbols = {}
    consistent = partial = mismatch = 0
    # TC 共识快照年龄(诚实度提示)
    _meta = (tc_consensus.get("meta") or tc_consensus.get("_meta") or {}) if isinstance(tc_consensus, dict) else {}
    tc_age = _tc_age_days(_meta.get("updated_at")) if isinstance(_meta, dict) else None
    tc_max_age = _meta.get("max_age_days", 7) if isinstance(_meta, dict) else 7
    tc_stale = (tc_age is not None and tc_age > tc_max_age)
    for s in summaries:
        eng = normalize_bias(s.get('bias'))
        tc = normalize_bias(tc_consensus.get(s['symbol']))
        if not tc:
            cons = None
        elif eng == tc:
            cons = True; consistent += 1
        elif eng == "SIDEWAYS" or tc == "SIDEWAYS":
            cons = "partial"; partial += 1
        else:
            cons = False; mismatch += 1
        adx = float(s.get('adx', 0))
        regime = "STRONG_TREND" if adx >= 50 else ("TREND" if adx >= 25 else "RANGING")
        symbols[s['symbol']] = {
            "price": s['price'],
            "bias": s['bias'],
            "bias_code": eng,
            "adx": adx,
            "adx_regime": regime,
            "support": s['support'],
            "resistance": s['resistance'],
            "pivot": s['pivot'],
            "score": s['score'],
            "recommendation": s['recommendation'],
            "momentum": s['momentum'],
            "tc_consensus": tc_consensus.get(s['symbol']),
            "tc_consistent": cons,
            "tc_age_days": tc_age,
            "tc_stale": tc_stale,
            # v2.0 D/W dual timeframe
            "weekly_direction": s.get('weekly_direction'),
            "dw_status": s.get('dw_status'),
            "dw_confidence": s.get('dw_confidence', 0.5),
            "tc_target": s.get('tc_target'),
            # 盘感神经网络 (DL Optimizer)
            "dl_direction": s.get('dl_direction'),
            "dl_confidence": s.get('dl_confidence'),
            "dl_score_adjust": s.get('dl_score_adjust'),
            "dl_combined": s.get('dl_combined'),
        }
    state = {
        "updated_at": datetime.now().isoformat(timespec='seconds'),
        "source": "MetaTrader5 (TradeMaxGlobal-Demo)",
        "provider": "A.T.E. Autonomous Trading Engine v2.0-DW",
        "tc_consensus_meta": {
            "updated_at": _meta.get("updated_at") if isinstance(_meta, dict) else None,
            "age_days": tc_age,
            "max_age_days": tc_max_age,
            "stale": tc_stale,
            "note": (_meta.get("source") if isinstance(_meta, dict) else None),
        },
        "symbols": symbols,
        "tc_consistency_summary": {
            "total": len(summaries),
            "consistent": consistent,
            "partial": partial,
            "mismatch": mismatch,
        },
    }
    out = os.path.join(BASE, "market_state.json")
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    return out, state

# ═══ 主流程 ═══
print("="*65)
print("  A.T.E. 多品种行情分析报告 v2.0-DW")
print("  (Trading Central Daily+Weekly 双框架版)")
print("="*65)

all_reports = {}
summaries = []

# 深度学习盘感模型(无训练模型则跳过, 不影响规则分析)
dl = DLOptimizer.load() if HAS_DL else None
if dl is not None:
    print(f"\n  🧠 盘感神经网络已加载: {os.path.basename(MODEL_PATH)} (每品种额外拉数据做 DL 偏置预测)")

# 加载 TC 共识 + 计算快照年龄(诚实度), 供 DL 加成与交叉验证使用
tc = load_tc_consensus()
_tc_meta = (tc.get("meta") or tc.get("_meta") or {}) if isinstance(tc, dict) else {}
tc_age = _tc_age_days(_tc_meta.get("updated_at")) if isinstance(_tc_meta, dict) else None
tc_stale = (tc_age is not None and tc_age > _tc_meta.get("max_age_days", 7)) if isinstance(_tc_meta, dict) else False

for sym, cfg in SYMBOLS.items():
    try:
        print(f"\n  分析 {sym} ({cfg['name']})...", end=" ")
        report, summary = generate_technical_summary(sym, cfg)
        # ── 深度学习加成 ──
        if dl is not None:
            try:
                d, c, adj = dl.boost_from_raw(sym, summary['bias'], tc, tc_stale, mt5)
                summary['dl_direction'] = d
                summary['dl_confidence'] = c
                summary['dl_score_adjust'] = adj
                # 综合建议: 规则 + 神经网络
                if d is not None and c is not None and c >= 0.55:
                    if _enc_bias(d) == _enc_bias(summary['bias']):
                        comb = "强化✓"
                    elif _enc_bias(d) == -_enc_bias(summary['bias']) and summary['bias'] != "SIDEWAYS":
                        comb = "⚠冲突"
                    else:
                        comb = "中性"
                else:
                    comb = "弱信号"
                summary['dl_combined'] = comb
                # 追加 NEURAL INTUITION 段到报告
                report += f"""
  ─────────────────────────────────────────────────────
  NEURAL INTUITION ★ 盘感神经网络
  ─────────────────────────────────────────────────────

  DL 方向:      {d or 'N/A'}  (置信度 {c if c is not None else 0:.2f})
  DL 评分加成:  {adj:+.2f}
  规则×神经网络: {comb}
  ─────────────────────────────────────────────────────
"""
                print(f"✓ Score={summary['score']:+.1f}, Action={summary['recommendation']} | 🧠DL {d} conf={c}")
            except Exception as e:
                summary['dl_direction'] = None
                summary['dl_confidence'] = None
                summary['dl_score_adjust'] = 0.0
                summary['dl_combined'] = "N/A"
                print(f"✓ Score={summary['score']:+.1f}, Action={summary['recommendation']} | 🧠DL skip: {e}")
        else:
            summary['dl_direction'] = None
            summary['dl_confidence'] = None
            summary['dl_score_adjust'] = 0.0
            summary['dl_combined'] = "N/A"
            print(f"✓ Score={summary['score']:+.1f}, Action={summary['recommendation']}")
        all_reports[sym] = report
        summaries.append(summary)
    except Exception as e:
        print(f"✗ Error: {e}")

# 汇总表格
print("\n" + "="*65)
print("  SUMMARY TABLE — 品种汇总 (v2.0 D/W双框架)")
print("="*65)
print(f"{'品种':<10} {'价格':>12} {'日线趋势':<14} {'周线方向':<14} {'D/W状态':<20} {'评分':>6} {'🧠DL':<14}")
print("-"*100)
for s in summaries:
    dw = s.get('dw_status', 'N/A') or 'N/A'
    wk = s.get('weekly_direction') or 'N/A'
    dl = s.get('dl_direction') or 'N/A'
    dlconf = s.get('dl_confidence')
    dlstr = f"{dl} {dlconf:.2f}" if dlconf is not None else "N/A"
    print(f"{s['symbol']:<10} ${s['price']:>10,.2f} {s['bias']:<14} {str(wk):<14} {str(dw):<20} {s['score']:>6.1f} {dlstr:<14}")

# 输出到文件
report_file = os.path.join(BASE, "daily_analysis_report.txt")
with open(report_file, 'w', encoding='utf-8') as f:
    f.write(f"A.T.E. Analysis Report v2.0-DW — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    f.write("="*80 + "\n\n")
    for sym, report in all_reports.items():
        f.write(report)
        f.write("\n" + "-"*80 + "\n\n")

# 机器可读状态(供 EA / Python 大脑读取调整参数)
tc = load_tc_consensus()
state_file, state = build_market_state(summaries, tc)
cs = state["tc_consistency_summary"]
print(f"\n\n完整报告已保存: {report_file}")
print(f"机器状态已保存: {state_file}")
print("共分析了 {} 个品种".format(len(summaries)))
print(f"TC一致性: 全一致 {cs['consistent']} | 部分 {cs['partial']} | 不符 {cs['mismatch']}")
# v2.0 D/W 汇总
agree = sum(1 for s in summaries if s.get('dw_status','').startswith('AGREE'))
conflict = sum(1 for s in summaries if s.get('dw_status','').startswith('CONFLICT'))
print(f"D/W框架: 日周同向 {agree} | 矛盾 {conflict} | 其他 {len(summaries)-agree-conflict}")
if conflict > 0:
    print("  ⚠ 矛盾品种(建议减仓或不交易):")
    for s in summaries:
        if s.get('dw_status','').startswith('CONFLICT'):
            print(f"    • {s['symbol']}: D={s['bias']} W={s.get('weekly_direction')} — {s.get('dw_note', '')}")
_tcm = state.get("tc_consensus_meta", {})
if _tcm.get("stale"):
    print(f"⚠ 警告: TC 共识快照已 {_tcm['age_days']} 天 (updated_at={_tcm.get('updated_at')}), 超过建议 {_tcm['max_age_days']} 天 — 交叉验证可信度下降, 请更新 tc_consensus.json")
elif _tcm.get("age_days") is not None:
    print(f"ℹ TC 共识快照 {_tcm['age_days']} 天前, 仍在有效期内 (≤{_tcm['max_age_days']}天)")

# 紧凑 hourly 表(对应 auto-market-analysis 定时任务)
print("\n  AUTO-MARKET-ANALYSIS (hourly)")
print(f"  {'品种':<8} {'趋势':<10} {'ADX':>6} {'支撑(3)':<26} {'阻力(3)':<26} {'建议':<12} {'🧠DL':<14}")
for s in summaries:
    st = state['symbols'][s['symbol']]
    d = SYMBOLS[s['symbol']]['digits']
    sup = "/".join(f"{x:,.{d}f}" for x in st['support'][:3])
    res = "/".join(f"{x:,.{d}f}" for x in st['resistance'][:3])
    dl = st.get('dl_direction') or 'N/A'
    dlconf = st.get('dl_confidence')
    dlstr = f"{dl} {dlconf:.2f}" if dlconf is not None else "N/A"
    print(f"  {s['symbol']:<8} {st['bias_code']:<10} {st['adx']:>6.1f} {sup:<26} {res:<26} {st['recommendation']:<12} {dlstr:<14}")

# ══ MT5 安全关闭守卫（铁律）══
# 当本机存在 live 交易实例共享同一 MT5 终端时, 严禁 shutdown()——会掐断 live 共享连接。
# 诊断/分析脚本默认不关闭终端; 仅当显式设置环境变量 ATE_FORCE_SHUTDOWN=1 时才关闭(独立排障用)。
if os.environ.get("ATE_FORCE_SHUTDOWN") == "1":
    mt5.shutdown()
    print("  [MT5] 已按 ATE_FORCE_SHUTDOWN=1 显式关闭终端。")
else:
    print("  [MT5] 跳过 shutdown() — 保留 live 共享连接(安全)。如需关闭请设 ATE_FORCE_SHUTDOWN=1。")
