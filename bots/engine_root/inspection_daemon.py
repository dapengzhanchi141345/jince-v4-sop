#!/usr/bin/env python3
"""
金策·进化营 - 定时巡检守护进程
每30分钟自动检查系统状态，发现问题立即告警
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# 配置日志
BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / '巡检守护.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('巡检守护')

class InspectionDaemon:
    """定时巡检守护进程"""

    def __init__(self, interval_minutes: int = 30):
        self.interval = interval_minutes * 60  # 转换为秒
        self.project_dir = BASE_DIR
        self.evolution_dir = self.project_dir / 'evolution'
        self.state_file = self.evolution_dir / 'daemon_state.json'
        self.incumbent_file = self.evolution_dir / 'incumbent_genome.json'
        self.alert_log = self.evolution_dir / '巡检告警.log'
        
        # 确保目录存在
        self.evolution_dir.mkdir(parents=True, exist_ok=True)
        
        # 告警阈值
        self.thresholds = {
            'max_consecutive_holds': 5,
            'min_exp_r': 0.0,
            'min_sample_size': 30,
            'max_errors': 10,
            'max_daemon_age_hours': 24
        }
        
        # 告警历史
        self.alert_history: List[Dict] = []

    def load_state(self) -> Optional[Dict]:
        """加载daemon状态"""
        if not self.state_file.exists():
            return None
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载状态失败: {e}")
            return None
    
    def load_incumbent(self) -> Optional[Dict]:
        """加载incumbent基因组"""
        if not self.incumbent_file.exists():
            return None
        try:
            with open(self.incumbent_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载incumbent失败: {e}")
            return None
    
    def check_health(self) -> Tuple[bool, List[str]]:
        """检查系统健康状态"""
        issues = []
        
        # 1. 检查状态文件
        state = self.load_state()
        if not state:
            issues.append("❌ daemon状态文件不存在")
            return False, issues
        
        # 2. 检查错误数量
        errors = state.get('errors', [])
        if len(errors) > self.thresholds['max_errors']:
            issues.append(f"⚠️  错误数量过多: {len(errors)} > {self.thresholds['max_errors']}")
        
        # 3. 检查连续HOLD次数
        consecutive_holds = state.get('consecutive_holds', 0)
        if consecutive_holds >= self.thresholds['max_consecutive_holds']:
            issues.append(f"🚨 连续HOLD次数过多: {consecutive_holds} >= {self.thresholds['max_consecutive_holds']}")
        
        # 4. 检查最后运行时间
        last_run = state.get('last_run')
        if last_run:
            try:
                last_run_time = datetime.fromisoformat(last_run.replace('Z', '+00:00'))
                age_hours = (datetime.now(last_run_time.tzinfo) - last_run_time).total_seconds() / 3600
                if age_hours > self.thresholds['max_daemon_age_hours']:
                    issues.append(f"⏰ Daemon已停止{age_hours:.1f}小时，可能已崩溃")
            except:
                pass
        
        # 5. 检查incumbent质量
        incumbent = self.load_incumbent()
        if incumbent:
            fitness = incumbent.get('fitness', {})
            exp_r = fitness.get('exp_r', 0.0)
            sample_size = fitness.get('sample_size', 0)
            
            if exp_r < self.thresholds['min_exp_r']:
                issues.append(f"📉 Incumbent负期望: exp_r={exp_r:.4f}")
            
            if sample_size < self.thresholds['min_sample_size']:
                issues.append(f"📊 样本量不足: {sample_size} < {self.thresholds['min_sample_size']}")
        
        # 6. 检查MT5数据文件
        mt5_data_dir = self.project_dir / 'data' / 'mt5'
        if not mt5_data_dir.exists():
            issues.append("📁 MT5数据目录不存在")
        else:
            csv_files = list(mt5_data_dir.glob('*.csv'))
            if len(csv_files) == 0:
                issues.append("⚠️  MT5数据目录为空，未下载历史数据")
        
        # 7. 检查WFO结果
        wfo_file = self.evolution_dir / 'wfo_result.json'
        if wfo_file.exists():
            try:
                with open(wfo_file, 'r', encoding='utf-8') as f:
                    wfo_data = json.load(f)
                
                # 检查是否有非零exp_r
                has_real_data = False
                for item in wfo_data:
                    for fold in item.get('summary', {}).get('details', []):
                        if abs(fold.get('exp_r_train', 0)) > 0.001 or abs(fold.get('exp_r_test', 0)) > 0.001:
                            has_real_data = True
                            break
                
                if not has_real_data:
                    issues.append("🔍 WFO验证结果全为零，信号生成可能有问题")
            except Exception as e:
                issues.append(f"🔍 解析WFO结果失败: {e}")
        
        # 8. 检查决策台账大小
        journal_file = self.evolution_dir / 'decision_journal.json'
        if journal_file.exists():
            size_mb = journal_file.stat().st_size / (1024 * 1024)
            if size_mb < 0.1:
                issues.append(f"📝 决策台账过小: {size_mb:.2f}MB，可能记录不完整")
        
        # 9. 检查Hermes通信记录
        replies_dir = self.project_dir / 'tools' / 'hermes_replies'
        if replies_dir.exists():
            reply_files = list(replies_dir.glob('round*_*.txt'))
            if len(reply_files) > 0:
                latest_reply = max(reply_files, key=lambda x: x.stat().st_mtime)
                reply_age_hours = (datetime.now() - datetime.fromtimestamp(latest_reply.stat().st_mtime)).total_seconds() / 3600
                if reply_age_hours > 24:
                    issues.append(f"💬 最后一条Chief回复已超过{reply_age_hours:.1f}小时，可能需要跟进")
        
        is_healthy = len(issues) == 0
        return is_healthy, issues
    
    def send_alert(self, message: str, severity: str = 'warning'):
        """发送告警"""
        alert = {
            'time': datetime.now().isoformat(),
            'severity': severity,
            'message': message
        }
        self.alert_history.append(alert)
        
        # 写入告警日志
        with open(self.alert_log, 'a', encoding='utf-8') as f:
            f.write(f"{alert['time']} [{severity.upper()}] {message}\n")
        
        # 控制台输出
        if severity == 'critical':
            logger.critical(f"🚨 {message}")
        elif severity == 'warning':
            logger.warning(f"⚠️  {message}")
        else:
            logger.info(f"ℹ️  {message}")
    
    def run_inspection(self):
        """执行一次完整巡检"""
        logger.info("="*60)
        logger.info("🔍 开始巡检...")
        logger.info("="*60)
        
        is_healthy, issues = self.check_health()
        
        if is_healthy:
            logger.info("✅ 系统健康，无需告警")
            return True
        
        logger.warning(f"❌ 发现 {len(issues)} 个问题")
        
        # 根据问题严重程度发送告警
        for issue in issues:
            if '🚨' in issue or '错误数量过多' in issue or '已停止' in issue:
                self.send_alert(issue, 'critical')
            elif '⚠️' in issue or '⏰' in issue or '超过24小时' in issue:
                self.send_alert(issue, 'warning')
            else:
                self.send_alert(issue, 'info')
        
        # 如果是critical级别，建议重启daemon
        critical_issues = [i for i in issues if '🚨' in i or '已停止' in i]
        if critical_issues:
            self.send_alert("建议立即重启daemon并检查日志", 'critical')
        
        return False
    
    def run_loop(self):
        """运行巡检循环"""
        logger.info(f"🚀 巡检守护进程启动，间隔: {self.interval/60}分钟")
        logger.info(f"📁 项目目录: {self.project_dir}")
        logger.info(f"📊 状态文件: {self.state_file}")
        
        while True:
            try:
                self.run_inspection()
                logger.info(f"💤 等待{self.interval/60}分钟后再次巡检...")
                time.sleep(self.interval)
            except KeyboardInterrupt:
                logger.info("🛑 巡检守护进程已停止")
                break
            except Exception as e:
                logger.error(f"❌ 巡检循环异常: {e}", exc_info=True)
                self.send_alert(f"巡检异常: {e}", 'critical')
                time.sleep(60)  # 出错后等待1分钟再重试

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='金策·进化营定时巡检守护')
    parser.add_argument('--interval', type=int, default=30, help='巡检间隔（分钟），默认30')
    parser.add_argument('--once', action='store_true', help='仅执行一次巡检后退出')
    
    args = parser.parse_args()
    
    daemon = InspectionDaemon(interval_minutes=args.interval)
    
    if args.once:
        daemon.run_inspection()
    else:
        daemon.run_loop()

if __name__ == '__main__':
    main()
