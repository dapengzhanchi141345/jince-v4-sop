# -*- coding: utf-8 -*-
"""
金策·进化营 - 定时调度器
=========================
支持多种调度模式：
1. 固定间隔（如每小时）
2. Cron表达式（如每天早上9点）
3. 事件驱动（如接到新数据时）
4. 混合调度（结合以上模式）
"""

import os
import sys
import time
import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Callable, Dict, Any, Optional
from croniter import croniter

logger = logging.getLogger('evolution_scheduler')


class Scheduler:
    """通用调度器"""

    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.running = False
        self.threads: Dict[str, threading.Thread] = {}

    def add_interval_task(
        self,
        task_id: str,
        func: Callable,
        interval_seconds: int,
        args: tuple = (),
        kwargs: dict = None
    ):
        """添加固定间隔任务"""
        self.tasks[task_id] = {
            'type': 'interval',
            'func': func,
            'interval': interval_seconds,
            'args': args,
            'kwargs': kwargs or {},
            'last_run': None,
            'enabled': True
        }
        logger.info(f"📅 添加定时任务: {task_id} (每{interval_seconds}秒)")

    def add_cron_task(
        self,
        task_id: str,
        func: Callable,
        cron_expression: str,
        args: tuple = (),
        kwargs: dict = None
    ):
        """添加Cron任务"""
        try:
            # 验证cron表达式
            croniter(cron_expression, datetime.now())
            self.tasks[task_id] = {
                'type': 'cron',
                'func': func,
                'cron': cron_expression,
                'args': args,
                'kwargs': kwargs or {},
                'next_run': self._get_next_cron_time(cron_expression),
                'enabled': True
            }
            logger.info(f"📅 添加Cron任务: {task_id} ({cron_expression})")
        except Exception as e:
            logger.error(f"❌ Cron表达式无效: {cron_expression} | {e}")

    def _get_next_cron_time(self, cron_expression: str) -> datetime:
        """计算下次运行时间"""
        now = datetime.now()
        next_time = croniter(cron_expression, now).get_next(datetime)
        return next_time

    def start(self):
        """启动调度器"""
        self.running = True
        logger.info("🚀 调度器启动")

        for task_id, task in self.tasks.items():
            if task['enabled']:
                thread = threading.Thread(
                    target=self._run_task_loop,
                    args=(task_id,),
                    daemon=True
                )
                self.threads[task_id] = thread
                thread.start()
                logger.info(f"✅ 启动任务线程: {task_id}")

    def _run_task_loop(self, task_id: str):
        """任务执行循环"""
        task = self.tasks[task_id]

        while self.running:
            try:
                now = datetime.now()

                # 检查是否到达执行时间
                should_run = False
                if task['type'] == 'interval':
                    if task['last_run'] is None:
                        should_run = True
                    else:
                        elapsed = (now - task['last_run']).total_seconds()
                        if elapsed >= task['interval']:
                            should_run = True

                elif task['type'] == 'cron':
                    if now >= task['next_run']:
                        should_run = True
                        task['next_run'] = self._get_next_cron_time(task['cron'])

                if should_run:
                    logger.info(f"⏰ 执行任务: {task_id}")
                    task['func'](*task['args'], **task['kwargs'])
                    task['last_run'] = datetime.now()

            except Exception as e:
                logger.error(f"❌ 任务执行失败 {task_id}: {e}")

            # 休眠防CPU占用
            time.sleep(1)

    def stop(self):
        """停止调度器"""
        self.running = False
        for thread in self.threads.values():
            thread.join(timeout=5)
        logger.info("📴 调度器已停止")

    def get_status(self) -> Dict[str, Any]:
        """获取调度器状态"""
        return {
            'running': self.running,
            'tasks': {
                task_id: {
                    'type': task['type'],
                    'enabled': task['enabled'],
                    'last_run': task.get('last_run'),
                    'next_run': task.get('next_run')
                }
                for task_id, task in self.tasks.items()
            }
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description='金策·进化营 - 定时调度器')
    parser.add_argument('--test', action='store_true', help='测试调度器')

    args = parser.parse_args()

    if args.test:
        # 测试调度器
        def test_task():
            print(f"[{datetime.now()}] 测试任务执行")

        scheduler = Scheduler()
        scheduler.add_interval_task('test', test_task, 5)
        scheduler.start()

        print("调度器运行中... (5秒后自动停止)")
        time.sleep(5)
        scheduler.stop()
        print("测试完成")


if __name__ == "__main__":
    main()
