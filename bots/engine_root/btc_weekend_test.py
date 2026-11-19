"""
金策宗师团 — BTCUSD 周末测试运行器
每30分钟自动分析一次, 记录结果, 生成仪表盘
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

# 设置CRYPTO模式
os.environ['MARKET_TYPE'] = 'CRYPTO'

LOG_DIR = "E:/GoldstrategyEngine/logs"
DATA_DIR = "E:/GoldstrategyEngine/data"
CYCLE_LOG = f"{LOG_DIR}/btc_test_cycles.json"
DASHBOARD_DIR = "C:/Users/ASUS/WorkBuddy/2026-07-03-21-37-46/logs"


class BTCWeekendTester:
    """BTCUSD 周末自动测试器"""

    def __init__(self):
        self.cycle_count = 0
        self.results = deque(maxlen=100)  # 保留最近100次分析
        self.start_time = datetime.now()
        self._ensure_dirs()

    def _ensure_dirs(self):
        for d in [LOG_DIR, DATA_DIR, DASHBOARD_DIR]:
            os.makedirs(d, exist_ok=True)

    def fetch_mt5_data(self) -> pd.DataFrame:
        """从MT5获取最新BTCUSD数据"""
        import MetaTrader5 as mt5

        if not mt5.initialize():
            print(f"  ❌ MT5初始化失败")
            return None

        # 检查是否需要登录
        info = mt5.account_info()
        if info is None:
            authorized = mt5.login(60043976, password="", server="TradeMaxGlobal-Demo")
            if not authorized:
                print(f"  ❌ MT5登录失败")
                mt5.shutdown()
                return None

        # 激活品种
        mt5.symbol_select("BTCUSD", True)

        # 获取H1数据
        rates = mt5.copy_rates_from_pos("BTCUSD", mt5.TIMEFRAME_H1, 0, 200)
        mt5.shutdown()

        if rates is None or len(rates) == 0:
            print(f"  ❌ 无法获取BTCUSD数据")
            return None

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)

        # 保存最新数据
        df.to_pickle(f"{DATA_DIR}/btc_data.pkl")

        return df

    def analyze(self, df: pd.DataFrame) -> dict:
        """执行完整分析"""
        from optimized.factor_library_v2 import MegaFactorLibrary
        from risk.risk_manager import RiskManager

        price = float(df['close'].iloc[-1])
        atr = float((df['high'] - df['low']).rolling(14).mean().dropna().iloc[-1])

        # 210因子
        mfl = MegaFactorLibrary()
        results = mfl.compute_all(df)
        buy = sum(1 for r in results.values() if r.direction == 'BUY')
        sell = sum(1 for r in results.values() if r.direction == 'SELL')
        sent = mfl.get_market_sentiment(results)
        bs = sum(abs(r.zscore) for r in results.values() if r.direction == 'BUY')
        ss = sum(abs(r.zscore) for r in results.values() if r.direction == 'SELL')

        # 决策
        total = bs + ss
        if total > 0:
            bp = bs / total * 100
            if bp > 55:
                direction = 'BUY'
                confidence = f'多头{bp:.0f}%'
            elif (ss / total * 100) > 55:
                direction = 'SELL'
                confidence = f'空头{ss/total*100:.0f}%'
            else:
                direction = 'HOLD'
                confidence = '多空均衡'
        else:
            direction = 'HOLD'
            confidence = '无信号'

        # 风控
        rm = RiskManager()
        rc = rm.check_all({
            'balance': 1000, 'equity': 1000, 'atr': atr,
            'current_price': price, 'spread': 1400,
            'entry': price, 'sl': price - atr * 0.5, 'tp': price + atr * 1.5,
            'direction': direction, 'current_hour': datetime.now().hour,
            'lot_size': 0.01,
        })

        p = sum(1 for v in rc['checks'].values() if v)
        t = len(rc['checks'])

        return {
            'timestamp': datetime.now().isoformat(),
            'price': round(price, 2),
            'atr': round(atr, 2),
            'buy_factors': buy,
            'sell_factors': sell,
            'sentiment': sent['sentiment'],
            'buy_score': round(bs, 1),
            'sell_score': round(ss, 1),
            'direction': direction,
            'confidence': confidence,
            'risk_pass': p,
            'risk_total': t,
            'risk_all_pass': rc['all_pass'],
        }

    def generate_report(self, result: dict):
        """生成分析报告"""
        now = datetime.now()
        elapsed = (now - self.start_time).total_seconds()
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)

        return f"""
╔══════════════════════════════════════════════╗
║   BTCUSD 周末测试 第{self.cycle_count}轮                    ║
║   {now.strftime('%Y-%m-%d %H:%M:%S')}              ║
╠══════════════════════════════════════════════╣
║ 当前价    ${result['price']:>8,.0f}                        ║
║ ATR       ${result['atr']:>6,.0f}                         ║
╠══════════════════════════════════════════════╣
║ 因子分析  {result['buy_factors']}买入 / {result['sell_factors']}卖出              ║
║ 情绪     {result['sentiment']:>8s}                         ║
║ 决策     {result['direction']:>4s} ({result['confidence']:<12s})              ║
╠══════════════════════════════════════════════╣
║ 风控     {'✅ 通过' if result['risk_all_pass'] else '⏸️ 拦截'} ({result['risk_pass']}/{result['risk_total']})                      ║
╠══════════════════════════════════════════════╣
║ 运行时长 {hours}小时{minutes}分钟                             ║
║ 分析轮次 {self.cycle_count}                                    ║
╚══════════════════════════════════════════════╝"""

    def update_dashboard(self, result: dict):
        """更新仪表盘"""
        from optimized.dashboard import DashboardGenerator
        dg = DashboardGenerator(output_dir=DASHBOARD_DIR)
        dg.generate({
            'market': {'price': result['price'], 'regime': result['sentiment']},
            'signals': {
                'buy_score': result['buy_score'],
                'sell_score': result['sell_score'],
                'direction': result['direction'],
            },
            'risk': {'all_pass': result['risk_all_pass'], 'checks': {}},
            'performance': {
                'balance': 1000,
                'win_rate': f'测试{self.cycle_count}轮',
                'sharpe': 0,
                'max_drawdown': '0%',
            },
            'evolution': {
                'count': self.cycle_count,
                'accepted': sum(1 for r in self.results if r.get('risk_all_pass')),
                'pool_size': 1,
            },
        })

    def save_results(self):
        """保存测试结果"""
        data = {
            'start_time': self.start_time.isoformat(),
            'total_cycles': self.cycle_count,
            'results': list(self.results),
        }
        with open(CYCLE_LOG, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def single_cycle(self) -> bool:
        """执行单次分析周期"""
        self.cycle_count += 1
        print(f"\n[{self.cycle_count}] {datetime.now().strftime('%H:%M:%S')} 分析中...")

        # 获取数据
        df = self.fetch_mt5_data()
        if df is None:
            print(f"  ⚠️ 使用缓存数据...")
            try:
                df = pd.read_pickle(f"{DATA_DIR}/btc_data.pkl")
            except:
                print(f"  ❌ 无可用数据")
                return False

        # 分析
        try:
            result = self.analyze(df)
            self.results.append(result)
        except Exception as e:
            print(f"  ❌ 分析失败: {e}")
            return False

        # 报告和仪表盘
        report = self.generate_report(result)
        print(report)
        self.update_dashboard(result)
        self.save_results()

        return True

    def run_forever(self, interval_minutes: int = 30):
        """持续运行"""
        print(f"\n🚀 BTCUSD 周末测试启动")
        print(f"   间隔: 每{interval_minutes}分钟")
        print(f"   开始: {self.start_time.strftime('%Y-%m-%d %H:%M')}")
        print(f"   仪表盘: {DASHBOARD_DIR}/dashboard.html")
        print()

        self.single_cycle()  # 立即跑第一轮

        while True:
            try:
                time.sleep(interval_minutes * 60)
                self.single_cycle()
            except KeyboardInterrupt:
                print(f"\n🛑 用户中断")
                print(f"   共运行 {self.cycle_count} 轮")
                print(f"   结果已保存: {CYCLE_LOG}")
                break
            except Exception as e:
                print(f"  ❌ 循环异常: {e}")
                time.sleep(60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--interval', type=int, default=30, help='分析间隔(分钟)')
    parser.add_argument('--once', action='store_true', help='只跑一轮')
    args = parser.parse_args()

    tester = BTCWeekendTester()

    if args.once:
        tester.single_cycle()
    else:
        tester.run_forever(args.interval)
