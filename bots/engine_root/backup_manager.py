"""
金策宗师团 — 备份管理器 (所有数据 → E盘统一备份)
Goldstrategy Guild — Backup Manager (All data → E: drive)

自动备份:
  1. 所有配置文件 → backup/config/
  2. 模型注册表DB → backup/registry/
  3. 交易日志CSV → backup/trades/
  4. 自进化历史 → backup/evolution/
  5. 策略参数池 → backup/strategies/
  6. 每日完整快照 → backup/snapshots/YYYY-MM-DD/

定时: 每次交易后增量备份, 每天19:00全量快照
"""

import os
import json
import shutil
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import numpy as np


BASE_DIR = "E:/GoldstrategyEngine"
BACKUP_DIR = f"{BASE_DIR}/backup"
DATA_DIR = f"{BASE_DIR}/data"
LOG_DIR = f"{BASE_DIR}/logs"
CONFIG_DIR = f"{BASE_DIR}/config"

# 确保目录存在
for d in [BASE_DIR, BACKUP_DIR, DATA_DIR, LOG_DIR, CONFIG_DIR,
          f"{BACKUP_DIR}/config", f"{BACKUP_DIR}/registry", f"{BACKUP_DIR}/trades",
          f"{BACKUP_DIR}/evolution", f"{BACKUP_DIR}/strategies", f"{BACKUP_DIR}/snapshots",
          f"{DATA_DIR}/market", f"{DATA_DIR}/factors", f"{DATA_DIR}/signals"]:
    os.makedirs(d, exist_ok=True)


class BackupManager:
    """
    备份管理器 — 数据永不丢失
    
    所有重要数据统一存放在 E:\GoldstrategyEngine\ 下:
      ├── backup/          ← 所有备份
      │   ├── config/      ← 配置文件快照
      │   ├── registry/    ← 模型注册表DB
      │   ├── trades/      ← 交易日志
      │   ├── evolution/   ← 自进化记录
      │   ├── strategies/  ← 策略参数池
      │   └── snapshots/   ← 日全量快照
      ├── data/            ← 运行时数据
      ├── logs/            ← 日志
      └── config/          ← 配置文件
    """

    def __init__(self):
        self.last_backup = None
        self.backup_count = 0
        self._load_state()

    def _load_state(self):
        """加载备份状态"""
        state_path = f"{DATA_DIR}/backup_state.json"
        if os.path.exists(state_path):
            try:
                with open(state_path, "r") as f:
                    data = json.load(f)
                    self.backup_count = data.get("count", 0)
            except Exception:
                pass

    def _save_state(self):
        """保存备份状态"""
        with open(f"{DATA_DIR}/backup_state.json", "w") as f:
            json.dump({
                "last_backup": self.last_backup,
                "count": self.backup_count,
                "updated": datetime.now().isoformat(),
            }, f, indent=2)

    def full_backup(self, reason: str = "scheduled") -> str:
        """
        全量备份 — 备份所有数据
        
        返回备份路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_dir = f"{BACKUP_DIR}/snapshots/{datetime.now().strftime('%Y-%m-%d')}"
        os.makedirs(snapshot_dir, exist_ok=True)
        
        backup_manifest = {
            "timestamp": datetime.now().isoformat(),
            "reason": reason,
            "files": [],
        }
        
        # 1. 备份配置
        config_backup = f"{BACKUP_DIR}/config/config_{timestamp}.json"
        config_files = []
        for f in ["config.py", "main.py"]:
            src = f"{BASE_DIR}/{f}"
            if os.path.exists(src):
                dst = f"{snapshot_dir}/{f}"
                shutil.copy2(src, dst)
                config_files.append(f)
                backup_manifest["files"].append(f"config/{f}")
        
        # 2. 备份模型注册表
        registry_src = f"{DATA_DIR}/model_registry.db"
        if os.path.exists(registry_src):
            registry_dst = f"{BACKUP_DIR}/registry/registry_{timestamp}.db"
            self._safe_copy_db(registry_src, registry_dst)
            shutil.copy2(registry_src, f"{snapshot_dir}/model_registry.db")
            backup_manifest["files"].append("registry/model_registry.db")
        
        # 3. 备份交易日志
        trades_src = f"{LOG_DIR}/trader_journal.csv"
        if os.path.exists(trades_src):
            trades_dst = f"{BACKUP_DIR}/trades/trades_{timestamp}.csv"
            shutil.copy2(trades_src, trades_dst)
            shutil.copy2(trades_src, f"{snapshot_dir}/trader_journal.csv")
            backup_manifest["files"].append("trades/trader_journal.csv")
        
        # 4. 备份自进化状态
        evolution_src = f"{DATA_DIR}/evolution_state.json"
        if os.path.exists(evolution_src):
            shutil.copy2(evolution_src, f"{BACKUP_DIR}/evolution/evolution_{timestamp}.json")
            shutil.copy2(evolution_src, f"{snapshot_dir}/evolution_state.json")
            backup_manifest["files"].append("evolution/evolution_state.json")
        
        # 5. 备份策略参数池
        strategy_src = f"{DATA_DIR}/strategy_pool.json"
        if os.path.exists(strategy_src):
            shutil.copy2(strategy_src, f"{BACKUP_DIR}/strategies/strategies_{timestamp}.json")
            shutil.copy2(strategy_src, f"{snapshot_dir}/strategy_pool.json")
            backup_manifest["files"].append("strategies/strategy_pool.json")
        
        # 6. 备份关键因子和信号日志
        for log_file in ["signals.csv", "trades.csv"]:
            src = f"{LOG_DIR}/{log_file}"
            if os.path.exists(src):
                shutil.copy2(src, f"{snapshot_dir}/{log_file}")
                backup_manifest["files"].append(f"logs/{log_file}")
        
        # 写备份清单
        with open(f"{snapshot_dir}/manifest.json", "w") as f:
            json.dump(backup_manifest, f, indent=2)
        
        self.last_backup = datetime.now().isoformat()
        self.backup_count += 1
        self._save_state()
        
        print(f"[备份] ✅ 全量备份完成: {snapshot_dir}")
        print(f"[备份]    文件数: {len(backup_manifest['files'])} | 总备份次数: {self.backup_count}")
        
        return snapshot_dir

    def incremental_backup(self, data: Dict, data_type: str):
        """
        增量备份 — 每笔交易/每次进化后保存
        
        Args:
            data: 要保存的数据
            data_type: "trade" / "evolution" / "signal" / "config"
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if data_type == "trade":
            path = f"{BACKUP_DIR}/trades/incremental_{timestamp}.json"
        elif data_type == "evolution":
            path = f"{BACKUP_DIR}/evolution/incremental_{timestamp}.json"
        elif data_type == "signal":
            path = f"{DATA_DIR}/signals/latest.json"
        else:
            path = f"{BACKUP_DIR}/config/incremental_{timestamp}.json"
        
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        with open(path, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "type": data_type,
                "data": data,
            }, f, indent=2, default=str)
        
        # 同时更新最新副本
        latest_path = f"{DATA_DIR}/{data_type}s/latest.json"
        os.makedirs(os.path.dirname(latest_path), exist_ok=True)
        with open(latest_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _safe_copy_db(self, src: str, dst: str):
        """安全复制SQLite数据库 (处理锁定)"""
        try:
            # 使用sqlite3备份
            conn_src = sqlite3.connect(src)
            conn_dst = sqlite3.connect(dst)
            conn_src.backup(conn_dst)
            conn_dst.close()
            conn_src.close()
        except Exception:
            # 回退: 文件复制
            try:
                shutil.copy2(src, dst)
            except Exception:
                print(f"[备份] ⚠️ 无法备份数据库: {src}")

    def restore(self, snapshot_date: str = None) -> bool:
        """
        从最近的快照恢复
        
        Args:
            snapshot_date: "YYYY-MM-DD", None=最近一个
        
        Returns:
            是否成功
        """
        snapshot_dir = f"{BACKUP_DIR}/snapshots"
        if not os.path.exists(snapshot_dir):
            print("[备份] ❌ 无可用快照")
            return False
        
        if snapshot_date:
            target = f"{snapshot_dir}/{snapshot_date}"
        else:
            # 找最近的
            snapshots = sorted(os.listdir(snapshot_dir), reverse=True)
            if not snapshots:
                print("[备份] ❌ 无可用快照")
                return False
            target = f"{snapshot_dir}/{snapshots[0]}"
        
        if not os.path.exists(target):
            print(f"[备份] ❌ 快照不存在: {target}")
            return False
        
        # 读取清单
        manifest_path = f"{target}/manifest.json"
        if os.path.exists(manifest_path):
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
        else:
            manifest = {"files": []}
        
        # 恢复每个文件
        restored = 0
        for rel_path in manifest["files"]:
            src = f"{target}/{os.path.basename(rel_path)}"
            if os.path.exists(src):
                if "registry" in rel_path:
                    dst = f"{DATA_DIR}/model_registry.db"
                elif "trades" in rel_path:
                    dst = f"{LOG_DIR}/trader_journal.csv"
                elif "evolution" in rel_path:
                    dst = f"{DATA_DIR}/evolution_state.json"
                elif "strategy" in rel_path:
                    dst = f"{DATA_DIR}/strategy_pool.json"
                elif "config" in rel_path:
                    dst = f"{BASE_DIR}/{os.path.basename(rel_path)}"
                else:
                    dst = f"{DATA_DIR}/{os.path.basename(rel_path)}"
                
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                restored += 1
        
        print(f"[备份] ✅ 从 {target} 恢复 {restored} 个文件")
        return True

    def get_backup_info(self) -> Dict:
        """获取备份信息"""
        snapshot_dir = f"{BACKUP_DIR}/snapshots"
        snapshots = []
        if os.path.exists(snapshot_dir):
            for s in sorted(os.listdir(snapshot_dir)):
                manifest = f"{snapshot_dir}/{s}/manifest.json"
                if os.path.exists(manifest):
                    with open(manifest, "r") as f:
                        m = json.load(f)
                    snapshots.append({
                        "date": s,
                        "time": m.get("timestamp", ""),
                        "files": len(m.get("files", [])),
                    })
        
        return {
            "backup_count": self.backup_count,
            "last_backup": self.last_backup,
            "total_snapshots": len(snapshots),
            "recent_snapshots": snapshots[-5:],
            "backup_dir": BACKUP_DIR,
            "data_dir": DATA_DIR,
        }


# ═══════════════════════════════════════════
# 2. 深度记忆系统
# ═══════════════════════════════════════════

class DeepMemory:
    """
    深度记忆系统
    
    记住:
      - 所有交易历史 (永远保留)
      - 所有策略版本 (每个版本的参数和性能)
      - 所有自进化记录 (每次进化的原因和结果)
      - 市场状态变化模式 (什么状态赚了/亏了)
      - 经验教训 (失败总结)
    """

    def __init__(self):
        self.memory_file = f"{DATA_DIR}/deep_memory.json"
        self.memory = self._load()
        self.backup = BackupManager()

    def _load(self) -> Dict:
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "created": datetime.now().isoformat(),
            "total_trades": 0,
            "total_evolutions": 0,
            "total_backups": 0,
            "best_strategy": None,
            "lessons": [],
            "market_patterns": {},
            "version_history": [],
            "daily_summaries": [],
        }

    def _save(self):
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
        with open(self.memory_file, "w") as f:
            json.dump(self.memory, f, indent=2, default=str)
        # 增量备份到备份目录
        shutil.copy2(self.memory_file, f"{BACKUP_DIR}/evolution/deep_memory.json")

    def remember_trade(self, trade: Dict):
        """记住一笔交易"""
        self.memory["total_trades"] += 1
        self._save()
        
        # 增量备份
        self.backup.incremental_backup(trade, "trade")

    def remember_evolution(self, evolution: Dict):
        """记住一次进化"""
        version = evolution.get("version", 0)
        self.memory["total_evolutions"] += 1
        self.memory["version_history"].append({
            "version": version,
            "time": datetime.now().isoformat(),
            "trigger": evolution.get("trigger", ""),
            "accepted": evolution.get("accepted", False),
            "old_wfer": evolution.get("old_wfer", 0),
            "new_wfer": evolution.get("new_wfer", 0),
        })
        self._save()
        
        # 增量备份
        self.backup.incremental_backup(evolution, "evolution")

    def remember_lesson(self, lesson: str, category: str = "general"):
        """记住经验教训"""
        self.memory["lessons"].append({
            "time": datetime.now().isoformat(),
            "category": category,
            "lesson": lesson,
        })
        # 只保留最近100条
        if len(self.memory["lessons"]) > 100:
            self.memory["lessons"] = self.memory["lessons"][-100:]
        self._save()

    def daily_summary(self, stats: Dict):
        """记录每日总结"""
        summary = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": datetime.now().isoformat(),
            "trades": stats.get("trades", 0),
            "pnl": stats.get("pnl", 0),
            "win_rate": stats.get("win_rate", 0),
            "balance": stats.get("balance", 0),
        }
        self.memory["daily_summaries"].append(summary)
        # 只保留最近365天
        if len(self.memory["daily_summaries"]) > 365:
            self.memory["daily_summaries"] = self.memory["daily_summaries"][-365:]
        
        self._save()
        
        # 每天全量备份
        self.backup.full_backup(reason="daily_summary")

    def get_summary(self) -> str:
        """生成记忆摘要"""
        m = self.memory
        lines = [
            f"🧠 金策宗师团 — 深度记忆",
            f"={'-'*40}",
            f"  创建时间: {m['created']}",
            f"  总交易数: {m['total_trades']}",
            f"  总进化次数: {m['total_evolutions']}",
            f"  经验教训: {len(m['lessons'])}条",
            f"  版本历史: {len(m['version_history'])}个",
            f"  日记录: {len(m['daily_summaries'])}天",
            f"",
            f"  备份状态:",
            f"    备份目录: {BACKUP_DIR}",
            f"    数据目录: {DATA_DIR}",
            f"    总备份次数: {self.backup.backup_count}",
        ]
        
        # 最近的教训
        if m["lessons"]:
            lines.append(f"")
            lines.append(f"  最近教训:")
            for l in m["lessons"][-3:]:
                lines.append(f"    [{l['category']}] {l['lesson'][:60]}")
        
        return "\n".join(lines)

    def consolidate(self):
        """
        整合所有数据 — 全量备份 + 清理临时文件
        """
        print(f"\n{'='*50}")
        print(f"  🗄️  金策宗师团 — 数据整合")
        print(f"{'='*50}")
        
        # 1. 全量备份
        snapshot = self.backup.full_backup(reason="consolidation")
        
        # 2. 保存深度记忆
        self._save()
        
        # 3. 生成整合报告
        report = {
            "consolidated_at": datetime.now().isoformat(),
            "backup_snapshot": snapshot,
            "memory": self.get_summary(),
            "files": self._list_all_data_files(),
        }
        
        report_path = f"{DATA_DIR}/consolidation_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        
        print(f"  ✅ 整合完成")
        print(f"  备份: {snapshot}")
        print(f"  报告: {report_path}")
        
        return report

    def _list_all_data_files(self) -> List[str]:
        """列出所有数据文件"""
        files = []
        for root, dirs, filenames in os.walk(BASE_DIR):
            for fn in filenames:
                if fn.endswith((".json", ".csv", ".db", ".txt", ".log")):
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, BASE_DIR)
                    files.append(rel)
        return sorted(files)


# ═══════════════════════════════════════════
# 3. 统一启动器
# ═══════════════════════════════════════════

def initialize_environment():
    """
    初始化整个环境 — 确保所有目录和数据就绪
    """
    print(f"\n{'='*50}")
    print(f"  🚀 金策宗师团 — 环境初始化")
    print(f"{'='*50}")
    
    # 创建所有目录
    dirs = [
        BASE_DIR, BACKUP_DIR, DATA_DIR, LOG_DIR, CONFIG_DIR,
        f"{BACKUP_DIR}/config", f"{BACKUP_DIR}/registry", f"{BACKUP_DIR}/trades",
        f"{BACKUP_DIR}/evolution", f"{BACKUP_DIR}/strategies", f"{BACKUP_DIR}/snapshots",
        f"{DATA_DIR}/market", f"{DATA_DIR}/factors", f"{DATA_DIR}/signals",
        f"{DATA_DIR}/trades", f"{DATA_DIR}/evolution",
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
    
    print(f"  📁 目录已创建: {len(dirs)}个")
    print(f"  根目录: {BASE_DIR}")
    print(f"  数据目录: {DATA_DIR}")
    print(f"  备份目录: {BACKUP_DIR}")
    print(f"  日志目录: {LOG_DIR}")
    
    # 初始化深度记忆
    memory = DeepMemory()
    print(f"  🧠 深度记忆已初始化")
    
    # 初始化备份管理器
    backup = BackupManager()
    info = backup.get_backup_info()
    print(f"  💾 备份管理器就绪 (已有{info['backup_count']}次备份)")
    
    # 检查关键文件
    engine_files = [
        "main.py", "config.py", "mt5_connector.py",
        "engine_v2.py", "engine_v3.py", "engine_v4_self_evolve.py",
    ]
    for f in engine_files:
        path = f"{BASE_DIR}/{f}"
        if os.path.exists(path):
            size = os.path.getsize(path)
            print(f"  ✅ {f} ({size:,} bytes)")
        else:
            print(f"  ⚠️ {f} 未找到")
    
    print(f"\n  ✅ 环境初始化完成")
    print(f"  ---")
    print(f"  运行: python {BASE_DIR}/main.py")
    print(f"  日志: {LOG_DIR}/dashboard.html")
    print(f"  备份: python {__file__} --backup")
    print(f"  整合: python {__file__} --consolidate")
    
    return memory


if __name__ == "__main__":
    import sys
    
    if "--backup" in sys.argv:
        bm = BackupManager()
        bm.full_backup(reason="manual")
    elif "--consolidate" in sys.argv:
        dm = DeepMemory()
        dm.consolidate()
    elif "--restore" in sys.argv:
        date = sys.argv[sys.argv.index("--restore") + 1] if "--restore" in sys.argv and len(sys.argv) > sys.argv.index("--restore") + 1 else None
        bm = BackupManager()
        bm.restore(date)
    elif "--info" in sys.argv:
        bm = BackupManager()
        info = bm.get_backup_info()
        print(json.dumps(info, indent=2, default=str))
    else:
        initialize_environment()
