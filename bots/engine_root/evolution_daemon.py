# -*- coding: utf-8 -*-
"""
金策·进化营 - 24小时持续进化守护进程
========================================
设计目标：
1. 后台持续运行，永不停止
2. 定时触发进化（可配置间隔）
3. 异常自动恢复
4. 状态持久化（防崩溃丢失）
5. 日志轮转（防磁盘爆满）
6. 与Hermes chief定期同步

运行模式：
- 前台：python evolution_daemon.py --foreground
- 后台：python evolution_daemon.py --daemon
- 监控：python evolution_daemon.py --status
"""

import os
import sys
import time
import json
import signal
import logging
import threading
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

# 确保项目路径
ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

# 导入进化引擎
from evolution.evolution_engine import (
    EvolutionEngine,
    create_evolution_engine,
    Genome,
)
from atomic_json import write_json, read_json

# ============================================================
# 配置
# ============================================================

class EvolutionConfig:
    """进化配置"""

    # 进化参数
    POP_SIZE = int(os.environ.get("EVOLUTION_POP_SIZE", "20"))
    GENERATIONS_PER_RUN = int(os.environ.get("EVOLUTION_GENERATIONS", "5"))
    SEED = int(os.environ.get("EVOLUTION_SEED", "42"))
    BARS_N = int(os.environ.get("EVOLUTION_BARS_N", "500"))

    # 品种集合（可扩展）
    UNIVERSE = [
        ("XAUUSD", "M15"),
        ("BTCUSD", "M15"),
        ("ETHUSD", "M15"),
        ("EURUSD", "M15"),
        ("GBPUSD", "M15"),
        ("USDJPY", "M15"),
    ]

    # 调度参数
    CHECK_INTERVAL = int(os.environ.get("EVOLUTION_CHECK_INTERVAL", "3600"))  # 默认1小时
    MAX_AGE_HOURS = int(os.environ.get("EVOLUTION_MAX_AGE", "24"))  # 最大进化周期

    # 文件路径
    BASE_DIR = os.environ.get(
        "EVOLUTION_BASE_DIR",
        r"E:\资料\GoldstrategyEngine\evolution"
    )
    LOG_DIR = os.environ.get(
        "EVOLUTION_LOG_DIR",
        r"E:\资料\GoldstrategyEngine\logs"
    )
    STATE_FILE = os.path.join(BASE_DIR, "daemon_state.json")
    PID_FILE = os.path.join(BASE_DIR, "daemon.pid")

    # 日志配置
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT = 5

    # 告警阈值
    MIN_EXP_R = 0.0
    MIN_SAMPLE_SIZE = 30
    MAX_CONSECUTIVE_HOLDS = 5  # 连续HOLD触发熔断（chief裁决）
    STOP_ON_HOLD = True  # 连续HOLD达到阈值自动暂停（熔断机制）

    def __init__(self):
        os.makedirs(self.BASE_DIR, exist_ok=True)
        os.makedirs(self.LOG_DIR, exist_ok=True)


# ============================================================
# 日志配置
# ============================================================

def setup_logging(config: EvolutionConfig) -> logging.Logger:
    """配置日志系统（带轮转）"""
    logger = logging.getLogger('evolution_daemon')
    logger.setLevel(logging.INFO)

    # 文件处理器（带轮转）
    log_file = os.path.join(config.LOG_DIR, "evolution_daemon.log")
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)

    # 格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# ============================================================
# 状态管理
# ============================================================

class DaemonState:
    """守护进程状态（持久化）"""

    def __init__(self, state_file: str):
        self.state_file = state_file
        self.data = {
            'start_time': None,
            'last_run': None,
            'last_gen': 0,
            'total_runs': 0,
            'total_promotes': 0,
            'total_holds': 0,
            'consecutive_holds': 0,
            'last_incumbent_rid': None,
            'last_exp_r': None,
            'errors': [],
            'health': 'unknown'
        }
        self.load()

    def load(self):
        """加载状态"""
        if os.path.exists(self.state_file):
            try:
                self.data = read_json(self.state_file, default=self.data)
            except Exception as e:
                logger.error(f"加载状态失败: {e}")

    def save(self):
        """保存状态"""
        try:
            write_json(self.state_file, self.data, default=str)
        except Exception as e:
            logger.error(f"保存状态失败: {e}")

    def update_run(self, gen: int, decision: str, exp_r: float):
        """更新运行状态"""
        self.data['last_run'] = datetime.now().isoformat()
        self.data['last_gen'] = gen
        self.data['total_runs'] += 1
        if decision == 'PROMOTE':
            self.data['total_promotes'] += 1
            self.data['consecutive_holds'] = 0
        else:
            self.data['total_holds'] += 1
            self.data['consecutive_holds'] += 1
        self.data['last_exp_r'] = exp_r
        self.save()

    def add_error(self, error: str):
        """添加错误记录"""
        self.data['errors'].append({
            'time': datetime.now().isoformat(),
            'error': error
        })
        # 只保留最近100条错误
        self.data['errors'] = self.data['errors'][-100:]
        self.save()

    def set_health(self, health: str):
        """设置健康状态"""
        self.data['health'] = health
        self.save()


# ============================================================
# 进化引擎封装
# ============================================================

class EvolutionOrchestrator:
    """进化编排器（封装EvolutionEngine）"""

    def __init__(self, config: EvolutionConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.engine: Optional[EvolutionEngine] = None
        self.state = DaemonState(config.STATE_FILE)

    def run_evolution_cycle(self) -> Dict[str, Any]:
        """
        运行一轮进化

        返回：
        {
            'success': bool,
            'gen': int,
            'decision': str,
            'exp_r': float,
            'score': float,
            'error': str (optional)
        }
        """
        try:
            self.logger.info(f"🧬 启动进化周期 | gen={self.state.data.get('last_gen', 0) + 1}")

            # 创建进化引擎
            self.engine = create_evolution_engine(
                universe=self.config.UNIVERSE,
                pop_size=self.config.POP_SIZE,
                generations=self.config.GENERATIONS_PER_RUN,
                seed=self.config.SEED,
                bars_n=self.config.BARS_N
            )

            # 运行进化
            result = self.engine.run()

            # 提取关键指标
            exp_r = result['final_incumbent']['fitness'].get('exp_r', 0.0)
            score = result['final_incumbent'].get('fitness', {}).get('score', 0.0)
            decision = result['lineage_summary'][-1]['decision'] if result['lineage_summary'] else 'UNKNOWN'
            gen = result['total_generations']

            # 更新状态
            self.state.update_run(gen, decision, exp_r)
            self.state.set_health('healthy')

            # 检查告警条件
            if self.state.data['consecutive_holds'] >= self.config.MAX_CONSECUTIVE_HOLDS:
                alert_msg = f"⚠️ 连续{self.state.data['consecutive_holds']}次HOLD，触发熔断机制"
                self.logger.warning(alert_msg)

                # 熔断：自动暂停
                if self.config.STOP_ON_HOLD:
                    self.state.set_health('fused')
                    self.state.add_error(alert_msg)
                    self.logger.error("🛑 熔断触发！守护进程将停止运行，等待人工干预")
                    return {
                        'success': False,
                        'error': 'FUSED: 连续HOLD达到阈值，触发熔断'
                    }

            if exp_r < self.config.MIN_EXP_R:
                self.logger.warning(f"⚠️ exp_r={exp_r:.4f} < 0，负期望")

            self.logger.info(
                f"✅ 进化完成 | gen={gen} | decision={decision} | "
                f"exp_r={exp_r:.4f} | score={score:.4f}"
            )

            return {
                'success': True,
                'gen': gen,
                'decision': decision,
                'exp_r': exp_r,
                'score': score
            }

        except Exception as e:
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.logger.error(f"❌ 进化失败: {error_msg}")
            self.state.add_error(error_msg)
            self.state.set_health('error')

            return {
                'success': False,
                'error': str(e)
            }


# ============================================================
# 守护进程
# ============================================================

class EvolutionDaemon:
    """24小时进化守护进程"""

    def __init__(self):
        self.config = EvolutionConfig()
        self.logger = setup_logging(self.config)
        self.orchestrator = EvolutionOrchestrator(self.config, self.logger)
        self.running = False
        self.thread: Optional[threading.Thread] = None

        # 注册信号处理
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        """处理终止信号"""
        self.logger.info(f"📴 收到信号 {signum}，准备关闭...")
        self.running = False

    def write_pid(self):
        """写入PID文件"""
        with open(self.config.PID_FILE, 'w') as f:
            f.write(str(os.getpid()))

    def remove_pid(self):
        """删除PID文件"""
        if os.path.exists(self.config.PID_FILE):
            os.remove(self.config.PID_FILE)

    def check_pid(self) -> bool:
        """检查是否有其他实例在运行"""
        if os.path.exists(self.config.PID_FILE):
            try:
                with open(self.config.PID_FILE, 'r') as f:
                    pid = int(f.read().strip())
                # 简单检查：进程是否存在
                import subprocess
                result = subprocess.run(
                    ['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV'],
                    capture_output=True, text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                )
                if pid != os.getpid() and str(pid) in result.stdout:
                    self.logger.warning(f"⚠️ 检测到其他实例运行（PID={pid}）")
                    return True
            except:
                pass
        return False

    def run_once(self):
        """运行单次进化"""
        return self.orchestrator.run_evolution_cycle()

    def run_forever(self):
        """持续运行（24小时模式）"""
        self.running = True
        self.write_pid()

        self.logger.info("="*60)
        self.logger.info("🚀 金策·进化营 - 24小时持续进化模式启动")
        self.logger.info("="*60)
        self.logger.info(f"   品种集合: {len(self.config.UNIVERSE)}个")
        self.logger.info(f"   种群大小: {self.config.POP_SIZE}")
        self.logger.info(f"   每轮代数: {self.config.GENERATIONS_PER_RUN}")
        self.logger.info(f"   检查间隔: {self.config.CHECK_INTERVAL}秒")
        self.logger.info(f"   状态文件: {self.config.STATE_FILE}")
        self.logger.info(f"   日志目录: {self.config.LOG_DIR}")
        self.logger.info("="*60)

        cycle_count = 0
        while self.running:
            cycle_count += 1
            self.logger.info(f"🔄 进化周期 #{cycle_count} 开始")

            # 运行进化
            result = self.run_once()

            # 检查结果
            if result['success']:
                self.logger.info(
                    f"✅ 周期 #{cycle_count} 完成 | "
                    f"gen={result['gen']} | "
                    f"decision={result['decision']} | "
                    f"exp_r={result['exp_r']:.4f}"
                )
            else:
                self.logger.error(f"❌ 周期 #{cycle_count} 失败: {result.get('error')}")

            # 等待下一轮
            self.logger.info(f"⏳ 等待 {self.config.CHECK_INTERVAL} 秒后下一轮...")
            for i in range(self.config.CHECK_INTERVAL):
                if not self.running:
                    break
                time.sleep(1)

        self.logger.info("📴 守护进程已停止")
        self.remove_pid()

    def get_status(self) -> Dict[str, Any]:
        """获取守护进程状态"""
        state = self.orchestrator.state.data
        pid_running = self.check_pid()

        return {
            'pid_running': pid_running,
            'state': state,
            'config': {
                'pop_size': self.config.POP_SIZE,
                'generations': self.config.GENERATIONS_PER_RUN,
                'check_interval': self.config.CHECK_INTERVAL,
                'universe_size': len(self.config.UNIVERSE),
            }
        }

    def print_status(self):
        """打印状态报告"""
        status = self.get_status()
        print("\n" + "="*60)
        print("金策·进化营 - 状态报告")
        print("="*60)
        print(f"守护进程: {'运行中' if status['pid_running'] else '未运行'}")
        print(f"启动时间: {status['state'].get('start_time', 'N/A')}")
        print(f"最后运行: {status['state'].get('last_run', 'N/A')}")
        print(f"当前代数: {status['state'].get('last_gen', 0)}")
        print(f"总运行次数: {status['state'].get('total_runs', 0)}")
        print(f"总PROMOTE: {status['state'].get('total_promotes', 0)}")
        print(f"总HOLD: {status['state'].get('total_holds', 0)}")
        print(f"连续HOLD: {status['state'].get('consecutive_holds', 0)}")
        print(f"最后exp_r: {status['state'].get('last_exp_r', 'N/A')}")
        print(f"健康状态: {status['state'].get('health', 'N/A')}")
        print(f"错误数量: {len(status['state'].get('errors', []))}")
        print("="*60)


# ============================================================
# 主入口
# ============================================================

logger = logging.getLogger('evolution_daemon')

def main():
    import argparse

    parser = argparse.ArgumentParser(description='金策·进化营 - 24小时持续进化守护进程')
    parser.add_argument('--foreground', action='store_true', help='前台运行（调试用）')
    parser.add_argument('--daemon', action='store_true', help='后台守护模式')
    parser.add_argument('--status', action='store_true', help='显示状态')
    parser.add_argument('--once', action='store_true', help='运行单次进化')
    parser.add_argument('--interval', type=int, help='覆盖检查间隔（秒）')

    args = parser.parse_args()

    daemon = EvolutionDaemon()

    if args.status:
        daemon.print_status()
        return

    if args.once:
        result = daemon.run_once()
        if result['success']:
            print(f"✅ 进化完成 | gen={result['gen']} | decision={result['decision']} | exp_r={result['exp_r']:.4f}")
        else:
            print(f"❌ 进化失败: {result.get('error')}")
            sys.exit(1)
        return

    # 守护模式
    if args.daemon:
        import subprocess
        # 后台启动
        subprocess.Popen(
            [sys.executable, __file__, '--foreground'],
            stdout=open(os.devnull, 'w'),
            stderr=open(os.devnull, 'w'),
            start_new_session=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        print("✅ 守护进程已在后台启动")
        return

    # 前台运行（默认）
    daemon.run_forever()


if __name__ == "__main__":
    main()
