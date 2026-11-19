#!/usr/bin/env python3
"""
金策·进化营 - 自动进化调度器
整合新闻分析 + 行情分析 + 进化引擎，实现全自动闭环
"""

import os
import sys
import json
import time
import logging
import subprocess as _sp
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# 无窗口后台执行 python 脚本：避免从 pythonw/服务父进程弹出 cmd 窗口
_HIDDEN = getattr(_sp, "CREATE_NO_WINDOW", 0)


def _run_script(path, *args):
    """无窗口后台执行一个 python 脚本（不弹 cmd 窗口）。"""
    return _sp.run([sys.executable, str(path), *args], creationflags=_HIDDEN)

# 配置日志
LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'auto_evolution.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('auto_evolution')

class AutoEvolutionScheduler:
    """自动进化调度器"""

    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.evolution_dir = self.base_dir / 'evolution'
        self.news_dir = self.base_dir / 'data' / 'news'
        self.report_dir = self.base_dir / 'data' / 'reports'
        self.report_dir.mkdir(parents=True, exist_ok=True)

        # 调度配置
        self.config = {
            'news_crawl_interval': 3600,  # 每小时爬取新闻
            'evolution_interval': 1800,    # 每30分钟进化一次
            'report_interval': 14400,      # 每4小时生成报告
            'inspection_interval': 1800,   # 每30分钟巡检
            'hermes_comm_interval': 7200,  # 每2小时向chief汇报
        }

        # 上次执行时间
        self.last_news_crawl = 0
        self.last_evolution = 0
        self.last_report = 0
        self.last_inspection = 0
        self.last_hermes_comm = 0

    def run_news_crawl(self):
        """执行新闻爬取"""
        try:
            logger.info("📰 开始新闻爬取...")
            _run_script(self.base_dir / "news_crawler.py", "--auto")
            self.last_news_crawl = time.time()
            logger.info("✅ 新闻爬取完成")
        except Exception as e:
            logger.error(f"❌ 新闻爬取失败: {e}")

    def run_evolution(self):
        """执行一次进化"""
        try:
            logger.info("🧬 开始进化...")
            _run_script(self.base_dir / "evolution_daemon.py", "--once")
            self.last_evolution = time.time()
            logger.info("✅ 进化完成")
        except Exception as e:
            logger.error(f"❌ 进化失败: {e}")

    def run_inspection(self):
        """执行巡检"""
        try:
            logger.info("🔍 开始巡检...")
            _run_script(self.base_dir / "inspection_daemon.py", "--once")
            self.last_inspection = time.time()
            logger.info("✅ 巡检完成")
        except Exception as e:
            logger.error(f"❌ 巡检失败: {e}")

    def generate_report(self):
        """生成分析报告"""
        try:
            logger.info("📊 开始生成报告...")

            # 读取新闻摘要
            today = datetime.now().strftime('%Y-%m-%d')
            news_file = self.news_dir / f'{today}.json'

            news_summary = {'date': today, 'total': 0, 'high': 0, 'news': []}
            if news_file.exists():
                with open(news_file, 'r', encoding='utf-8') as f:
                    news_summary = json.load(f)

            # 读取incumbent状态
            incumbent_file = self.evolution_dir / 'incumbent_genome.json'
            incumbent_data = {}
            if incumbent_file.exists():
                with open(incumbent_file, 'r', encoding='utf-8') as f:
                    incumbent_data = json.load(f)

            # 生成报告
            report = {
                'generated_at': datetime.now().isoformat(),
                'news_summary': news_summary,
                'incumbent': {
                    'exp_r': incumbent_data.get('fitness', {}).get('exp_r', 0),
                    'win_rate': incumbent_data.get('fitness', {}).get('win_rate', 0),
                    'sample_size': incumbent_data.get('fitness', {}).get('sample_size', 0),
                    'score': incumbent_data.get('fitness', {}).get('score', 0)
                },
                'recommendations': self._generate_recommendations(news_summary, incumbent_data)
            }

            # 保存报告
            report_file = self.report_dir / f'report_{today}_{datetime.now().strftime("%H%M")}.json'
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

            logger.info(f"✅ 报告已生成: {report_file}")
            self.last_report = time.time()

        except Exception as e:
            logger.error(f"❌ 生成报告失败: {e}")

    def _generate_recommendations(self, news_summary: Dict, incumbent: Dict) -> List[str]:
        """生成投资建议"""
        recommendations = []

        # 基于新闻情绪（处理news_summary可能是list的情况）
        if isinstance(news_summary, dict):
            high_importance = news_summary.get('high', 0)
            if high_importance > 5:
                recommendations.append("⚠️  今日高重要性新闻较多，建议降低仓位或暂停交易")
            elif high_importance == 0:
                recommendations.append("✅  今日无重大新闻，市场相对平稳，可正常交易")

            # 基于incumbent性能
            fitness = incumbent.get('fitness', {})
            exp_r = fitness.get('exp_r', 0)
            if exp_r > 0.1:
                recommendations.append("🚀  incumbent表现优秀（exp_r>0.1R），可考虑扩大仓位")
            elif exp_r > 0:
                recommendations.append("✅  incumbent正期望，可正常交易")
            elif exp_r > -0.05:
                recommendations.append("⚠️  incumbent勉强正期望，建议谨慎交易")
            else:
                recommendations.append("🚨  incumbent负期望，建议暂停交易并优化策略")

            # 基于样本量
            sample_size = fitness.get('sample_size', 0)
            if sample_size < 100:
                recommendations.append("📊  样本量不足，建议继续进化直至样本显著")
        else:
            recommendations.append("⚠️  新闻数据格式异常，无法生成建议")

        return recommendations

    def run_hermes_communication(self):
        """执行Hermes沟通"""
        try:
            logger.info("💬 开始Hermes沟通...")

            # 检查是否需要汇报（每2小时或首次）
            if time.time() - self.last_hermes_comm < self.config['hermes_comm_interval']:
                logger.info("⏰ 距离上次Hermes沟通不足2小时，跳过")
                return

            # 运行Round通信脚本
            round_num = self._get_next_round_number()
            script_path = self.base_dir / 'tools' / f'talk_evolution_round{round_num}.py'

            if script_path.exists():
                _run_script(script_path)
                logger.info(f"✅ Round {round_num}沟通完成")
            else:
                logger.warning(f"⚠️  Round {round_num}脚本不存在，创建新脚本...")
                self._create_round_script(round_num)
                _run_script(self.base_dir / "tools" / f"talk_evolution_round{round_num}.py")

            self.last_hermes_comm = time.time()

        except Exception as e:
            logger.error(f"❌ Hermes沟通失败: {e}")

    def _get_next_round_number(self) -> int:
        """获取下一轮Round号"""
        tools_dir = self.base_dir / 'tools' / 'hermes_replies'
        if not tools_dir.exists():
            return 17

        rounds = []
        for f in tools_dir.glob('round*_*.txt'):
            try:
                round_num = int(f.stem.split('_')[0].replace('round', ''))
                rounds.append(round_num)
            except:
                pass

        return max(rounds, default=16) + 1

    def _create_round_script(self, round_num: int):
        """创建Round通信脚本"""
        script_content = f'''#!/usr/bin/env python3
"""金策·进化营 - Round {round_num} 向Hermes Chief汇报"""

import sys
sys.path.insert(0, r'E:\\\\资料\\\\GoldstrategyEngine')
from tools.talk_evolution_round16 import main as round16_main

if __name__ == '__main__':
    print(f"🧬 启动金策进化营 Round {round_num} 通信...")
    # TODO: 实现Round {round_num}的具体汇报内容
    print(f"⏸️  Round {round_num}通信暂未实现，跳过")
'''

        script_path = self.base_dir / 'tools' / f'talk_evolution_round{round_num}.py'
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_content)

        logger.info(f"✅ Round {round_num}脚本已创建")

    def run_loop(self):
        """运行自动进化循环"""
        logger.info("="*60)
        logger.info("🚀 金策·进化营自动进化调度器启动")
        logger.info("="*60)
        logger.info(f"📁 项目目录: {self.base_dir}")
        logger.info(f"📊 新闻目录: {self.news_dir}")
        logger.info(f"📈 报告目录: {self.report_dir}")
        logger.info("")
        logger.info("⏰ 调度配置:")
        for key, value in self.config.items():
            logger.info(f"   {key}: {value//60}分钟")
        logger.info("")

        while True:
            try:
                now = time.time()

                # 新闻爬取
                if now - self.last_news_crawl >= self.config['news_crawl_interval']:
                    self.run_news_crawl()

                # 进化运行
                if now - self.last_evolution >= self.config['evolution_interval']:
                    self.run_evolution()

                # 巡检执行
                if now - self.last_inspection >= self.config['inspection_interval']:
                    self.run_inspection()

                # 报告生成
                if now - self.last_report >= self.config['report_interval']:
                    self.generate_report()

                # Hermes沟通
                if now - self.last_hermes_comm >= self.config['hermes_comm_interval']:
                    self.run_hermes_communication()

                # 等待1分钟
                time.sleep(60)

            except KeyboardInterrupt:
                logger.info("🛑 自动进化调度器已停止")
                break
            except Exception as e:
                logger.error(f"❌ 调度循环异常: {e}", exc_info=True)
                time.sleep(60)

def main():
    import argparse

    parser = argparse.ArgumentParser(description='金策·进化营自动进化调度器')
    parser.add_argument('--once', action='store_true', help='仅执行一轮后退出')
    parser.add_argument('--daemon', action='store_true', help='后台守护模式')
    parser.add_argument('--status', action='store_true', help='查看当前状态')

    args = parser.parse_args()

    scheduler = AutoEvolutionScheduler()

    if args.status:
        # 显示当前状态
        print("="*60)
        print("📊 金策·进化营 - 当前状态")
        print("="*60)

        # 检查各组件状态
        components = {
            '新闻爬虫': scheduler.base_dir / 'news_crawler.py',
            '进化引擎': scheduler.base_dir / 'evolution_daemon.py',
            '巡检系统': scheduler.base_dir / 'inspection_daemon.py',
            'Hermes通信': scheduler.base_dir / 'tools' / 'talk_evolution_round16.py'
        }

        for name, path in components.items():
            status = "✅ 可用" if path.exists() else "❌ 缺失"
            print(f"   {name}: {status}")

        # 检查数据文件
        data_files = {
            '新闻数据': scheduler.news_dir / f'{datetime.now().strftime("%Y-%m-%d")}.json',
            'Incumbent': scheduler.evolution_dir / 'incumbent_genome.json',
            '决策台账': scheduler.evolution_dir / 'decision_journal.json'
        }

        print("\\n📁 数据文件:")
        for name, path in data_files.items():
            if path.exists():
                size_kb = path.stat().st_size / 1024
                print(f"   {name}: ✅ {size_kb:.1f}KB")
            else:
                print(f"   {name}: ❌ 不存在")

        print("="*60)

    elif args.daemon:
        # 后台守护模式
        print("🚀 启动自动进化守护进程...")
        print("💡 提示: 使用 Ctrl+C 停止进程")
        print("")
        scheduler.run_loop()

    elif args.once:
        # 执行一轮
        print("🔄 执行一轮自动进化...")
        scheduler.run_news_crawl()
        scheduler.run_evolution()
        scheduler.run_inspection()
        scheduler.generate_report()
        print("\\n✅ 一轮完成")

    else:
        # 默认前台运行
        parser.print_help()

if __name__ == '__main__':
    main()
