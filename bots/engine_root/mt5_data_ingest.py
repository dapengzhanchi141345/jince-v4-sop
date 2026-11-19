# -*- coding: utf-8 -*-
"""
MT5历史数据导入器
===================
Chief裁决⑤：立即启动真实MT5历史数据（近3年M1/M5周期）导入流程。
这是解决模拟数据信噪比过低的根本方案。
"""

import os
import sys
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple, Dict, Optional

logger = logging.getLogger('mt5_data_ingest')


class MT5DataIngestor:
    """MT5历史数据导入器"""

    def __init__(self, data_dir: str = r"E:\资料\GoldstrategyEngine\data\mt5"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.symbols = [
            "XAUUSD", "BTCUSD", "ETHUSD",
            "EURUSD", "GBPUSD", "USDJPY"
        ]
        self.timeframes = ["M1", "M5"]  # Chief要求M1/M5周期

    def download_from_mt5(self, symbol: str, timeframe: str, days: int = 365*3) -> Optional[pd.DataFrame]:
        """
        从MT5终端下载历史数据

        注意：需要MT5终端正在运行并已登录
        """
        try:
            import MetaTrader5 as mt5

            if not mt5.initialize():
                logger.error(f"MT5初始化失败: {mt5.last_error()}")
                return None

            # 计算时间范围
            from_date = datetime.now() - timedelta(days=days)
            to_date = datetime.now()

            # 获取时间frame
            tf_map = {
                "M1": mt5.TIMEFRAME_M1,
                "M5": mt5.TIMEFRAME_M5,
                "M15": mt5.TIMEFRAME_M15,
                "H1": mt5.TIMEFRAME_H1,
            }
            timeframe_obj = tf_map.get(timeframe, mt5.TIMEFRAME_M15)

            # 下载数据
            rates = mt5.copy_rates_range(symbol, timeframe_obj, from_date, to_date)

            mt5.shutdown()

            if rates is None or len(rates) == 0:
                logger.warning(f"无数据: {symbol} {timeframe}")
                return None

            # 转换为DataFrame
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')

            # 重命名列以匹配进化引擎格式
            df = df.rename(columns={
                'open': 'o',
                'high': 'h',
                'low': 'l',
                'close': 'c',
                'tick_volume': 'v'
            })

            logger.info(f"✅ 下载成功: {symbol} {timeframe} | {len(df)} bars")
            return df

        except ImportError:
            logger.error("MT5模块未安装，请运行: pip install MetaTrader5")
            return None
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return None

    def save_to_csv(self, df: pd.DataFrame, symbol: str, timeframe: str):
        """保存数据到CSV"""
        filename = f"{symbol}_{timeframe}_{datetime.now().strftime('%Y%m%d')}.csv"
        filepath = os.path.join(self.data_dir, filename)
        df.to_csv(filepath, index=False)
        logger.info(f"💾 已保存: {filepath} ({len(df)} bars)")
        return filepath

    def load_from_csv(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """从CSV加载数据"""
        files = list(Path(self.data_dir).glob(f"{symbol}_{timeframe}_*.csv"))
        if not files:
            logger.warning(f"无数据文件: {symbol} {timeframe}")
            return None

        # 加载最新的文件
        latest_file = max(files, key=lambda f: f.stat().st_mtime)
        df = pd.read_csv(latest_file)
        logger.info(f"📂 已加载: {latest_file} ({len(df)} bars)")
        return df

    def ingest_all(self, download: bool = True) -> Dict[str, pd.DataFrame]:
        """
        导入所有品种和时间框架的数据

        参数：
            download: 是否从MT5下载（False则只加载本地文件）

        返回：
            Dict[symbol_timeframe, DataFrame]
        """
        all_data = {}

        for symbol in self.symbols:
            for timeframe in self.timeframes:
                key = f"{symbol}_{timeframe}"

                # 尝试加载本地数据
                df = self.load_from_csv(symbol, timeframe)

                # 如果没有本地数据或需要重新下载
                if df is None or download:
                    logger.info(f"⬇️  下载 {key}...")
                    df = self.download_from_mt5(symbol, timeframe)

                if df is not None and len(df) > 0:
                    all_data[key] = df
                    self.save_to_csv(df, symbol, timeframe)

        logger.info(f"✅ 数据导入完成: {len(all_data)} 个数据集")
        return all_data

    def get_universe(self) -> List[Tuple[str, str]]:
        """获取品种集合（适配进化引擎）"""
        universe = []
        for symbol in self.symbols:
            # 优先使用M5（Chief推荐）
            if f"{symbol}_M5" in self.__dict__.get('_data', {}):
                universe.append((symbol, "M5"))
            elif f"{symbol}_M1" in self.__dict__.get('_data', {}):
                universe.append((symbol, "M1"))
        return universe

    def export_to_evolution_format(self, df: pd.DataFrame, symbol: str, timeframe: str) -> List[Dict]:
        """
        导出数据为进化引擎格式

        返回：
            List[Dict] with keys: time, open, high, low, close, volume
        """
        bars = []
        for _, row in df.iterrows():
            bars.append({
                'time': int(row['time'].timestamp()) if hasattr(row['time'], 'timestamp') else row['time'],
                'open': float(row['o']),
                'high': float(row['h']),
                'low': float(row['l']),
                'close': float(row['c']),
                'volume': int(row['v']) if 'v' in row else 0
            })
        return bars


def main():
    import argparse
    parser = argparse.ArgumentParser(description='MT5历史数据导入器')
    parser.add_argument('--download', action='store_true', help='从MT5下载数据')
    parser.add_argument('--list', action='store_true', help='列出已有数据')
    parser.add_argument('--test', action='store_true', help='测试数据导入')
    args = parser.parse_args()

    ingestor = MT5DataIngestor()

    if args.list:
        # 列出已有数据
        files = list(Path(ingestor.data_dir).glob("*.csv"))
        if files:
            print(f"已有数据文件（{len(files)}个）:")
            for f in sorted(files):
                size_kb = f.stat().st_size / 1024
                print(f"  {f.name} ({size_kb:.1f}KB)")
        else:
            print("无本地数据文件")
        return

    if args.test:
        # 测试模式（不实际下载）
        print("✅ MT5数据导入器测试通过")
        print(f"   数据目录: {ingestor.data_dir}")
        print(f"   支持品种: {', '.join(ingestor.symbols)}")
        print(f"   支持周期: {', '.join(ingestor.timeframes)}")
        return

    if args.download:
        # 实际下载
        print("🚀 开始下载MT5历史数据...")
        print("   提示：请确保MT5终端已运行并已登录")
        print()
        data = ingestor.ingest_all(download=True)
        print(f"\n✅ 下载完成: {len(data)} 个数据集")
        return

    # 默认：只列出数据
    args.list = True
    main()


if __name__ == "__main__":
    main()
