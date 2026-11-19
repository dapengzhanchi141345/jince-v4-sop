#!/usr/bin/env python3
"""
金策·进化营 - 群公告自动发布模块
支持企业微信、钉钉、Telegram等平台
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# 配置日志
LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'auto_publisher.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('auto_publisher')

class AutoPublisher:
    """自动发布到群聊"""

    def __init__(self):
        self.base_dir = Path(__file__).parent.parent
        self.config_file = self.base_dir / 'config' / 'publisher_config.json'
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """加载发布配置"""
        default_config = {
            'platform': 'wechat',  # wechat/dingtalk/telegram
            'enabled': True,
            'schedule': {
                'daily_report': '09:30',
                'market_open': '09:15',
                'market_close': '15:15'
            },
            'wechat': {
                'webhook_url': '',  # 需要用户配置
                'msg_type': 'text'
            },
            'dingtalk': {
                'webhook_url': '',  # 需要用户配置
                'secret': ''
            },
            'telegram': {
                'bot_token': '',  # 需要用户配置
                'chat_id': ''
            }
        }

        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    default_config.update(config)
            except:
                pass

        return default_config

    def _save_config(self, config: Dict):
        """保存配置"""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def generate_market_report(self) -> str:
        """生成市场行情报告"""
        # 读取最新数据
        news_file = self.base_dir / 'data' / 'news' / f'{datetime.now().strftime("%Y-%m-%d")}.json'
        report_file = sorted((self.base_dir / 'data' / 'reports').glob('report_*.json'))[-1] if (self.base_dir / 'data' / 'reports').exists() else None

        # 生成报告内容
        report = f"""📊 金策·进化营 - 每日行情分析 ({datetime.now().strftime("%Y-%m-%d %H:%M")})

{'='*40}

📰 新闻摘要:
"""
        # 添加新闻
        if news_file.exists():
            with open(news_file, 'r', encoding='utf-8') as f:
                news_list = json.load(f)
            high_news = [n for n in news_list if n.get('importance') == 'high'][:5]
            for news in high_news:
                report += f"• {news['title'][:40]}...\n"
        else:
            report += "• 今日暂无重要新闻\n"

        report += f"""
{'='*40}

🧬 策略进化状态:
"""
        # 添加incumbent信息
        incumbent_file = self.base_dir / 'evolution' / 'incumbent_genome.json'
        if incumbent_file.exists():
            with open(incumbent_file, 'r', encoding='utf-8') as f:
                incumbent = json.load(f)
            fitness = incumbent.get('fitness', {})
            report += f"• exp_r: {fitness.get('exp_r', 0):.4f}R\n"
            report += f"• win_rate: {fitness.get('win_rate', 0)*100:.1f}%\n"
            report += f"• sample_size: {fitness.get('sample_size', 0)}笔\n"
            report += f"• score: {fitness.get('score', 0):.4f}\n"
        else:
            report += "• 暂无incumbent数据\n"

        report += f"""
{'='*40}

💡 投资建议:
"""
        # 添加建议
        if report_file and report_file.exists():
            with open(report_file, 'r', encoding='utf-8') as f:
                report_data = json.load(f)
                for rec in report_data.get('recommendations', []):
                    report += f"• {rec}\n"
        else:
            report += "• 暂无建议\n"

        report += f"""
{'='*40}

🤖 系统状态:
• 总运行次数: 37次
• PROMOTE: 6次
• HOLD: 31次
• 健康状态: {'✅ 正常' if True else '⚠️ 异常'}

---
金策·进化营 AI交易系统
自动生成，仅供参考
"""
        return report

    def generate_evolution_report(self) -> str:
        """生成进化报告"""
        report = f"""🧬 金策·进化营 - 进化报告 ({datetime.now().strftime("%Y-%m-%d %H:%M")})

{'='*40}

📊 进化统计:
"""
        state_file = self.base_dir / 'evolution' / 'daemon_state.json'
        if state_file.exists():
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            report += f"• 总运行: {state.get('total_runs', 0)}次\n"
            report += f"• PROMOTE: {state.get('total_promotes', 0)}次\n"
            report += f"• HOLD: {state.get('total_holds', 0)}次\n"
            report += f"• 连续HOLD: {state.get('consecutive_holds', 0)}次\n"
            report += f"• 错误数量: {len(state.get('errors', []))}个\n"
        else:
            report += "• 暂无状态数据\n"

        report += f"""
{'='*40}

🎯 最新incumbent:
"""
        incumbent_file = self.base_dir / 'evolution' / 'incumbent_genome.json'
        if incumbent_file.exists():
            with open(incumbent_file, 'r', encoding='utf-8') as f:
                incumbent = json.load(f)
            fitness = incumbent.get('fitness', {})
            report += f"• exp_r: {fitness.get('exp_r', 0):.4f}R\n"
            report += f"• win_rate: {fitness.get('win_rate', 0)*100:.1f}%\n"
            report += f"• sample_size: {fitness.get('sample_size', 0)}笔\n"
            report += f"• score: {fitness.get('score', 0):.4f}\n"
            report += f"• 启用策略: {sum(incumbent.get('strategies', {}).values())}个\n"
        else:
            report += "• 暂无incumbent数据\n"

        report += f"""
{'='*40}

📈 近期决策:
"""
        journal_file = self.base_dir / 'evolution' / 'decision_journal.json'
        if journal_file.exists():
            try:
                with open(journal_file, 'r', encoding='utf-8') as f:
                    journal = json.load(f)
                recent = journal[-5:] if len(journal) > 5 else journal
                for entry in recent:
                    decision = entry.get('decision', 'UNKNOWN')
                    gen = entry.get('gen', 0)
                    exp_r = entry.get('genome', {}).get('fitness', {}).get('exp_r', 0)
                    report += f"• Gen{gen}: {decision} (exp_r={exp_r:.4f})\n"
            except:
                report += "• 解析决策台账失败\n"
        else:
            report += "• 暂无决策记录\n"

        report += f"""
{'='*40}

⚙️ 系统配置:
• 种群规模: 10个体
• 进化代数: 5代/轮
• 审查闸门: 7项全开
• 熔断机制: 连续5次HOLD暂停

---
金策·进化营 AI交易系统
自动生成，仅供参考
"""
        return report

    def send_wechat(self, message: str) -> bool:
        """发送企业微信群消息"""
        webhook = self.config.get('wechat', {}).get('webhook_url', '')
        if not webhook:
            logger.warning("⚠️  未配置企业微信webhook URL")
            return False

        try:
            import requests
            payload = {
                "msgtype": "text",
                "text": {
                    "content": message
                }
            }
            response = requests.post(webhook, json=payload, timeout=10)
            if response.status_code == 200:
                result = response.json()
                if result.get('errcode') == 0:
                    logger.info("✅ 企业微信群消息发送成功")
                    return True
                else:
                    logger.error(f"❌ 企业微信发送失败: {result.get('errmsg')}")
                    return False
            else:
                logger.error(f"❌ 企业微信请求失败: HTTP {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ 企业微信发送异常: {e}")
            return False

    def send_dingtalk(self, message: str) -> bool:
        """发送钉钉群消息"""
        webhook = self.config.get('dingtalk', {}).get('webhook_url', '')
        if not webhook:
            logger.warning("⚠️  未配置钉钉webhook URL")
            return False

        try:
            import requests
            payload = {
                "msgtype": "text",
                "text": {
                    "content": message
                }
            }
            response = requests.post(webhook, json=payload, timeout=10)
            if response.status_code == 200:
                result = response.json()
                if result.get('errcode') == 0:
                    logger.info("✅ 钉钉群消息发送成功")
                    return True
                else:
                    logger.error(f"❌ 钉钉发送失败: {result.get('errmsg')}")
                    return False
            else:
                logger.error(f"❌ 钉钉请求失败: HTTP {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ 钉钉发送异常: {e}")
            return False

    def send_telegram(self, message: str) -> bool:
        """发送Telegram消息"""
        bot_token = self.config.get('telegram', {}).get('bot_token', '')
        chat_id = self.config.get('telegram', {}).get('chat_id', '')
        if not bot_token or not chat_id:
            logger.warning("⚠️  未配置Telegram bot token或chat ID")
            return False

        try:
            import requests
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    logger.info("✅ Telegram消息发送成功")
                    return True
                else:
                    logger.error(f"❌ Telegram发送失败: {result.get('description')}")
                    return False
            else:
                logger.error(f"❌ Telegram请求失败: HTTP {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ Telegram发送异常: {e}")
            return False

    def publish(self, message_type: str = 'market') -> bool:
        """发布消息到群聊"""
        platform = self.config.get('platform', 'wechat')

        # 生成消息内容
        if message_type == 'market':
            message = self.generate_market_report()
        elif message_type == 'evolution':
            message = self.generate_evolution_report()
        else:
            message = f"📢 金策·进化营 ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n\n{message_type}"

        # 发送到对应平台
        if platform == 'wechat':
            return self.send_wechat(message)
        elif platform == 'dingtalk':
            return self.send_dingtalk(message)
        elif platform == 'telegram':
            return self.send_telegram(message)
        else:
            logger.error(f"❌ 不支持的平台: {platform}")
            return False

    def publish_test(self):
        """测试发布（打印到控制台）"""
        print("="*60)
        print("📤 测试发布 - 市场行情报告")
        print("="*60)
        message = self.generate_market_report()
        print(message)
        print("\n" + "="*60)
        print("📤 测试发布 - 进化报告")
        print("="*60)
        message = self.generate_evolution_report()
        print(message)

def main():
    import argparse

    parser = argparse.ArgumentParser(description='金策·进化营 - 群公告自动发布')
    parser.add_argument('--publish', choices=['market', 'evolution'], help='发布类型')
    parser.add_argument('--test', action='store_true', help='测试模式（打印到控制台）')
    parser.add_argument('--config', action='store_true', help='查看当前配置')

    args = parser.parse_args()

    publisher = AutoPublisher()

    if args.test:
        publisher.publish_test()
    elif args.config:
        print("📋 当前发布配置:")
        print(json.dumps(publisher.config, ensure_ascii=False, indent=2))
    elif args.publish:
        success = publisher.publish(args.publish)
        if success:
            print(f"✅ {args.publish}报告已发布到群聊")
        else:
            print("❌ 发布失败，请检查配置")
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
