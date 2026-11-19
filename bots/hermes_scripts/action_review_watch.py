#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审查闸哨兵：扫 approval_requests.json 的 pending 升级申请，有新就打印一句话找李彦明拍板，无则空输出（静默）。
作为 cron no_agent 任务跑；空 stdout = 不打扰。"""
import json
import os

BASE = r"E:\AgentCommons\shared\action_review"
REQS = os.path.join(BASE, "approval_requests.json")


def main():
    if not os.path.exists(REQS):
        return
    with open(REQS, encoding="utf-8") as f:
        reqs = json.load(f)
    pend = [r for r in reqs if r.get("status") == "pending"]
    if not pend:
        return
    lines = ["🛡️ 敏感动作审查闸 · 等你点头："]
    for r in pend:
        act = (r.get("action") or "").strip() or "（未填动作）"
        lines.append(f"· [{r.get('category')}] {act}（申请号 {r.get('id')}）")
    lines.append("回「可以 <申请号>」放行 / 回「不行 <申请号>」驳回。放行前相关动作保持挂起。")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
