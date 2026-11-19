"""
MT5 连接器 — 单例模式管理 MT5 连接
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Tuple, List
import time

from config import MT5_CONFIG, TRADING_CONFIG


class MT5Connector:
    """MT5 连接管理器 (单例)"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._connected = False
        self._symbol = TRADING_CONFIG["symbol"]
        self._point = None
        self._digits = None
        self._lot_step = None

    # ─── 连接管理 ─────────────────────────

    def connect(self, server=None, login=None, password=None, path=None) -> bool:
        """连接到 MT5 终端"""
        if self._connected:
            return True

        server = server or MT5_CONFIG["server"]
        login = login or MT5_CONFIG["login"]
        password = password or MT5_CONFIG["password"]
        path = path or MT5_CONFIG["path"]

        if not mt5.initialize(path=path):
            err = mt5.last_error()
            print(f"[MT5] 初始化失败: {err}")
            return False

        if login and password:
            authorized = mt5.login(login, password=password, server=server)
            if not authorized:
                err = mt5.last_error()
                print(f"[MT5] 登录失败: {err}")
                mt5.shutdown()
                return False

        account = mt5.account_info()
        if account is None:
            print("[MT5] 无法获取账户信息")
            mt5.shutdown()
            return False

        self._connected = True
        self._init_symbol_info()

        print(f"[MT5] 连接成功 | 账户: {account.login} | 余额: {account.balance:.2f} {account.currency}")
        print(f"[MT5] 品种: {self._symbol} | 点值: {self._point} | 位数: {self._digits}")
        return True

    def disconnect(self):
        """断开 MT5 连接"""
        if self._connected:
            mt5.shutdown()
            self._connected = False
            print("[MT5] 已断开连接")

    def is_connected(self) -> bool:
        return self._connected

    def reconnect(self) -> bool:
        """重连 MT5"""
        self.disconnect()
        time.sleep(2)
        return self.connect()

    # ─── 品种信息 ─────────────────────────

    def _init_symbol_info(self):
        """初始化品种信息"""
        info = mt5.symbol_info(self._symbol)
        if info is None:
            # 尝试激活品种
            mt5.symbol_select(self._symbol, True)
            info = mt5.symbol_info(self._symbol)

        if info:
            self._point = info.point
            self._digits = info.digits
            self._lot_step = info.volume_step
            # 确保品种在报价窗口
            mt5.symbol_select(self._symbol, True)

    def get_symbol_info(self) -> dict:
        """获取品种详细信息"""
        info = mt5.symbol_info(self._symbol)
        if info is None:
            return {}
        return {
            "symbol": info.name,
            "digits": info.digits,
            "point": info.point,
            "spread": info.spread,
            "trade_mode": info.trade_mode,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "swap_long": info.swap_long,
            "swap_short": info.swap_short,
        }

    # ─── 行情数据 ─────────────────────────

    def get_rates(self, timeframe="H1", count=500) -> Optional[pd.DataFrame]:
        """获取历史K线数据"""
        tf_map = {
            "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }
        tf = tf_map.get(timeframe, mt5.TIMEFRAME_H1)

        rates = mt5.copy_rates_from_pos(self._symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            print(f"[MT5] 无法获取 {timeframe} 数据")
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        return df

    def get_tick(self) -> Optional[dict]:
        """获取最新Tick"""
        tick = mt5.symbol_info_tick(self._symbol)
        if tick is None:
            return None
        return {
            "bid": tick.bid,
            "ask": tick.ask,
            "spread": tick.ask - tick.bid,
            "time": datetime.fromtimestamp(tick.time),
        }

    # ─── 账户信息 ─────────────────────────

    def get_account_info(self) -> dict:
        """获取账户信息"""
        info = mt5.account_info()
        if info is None:
            return {}
        return {
            "login": info.login,
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "margin_free": info.margin_free,
            "margin_level": info.margin_level,
            "profit": info.profit,
            "currency": info.currency,
            "leverage": info.leverage,
        }

    def get_positions(self) -> List[dict]:
        """获取当前持仓"""
        positions = mt5.positions_get(symbol=self._symbol)
        if positions is None:
            return []
        result = []
        for pos in positions:
            result.append({
                "ticket": pos.ticket,
                "type": "BUY" if pos.type == 0 else "SELL",
                "volume": pos.volume,
                "price_open": pos.price_open,
                "sl": pos.sl,
                "tp": pos.tp,
                "profit": pos.profit,
                "swap": pos.swap,
                "magic": pos.magic,
                "comment": pos.comment,
                "time": datetime.fromtimestamp(pos.time),
            })
        return result

    def get_daily_stats(self) -> dict:
        """获取当日交易统计"""
        now = datetime.now()
        day_start = datetime(now.year, now.month, now.day)
        deals = mt5.history_deals_get(day_start, now)

        if deals is None:
            return {"trades": 0, "profit": 0.0, "loss": 0.0, "net": 0.0}

        total_profit = 0.0
        total_loss = 0.0
        trade_count = 0

        for deal in deals:
            if deal.symbol == self._symbol:
                profit = deal.profit
                if profit > 0:
                    total_profit += profit
                else:
                    total_loss += abs(profit)
                trade_count += 1

        return {
            "trades": trade_count,
            "profit": total_profit,
            "loss": total_loss,
            "net": total_profit - total_loss,
        }

    @property
    def point(self):
        return self._point

    @property
    def digits(self):
        return self._digits

    @property
    def lot_step(self):
        return self._lot_step

    @property
    def symbol(self):
        return self._symbol
