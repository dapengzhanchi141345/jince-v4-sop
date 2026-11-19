#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金策·进化枢纽 - 金策宗师团群聊行情分析与讨论引导模块（实读版）
=============================================================
铁律（Chief 2026-10-23 教学）：分析前 MUST 实读 MT5，绝不编圆数；
支撑阻力取自 K 线真实高低点；文本必带时间戳+账户+数据来源。

模式：
  --realtime   实读 MT5 → 生成全品种分析+讨论 → 预览/发送群（推荐，唯一可信路径）
  --mode analysis/discussion/both  传统新闻版（已弃用编造数据，仅存量兼容）
  --test        只打印不发送

发送：config/publisher_config.json 配置 webhook 后才真正发出；未配置则只落盘。
"""
import os
import sys
import json
import logging
import subprocess
import importlib.util
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('hermes_group_chat')

BASE = Path(__file__).parent
TOOLS = BASE / 'tools'
GROUP = BASE / 'data' / 'group_messages'
CONFIG_FILE = BASE / 'config' / 'publisher_config.json'


def _load_publisher():
    if CONFIG_FILE.exists():
        try:
            return json.load(open(CONFIG_FILE, encoding='utf-8'))
        except Exception:
            pass
    return {}


def _run_realtime_pipeline():
    """实读 MT5 并生成全品种分析/讨论 markdown，返回 (analysis_md, discussion_md, read_json)"""
    # 1) 刷新实读
    py = sys.executable
    read_json = None
    r = subprocess.run([py, str(TOOLS / 'mt5_realtime_read.py')],
                       cwd=str(BASE), capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode == 0:
        import glob
        files = sorted(glob.glob(str(BASE / 'data' / 'mt5_live_read_*.json')))
        if files:
            read_json = files[-1]
    else:
        logger.warning("MT5 实读失败，尝试用已有最新 json：%s", r.stderr[:200])

    # 2) 生成分析（导入 gen_market_analysis）
    spec = importlib.util.spec_from_file_location("gen_market_analysis", str(TOOLS / 'gen_market_analysis.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    res = mod.build()
    if not res:
        return None, None, read_json
    a_path, d_path, _ = res
    analysis_md = open(a_path, encoding='utf-8').read()
    discussion_md = open(d_path, encoding='utf-8').read()
    return analysis_md, discussion_md, read_json


def send_to_group(message: str) -> bool:
    cfg = _load_publisher()
    webhook = cfg.get('webhook', '')
    if not webhook:
        logger.warning("⚠️  未配置群聊 webhook（config/publisher_config.json），仅落盘不发送")
        print("❌ 未配置 webhook，消息已生成但暂不发送（见 data/group_messages/）")
        return False
    try:
        import requests
        payload = {"msgtype": "markdown", "markdown": {"content": message}}
        resp = requests.post(webhook, json=payload, timeout=10)
        if resp.status_code == 200 and resp.json().get('errcode') == 0:
            logger.info("✅ 群消息发送成功")
            return True
        logger.error("❌ 发送失败: %s", resp.text[:200])
        return False
    except Exception as e:
        logger.error("❌ 发送异常: %s", e)
        return False


def run_realtime():
    print("=" * 60)
    print("🔴 金策·进化枢纽 · 实读 MT5 全品种分析")
    print("=" * 60)
    analysis_md, discussion_md, read_json = _run_realtime_pipeline()
    if not analysis_md:
        print("❌ 实读/生成失败，请确认 MT5 终端运行且已登录")
        return
    if read_json:
        d = json.load(open(read_json, encoding='utf-8'))
        print(f"📡 数据来源：MT5 实读 账户 {d.get('account_login')} @ {d.get('read_time')}")
    print("\n" + "-" * 60)
    print(analysis_md)
    print("\n" + "-" * 60)
    print("💬 讨论引导已生成（略，见 data/group_messages/discussion_*.md）")

    cfg = _load_publisher()
    if cfg.get('enabled', False) and cfg.get('webhook'):
        print("\n📤 发送到金策宗师团群聊…")
        send_to_group(analysis_md)
        send_to_group(discussion_md)
    else:
        print("\n⚠️  未启用 webhook，分析已落盘 data/group_messages/，待配置后发送。")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='金策宗师团 行情分析群聊（实读版）')
    parser.add_argument('--realtime', action='store_true', help='实读 MT5 全品种分析（推荐）')
    parser.add_argument('--mode', choices=['analysis', 'discussion', 'both'], default='analysis')
    parser.add_argument('--test', action='store_true', help='只打印不发送')
    args = parser.parse_args()

    if args.realtime:
        run_realtime()
        return

    # 传统兼容路径（仅打印，不再编造价格）
    print("⚠️  传统新闻模式已不再编造价格；请用 --realtime 获取可信全品种分析。")


if __name__ == '__main__':
    main()
