"""
金策宗师团 — 24小时自动交易机器人 (Demo)
像一个真操盘手一样坐在电脑前, 持续盯盘, 自动交易
"""

import sys
import os
import time
import json
import warnings
import numpy as np
import pandas as pd
from datetime import datetime
from collections import deque

warnings.filterwarnings('ignore')

# ─── 配置 ────────────────────────────
MARKET = "CRYPTO"       # CRYPTO / FOREX
SYMBOL = "BTCUSD"
INTERVAL = 60           # 每秒检查一次 (高频)
MIN_TRADE_INTERVAL = 300  # 同一方向至少等5分钟再开仓
MAX_SPREAD = 5000       # BTC最大点差
LOT_SIZE = 0.01
ACCOUNT_BALANCE = 1000
RISK_PCT = 0.5          # 单笔风险0.5%
LOG_FILE = "E:/GoldstrategyEngine/logs/auto_trade_log.csv"
DASHBOARD_DIR = "C:/Users/ASUS/WorkBuddy/2026-07-03-21-37-46/logs"

os.environ['MARKET_TYPE'] = MARKET


class AutoTrader:
    """24小时自动交易机器人"""

    def __init__(self):
        self.cycles = 0
        self.last_trade_time = { "BUY": 0, "SELL": 0 }
        self.trades = []
        self.start_time = datetime.now()
        self.mt5_connected = False
        self._init_log()
        print(f"🤖 金策宗师团 自动交易启动")
        print(f"   品种: {SYMBOL} | 账户: TradeMaxGlobal-Demo")
        print(f"   手数: {LOT_SIZE} | 单笔风险: {RISK_PCT}%")
        print(f"   开始: {self.start_time.strftime('%Y-%m-%d %H:%M')}")
        print()

    def _init_log(self):
        """初始化CSV日志"""
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        if not os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'w') as f:
                f.write("time,price,direction,buy_factors,sell_factors,sentiment,"
                       "risk_pass,risk_total,executed,profit,balance\n")

    def _connect_mt5(self):
        """连接MT5"""
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return None
        info = mt5.account_info()
        if info is None:
            mt5.login(60043976, password="", server="TradeMaxGlobal-Demo")
        mt5.symbol_select(SYMBOL, True)
        return mt5

    def _get_data(self, mt5):
        """获取最新数据"""
        rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M1, 0, 200)
        if rates is None:
            return None
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        return df

    def _get_positions(self, mt5):
        """获取当前持仓"""
        pos = mt5.positions_get(symbol=SYMBOL)
        if pos and len(pos) > 0:
            p = pos[0]
            return {
                "ticket": p.ticket,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "price": p.price_open,
                "profit": p.profit,
                "sl": p.sl,
                "tp": p.tp,
            }
        return None

    def _execute_trade(self, mt5, direction: str, price: float, atr: float):
        """执行交易 (Demo真实下单)"""
        import MetaTrader5 as mt5lib
        
        sl = price - atr * 0.5 if direction == "BUY" else price + atr * 0.5
        tp = price + atr * 1.5 if direction == "BUY" else price - atr * 1.5
        
        order_type = mt5lib.ORDER_TYPE_BUY if direction == "BUY" else mt5lib.ORDER_TYPE_SELL
        tick = mt5lib.symbol_info_tick(SYMBOL)
        if tick is None:
            return None
        
        request = {
            "action": mt5lib.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": LOT_SIZE,
            "type": order_type,
            "price": tick.ask if direction == "BUY" else tick.bid,
            "sl": sl,
            "tp": tp,
            "deviation": 50,
            "magic": 20260704,
            "comment": "Goldstrategy Guild",
            "type_time": mt5lib.ORDER_TIME_GTC,
            "type_filling": mt5lib.ORDER_FILLING_IOC,
        }
        
        result = mt5lib.order_send(request)
        if result and result.retcode == mt5lib.TRADE_RETCODE_DONE:
            print(f"\n  ✅ 成交! #{result.order} {direction} 0.01手 @ ${price:,.0f}")
            self.last_trade_time[direction] = time.time()
            return {
                "ticket": result.order,
                "direction": direction,
                "price": price,
                "sl": sl,
                "tp": tp,
            }
        else:
            err = result.comment if result else "未知错误"
            print(f"\n  ❌ 下单失败: {err}")
            return None

    def _close_position(self, mt5, position: dict):
        """平仓"""
        import MetaTrader5 as mt5lib
        tick = mt5lib.symbol_info_tick(SYMBOL)
        if tick is None:
            return
        
        close_type = mt5lib.ORDER_TYPE_SELL if position["type"] == "BUY" else mt5lib.ORDER_TYPE_BUY
        close_price = tick.bid if position["type"] == "BUY" else tick.ask
        
        request = {
            "action": mt5lib.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": position["volume"],
            "type": close_type,
            "position": position["ticket"],
            "price": close_price,
            "deviation": 50,
            "magic": 20260704,
        }
        
        result = mt5lib.order_send(request)
        if result and result.retcode == mt5lib.TRADE_RETCODE_DONE:
            print(f"\n  ✅ 平仓! {position['type']} 盈利=${position['profit']:.2f}")
            return True
        return False

    def _update_dashboard(self, state: dict):
        """更新仪表盘"""
        from optimized.dashboard import DashboardGenerator
        dg = DashboardGenerator(output_dir=DASHBOARD_DIR)
        dg.generate({
            'market': {'price': state.get('price', 0), 'regime': state.get('sentiment', 'N/A')},
            'signals': {
                'buy_score': state.get('buy_score', 0),
                'sell_score': state.get('sell_score', 0),
                'direction': state.get('direction', 'NONE'),
            },
            'risk': {'all_pass': state.get('risk_pass', False), 'checks': {}},
            'performance': {
                'balance': state.get('balance', ACCOUNT_BALANCE),
                'win_rate': f'{len(self.trades)}笔交易',
                'sharpe': 0,
                'max_drawdown': 'Demo',
            },
            'evolution': {
                'count': self.cycles,
                'accepted': sum(1 for t in self.trades if t.get('profit', 0) > 0),
                'pool_size': 1,
            },
        })

    def _log_trade(self, entry: dict):
        """写日志"""
        self.trades.append(entry)
        with open(LOG_FILE, 'a') as f:
            f.write(f"{entry['time']},{entry['price']},{entry['direction']},"
                   f"{entry['buy']},{entry['sell']},{entry['sentiment']},"
                   f"{entry['risk_pass']}/{entry['risk_total']},"
                   f"{entry['executed']},{entry.get('profit', 0)},{entry.get('balance', ACCOUNT_BALANCE)}\n")

    def run(self):
        """主循环 — 持续运行"""
        while True:
            try:
                self._cycle()
            except KeyboardInterrupt:
                print(f"\n🛑 用户停止")
                print(f"   运行: {(datetime.now()-self.start_time).total_seconds()/60:.0f}分钟")
                print(f"   交易: {len(self.trades)}笔")
                break
            except Exception as e:
                print(f"  ❌ 循环异常: {e}")
                time.sleep(5)

    def _cycle(self):
        """单次循环"""
        self.cycles += 1
        now = datetime.now()
        timestamp = now.strftime("%H:%M:%S")

        # 连接MT5
        mt5 = self._connect_mt5()
        if mt5 is None:
            print(f"[{timestamp}] ❌ MT5连接失败, 5秒后重试")
            time.sleep(5)
            return

        # 获取数据
        df = self._get_data(mt5)
        if df is None or len(df) < 50:
            mt5.shutdown()
            time.sleep(1)
            return

        price = float(df['close'].iloc[-1])
        atr = float((df['high'] - df['low']).rolling(14).mean().dropna().iloc[-1])

        # 检查当前持仓
        position = self._get_positions(mt5)

        # 210因子分析
        from optimized.factor_library_v2 import MegaFactorLibrary
        from risk.risk_manager import RiskManager
        
        mfl = MegaFactorLibrary()
        results = mfl.compute_all(df)
        buy = sum(1 for r in results.values() if r.direction == 'BUY')
        sell = sum(1 for r in results.values() if r.direction == 'SELL')
        sent = mfl.get_market_sentiment(results)
        bs = sum(abs(r.zscore) for r in results.values() if r.direction == 'BUY')
        ss = sum(abs(r.zscore) for r in results.values() if r.direction == 'SELL')

        # 决策
        total = bs + ss
        direction = 'HOLD'
        if total > 0:
            if bs / total > 0.55:
                direction = 'BUY'
            elif ss / total > 0.55:
                direction = 'SELL'

        # 风控
        risk = RiskManager()
        rc = risk.check_all({
            'balance': ACCOUNT_BALANCE, 'equity': ACCOUNT_BALANCE, 'atr': atr,
            'current_price': price, 'spread': 1400,
            'entry': price, 'sl': price - atr * 0.5, 'tp': price + atr * 1.5,
            'direction': direction, 'current_hour': now.hour,
            'lot_size': LOT_SIZE,
        })
        p = sum(1 for v in rc['checks'].values() if v)
        t = len(rc['checks'])

        should_trade = (direction != 'HOLD' and rc['all_pass'] 
                        and position is None
                        and time.time() - self.last_trade_time[direction] > MIN_TRADE_INTERVAL)

        # 执行交易
        executed = False
        trade = {
            'time': now.isoformat(), 'price': price,
            'direction': direction, 'buy': buy, 'sell': sell,
            'sentiment': sent['sentiment'],
            'risk_pass': p, 'risk_total': t,
            'executed': False, 'profit': 0, 'balance': ACCOUNT_BALANCE,
        }

        if should_trade:
            result = self._execute_trade(mt5, direction, price, atr)
            if result:
                trade['executed'] = True
                executed = True
                print(f"  ✅ 开仓: {direction} 0.01手 BTCUSD @ ${price:,.0f}")

        # 管理持仓
        if position:
            if position['profit'] > 0:
                print(f"  💰 浮动盈利: ${position['profit']:.2f}")
            elif position['profit'] < -5:
                print(f"  ⚠️ 止损中: ${position['profit']:.2f}")

        # 每60秒打印一次状态
        if self.cycles % 60 == 0 or executed:
            elapsed = (now - self.start_time).total_seconds() / 60
            print(f"[{timestamp}] ${price:,.0f} | {buy}多/{sell}空 | "
                  f"{'📈' if direction=='BUY' else '📉' if direction=='SELL' else '⏸️'} {direction} | "
                  f"风控{p}/{t} | 运行{elapsed:.0f}分 | {len(self.trades)}笔交易")

        # 更新日志和仪表盘
        self._log_trade(trade)
        self._update_dashboard({
            'price': price, 'sentiment': sent['sentiment'],
            'buy_score': round(bs, 1), 'sell_score': round(ss, 1),
            'direction': direction, 'risk_pass': rc['all_pass'],
            'balance': ACCOUNT_BALANCE,
        })

        mt5.shutdown()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    trader = AutoTrader()
    trader.run()
