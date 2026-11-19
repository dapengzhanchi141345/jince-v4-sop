"""金策宗师团 v5.0 — 自动交易引擎 (学习自SDP EA v5.00盈利策略)"""
import sys, os, time, json, warnings
import numpy as np, pandas as pd
from datetime import datetime, timedelta
warnings.filterwarnings('ignore')

# ───────── 从SDP EA v5.00学到的配置 ─────────
ACCOUNT = 60043976
PASSWORD = ""
SERVER = "TradeMaxGlobal-Demo"
SYMBOL = "BTCUSD"
BASE_LOT = 0.01
LOG_FILE = "E:/GoldstrategyEngine/logs/daemon.log"
sys.stdout.reconfigure(encoding='utf-8', errors='replace') if hasattr(sys.stdout, 'reconfigure') else None

# SDP EA v5.00核心参数
RISK_PERCENT = 1.0          # 每笔风险1%
MAX_DAILY_LOSS = 5.0        # 日最大亏损5%
MAX_DAILY_TRADES = 5        # 日最大交易次
MAX_POSITIONS = 2           # 最大同向持仓
TP_R_MULTIPLE = 2.0         # 止盈2R
PARTIAL_CLOSE_PCT = 50.0    # 部分平仓50% @ 1R

def log(msg):
    t = datetime.now().strftime('%H:%M:%S')
    safe = msg.replace('\u2705','[OK]').replace('\u274c','[X]').replace('\u26a0\ufe0f','[!]')
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f'[{t}] {msg}\n')
    except:
        pass
    try:
        print(f'[{t}] {safe}')
    except:
        try:
            print(f'[{t}] {msg.encode("ascii", errors="replace").decode("ascii")}')
        except:
            pass

def setup_debug_logging():
    """修复stdout/stderr编码问题"""
    try:
        import codecs
        # 只在新终端中修复，如果已损坏则跳过
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

def run_daemon():
    """主入口函数"""
    setup_debug_logging()
    
    log('='*50)
    log('Goldstrategy Guild v5.0 Auto Trader')
    log('='*50)
    
    # ───────── MT5连接 ─────────
    global acct
    import MetaTrader5 as mt5
    MT5_PATH = r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe"
    if not mt5.initialize(path=MT5_PATH):
        log('[X] MT5 init failed - terminal not found or not accessible')
        log('[!] Make sure MT5 is installed at: C:\\Program Files\\TMGM MT5 Terminal\\')
        return
    mt5.login(ACCOUNT, password=PASSWORD, server=SERVER)
    if not mt5.account_info():
        log('[X] Login failed - check account/password/server')
        mt5.shutdown()
        return
    acct = mt5.account_info()
    log(f'[OK] Balance: ${acct.balance:.2f} | Equity: ${acct.equity:.2f}')

    # AutoTrading check
    ti = mt5.terminal_info()
    if ti and not ti.trade_allowed:
        log('[!] MT5 AutoTrading disabled - click green triangle in MT5 toolbar!')
        log('[!] Waiting 30s for you to enable it...')
        time.sleep(30)
        ti = mt5.terminal_info()
        if ti and not ti.trade_allowed:
            log('[X] Still disabled. Exiting.')
            mt5.shutdown()
            return

    mt5.symbol_select(SYMBOL, True)
    log(f'[OK] {SYMBOL} selected')

    # ───────── 加载引擎 ─────────
    os.environ['MARKET_TYPE'] = 'FOREX'
    from optimized.factor_library_v2 import MegaFactorLibrary
    mfl = MegaFactorLibrary()
    log(f'[OK] Factor library loaded: {mfl.count} factors')

    # ───────── 状态变量 ─────────
    cycles = 0
    last_trade_time = 0
    consecutive_wins = 0
    consecutive_losses = 0
    daily_trades = 0
    daily_pnl = 0.0
    current_date = datetime.now().date()

    # ───────── 主循环 ─────────
    log('[OK] Starting main loop (5s interval)')

    while True:
        try:
            cycles += 1
            now = datetime.now()

            # 1. 获取数据
            rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M1, 0, 200)
            if rates is None:
                time.sleep(5)
                continue
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            price = float(df['close'].iloc[-1])
            atr = float((df['high']-df['low']).rolling(14).mean().dropna().iloc[-1])
            spread = mt5.symbol_info(SYMBOL).spread

            # 2. 因子分析
            results = mfl.compute_all(df)
            buy = sum(1 for r in results.values() if r.direction == 'BUY')
            sell = sum(1 for r in results.values() if r.direction == 'SELL')
            bs = sum(abs(r.zscore) for r in results.values() if r.direction == 'BUY')
            ss = sum(abs(r.zscore) for r in results.values() if r.direction == 'SELL')
            
            # 方向判断: 需要明确优势 (60%胜率)
            direction = 'HOLD'
            total = bs + ss
            if total > 0:
                if bs/total > 0.60: direction = 'BUY'
                elif ss/total > 0.60: direction = 'SELL'

            # 3. 每日重置
            if now.date() != current_date:
                current_date = now.date()
                daily_trades = 0
                daily_pnl = 0.0
                log(f'[Daily] New trading day {current_date}')

            # 风控
            risk_pass, risk_detail = _risk_check(
                price, atr, float(acct.balance), float(acct.equity), now.hour,
                daily_pnl, daily_trades, consecutive_losses
            )

            # 4. 管理现有持仓
            pos = mt5.positions_get(symbol=SYMBOL)
            in_position = pos and len(pos) > 0
            if in_position:
                for p in pos:
                    if float(p.sl) == 0.0:
                        sl_price = round(float(p.price_open) - atr * 2.0, 2)
                        req = {'action': mt5.TRADE_ACTION_SLTP, 'symbol': SYMBOL,
                               'position': p.ticket, 'sl': sl_price, 'tp': p.tp}
                        r = mt5.order_send(req)
                        if r and r.retcode == mt5.TRADE_RETCODE_DONE:
                            log(f'[SDP] SL set on manual @ ${sl_price:.2f} (2ATR)')
                        break
                _manage_position(pos, atr)
                pnl = pos[0].profit
            else:
                pnl = 0

            # 5. 状态显示
            dir_icon = {'BUY':'[UP]','SELL':'[DN]','HOLD':'[-]'}
            pos_str = f'{pos[0].volume}B' if in_position else 'empty'
            r_info = f'd{daily_trades} p{daily_pnl:+.0f}' if daily_trades > 0 else ''
            log(f'${price:,.0f} | {dir_icon.get(direction,"?")}{direction:<4} | {buy}B/{sell}S | '
                f'{"[OK]" if risk_pass else "[X]"}{risk_detail[:30]:<30} | {pos_str} | P/L${pnl:.2f} | {r_info}')

            # 6. 交易决策
            can_trade = (direction != 'HOLD' and risk_pass 
                         and not in_position 
                         and time.time() - last_trade_time > 300)
            
            if can_trade:
                lot = _calc_lot(float(acct.balance), atr, consecutive_wins, consecutive_losses)
                if _send_trade(direction, lot, price, atr):
                    last_trade_time = time.time()
                    daily_trades += 1
                    log(f'[SDP] Trade #{daily_trades}: {direction} {lot} @ ${price:.2f} | {buy}B/{sell}S')

            # 7. 检测平仓并学习
            if not in_position:
                hist = mt5.history_deals_get(datetime(2026,7,4,0,0), datetime.now())
                if hist and len(hist) > 0:
                    last_deal = hist[-1]
                    if last_deal.comment == 'Goldstrategy Guild':
                        profit = float(last_deal.profit)
                        if profit > 0:
                            consecutive_wins += 1
                            consecutive_losses = 0
                        else:
                            consecutive_losses += 1
                            consecutive_wins = 0
                        daily_pnl += profit
                        r = 'W' if profit > 0 else 'L'
                        log(f'[SDP] Close {r} ${profit:.2f} | {consecutive_wins}W/{consecutive_losses}L | Daily${daily_pnl:.2f}')

            time.sleep(5)
        except KeyboardInterrupt:
            log('Stopped by user')
            break
        except Exception as e:
            log(f'[Error] {e}')
            time.sleep(10)

    mt5.shutdown()
    log('Daemon stopped')

def _risk_check(price, atr, balance, equity, hour, dpnl, dtrades, closses):
    """SDP风格风控"""
    fails = []
    if dpnl <= -balance * MAX_DAILY_LOSS / 100:
        fails.append(f'日亏超{MAX_DAILY_LOSS}%')
    if dtrades >= MAX_DAILY_TRADES:
        fails.append(f'日交易{dtrades}次上限')
    if closses >= 3:
        fails.append(f'连亏{closses}冷却')
    if hour < 1:
        fails.append('凌晨休整')
    if atr <= 0 or atr > 10000:
        fails.append(f'ATR={atr:.0f}异常')
    return len(fails) == 0, '; '.join(fails) if fails else 'ALL PASS'

def _calc_lot(balance, atr, cwins, closses):
    """SDP方式: 风险1%, ATR自适应仓位"""
    risk_amount = balance * RISK_PERCENT / 100.0
    sl_distance = atr * 2.0
    tick_value = 0.01
    raw_lot = risk_amount / (sl_distance * tick_value * 100)
    lot = max(0.01, min(0.1, round(raw_lot, 2)))
    if closses >= 2: lot = max(0.01, lot * 0.5)
    if closses >= 4: lot = 0.01
    if cwins >= 3: lot = min(0.1, lot * 1.5)
    return lot

def _send_trade(direction, lot, price, atr):
    """SDP方式下单: 2ATR止损, 2R止盈"""
    import MetaTrader5 as mt5
    ot = mt5.ORDER_TYPE_BUY if direction == 'BUY' else mt5.ORDER_TYPE_SELL
    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick: return False
    
    order_price = tick.ask if direction=='BUY' else tick.bid
    sl_distance = atr * 2.0
    tp_distance = sl_distance * TP_R_MULTIPLE
    
    sl = order_price - sl_distance if direction=='BUY' else order_price + sl_distance
    tp = order_price + tp_distance if direction=='BUY' else order_price - tp_distance
    sl = round(sl, 2)
    tp = round(tp, 2)
    
    for fill in [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]:
        req = {
            'action': mt5.TRADE_ACTION_DEAL, 'symbol': SYMBOL, 'volume': lot,
            'type': ot, 'price': order_price, 'sl': sl, 'tp': tp,
            'deviation': 500, 'magic': 20260705,
            'comment': 'Goldstrategy Guild',
            'type_time': mt5.ORDER_TIME_GTC, 'type_filling': fill,
        }
        res = mt5.order_send(req)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            log(f'[SDP] {direction} {lot} @ ${order_price:.2f} SL=${sl:.2f}(-${sl_distance:.0f}) TP=${tp:.2f}(+${tp_distance:.0f})')
            return True
        elif res and res.retcode == 10027:
            if fill == mt5.ORDER_FILLING_RETURN:
                req2 = dict(req)
                req2.pop('sl', None)
                req2.pop('tp', None)
                res2 = mt5.order_send(req2)
                if res2 and res2.retcode == mt5.TRADE_RETCODE_DONE:
                    log(f'[SDP] {direction} {lot} (no SL/TP) @ ${order_price:.2f}')
                    return True
                log(f'[X] Order failed: {res2.comment if res2 else "no response"}')
    return False

def _manage_position(pos, atr):
    """SDP方式管理持仓: 保本+追踪"""
    import MetaTrader5 as mt5
    for p in pos:
        entry = float(p.price_open)
        current = float(p.price_current)
        is_buy = p.type == 0
        dist = (current - entry) if is_buy else (entry - current)
        r_distance = atr * 2.0
        
        # 保本 (0.5R)
        if dist > r_distance * 0.5:
            be_sl = entry + 5 if is_buy else entry - 5
            be_sl = round(be_sl, 2)
            if (is_buy and float(p.sl) < be_sl) or (not is_buy and float(p.sl) > be_sl):
                req = {'action': mt5.TRADE_ACTION_SLTP, 'symbol': SYMBOL,
                       'position': p.ticket, 'sl': be_sl, 'tp': p.tp}
                r = mt5.order_send(req)
                if r and r.retcode == mt5.TRADE_RETCODE_DONE:
                    log(f'[SDP] Breakeven SL @ ${be_sl:.2f} (profit=${dist:.0f})')
        
        # 追踪 (1R后收紧)
        if dist > r_distance * 1.0:
            trail_sl = current - r_distance * 0.5 if is_buy else current + r_distance * 0.5
            trail_sl = round(trail_sl, 2)
            if (is_buy and trail_sl > float(p.sl)) or (not is_buy and trail_sl < float(p.sl)):
                req = {'action': mt5.TRADE_ACTION_SLTP, 'symbol': SYMBOL,
                       'position': p.ticket, 'sl': trail_sl, 'tp': p.tp}
                r = mt5.order_send(req)
                if r and r.retcode == mt5.TRADE_RETCODE_DONE:
                    log(f'[SDP] Trail SL @ ${trail_sl:.2f} (lock ${dist-r_distance*0.5:.0f})')

# ───────── 入口 ─────────
if __name__ == '__main__':
    run_daemon()
