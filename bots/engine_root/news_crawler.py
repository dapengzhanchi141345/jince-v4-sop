#!/usr/bin/env python3
"""
金策·进化营 - 财经新闻爬虫模块（简化版，无需BeautifulSoup）
每日定时爬取财经新闻，解析关键事件，生成新闻摘要
"""

import os
import sys
import json
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import requests

# 配置日志
LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'news_crawler.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('news_crawler')

class NewsCrawler:
    """财经新闻爬虫（简化版）"""

    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.news_dir = self.base_dir / 'data' / 'news'
        self.news_dir.mkdir(parents=True, exist_ok=True)
        self.seen_hashes = self._load_seen_hashes()

        # 关键事件关键词
        self.important_keywords = [
            '利率', '非农', 'CPI', 'GDP', 'PMI',
            'Fed', '美联储', '央行', '通胀', '就业',
            'NFP', 'Consumer Price', 'Industrial Production',
            '利率决议', '加息', '降息', 'QE', 'QT'
        ]

    def _load_seen_hashes(self) -> set:
        """加载已处理新闻的哈希"""
        hash_file = self.news_dir / 'seen_hashes.json'
        if hash_file.exists():
            try:
                with open(hash_file, 'r', encoding='utf-8') as f:
                    return set(json.load(f))
            except:
                pass
        return set()

    def _save_seen_hashes(self):
        """保存已处理新闻的哈希"""
        hash_file = self.news_dir / 'seen_hashes.json'
        with open(hash_file, 'w', encoding='utf-8') as f:
            json.dump(list(self.seen_hashes), f, ensure_ascii=False, indent=2)

    def _calculate_hash(self, title: str, time: str) -> str:
        """计算新闻哈希，用于去重"""
        content = f"{title}:{time}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def _calculate_importance(self, title: str) -> str:
        """计算新闻重要性"""
        for kw in self.important_keywords:
            if kw in title:
                return 'high'
        return 'medium'

    def _extract_categories(self, title: str) -> List[str]:
        """提取新闻分类"""
        categories = []
        if any(kw in title for kw in ['美圆', 'USD', '美元']):
            categories.append('USD')
        if any(kw in title for kw in ['欧元', 'EUR']):
            categories.append('EUR')
        if any(kw in title for kw in ['英镑', 'GBP']):
            categories.append('GBP')
        if any(kw in title for kw in ['日元', 'JPY']):
            categories.append('JPY')
        if any(kw in title for kw in ['黄金', 'XAU', 'gold']):
            categories.append('Gold')
        if any(kw in title for kw in ['原油', 'Oil']):
            categories.append('Oil')
        if any(kw in title for kw in ['比特币', 'BTC']):
            categories.append('Crypto')
        if any(kw in title for kw in ['利率', 'Fed', '美联储', '央行']):
            categories.append('Monetary')
        if any(kw in title for kw in ['非农', '就业', 'NFP']):
            categories.append('Employment')
        if any(kw in title for kw in ['CPI', '通胀']):
            categories.append('Inflation')
        return categories if categories else ['General']

    def crawl_simulated(self) -> List[Dict]:
        """模拟新闻数据（用于测试）"""
        now = datetime.now()
        news_list = []

        # 模拟今日重要新闻
        simulated_news = [
            {
                'source': 'simulated',
                'title': f'【{now.strftime("%m-%d")}】美联储主席鲍威尔讲话：通胀压力仍需关注，加息节奏将视数据而定',
                'time': now.isoformat(),
                'importance': 'high',
                'categories': ['Monetary', 'USD'],
                'hash': self._calculate_hash('鲍威尔讲话', now.isoformat())
            },
            {
                'source': 'simulated',
                'title': f'【{now.strftime("%m-%d")}】美国9月CPI同比上涨3.2%，预期3.1%，核心CPI同比上涨4.0%',
                'time': (now - timedelta(hours=2)).isoformat(),
                'importance': 'high',
                'categories': ['Inflation', 'USD'],
                'hash': self._calculate_hash('美国CPI数据', now.isoformat())
            },
            {
                'source': 'simulated',
                'title': f'【{now.strftime("%m-%d")}】EURUSD跌破1.08支撑位，技术分析显示可能进一步下行至1.075',
                'time': (now - timedelta(hours=1)).isoformat(),
                'importance': 'medium',
                'categories': ['EUR', 'USD'],
                'hash': self._calculate_hash('EURUSD技术分析', now.isoformat())
            },
            {
                'source': 'simulated',
                'title': f'【{now.strftime("%m-%d")}】黄金突破2000美元关口，避险情绪升温',
                'time': (now - timedelta(minutes=30)).isoformat(),
                'importance': 'high',
                'categories': ['Gold'],
                'hash': self._calculate_hash('黄金突破2000', now.isoformat())
            },
            {
                'source': 'simulated',
                'title': f'【{now.strftime("%m-%d")}】美元指数DXY跌破104，非美货币普遍上涨',
                'time': (now - timedelta(minutes=15)).isoformat(),
                'importance': 'medium',
                'categories': ['USD'],
                'hash': self._calculate_hash('美元指数下跌', now.isoformat())
            }
        ]

        for news in simulated_news:
            if news['hash'] not in self.seen_hashes:
                news_list.append(news)
                self.seen_hashes.add(news['hash'])

        self._save_seen_hashes()
        logger.info(f"模拟新闻生成: {len(news_list)} 条")

        return news_list

    def crawl_all(self) -> List[Dict]:
        """爬取所有新闻源"""
        # 使用模拟数据（因为没有API key）
        news_list = self.crawl_simulated()

        # 保存新闻
        if news_list:
            self._save_news(news_list)

        return news_list

    def _save_news(self, news_list: List[Dict]):
        """保存新闻到JSON文件"""
        today = datetime.now().strftime('%Y-%m-%d')
        news_file = self.news_dir / f'{today}.json'

        existing_news = []
        if news_file.exists():
            try:
                with open(news_file, 'r', encoding='utf-8') as f:
                    existing_news = json.load(f)
            except:
                pass

        all_news = news_list + existing_news

        # 只保留最近7天
        cutoff_date = datetime.now() - timedelta(days=7)
        filtered_news = []
        for news in all_news:
            try:
                news_time = datetime.fromisoformat(news['time'].replace('Z', '+00:00'))
                if news_time > cutoff_date:
                    filtered_news.append(news)
            except:
                filtered_news.append(news)

        with open(news_file, 'w', encoding='utf-8') as f:
            json.dump(filtered_news, f, ensure_ascii=False, indent=2)

        logger.info(f"新闻已保存: {len(filtered_news)} 条 -> {news_file}")

    def get_daily_summary(self) -> Dict:
        """生成每日新闻摘要"""
        today = datetime.now().strftime('%Y-%m-%d')
        news_file = self.news_dir / f'{today}.json'

        if not news_file.exists():
            return {'date': today, 'total': 0, 'high': 0, 'medium': 0, 'low': 0, 'news': []}

        try:
            with open(news_file, 'r', encoding='utf-8') as f:
                news_list = json.load(f)
        except:
            return {'date': today, 'total': 0, 'high': 0, 'medium': 0, 'low': 0, 'news': []}

        high_count = sum(1 for n in news_list if n.get('importance') == 'high')
        medium_count = sum(1 for n in news_list if n.get('importance') == 'medium')
        low_count = sum(1 for n in news_list if n.get('importance') == 'low')

        high_news = [n for n in news_list if n.get('importance') == 'high'][:10]

        return {
            'date': today,
            'total': len(news_list),
            'high': high_count,
            'medium': medium_count,
            'low': low_count,
            'high_priority_news': high_news,
            'all_news': news_list[:50]
        }

def main():
    import argparse

    parser = argparse.ArgumentParser(description='财经新闻爬虫')
    parser.add_argument('--crawl', action='store_true', help='爬取新闻')
    parser.add_argument('--summary', action='store_true', help='生成每日摘要')
    parser.add_argument('--auto', action='store_true', help='自动模式')

    args = parser.parse_args()

    crawler = NewsCrawler()

    if args.crawl:
        news_list = crawler.crawl_all()
        print(f"✅ 爬取完成: {len(news_list)} 条新新闻")
        for news in news_list[:5]:
            print(f"   [{news['importance']}] {news['title'][:50]}...")

    elif args.summary:
        summary = crawler.get_daily_summary()
        print(f"📊 每日新闻摘要 ({summary['date']})")
        print(f"   总新闻: {summary['total']} 条")
        print(f"   高重要性: {summary['high']} 条")
        print(f"   中重要性: {summary['medium']} 条")
        print(f"   低重要性: {summary['low']} 条")

        if summary['high_priority_news']:
            print(f"\n🔥 高重要性新闻:")
            for news in summary['high_priority_news']:
                print(f"   - {news['title'][:60]}...")
                print(f"     类别: {', '.join(news['categories'])}")

    elif args.auto:
        news_list = crawler.crawl_all()
        summary = crawler.get_daily_summary()
        print(f"✅ 自动模式完成")
        print(f"   新新闻: {len(news_list)} 条")
        print(f"   总新闻: {summary['total']} 条")
        print(f"   高重要性: {summary['high']} 条")

    else:
        parser.print_help()

if __name__ == '__main__':
    main()
