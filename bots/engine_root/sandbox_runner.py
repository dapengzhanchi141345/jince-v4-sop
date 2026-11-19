"""
Goldstrategy Guild v5.1 — Multi-Symbol Crypto Runner
支持 BTCUSD + ETHUSD 双品种并行自动交易
"""
import sys, os, time, json, warnings
import numpy as np, pandas as pd
from datetime import datetime, timedelta
warnings.filterwarnings('ignore')

ACCOUNT = 60043976
PASSWORD = ""
SERVER = "TradeMaxGlobal-Demo"

# ───────── 多品种配置 ─────────
SYMBOLS = ["BTCUSD", "ETHUSD"]
RISK_PERCENT = 1.0
MAX_DAILY_LOSS = 5.0
MAX_DAILY_TRADES = 5
TP_R_MULTIPLE = 2.0
MIN_TRADE_INTERVAL = 600  # 10分钟间隔 (原来300)
SIGNAL_THRESHOLD = 0.65  # 信号阈值65% (原来60%)
MAX_LOT_PER_TRADE = 0.01  # 单笔最大硬限制0.01手

# 品种特定参数
SYMBOL_CONFIG = {
    "BTCUSD": {
        "magic": 20260704,
        "tick_value": 0.01,
        "lot_min": 0.01,
        "lot_max": 0.01,  # 硬限制0.01
        "deviation": 500,
        "atr_stop_mult": 2.0,
    },
    "ETHUSD": {
        "magic": 20260705,
        "tick_value": 0.001,
        "lot_min": 0.01,
        "lot_max": 0.01,  # 硬限制0.01
        "deviation": 500,
        "atr_stop_mult": 2.0,
    },
}

t0 = datetime.now()
LOG_FILE = "E:/GoldstrategyEngine/logs/daemon.log"

def log(msg):
    t = datetime.now().strftime('%H:%M:%S')
    safe = msg
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f'[{t}] {msg}\n')
    except:
        pass
    try:
        print(f'[{t}] {safe}', flush=True)
    except:
        pass

log('='*60)
log('Goldstrategy Guild v5.1 — Multi-Symbol Crypto Runner')
log(f'Account: {ACCOUNT} @ {SERVER} | Symbols: {", ".join(SYMBOLS)}')
log('='*60)

# ───────── MT5 连接 ─────────
import MetaTrader5 as mt5
MT5_PATH = r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe"

log('[.] Initializing MT5...')
if not mt5.initialize(path=MT5_PATH):
    log('[X] mt5.initialize() failed')
    import subprocess
    try:
        subprocess.Popen([MT5_PATH],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        log('[.] Waiting 15s for MT5 to start...')
        time.sleep(15)
        if not mt5.initialize(path=MT5_PATH):
            log('[X] Still cannot initialize. Please start MT5 manually.')
            sys.exit(1)
    except:
        sys.exit(1)

mt5.login(ACCOUNT, password=PASSWORD, server=SERVER)
acct = mt5.account_info()
if not acct:
    log('[X] Login failed!')
    mt5.shutdown()
    sys.exit(1)

log(f'[OK] Connected! Balance: ${acct.balance:.2f} | Equity: ${acct.equity:.2f}')
log(f'[OK] Server: {acct.server} | Leverage: 1:{acct.leverage}')

# AutoTrading检查
ti = mt5.terminal_info()
if ti and not ti.trade_allowed:
    log('[!] AutoTrading disabled! Enable green triangle in MT5 toolbar!')
    log('[!] Waiting 30s...')
    time.sleep(30)
    ti = mt5.terminal_info()
    if ti and not ti.trade_allowed:
        log('[X] Still disabled. Exiting.')
        mt5.shutdown()
        sys.exit(1)

for sym in SYMBOLS:
    mt5.symbol_select(sym, True)
    tick = mt5.symbol_info_tick(sym)
    if tick:
        log(f'[OK] {sym}: Bid=${tick.bid:.2f} Ask=${tick.ask:.2f} Spread={mt5.symbol_info(sym).spread}')
    else:
        log(f'[!] {sym}: No tick data')

# ───────── 加载因子库 ─────────
log('[.] Loading MegaFactorLibrary...')
os.environ['MARKET_TYPE'] = 'CRYPTO'
sys.path.insert(0, 'E:/GoldstrategyEngine')
from optimized.factor_library_v2 import MegaFactorLibrary
mfl = MegaFactorLibrary()
log(f'[OK] Factor library loaded: {mfl.count} factors')

# ───────── 共享风控状态 ─────────
cycles = 0
consecutive_wins = 0
consecutive_losses = 0
daily_trades = 0
daily_pnl = 0.0
current_date = datetime.now().date()
cooldown_until = 0  # 连亏冷却时间戳 (time.time())

# 每品种最新信号缓存
signal_cache = {}

# ───────── 核心函数 ─────────
def get_sym_config(symbol):
    return SYMBOL_CONFIG.get(symbol, SYMBOL_CONFIG["BTCUSD"])

def calc_atr_stop(atr, mult=2.0): return atr * mult

def calc_position_size(balance, atr, symbol):
    cfg = get_sym_config(symbol)
    risk_amount = balance * RISK_PERCENT / 100.0
    sl_distance = calc_atr_stop(atr, cfg["atr_stop_mult"])
    raw_lot = risk_amount / (sl_distance * cfg["tick_value"] * 100)
    lot = max(cfg["lot_min"], min(cfg["lot_max"], round(raw_lot, 2)))  # 受MAX_LOT_PER_TRADE限制
    return lot

def risk_check(price, atr, balance, equity, hour):
    fails = []
    # 冷却检查
    if time.time() < cooldown_until:
        remain = int(cooldown_until - time.time())
        fails.append(f'Cooling {remain}s')
    if daily_pnl <= -balance * MAX_DAILY_LOSS / 100: fails.append(f'Dloss>{MAX_DAILY_LOSS}%')
    if daily_trades >= MAX_DAILY_TRADES: fails.append(f'MaxTr={MAX_DAILY_TRADES}')
    if consecutive_losses >= 3: fails.append(f'Cool{consecutive_losses}L')
    if hour < 1: fails.append('Off')
    if atr <= 0 or atr > 10000: fails.append(f'ATR={atr:.0f}')
    return len(fails) == 0, '; '.join(fails) if fails else 'PASS'

def send_order(direction, lot, price, atr, symbol):
    cfg = get_sym_config(symbol)
    ot = mt5.ORDER_TYPE_BUY if direction == 'BUY' else mt5.ORDER_TYPE_SELL
    tick = mt5.symbol_info_tick(symbol)
    if not tick: return False
    
    order_price = tick.ask if direction=='BUY' else tick.bid
    sl_distance = calc_atr_stop(atr, cfg["atr_stop_mult"])
    tp_distance = sl_distance * TP_R_MULTIPLE
    
    sl = order_price - sl_distance if direction=='BUY' else order_price + sl_distance
    tp = order_price + tp_distance if direction=='BUY' else order_price - tp_distance
    sl, tp = round(sl, 2), round(tp, 2)
    
    for fill in [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]:
        req = {
            'action': mt5.TRADE_ACTION_DEAL, 'symbol': symbol, 'volume': lot,
            'type': ot, 'price': order_price, 'sl': sl, 'tp': tp,
            'deviation': cfg["deviation"], 'magic': cfg["magic"],
            'comment': 'Goldstrategy Guild',
            'type_time': mt5.ORDER_TIME_GTC, 'type_filling': fill,
        }
        res = mt5.order_send(req)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            log(f'[TRADE][{symbol}] {direction} {lot} @ ${order_price:.2f} SL=${sl:.2f}(-${sl_distance:.0f}) TP=${tp:.2f}(+${tp_distance:.0f})')
            return True
        elif res and res.retcode == 10027 and fill == mt5.ORDER_FILLING_RETURN:
            req2 = dict(req); req2.pop('sl',None); req2.pop('tp',None)
            res2 = mt5.order_send(req2)
            if res2 and res2.retcode == mt5.TRADE_RETCODE_DONE:
                log(f'[TRADE][{symbol}] {direction} {lot} (no SL/TP) @ ${order_price:.2f}')
                return True
    return False

def manage_positions(pos, atr, symbol):
    for p in pos:
        entry, current = float(p.price_open), float(p.price_current)
        is_buy = p.type == 0
        dist = (current - entry) if is_buy else (entry - current)
        r_dist = calc_atr_stop(atr)
        
        if dist > r_dist * 0.5:
            be_sl = round(entry + 3 if is_buy else entry - 3, 2)
            if (is_buy and float(p.sl) < be_sl) or (not is_buy and float(p.sl) > be_sl):
                r = mt5.order_send({'action': mt5.TRADE_ACTION_SLTP, 'symbol': symbol, 'position': p.ticket, 'sl': be_sl, 'tp': p.tp})
                if r and r.retcode == mt5.TRADE_RETCODE_DONE: log(f'[MGMT][{symbol}] BE SL @ ${be_sl:.2f}')
        if dist > r_dist * 1.0:
            trail_sl = round(current - r_dist * 0.5 if is_buy else current + r_dist * 0.5, 2)
            if (is_buy and trail_sl > float(p.sl)) or (not is_buy and trail_sl < float(p.sl)):
                r = mt5.order_send({'action': mt5.TRADE_ACTION_SLTP, 'symbol': symbol, 'position': p.ticket, 'sl': trail_sl, 'tp': p.tp})
                if r and r.retcode == mt5.TRADE_RETCODE_DONE: log(f'[MGMT][{symbol}] Trail SL @ ${trail_sl:.2f}')

def process_symbol(symbol):
    """处理单个品种: 因子分析→信号生成→趋势过滤→持仓管理→交易决策"""
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 200)
    if rates is None: return None
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    price = float(df['close'].iloc[-1])
    atr = float((df['high']-df['low']).rolling(14).mean().dropna().iloc[-1])
    
    # EMA趋势过滤 (15周期EMA方向)
    ema15 = float(df['close'].rolling(15).mean().iloc[-1])
    ema15_prev = float(df['close'].rolling(15).mean().iloc[-5]) if len(df) >= 5 else ema15
    ema_trend = 'UP' if ema15 > ema15_prev else 'DOWN'
    
    results = mfl.compute_all(df)
    buy_f = sum(1 for r in results.values() if r.direction == 'BUY')
    sell_f = sum(1 for r in results.values() if r.direction == 'SELL')
    bs = sum(abs(r.zscore) for r in results.values() if r.direction == 'BUY')
    ss = sum(abs(r.zscore) for r in results.values() if r.direction == 'SELL')
    
    direction = 'HOLD'
    total = bs + ss
    if total > 0:
        # 65%阈值 + EMA趋势一致性检查
        if bs/total > SIGNAL_THRESHOLD and ema_trend == 'UP':
            direction = 'BUY'
        elif ss/total > SIGNAL_THRESHOLD and ema_trend == 'DOWN':
            direction = 'SELL'
    
    # 持仓管理
    pos = mt5.positions_get(symbol=symbol)
    in_pos = pos and len(pos) > 0
    pnl = 0
    volume = 0
    
    if in_pos:
        manage_positions(pos, atr, symbol)
        pnl = sum(float(p.profit) for p in pos)
        volume = sum(float(p.volume) for p in pos)
    
    return {
        'symbol': symbol, 'price': price, 'atr': atr,
        'buy_f': buy_f, 'sell_f': sell_f, 'direction': direction,
        'in_pos': in_pos, 'pnl': pnl, 'volume': volume,
        'pos_count': len(pos) if pos else 0,
        'ema_trend': ema_trend,
    }

# ───────── 主循环 ─────────
log(f'[OK] Starting main loop (5s interval)')
log(f'[OK] Monitoring: {", ".join(SYMBOLS)}')
print()

while True:
    try:
        cycles += 1
        now = datetime.now()
        
        if now.date() != current_date:
            current_date = now.date()
            daily_trades = 0; daily_pnl = 0.0
            log(f'[DAY] New trading day {current_date}')
        
        # 处理每个品种
        statuses = []
        for sym in SYMBOLS:
            try:
                st = process_symbol(sym)
                if st: statuses.append(st)
            except Exception as e:
                log(f'[ERR][{sym}] {e}')
        
        # 全局风控
        balance = float(acct.balance)
        equity = float(acct.equity)
        
        # 检查平仓记录 (跨品种) — 修复: 用ticket去重
        hist = mt5.history_deals_get(datetime.now().replace(hour=0,minute=0,second=0), datetime.now())
        if hist and len(hist) > 0:
            ld = hist[-1]
            if ld.comment == 'Goldstrategy Guild' and float(ld.profit) != 0:
                # 用ticket去重，修复id()每次不同的bug
                last_ticket = getattr(process_symbol, '_last_deal_ticket', None)
                if ld.ticket != last_ticket:
                    process_symbol._last_deal_ticket = ld.ticket
                    new_profit = float(ld.profit)
                    if new_profit > 0: consecutive_wins += 1; consecutive_losses = 0
                    else:
                        consecutive_losses += 1
                        consecutive_wins = 0
                        # 连亏冷却：2连亏停30分，3连亏停到次日
                        if consecutive_losses >= 3:
                            cooldown_until = time.time() + 3600 * 12  # 12小时
                            log(f'[COOLDOWN] {consecutive_losses}L in a row! Cooling 12h')
                        elif consecutive_losses >= 2:
                            cooldown_until = time.time() + 1800  # 30分钟
                            log(f'[COOLDOWN] {consecutive_losses}L in a row! Cooling 30m')
                    daily_pnl += new_profit
                    log(f'[CLOSE][{ld.symbol}] {"W" if new_profit>0 else "L"} ${new_profit:.2f} | {consecutive_wins}W/{consecutive_losses}L | Daily ${daily_pnl:.2f}')
        
        rp, rd = risk_check(0, 100, balance, equity, now.hour)
        
        # 输出状态 (每5cycle一次)
        if cycles % 5 == 1:
            dir_c = {'BUY':'\u2191','SELL':'\u2193','HOLD':'\u2014'}
            line_parts = [f'[C{cycles}]']
            for st in statuses:
                sym = st['symbol'][:4]
                d = dir_c.get(st['direction'],'?')
                pos_str = f'{st["volume"]}B' if st['in_pos'] else '--'
                et = st['ema_trend']
                line_parts.append(f'{sym}${st["price"]:,.0f}{d}{st["direction"]:<4}E{et}|{pos_str}PL${st["pnl"]:.2f}')
            line_parts.append(f'Bal${balance:.0f} Eq${equity:.0f}')
            line_parts.append(f'>' if rp else 'X')
            line_parts.append(rd[:20])
            log(' | '.join(line_parts))
        
        # 交易决策 (按品种)
        now_ts = time.time()
        if rp:
            for st in statuses:
                if st['direction'] != 'HOLD' and not st['in_pos']:
                    # 检查是否刚平过仓(5分钟冷却)
                    if hasattr(process_symbol, f'_last_trade_{st["symbol"]}'):
                        last_t = getattr(process_symbol, f'_last_trade_{st["symbol"]}', 0)
                        if now_ts - last_t < MIN_TRADE_INTERVAL: continue
                    
                    lot = calc_position_size(balance, st['atr'], st['symbol'])
                    if send_order(st['direction'], lot, st['price'], st['atr'], st['symbol']):
                        daily_trades += 1
                        setattr(process_symbol, f'_last_trade_{st["symbol"]}', now_ts)
                        log(f'[TRADE][{st["symbol"]}] #{daily_trades} today: {st["direction"]} {lot} @ ${st["price"]:.2f}')
        
        time.sleep(5)
    except KeyboardInterrupt:
        log('Stopped by user')
        break
    except Exception as e:
        log(f'[ERR][Main] {e}')
        time.sleep(10)

mt5.shutdown()
elapsed = datetime.now() - t0
log(f'Daemon stopped. {cycles} cycles in {elapsed}')
