#!/usr/bin/env python3
"""
金策·进化营 - 纯Python定时调度器（不依赖Windows任务计划）
实现每日定时任务、周期性任务、开机自启
"""

import os
import sys
import json
import time
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, List, Optional, Callable
import threading

# 配置日志
LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'python_scheduler.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('python_scheduler')

class PythonScheduler:
    """纯Python定时调度器"""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.state_file = base_dir / 'scheduler_state.json'
        self.tasks: List[Dict] = []
        self.load_state()

        # Python路径
        self.python_exe = r'C:\Users\ASUS\.workbuddy\binaries\python\versions\3.13.12\python.exe'

    def load_state(self):
        """加载调度器状态"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self.state = loaded.get('state', {'last_run': {}, 'enabled': True})
                    # 恢复任务列表
                    if 'tasks' in loaded:
                        self.tasks = loaded['tasks']
            except:
                self.state = {'last_run': {}, 'enabled': True}
                self.tasks = []
        else:
            self.state = {'last_run': {}, 'enabled': True}
            self.tasks = []

    def save_state(self):
        """保存调度器状态"""
        state_to_save = {
            'last_run': self.state.get('last_run', {}),
            'enabled': self.state.get('enabled', True),
            'tasks': self.tasks  # 保存任务列表
        }
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(state_to_save, f, ensure_ascii=False, indent=2)

    def add_task(self, name: str, command: str, schedule_type: str, schedule_time: Optional[str] = None, interval_minutes: Optional[int] = None):
        """添加定时任务"""
        task = {
            'name': name,
            'command': command,
            'schedule_type': schedule_type,  # 'daily', 'interval', 'once'
            'schedule_time': schedule_time,  # HH:MM for daily
            'interval_minutes': interval_minutes,  # for interval
            'enabled': True,
            'last_run': None,
            'next_run': None
        }

        # 计算下次运行时间
        task['next_run'] = self._calculate_next_run(task)
        self.tasks.append(task)
        logger.info(f"✅ 添加任务: {name} ({schedule_type})")

    def _calculate_next_run(self, task: Dict) -> Optional[str]:
        """计算下次运行时间"""
        now = datetime.now()

        if task['schedule_type'] == 'daily' and task['schedule_time']:
            # 每日定时
            parts = task['schedule_time'].split(':')
            next_run = now.replace(hour=int(parts[0]), minute=int(parts[1]), second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run.isoformat()

        elif task['schedule_type'] == 'interval' and task['interval_minutes']:
            # 间隔运行
            last_run_str = task.get('last_run')
            if last_run_str:
                last_run = datetime.fromisoformat(last_run_str)
                next_run = last_run + timedelta(minutes=task['interval_minutes'])
                if next_run <= now:
                    next_run = now + timedelta(minutes=task['interval_minutes'])
                return next_run.isoformat()
            else:
                return (now + timedelta(minutes=task['interval_minutes'])).isoformat()

        return None

    def run_task(self, task: Dict) -> bool:
        """运行单个任务"""
        try:
            logger.info(f"🚀 执行任务: {task['name']}")
            logger.info(f"   命令: {task['command']}")

            # 构建命令
            cmd = [self.python_exe, task['command']]

            # 执行
            result = subprocess.run(
                cmd,
                cwd=str(self.base_dir),
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )

            # 记录结果
            task['last_run'] = datetime.now().isoformat()
            task['next_run'] = self._calculate_next_run(task)

            if result.returncode == 0:
                logger.info(f"✅ 任务完成: {task['name']}")
                return True
            else:
                logger.error(f"❌ 任务失败: {task['name']}")
                logger.error(f"   stderr: {result.stderr[:500]}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"❌ 任务超时: {task['name']}")
            return False
        except Exception as e:
            logger.error(f"❌ 任务异常: {task['name']}: {e}")
            return False

    def check_and_run_tasks(self):
        """检查并运行到期的任务"""
        now = datetime.now()
        changed = False

        for task in self.tasks:
            if not task['enabled']:
                continue

            next_run_str = task.get('next_run')
            if not next_run_str:
                continue

            next_run = datetime.fromisoformat(next_run_str)
            if now >= next_run:
                if self.run_task(task):
                    changed = True

        if changed:
            self.save_state()

    def run_loop(self):
        """运行调度循环"""
        logger.info("="*60)
        logger.info("🚀 金策·进化营 Python定时调度器启动")
        logger.info("="*60)
        logger.info(f"📁 项目目录: {self.base_dir}")
        logger.info(f"📊 已注册任务数: {len(self.tasks)}")
        logger.info("")

        while True:
            try:
                self.check_and_run_tasks()
                time.sleep(30)  # 每30秒检查一次
            except KeyboardInterrupt:
                logger.info("🛑 调度器已停止")
                break
            except Exception as e:
                logger.error(f"❌ 调度循环异常: {e}", exc_info=True)
                time.sleep(60)

def main():
    import argparse

    parser = argparse.ArgumentParser(description='金策·进化营 Python定时调度器')
    parser.add_argument('--install', action='store_true', help='安装所有任务')
    parser.add_argument('--run-now', nargs='*', help='立即运行指定任务')
    parser.add_argument('--status', action='store_true', help='查看任务状态')
    parser.add_argument('--daemon', action='store_true', help='后台守护模式')

    args = parser.parse_args()

    base_dir = Path(__file__).parent
    scheduler = PythonScheduler(base_dir)

    if args.install:
        # 安装所有任务
        print("📦 正在安装定时任务...")

        # 每日任务
        scheduler.add_task("每日新闻爬取", "news_crawler.py --auto", "daily", "08:00")
        scheduler.add_task("每日开盘报告", "auto_publisher.py --publish market", "daily", "09:15")
        scheduler.add_task("每日收盘报告", "auto_publisher.py --publish evolution", "daily", "15:15")

        # 周期任务
        scheduler.add_task("30分钟进化", "evolution_daemon.py --once", "interval", interval_minutes=30)
        scheduler.add_task("30分钟巡检", "inspection_daemon.py --once", "interval", interval_minutes=30)

        # 保存状态
        scheduler.save_state()
        print("✅ 任务安装完成！")
        print("\n📋 已安装任务:")
        for task in scheduler.tasks:
            print(f"   • {task['name']}: {task['schedule_type']}" +
                  (f" @ {task['schedule_time']}" if task['schedule_time'] else "") +
                  (f" 每{task['interval_minutes']}分钟" if task['interval_minutes'] else ""))

    elif args.run_now:
        # 立即运行指定任务
        print("🔄 正在运行任务...")
        for task_name in args.run_now:
            for task in scheduler.tasks:
                if task['name'] == task_name:
                    scheduler.run_task(task)
                    break

    elif args.status:
        # 查看任务状态
        print("="*60)
        print("📊 金策·进化营 - 定时任务状态")
        print("="*60)
        print(f"\n总任务数: {len(scheduler.tasks)}")
        print(f"启用任务: {sum(1 for t in scheduler.tasks if t['enabled'])}")
        print("")

        for task in scheduler.tasks:
            status = "✅" if task['enabled'] else "❌"
            last_run = task.get('last_run', '从未')
            next_run = task.get('next_run', '未计算')
            print(f"{status} {task['name']}")
            print(f"   上次运行: {last_run}")
            print(f"   下次运行: {next_run}")
            print("")

    elif args.daemon:
        # 后台守护模式
        scheduler.run_loop()

    else:
        parser.print_help()

if __name__ == '__main__':
    main()
