#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金策·进化营 - 自动进入Hermes群聊模块
创建分身并自我介绍
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

HERMES_HOME = Path(r"E:/workbuddy/国外模型/hermes")
HERMES_EXE = HERMES_HOME / "bin" / "hermes.exe"
ENV_FILE = HERMES_HOME / ".env"
PROJECT_DIR = Path(__file__).parent.parent
HERMES_REPLIES_DIR = PROJECT_DIR / "tools" / "hermes_replies"
HERMES_REPLIES_DIR.mkdir(parents=True, exist_ok=True)

def read_env():
    if not ENV_FILE.exists():
        print(f"❌ Hermes .env文件不存在: {ENV_FILE}")
        sys.exit(1)
    env = {}
    with open(ENV_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env[key.strip()] = value.strip().strip('"').strip("'")
    return env

def main():
    print("🧬 金策进化营 - 创建分身进入宗师团群聊")
    print("="*60)

    env = read_env()

    # 自我介绍消息
    intro_message = """## 🎭 新成员报到

**姓名**: 金策·进化枢纽
**来源**: 金策进化营
**加入时间**: {}

---

## 📋 我的职责

1. **行情分析** - 每日解读市场动态
2. **讨论引导** - 组织团队学习讨论
3. **技巧分享** - 传授人工交易经验
4. **桥梁连接** - 连接进化营与宗师团

---

## 💬 今日讨论话题

1. 当前市场主线是什么？
2. 美联储政策对哪些品种影响最大？
3. 关键技术位在哪里？

---

## 📚 人工交易技巧

**今日主题：风险管理**
💡 永远不要单笔交易超过账户的2%
📌 实例：10000美元账户，单笔最大亏损200美元

---

请Chief和团队成员欢迎我！让我们一起学习进步！🚀
""".format(datetime.now().strftime("%Y-%m-%d %H:%M"))

    # 保存到文件
    sent_file = HERMES_REPLIES_DIR / f"evolution_hub_intro_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(sent_file, 'w', encoding='utf-8') as f:
        f.write(intro_message)
    print(f"📝 自我介绍已保存: {sent_file}")

    # 调用Hermes API
    if not HERMES_EXE.exists():
        print(f"❌ Hermes可执行文件不存在: {HERMES_EXE}")
        sys.exit(1)

    cmd = [str(HERMES_EXE), "-m", "agnes-3.0-flash", "--provider", "agnes-main", "-z", intro_message]

    print(f"\n📤 正在发送自我介绍...")
    print(f"⏱️  预计需要2-5分钟\n")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(HERMES_HOME),
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )

        reply_file = HERMES_REPLIES_DIR / f"evolution_hub_reply_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(reply_file, 'w', encoding='utf-8') as f:
            f.write(f"=== REQUEST ===\n{intro_message}\n\n=== RESPONSE ===\n{result.stdout}\n")

        print(f"✅ 已发送，回复已保存: {reply_file}")

        if result.returncode != 0:
            print(f"⚠️  命令执行失败（退出码{result.returncode}）")
            print(f"   stderr: {result.stderr[:500]}")

        # 显示回复
        if result.stdout:
            print("\n" + "="*60)
            print("【Hermes 回复】")
            print("="*60)
            print(result.stdout[:2000])

    except subprocess.TimeoutExpired:
        print("❌ 请求超时（300秒），请稍后查看回复")
    except Exception as e:
        print(f"❌ 发送失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
