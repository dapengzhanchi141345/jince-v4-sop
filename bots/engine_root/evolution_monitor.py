# -*- coding: utf-8 -*-
"""
金策·进化营 - 监控告警模块
===========================
功能：
1. 性能监控（内存/CPU/磁盘）
2. 异常检测（exp_r/胜率/样本数）
3. 阈值告警（连续HOLD/负期望/崩溃）
4. 健康检查（进程存活/文件完整性）
5. 日志聚合（多维度汇总）
"""

import os
import sys
import json
import time
import logging
import psutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

# 配置
logger = logging.getLogger('evolution_monitor')


class EvolutionMonitor:
    """进化监控器"""

    def __init__(self, base_dir: str = r"E:\资料\GoldstrategyEngine\evolution"):
        self.base_dir = base_dir
        self.state_file = os.path.join(base_dir, "daemon_state.json")
        self.journal_file = os.path.join(base_dir, "decision_journal.json")
        self.incumbent_file = os.path.join(base_dir, "incumbent_genome.json")

        # 告警阈值
        self.thresholds = {
            'min_exp_r': 0.0,
            'min_sample_size': 30,
            'max_consecutive_holds': 10,
            'max_memory_mb': 500,
            'max_disk_usage_pct': 90,
        }

        # 告警历史
        self.alerts: List[Dict[str, Any]] = []

    def check_health(self) -> Dict[str, Any]:
        """
        全面健康检查

        返回：
        {
            'status': 'healthy' | 'warning' | 'critical',
            'checks': {...},
            'alerts': [...]
        }
        """
        checks = {}
        alerts = []

        # 1. 进程存活检查
        checks['process'] = self._check_process()
        if not checks['process']['alive']:
            alerts.append({
                'type': 'critical',
                'message': '进化守护进程未运行',
                'time': datetime.now().isoformat()
            })

        # 2. 状态文件检查
        checks['state_file'] = self._check_state_file()
        if not checks['state_file']['exists']:
            alerts.append({
                'type': 'warning',
                'message': '状态文件不存在',
                'time': datetime.now().isoformat()
            })

        # 3. Incumbent检查
        checks['incumbent'] = self._check_incumbent()
        if checks['incumbent']['valid']:
            exp_r = checks['incumbent']['data'].get('fitness', {}).get('exp_r', 0.0)
            if exp_r < self.thresholds['min_exp_r']:
                alerts.append({
                    'type': 'warning',
                    'message': f'incumbent exp_r={exp_r:.4f} < 0（负期望）',
                    'time': datetime.now().isoformat()
                })

        # 4. 决策台账检查
        checks['journal'] = self._check_journal()

        # 5. 系统资源检查
        checks['system'] = self._check_system_resources()
        if checks['system']['memory_mb'] > self.thresholds['max_memory_mb']:
            alerts.append({
                'type': 'warning',
                'message': f'内存使用过高: {checks["system"]["memory_mb"]:.0f}MB',
                'time': datetime.now().isoformat()
            })

        # 6. 连续HOLD检查
        if checks.get('state', {}).get('consecutive_holds', 0) >= self.thresholds['max_consecutive_holds']:
            alerts.append({
                'type': 'critical',
                'message': f'连续{checks["state"]["consecutive_holds"]}次HOLD，进化停滞',
                'time': datetime.now().isoformat()
            })

        # 综合状态
        if any(a['type'] == 'critical' for a in alerts):
            status = 'critical'
        elif any(a['type'] == 'warning' for a in alerts):
            status = 'warning'
        else:
            status = 'healthy'

        self.alerts = alerts

        return {
            'status': status,
            'checks': checks,
            'alerts': alerts
        }

    def _check_process(self) -> Dict[str, Any]:
        """检查进程存活"""
        pid_file = os.path.join(self.base_dir, "daemon.pid")
        if not os.path.exists(pid_file):
            return {'alive': False, 'pid': None}

        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            process = psutil.Process(pid)
            return {
                'alive': process.is_running(),
                'pid': pid,
                'cpu_percent': process.cpu_percent(),
                'memory_mb': process.memory_info().rss / 1024 / 1024
            }
        except (psutil.NoSuchProcess, ValueError):
            return {'alive': False, 'pid': None}

    def _check_state_file(self) -> Dict[str, Any]:
        """检查状态文件"""
        if not os.path.exists(self.state_file):
            return {'exists': False}

        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {
                'exists': True,
                'data': data,
                'last_run': data.get('last_run'),
                'total_runs': data.get('total_runs', 0),
                'consecutive_holds': data.get('consecutive_holds', 0)
            }
        except Exception as e:
            return {'exists': True, 'error': str(e)}

    def _check_incumbent(self) -> Dict[str, Any]:
        """检查incumbent基因组"""
        if not os.path.exists(self.incumbent_file):
            return {'valid': False}

        try:
            with open(self.incumbent_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            fitness = data.get('fitness', {})
            return {
                'valid': True,
                'data': data,
                'exp_r': fitness.get('exp_r'),
                'win_rate': fitness.get('win_rate'),
                'sample_size': fitness.get('sample_size'),
                'score': fitness.get('score')
            }
        except Exception as e:
            return {'valid': False, 'error': str(e)}

    def _check_journal(self) -> Dict[str, Any]:
        """检查决策台账"""
        if not os.path.exists(self.journal_file):
            return {'count': 0}

        try:
            with open(self.journal_file, 'r', encoding='utf-8') as f:
                journal = json.load(f)
            return {
                'count': len(journal),
                'recent_decisions': [
                    {
                        'gen': d.get('gen'),
                        'decision': d.get('decision_type'),
                        'time': d.get('timestamp')
                    }
                    for d in journal[-5:]
                ]
            }
        except Exception as e:
            return {'count': 0, 'error': str(e)}

    def _check_system_resources(self) -> Dict[str, Any]:
        """检查系统资源"""
        return {
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_mb': psutil.virtual_memory().used / 1024 / 1024,
            'memory_percent': psutil.virtual_memory().percent,
            'disk_usage_pct': psutil.disk_usage('/').percent
        }

    def get_summary(self) -> str:
        """获取监控摘要报告"""
        health = self.check_health()

        lines = [
            "="*60,
            "金策·进化营 - 监控报告",
            "="*60,
            f"健康状态: {health['status'].upper()}",
            f"告警数量: {len(health['alerts'])}",
            ""
        ]

        # 检查项详情
        checks = health['checks']
        if 'process' in checks:
            p = checks['process']
            lines.append(f"进程: {'运行中' if p['alive'] else '未运行'}")
            if p['alive']:
                lines.append(f"  PID: {p['pid']}")
                lines.append(f"  CPU: {p['cpu_percent']:.1f}%")
                lines.append(f"  内存: {p['memory_mb']:.1f}MB")

        if 'state' in checks:
            s = checks['state']
            lines.append(f"最后运行: {s.get('last_run', 'N/A')}")
            lines.append(f"总运行次数: {s.get('total_runs', 0)}")
            lines.append(f"连续HOLD: {s.get('consecutive_holds', 0)}")

        if 'incumbent' in checks and checks['incumbent']['valid']:
            inc = checks['incumbent']
            lines.append(f"Incumbent: {inc['data'].get('rid', 'N/A')}")
            lines.append(f"  exp_r: {inc['exp_r']:.4f}")
            lines.append(f"  win_rate: {inc['win_rate']:.1%}" if inc['win_rate'] else "  win_rate: N/A")
            lines.append(f"  sample_size: {inc['sample_size']}")
            lines.append(f"  score: {inc['score']:.4f}")

        lines.append("")

        # 告警列表
        if health['alerts']:
            lines.append("⚠️ 告警列表:")
            for alert in health['alerts']:
                lines.append(f"  [{alert['type'].upper()}] {alert['message']}")
        else:
            lines.append("✅ 无告警")

        lines.append("="*60)

        return "\n".join(lines)

    def save_alert(self, alert: Dict[str, Any]):
        """保存告警记录"""
        alert_file = os.path.join(self.base_dir, "alerts.json")
        alerts = []
        if os.path.exists(alert_file):
            try:
                with open(alert_file, 'r', encoding='utf-8') as f:
                    alerts = json.load(f)
            except:
                alerts = []

        alerts.append(alert)
        # 只保留最近100条
        alerts = alerts[-100:]

        with open(alert_file, 'w', encoding='utf-8') as f:
            json.dump(alerts, f, ensure_ascii=False, indent=2)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='金策·进化营 - 监控告警')
    parser.add_argument('--check', action='store_true', help='执行健康检查')
    parser.add_argument('--summary', action='store_true', help='显示摘要报告')
    parser.add_argument('--alerts', action='store_true', help='显示告警历史')

    args = parser.parse_args()

    monitor = EvolutionMonitor()

    if args.check:
        health = monitor.check_health()
        print(json.dumps(health, ensure_ascii=False, indent=2))
    elif args.summary:
        print(monitor.get_summary())
    elif args.alerts:
        alert_file = os.path.join(monitor.base_dir, "alerts.json")
        if os.path.exists(alert_file):
            with open(alert_file, 'r', encoding='utf-8') as f:
                alerts = json.load(f)
            print(f"告警历史（最近{len(alerts)}条）:")
            for i, alert in enumerate(alerts[-20:], 1):
                print(f"  {i}. [{alert.get('type', 'unknown')}] {alert.get('message')}")
        else:
            print("无告警历史")
    else:
        # 默认显示摘要
        print(monitor.get_summary())


if __name__ == "__main__":
    main()
