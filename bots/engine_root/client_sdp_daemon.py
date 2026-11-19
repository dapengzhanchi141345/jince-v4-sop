"""
SDP Trader v6.0 — 纯 SDP 模式守护进程 (client_sdp_daemon.py)
============================================================
实现真正的 SDP 策略（与旧 M1 因子引擎 sandbox_runner.py 完全解耦）：

    策略流程：H4 供需区  →  H1 趋势(EMA+结构+ADX>20)  →  M5 确认  →  0.01 入场

核心规则（来自 USER.md / MEMORY.md）：
  - H1 趋势为主过滤，ADX<20 震荡市硬跳过
  - 只在价格回到 H4 供需区 + M5 出现拒绝信号时才反应（不预测，只反应）
  - 0.01 手硬上限；2×ATR 止损；2R 止盈；0.5R 保本；1R 追踪
  - 连亏冷却：2L=1h，3L=12h；日亏上限 3%；日交易上限 6

🔒 实盘安全锁：IS_LIVE 必须为 False，切换实盘需手动改 True 并复核账号。
运行方式：python client_sdp_daemon.py   （替代 sandbox_runner.py 即可退役旧引擎）
"""
import sys, os, time, json, warnings

# ---- LightGBM DLL path fix（保持与旧引擎一致，避免环境告警）----
try:
    import lgb_patch
except Exception:
    pass

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
warnings.filterwarnings('ignore')

# ================================================================
# 路径
# ================================================================
ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE_DIR)
os.chdir(ENGINE_DIR)

# ================================================================
# 🔒 安全锁 & 账号
# ================================================================
IS_LIVE = False
ACCOUNT = 60111502
PASSWORD = ""  # P0: 明文凭证已剔除（走 broker 侧轮换），凭证不入库；此树为废弃审计树，不再实跑
SERVER = "TradeMaxGlobal-Demo"
MT5_PATH = r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe"

# ================================================================
# SDP 参数（不可被外部覆盖的硬规则）
# ================================================================
MAX_LOT = 0.01            # 🔒 单笔最大手数硬上限（任何情况下不可突破）
RISK_PERCENT = 1.0        # P0：单笔风险占净值百分比（tick_value 定仓用；$971→约$9.7 单笔风险额）
MIN_ADX = 20             # H1 ADX<20 = 震荡市，禁止开单
TP_R_MULT = 2.0          # 2R 止盈
ATR_SL_MULT = 2.0        # 2×ATR 止损
BE_R = 0.5              # 盈利达 0.5R 推保本
TRAIL_R = 1.0           # 盈利达 1R 启动追踪
ZONE_TOUCH_PCT = 0.004  # 价格进入区间 ±0.4% 视为"到达供需区"
MIN_TRADE_INTERVAL = 300  # 同品种最小开单间隔（秒）

# 品种调度（来自 USER.md）
WEEKDAY_SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "BTCUSD", "ETHUSD"]
WEEKEND_SYMBOLS = ["BTCUSD", "ETHUSD"]

SYMBOL_CONFIG = {
    "BTCUSD": {"magic": 20260704, "lot_min": 0.01, "lot_max": 0.01, "deviation": 500, "comment": "SDP Crypto BTC"},
    "ETHUSD": {"magic": 20260705, "lot_min": 0.01, "lot_max": 0.01, "deviation": 500, "comment": "SDP Crypto ETH"},
    "XAUUSD": {"magic": 20260706, "lot_min": 0.01, "lot_max": 0.01, "deviation": 50, "comment": "SDP Forex XAU"},
    "EURUSD": {"magic": 20260707, "lot_min": 0.01, "lot_max": 0.01, "deviation": 20, "comment": "SDP Forex EUR"},
    "GBPUSD": {"magic": 20260708, "lot_min": 0.01, "lot_max": 0.01, "deviation": 20, "comment": "SDP Forex GBP"},
    "USDJPY": {"magic": 20260709, "lot_min": 0.01, "lot_max": 0.01, "deviation": 15, "comment": "SDP Forex JPY"},
    "AUDUSD": {"magic": 20260710, "lot_min": 0.01, "lot_max": 0.01, "deviation": 20, "comment": "SDP Forex AUD"},
}

# ================================================================
# 日志
# ================================================================
SDP_LOG = f"{ENGINE_DIR}/logs/sdp_daemon.log"

def log(msg):
    t = datetime.now().strftime('%H:%M:%S')
    try:
        with open(SDP_LOG, 'a', encoding='utf-8') as f:
            f.write(f'[{t}] {msg}\n')
    except Exception:
        pass
    try:
        print(f'[{t}] {msg}', flush=True)
    except Exception:
        pass

# ================================================================
# 崩溃捕获
# ================================================================
CRASH_LOG_FILE = f"{ENGINE_DIR}/logs/sdp_crash.log"

def log_crash(exc_type, exc_value, exc_tb):
    import traceback
    tb_text = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    msg = f'[{datetime.now():%Y-%m-%d %H:%M:%S}] UNCAUGHT EXCEPTION:\n{tb_text}\n{"="*60}\n'
    try:
        with open(CRASH_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(msg)
    except Exception:
        pass
    try:
        print(msg, flush=True)
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = log_crash

# ================================================================
# 优雅重启（单会话最长 8 小时）
# ================================================================
SESSION_START_TIME = time.time()
MAX_SESSION_HOURS = 8

def should_graceful_restart():
    elapsed = (time.time() - SESSION_START_TIME) / 3600
    if elapsed >= MAX_SESSION_HOURS:
        log(f'[RESTART] Session reached {elapsed:.1f}h, graceful restart')
        return True
    return False

# ================================================================
# MT5 连接
# ================================================================
log('=' * 60)
log('SDP Trader v6.0 — Pure SDP Mode Daemon')
log(f'Account: {ACCOUNT} @ {SERVER}')
log(f'Live Mode: {IS_LIVE}')
if IS_LIVE:
    log('[!] ⚠️ LIVE TRADING MODE — 请确认账号/密码/服务器正确！')
else:
    log('[OK] Demo mode (IS_LIVE=False) — safe trading')
log('=' * 60)

log('[.] Initializing MT5...')
import MetaTrader5 as mt5

def init_mt5():
    if not mt5.initialize(path=MT5_PATH):
        import subprocess
        try:
            subprocess.Popen([MT5_PATH],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            log('[.] Waiting 15s for MT5...')
            time.sleep(15)
            if not mt5.initialize(path=MT5_PATH):
                log('[X] Cannot init MT5.')
                return False
        except Exception:
            return False
    if not mt5.login(ACCOUNT, password=PASSWORD, server=SERVER):
        log('[X] MT5 login failed')
        return False
    acct = mt5.account_info()
    if acct:
        log(f'[OK] Balance: ${acct.balance:.2f} | Equity: ${acct.equity:.2f}')
    ti = mt5.terminal_info()
    if ti and not ti.trade_allowed:
        log('[!] AutoTrading disabled! Enable green triangle!')
        time.sleep(30)
    return True

if not init_mt5():
    sys.exit(1)

# ================================================================
# 复用共享执行层：OrderManager + RiskManager（13 层）
# ================================================================
from execution.order_manager import OrderManager
from risk.risk_manager import RiskManager, RiskState

order_mgr = OrderManager(mt5, SYMBOL_CONFIG)
risk_state = RiskState()
risk_mgr = RiskManager(state=risk_state, config={
    'risk_percent': 0.5,        # L0/L1
    'max_daily_loss': 3.0,      # L2（USER.md: 3%）
    'max_daily_trades': 6,      # L3
    'cooldown_2L_mins': 60,     # L4（USER.md: 2L=1h）
    'cooldown_3L_hours': 12,    # L4（USER.md: 3L=12h）
    'max_lot_per_trade': MAX_LOT,
})
log('[OK] Order manager + 13-layer risk engine ready')

# ================================================================
# 数据获取（多周期）
# ================================================================
def get_rates(symbol, timeframe, count=200):
    """统一获取 K 线并做 MT5 列名映射（tick_volume→volume）"""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    if 'tick_volume' in df.columns and 'volume' not in df.columns:
        df['volume'] = df['tick_volume']
    elif 'real_volume' in df.columns and 'volume' not in df.columns:
        df['volume'] = df['real_volume']
    df = df.ffill().fillna(0)
    return df

# ================================================================
# SDP 核心：指标
# ================================================================
def compute_adx(df, period=14):
    """向量化 ADX 计算（H1 用）"""
    high, low, close = df['high'], df['low'], df['close']
    up = high - high.shift(1)
    dn = low.shift(1) - low
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([(high - low),
                    (high - close.shift(1)).abs(),
                    (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr = pd.Series(tr).rolling(period).mean()
    plus_di = 100 * pd.Series(plus_dm).rolling(period).mean() / atr
    minus_di = 100 * pd.Series(minus_dm).rolling(period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.rolling(period).mean()
    v = adx.dropna()
    return float(v.iloc[-1]) if len(v) > 0 else 0.0

# ================================================================
# SDP 核心①：H1 趋势 + ADX 过滤
# ================================================================
def analyze_h1(symbol):
    df = get_rates(symbol, mt5.TIMEFRAME_H1, 100)
    if df is None or len(df) < 30:
        return None
    close = df['close']
    ema = float(close.rolling(20).mean().iloc[-1])
    ema_prev = float(close.rolling(20).mean().iloc[-5])
    price = float(close.iloc[-1])
    # 结构：近 20 根摆动高低点
    hh = float(df['high'].iloc[-20:].max())
    ll = float(df['low'].iloc[-20:].min())
    # 趋势判定：价格在 EMA 上方且抬高低点 = UP；下方且降低高点 = DOWN
    if price > ema and ll > float(df['low'].iloc[-40:-20].min()):
        trend = 'UP'
    elif price < ema and hh < float(df['high'].iloc[-40:-20].max()):
        trend = 'DOWN'
    else:
        trend = 'NEUTRAL'
    adx = compute_adx(df, 14)
    atr = float((df['high'] - df['low']).rolling(14).mean().iloc[-1])
    return {'trend': trend, 'adx': adx, 'atr': atr, 'price': price, 'ema': ema}

# ================================================================
# SDP 核心②：H4 供需区识别（位移法）
# ================================================================
def find_h4_zones(symbol, lookback=200):
    df = get_rates(symbol, mt5.TIMEFRAME_H4, lookback)
    if df is None or len(df) < 40:
        return []
    atr = float((df['high'] - df['low']).rolling(14).mean().iloc[-1])
    if atr <= 0:
        return []
    zones = []
    for i in range(3, len(df) - 5):
        body = abs(df['close'].iloc[i] - df['open'].iloc[i])
        rng = (df['high'].iloc[i] - df['low'].iloc[i]) or 1e-9
        # 位移强度：实体 > 1.5×ATR 且实体占振幅 > 60%
        if body > 1.5 * atr and (body / rng) > 0.6:
            base = df.iloc[i - 3:i]
            z_high = float(base['high'].max())
            z_low = float(base['low'].min())
            z_mid = float(base['close'].mean())
            strength = body / atr
            if df['close'].iloc[i] < df['open'].iloc[i]:
                zones.append({'type': 'SUPPLY', 'high': z_high, 'low': z_low,
                              'mid': z_mid, 'strength': strength})
            else:
                zones.append({'type': 'DEMAND', 'high': z_high, 'low': z_low,
                              'mid': z_mid, 'strength': strength})
    # 仅保留最强的 4 个区
    zones = sorted(zones, key=lambda z: z['strength'], reverse=True)[:4]
    return zones

# ================================================================
# SDP 核心③：M5 入场确认（拒绝信号 / Pinbar）
# ================================================================
def check_m5_confirm(symbol, direction):
    df = get_rates(symbol, mt5.TIMEFRAME_M5, 30)
    if df is None or len(df) < 10:
        return False
    last = df.iloc[-1]
    body = last['close'] - last['open']
    rng = (last['high'] - last['low']) or 1e-9
    upper_wick = last['high'] - max(last['open'], last['close'])
    lower_wick = min(last['open'], last['close']) - last['low']
    if direction == 'BUY':
        # 看涨拒绝：长下影 + 收阳 + 上影短
        return (lower_wick > 0.6 * rng) and (body > 0) and (upper_wick < 0.3 * rng)
    else:
        # 看跌拒绝：长上影 + 收阴 + 下影短
        return (upper_wick > 0.6 * rng) and (body < 0) and (lower_wick < 0.3 * rng)

# ================================================================
# SDP 持仓管理：0.5R 保本 / 1R 追踪
# ================================================================
def manage_sdp_position(pos, atr):
    symbol = pos.symbol
    digits = order_mgr.get_digits(symbol)
    entry = float(pos.price_open)
    current = float(pos.price_current)
    is_buy = (pos.type == 0)
    dist = (current - entry) if is_buy else (entry - current)
    if dist <= 0:
        return
    r_dist = atr * ATR_SL_MULT           # 1R = 2×ATR
    new_sl = float(pos.sl) if pos.sl else 0
    need_update = False

    # 0.5R 保本
    if dist >= r_dist * BE_R:
        be_sl = entry + 3 * (0.1 ** (digits - 1)) if is_buy else entry - 3 * (0.1 ** (digits - 1))
        be_sl = round(be_sl, digits)
        if (is_buy and new_sl < be_sl) or (not is_buy and new_sl > be_sl):
            new_sl = be_sl
            need_update = True
            log(f'[SDP-BE] {symbol} → SL@{new_sl}')

    # 1R 追踪
    if dist >= r_dist * TRAIL_R:
        trail_sl = round(current - r_dist * 0.5 if is_buy else current + r_dist * 0.5, digits)
        if (is_buy and trail_sl > new_sl) or (not is_buy and trail_sl < new_sl):
            new_sl = trail_sl
            need_update = True
            log(f'[SDP-TRAIL] {symbol} → SL@{new_sl}')

    if need_update:
        try:
            req = {
                'action': mt5.TRADE_ACTION_SLTP,
                'symbol': symbol, 'position': pos.ticket,
                'sl': new_sl, 'tp': pos.tp,
            }
            r = mt5.order_send(req)
            if r and r.retcode == mt5.TRADE_RETCODE_DONE:
                pass
        except Exception:
            pass

# ================================================================
# 每笔交易自动反思（Post-Trade Reflection）— 免费模型 HY3
# 每笔平仓调用 HY3（经 Agnes AI API）生成反思，追加写入 .learnings/SDP_REFLECTIONS.md
# 若未配置密钥，则仅记录骨架，不阻塞主循环
# ================================================================
import os as _os
AGNES_API_KEY = _os.environ.get('AGNES_API_KEY', '')
AGNES_BASE = _os.environ.get('AGNES_BASE', 'https://api.agnes.ai/v1')
REFLECT_DIR = _os.path.join(ENGINE_DIR, '.learnings')
REFLECT_FILE = _os.path.join(REFLECT_DIR, 'SDP_REFLECTIONS.md')

def _append_reflect(block):
    try:
        _os.makedirs(REFLECT_DIR, exist_ok=True)
        with open(REFLECT_FILE, 'a', encoding='utf-8') as f:
            f.write(block + '\n')
    except Exception:
        pass

def reflect_on_trade(trade):
    """调用免费模型 HY3 生成交易反思并落盘 .learnings/"""
    symbol = trade.get('symbol', '?')
    profit = trade.get('profit', 0.0)
    direction = trade.get('direction', '?')
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    try:
        if not AGNES_API_KEY:
            log('[REFLECT] 未配置 AGNES_API_KEY，记骨架（HY3 反思跳过）')
            _append_reflect(f"## {symbol} {direction} {profit:+.2f} @ {ts}\n- 未配置 HY3 密钥，仅记骨架\n")
            return
        import requests
        prompt = (f"你是 SDP Trader v6.0 复盘助手。交易：{symbol} {direction} 盈亏 {profit:+.2f}。"
                  f"基于 SDP 规则(H4供需区+H1趋势且ADX>20+M5确认, 0.01手, 2xATR止损, 2R止盈)"
                  f"做 120 字内根因反思：赢因/亏因/下一步。")
        r = requests.post(f"{AGNES_BASE}/chat/completions",
                          headers={"Authorization": f"Bearer {AGNES_API_KEY}"},
                          json={"model": "HY3",
                                "messages": [{"role": "user", "content": prompt}]},
                          timeout=20)
        text = ''
        if r.ok:
            text = r.json().get('choices', [{}])[0].get('message', {}).get('content', '')
        _append_reflect(f"## {symbol} {direction} {profit:+.2f} @ {ts}\n{text}\n")
        log(f'[REFLECT][{symbol}] HY3 反思已写入 .learnings/')
    except Exception as e:
        log(f'[REFLECT-ERR] {e}')

# ================================================================
# 模式 & 运行时状态
# ================================================================
WEEKEND_DAYS = [5, 6]
def get_symbols():
    now = datetime.now()
    return WEEKEND_SYMBOLS if now.weekday() in WEEKEND_DAYS else WEEKDAY_SYMBOLS

last_trade_time = {}   # {symbol: timestamp} 信号去重
cycles = 0

def switch_mode_if_needed():
    """午夜切换模式并平旧持仓"""
    global last_trade_time
    now = datetime.now()
    if now.hour == 0 and now.minute == 0:
        syms = get_symbols()
        log(f'[SWITCH] Midnight → symbols {", ".join(syms)}')
        order_mgr.close_all()
        risk_state.consecutive_wins = 0
        risk_state.consecutive_losses = 0
        risk_state.daily_trades = 0
        risk_state.daily_pnl = 0.0
        last_trade_time = {}
        for s in syms:
            mt5.symbol_select(s, True)

# 启用品种
for s in get_symbols():
    mt5.symbol_select(s, True)
    tick = mt5.symbol_info_tick(s)
    if tick:
        log(f'[OK] {s}: Bid=${tick.bid:.2f} Ask=${tick.ask:.2f}')

log(f'[OK] Main loop started (10s interval) | Mode symbols: {", ".join(get_symbols())}')
print()

# ================================================================
# 主循环
# ================================================================
while True:
    try:
        cycles += 1
        now = datetime.now()

        # 每日清零
        if now.date() != risk_state.current_date:
            risk_mgr.reset_daily()
            last_trade_time = {}
            log(f'[DAY] New day {now.date()}')

        # 会话软重置（P0：原 8h 硬 break 会让进程退出、无守护拉起 → 每天 16h 系统死）
        # 现改为进程内软重置：重连一次 MT5 保持连接新鲜，但绝不退出进程，7×24 在线。
        # 不清 _seen_sdp（防重复记账），不清 risk_state（保留连亏/日亏风控计数）。
        if should_graceful_restart():
            log('[SOFT-RESTART] Session reached 8h, reinit MT5 in-process (no exit, 24/7 alive)')
            try:
                mt5.shutdown()
                time.sleep(2)
                init_mt5()
            except Exception as _e:
                log(f'[SOFT-RESTART][WARN] reinit failed: {_e}')
            SESSION_START_TIME = time.time()
            continue

        # 午夜模式切换
        switch_mode_if_needed()

        # MT5 健康检查（每 30 分钟）
        if cycles % 180 == 1:
            acct = mt5.account_info()
            if acct is None:
                log('[HEALTH] MT5 disconnected, reconnecting...')
                mt5.shutdown()
                time.sleep(3)
                init_mt5()

        acct = mt5.account_info()
        if not acct:
            log('[!] MT5 disconnected')
            time.sleep(5)
            mt5.shutdown()
            init_mt5()
            continue
        balance = float(acct.balance)
        equity = float(acct.equity)
        risk_mgr.record_equity(equity)

        # 平仓结果记录（按 magic 号识别本系统成交，修记账断链：自动 SL/TP 平仓也认得到）
        _MAGIC_SET = set(cfg['magic'] for cfg in SYMBOL_CONFIG.values())
        deals = order_mgr.check_recent_deals(magic_set=_MAGIC_SET)
        for d in deals[-1:]:
            if not hasattr(order_mgr, '_seen_sdp'):
                order_mgr._seen_sdp = set()
            if d['ticket'] not in order_mgr._seen_sdp:
                order_mgr._seen_sdp.add(d['ticket'])
                risk_mgr.record_trade_result(d['profit'])
                log(f'[SDP-CLOSE][{d["symbol"]}] {"W" if d["profit"] > 0 else "L"} '
                    f'${d["profit"]:.2f} | {risk_state.consecutive_wins}W/'
                    f'{risk_state.consecutive_losses}L')
                reflect_on_trade(d)   # 免费模型 HY3 自动复盘

        now_ts = time.time()
        for symbol in get_symbols():
            try:
                # ---- 持仓管理（不论是否有新信号都执行）----
                positions = order_mgr.get_open_positions(symbol)
                if positions:
                    h1 = analyze_h1(symbol)
                    atr = h1['atr'] if h1 else 0
                    for p in positions:
                        manage_sdp_position(p, atr)
                    continue  # 已有持仓，等平仓后再考虑下一单

                # ---- ① H1 趋势 + ADX ----
                h1 = analyze_h1(symbol)
                if h1 is None:
                    continue
                if h1['adx'] < MIN_ADX:
                    if cycles % 60 == 1:
                        log(f'[SDP][{symbol}] ADX={h1["adx"]:.1f}<{MIN_ADX} 震荡市 → 等待')
                    continue
                if h1['trend'] == 'NEUTRAL':
                    if cycles % 60 == 1:
                        log(f'[SDP][{symbol}] H1 无明确趋势 → 等待')
                    continue

                # ---- ② H4 供需区 ----
                zones = find_h4_zones(symbol)
                price = h1['price']
                touch = None
                for z in zones:
                    if z['low'] <= price <= z['high']:
                        touch = z
                        break
                    if abs(price - z['mid']) / (z['mid'] or 1) < ZONE_TOUCH_PCT:
                        touch = z
                        break
                if touch is None:
                    if cycles % 60 == 1:
                        log(f'[SDP][{symbol}] 价格未到达供需区 → 等待')
                    continue

                # ---- ③ 方向必须趋势+区 一致 ----
                if touch['type'] == 'DEMAND' and h1['trend'] == 'UP':
                    direction = 'BUY'
                elif touch['type'] == 'SUPPLY' and h1['trend'] == 'DOWN':
                    direction = 'SELL'
                else:
                    if cycles % 60 == 1:
                        log(f'[SDP][{symbol}] 区({touch["type"]})与趋势({h1["trend"]})冲突 → 跳过')
                    continue

                # ---- ④ M5 确认 ----
                if not check_m5_confirm(symbol, direction):
                    if cycles % 60 == 1:
                        log(f'[SDP][{symbol}] M5 未确认 {direction} → 等待')
                    continue

                # ---- ⑤ 信号去重（同品种间隔）----
                last_t = last_trade_time.get(symbol, 0)
                if now_ts - last_t < MIN_TRADE_INTERVAL:
                    continue

                # ---- ⑥ 13 层风控 ----
                si = mt5.symbol_info(symbol)
                spread = si.spread if si else 0
                positions_info = [{'symbol': p.symbol, 'volume': float(p.volume)}
                                  for p in (mt5.positions_get() or [])]
                rp, rd, lot_mult = risk_mgr.check_all(
                    symbol, price, h1['atr'], balance, equity, now.hour,
                    'SDP', spread=spread, positions_info=positions_info)
                if not rp:
                    if cycles % 30 == 1:
                        log(f'[SDP-RISK][{symbol}] blocked: {rd}')
                    continue

                # ---- ⑦ 下单（P0：tick_value 动态定仓接入，治小账户必亏根）----
                # 先按「单笔风险 1% 净值 ÷ 止损距离 × tick_value」算合理手数（calc_lot 真正被调用，
                # 之前全项目无人调用 → 0.01 手硬顶锁死，赢 0.09 付 0.18 成本 = 数学必亏）。
                # demo 仍用 MAX_LOT 封顶保安全；账户放大时抬高 MAX_LOT 即可自动跟上合理手数。
                risk_lot = order_mgr.calc_lot(symbol, balance, RISK_PERCENT, h1['atr'], max_lot=MAX_LOT)
                lot = min(MAX_LOT, risk_lot * lot_mult)
                lot = round(max(0.01, lot), 2)
                success, ticket, info = order_mgr.send_order(
                    symbol, direction, lot, h1['atr'], tp_r_multiple=TP_R_MULT)
                if success:
                    last_trade_time[symbol] = now_ts
                    risk_state.daily_trades += 1
                    risk_state.last_trade_time[symbol] = now_ts
                    log(f'[SDP-TRADE][{symbol}] {direction} {lot} @ ${price:.2f} '
                        f'| H1 ADX={h1["adx"]:.1f} zone={touch["type"]} '
                        f'SL=2xATR TP=2R | {risk_state.consecutive_wins}W/'
                        f'{risk_state.consecutive_losses}L')
            except Exception as e:
                log(f'[ERR][{symbol}] {e}')

        time.sleep(10)

    except KeyboardInterrupt:
        log('Stopped by user')
        break
    except Exception as e:
        log(f'[ERR][Main] {e}')
        time.sleep(10)

mt5.shutdown()
log(f'SDP Daemon stopped. {cycles} cycles.')
