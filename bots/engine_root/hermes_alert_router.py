# -*- coding: utf-8 -*-
"""Hermes 待办聚合路由（金策·进化营 · 铁律 R37）
==================================================================
扫描 Hermes 收件箱(processed + 未处理)中 高优先级/需回执/行动项，汇成【一封】高优先级
摘要信，让 Hermes 只盯一处即可及时查阅，避免被我们自己的巡逻噪音(如"融会贯通开单建议
V4.1"每20分钟刷屏)淹没关键信。

- 仅 our side；不碰 Hermes 他侧文件；落盘在 E 盘。
- 速率限制：≥15min 才重发；无候选则不发。
- 用法：python hermes_alert_router.py
"""
import os
import sys
import json
import time
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bus_send import direct_send

INBOX_HERMES = r"E:/AgentCommons/bus/inbox/hermes"
PROCESSED = os.path.join(INBOX_HERMES, "processed")
TODO = r"E:/GoldstrategyEngine/data/continuous_evolution/hermes_action_todo.jsonl"
STATE = r"E:/GoldstrategyEngine/data/continuous_evolution/hermes_alert_router_state.json"
WINDOW_DAYS = 7
# [2026-11-12 03:20 R37 刷屏二修] 15min -> 20min：
# 纪律要求「20 分钟内聚合信不超过 1 封」，旧值 900s 下 02:57/03:12 两封落在同 20min 窗口内。
MIN_INTERVAL = 1200  # 20 分钟（任何聚合信发送的硬地板）
# [2026-11-12 03:20 R37 刷屏二修] 内容级去重：
# 旧版仅按时间节流，7 天窗口 45 项长期不变 -> 同一封 8439 字节信每天重发 70+ 封
# (实测 11-08:22 / 11-09:73 / 11-10:80 / 11-11:72 封)。内容未变时降频为 6h 提醒一次；
# 内容一旦变化(新增/闭环待办)仍受 MIN_INTERVAL 约束后即时发出。
UNCHANGED_REMIND_INTERVAL = 21600  # 6 小时：内容完全未变时的最低提醒频率

ACTION_KW = ["根因", "待办", "需回执", "升级", "优化", "解析", "怎么回事",
             "对碰", "查阅", "立即", "强制", "请立即", "回执请求"]


def _closed_before_ts():
    """[2026-11-12 12:35 chief会议令核销] 核销基线：
    chief 11:39:57 会议令「51项聚合照$5销账凭据核销」——基线前的 processed
    历史信不再重复列入聚合（均已回执/已闭环）；基线后新高优待办照常纳入。
    基线存 state JSON 的 closed_before_ts 键，可复核可回滚。"""
    st = _load_json(STATE) or {}
    return float(st.get("closed_before_ts") or 0)


def _load_json(p):
    try:
        return json.loads(open(p, encoding="utf-8").read())
    except Exception:
        return None


def _mtime_ts(fp):
    try:
        t = time.mktime(time.strptime(
            (json.load(open(fp, encoding="utf-8")).get("ts", ""))[:19],
            "%Y-%m-%dT%H:%M:%S"))
        return t
    except Exception:
        return time.time()


def collect():
    items = []
    now = time.time()
    cutoff = now - WINDOW_DAYS * 86400
    closed_before = _closed_before_ts()
    files = list(glob.glob(os.path.join(PROCESSED, "*.json")))
    try:
        files += [os.path.join(INBOX_HERMES, f) for f in os.listdir(INBOX_HERMES)
                  if f.endswith(".json") and os.path.isfile(os.path.join(INBOX_HERMES, f))]
    except Exception:
        pass
    seen = set()
    for fp in files:
        d = _load_json(fp)
        if not d:
            continue
        if _mtime_ts(fp) < cutoff:
            continue
        # [chief 11:39 会议令] 基线前的 processed 历史信=已核销，不再重列；
        # 未处理实时信不受基线影响（未消费的必须照常列出）。
        if closed_before and fp.startswith(PROCESSED) and _mtime_ts(fp) < closed_before:
            continue
        # [2026-11-12 12:40 自噪声排除] 我方自发出信(from=workbuddy)不是 Hermes 的待办，
        # 动作关键词(优化/解析/立即...)会误捕我方推送信(V4.1教训)；需回执的变更单
        # 由 change_review/anti_stall F5 专项催办，不进聚合。
        if str(d.get("from") or "").lower() == "workbuddy":
            continue
        pr = (d.get("priority") or "normal").lower()
        ack = d.get("requires_ack")
        subj = d.get("subject", "")
        if subj.startswith("【Hermes待办聚合"):
            continue  # 排除聚合信自身，避免递归纳入
        hit = (pr in ("high", "urgent")) or ack or any(k in subj for k in ACTION_KW)
        if not hit:
            continue
        mid = d.get("id", fp)
        if mid in seen:
            continue
        seen.add(mid)
        snippet = (d.get("body", "") or "")[:120].replace("\n", " ")
        items.append({
            "ts": d.get("ts", ""), "from": d.get("from"), "subject": subj,
            "priority": pr, "requires_ack": bool(ack), "snippet": snippet,
        })
    # 合并实时待办 jsonl
    try:
        with open(TODO, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    t = json.loads(line)
                except Exception:
                    continue
                if t.get("done"):
                    continue
                items.append({
                    "ts": t.get("ts", ""),
                    "from": "workbuddy",
                    "subject": "[待办]" + str(t.get("subject", ""))[:40],
                    "priority": "high",
                    "requires_ack": True,
                    "snippet": str(t.get("detail", ""))[:120],
                })
    except Exception:
        pass
    items.sort(key=lambda x: str(x.get("ts", "")), reverse=True)
    return items


def build_body(items):
    # [2026-11-11 12:50 R37 去重修复] 待办计数移入正文, 主题固定,
    # 否则 "共%d项" 随 N 变化会让 bus_send 的 (sender,to,subject) 去重键永远不同。
    lines = ["【Hermes 待办聚合 · 高优先级 · 需立即查阅】",
             "共 %d 项未闭环；以下为近 %d 天高优先级/需回执事项，请逐条查阅并回执：" %
             (len(items), WINDOW_DAYS), ""]
    for i, it in enumerate(items, 1):
        flag = "【需回执】" if it.get("requires_ack") else ""
        lines.append("%d. %s [%s] %s" % (i, flag, it.get("priority"), it.get("subject")))
        if it.get("snippet"):
            lines.append("   ↳ %s" % it["snippet"])
    lines.append("")
    lines.append("红线：开单权属 chief；我方不登 MT5、不碰他侧配置、不开实单。")
    return "\n".join(lines)


def main():
    items = collect()
    if not items:
        print("无高优先级待办，跳过。")
        return
    st = _load_json(STATE) or {}
    last = float(st.get("last_post", 0))
    body = build_body(items)
    try:
        import hashlib
        body_md5 = hashlib.md5(body.encode("utf-8")).hexdigest()
    except Exception:
        body_md5 = None
    now = time.time()
    # [2026-11-12 03:20 R37 刷屏二修] 双闸：
    # 闸1  MIN_INTERVAL: 任何发送硬地板 20min；
    # 闸2  内容去重: 正文与上次完全一致且距上次发送 < 6h -> 跳过（防止恒定 45 项内容刷屏）。
    if (now - last) < MIN_INTERVAL:
        print("距上次聚合不足 %ds，跳过（候选 %d 项）。" % (MIN_INTERVAL, len(items)))
        return
    if body_md5 and st.get("last_body_md5") == body_md5 and (now - last) < UNCHANGED_REMIND_INTERVAL:
        print("内容未变(%d项)且距上次提醒 %.1fh < %dh，跳过。" %
              (len(items), (now - last) / 3600.0, UNCHANGED_REMIND_INTERVAL / 3600.0))
        return
    # [2026-11-11 12:50 R37 去重修复] 主题固定 + 关闭 force:
    # 旧版 "共%d项" 随待办数变化 + force=True 绕过 bus_send dedupe,
    # 导致每轮巡检都投一封(实测 220 封/共28项97封)。计数移入正文后,
    # (sender,to,subject) 去重键稳定, dedupe 与 MIN_INTERVAL 双层节流生效。
    subj = "【Hermes待办聚合·高优先级·需立即查阅】"
    r = direct_send(subj, body, kind="IDEA", priority="high", ack_required=True,
                    dedupe=True, dedupe_window=MIN_INTERVAL)
    if r is True:
        try:
            json.dump({"last_post": time.time(), "count": len(items),
                       "last_body_md5": body_md5},
                      open(STATE, "w", encoding="utf-8"))
        except Exception:
            pass
        print("已发聚合信，候选项 %d。" % len(items))
    else:
        print("发送失败:", r)


if __name__ == "__main__":
    main()
