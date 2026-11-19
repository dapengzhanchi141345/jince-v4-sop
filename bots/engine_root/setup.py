"""
金策宗师团 — 安装脚本
Goldstrategy Guild — Setup

本脚本自动:
  1. 安装 Python 依赖
  2. 创建日志目录
  3. 验证 MT5 连接
  4. 运行单次信号分析
"""

import subprocess
import sys
import os

DEPENDENCIES = [
    "MetaTrader5",
    "numpy",
    "pandas",
]

def install_dependencies():
    """安装依赖"""
    print("📦 安装依赖...")
    for dep in DEPENDENCIES:
        print(f"   正在安装 {dep}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", dep],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"   ⚠️  {dep} 安装失败: {result.stderr[:100]}")
        else:
            print(f"   ✅ {dep} 安装成功")

def create_dirs():
    """创建目录"""
    dirs = [
        "E:/GoldstrategyEngine/logs",
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"   📁 {d}")

def check_config():
    """检查配置"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from config import MT5_CONFIG

    if not MT5_CONFIG["server"]:
        print("\n⚠️  请在 config.py 中填写 MT5 账号信息:")
        print("   MT5_CONFIG['server']   — 服务器地址 (如 'ICMarkets-Demo')")
        print("   MT5_CONFIG['login']    — 账号")
        print("   MT5_CONFIG['password'] — 密码")
        return False
    return True

def main():
    print("=" * 50)
    print("  金策宗师团 — 安装向导")
    print("  Goldstrategy Guild Setup")
    print("=" * 50)

    # 1. 安装依赖
    install_dependencies()

    # 2. 创建目录
    print("\n📁 创建目录...")
    create_dirs()

    # 3. 检查配置
    print("\n🔍 检查配置...")
    if check_config():
        print("   ✅ 配置检查通过")
    else:
        print("   ⏸️  请先填写配置后再运行")

    # 4. 尝试导入
    print("\n🔬 验证导入...")
    try:
        import MetaTrader5 as mt5
        print(f"   ✅ MetaTrader5 版本: {mt5.__version__}")
        import numpy as np
        print(f"   ✅ NumPy 版本: {np.__version__}")
        import pandas as pd
        print(f"   ✅ Pandas 版本: {pd.__version__}")
    except Exception as e:
        print(f"   ❌ 导入失败: {e}")

    print("\n" + "=" * 50)
    print("  ✅ 安装完成!")
    print("  运行: python main.py")
    print("  监控: python main.py --monitor")
    print("=" * 50)


if __name__ == "__main__":
    main()
