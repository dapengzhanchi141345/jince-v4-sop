# -*- coding: utf-8 -*-
"""
AgentCommons 总线直投（金策·进化营核心通信模块）
================================================
根治历史 bug：计划任务长驻进程里 `powershell ... commons.ps1 post` 返回 rc=0 但
stdout 为空（"已投递"确认串丢失），导致 send 被误判失败 → 自动回执不归档 → 每 60s
重复投递，污染 Hermes 收件箱。

本模块在 Python 内直接落盘与 commons.ps1 `post` 完全一致的 JSON 消息到
E:/AgentCommons/bus/inbox/<to>/，100% 绕过 powershell 环境依赖，在任何进程
（交互式 / 计划任务长驻）中均稳定送达。消息结构、文件名格式与总线规范逐字段对齐。
"""
import os
import re
import sys
import json
import time
import uuid
from pathlib import Path
from datetime import datetime

BUS_ROOT = Path(r"E:/AgentCommons/bus/inbox")
_DEDUPE_PATH = Path(r"E:/GoldstrategyEngine/data/continuous_evolution/bus_send_dedupe.json")


def _dedupe_should_skip(sender, to, subj, window, force):
    """去重节流：相同(发件人+收件人+主题)在窗口内重复投递则抑制，避免刷屏淹没关键信。

    返回 (suppressed: bool, last_ts: str|None)。force=True 时强制直发（用于关键升级信）。
    """
    if force:
        return False, None
    try:
        import time as _t
        st = json.loads(_DEDUPE_PATH.read_text(encoding="utf-8")) if _DEDUPE_PATH.exists() else {}
    except Exception:
        st = {}
    key = "%s|%s|%s" % (sender, to, subj)
    now = time.time()
    last = st.get(key)
    if last and (now - float(last)) < window:
        return True, str(last)
    st[key] = now
    try:
        _DEDUPE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _DEDUPE_PATH.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return False, None


def _slug(text):
    if not text or not str(text).strip():
        return "message"
    s = re.sub(r'[\\/:*?"<>|\r\n\t]', ' ', str(text))
    s = s.strip()
    if len(s) > 24:
        s = s[:24]
    return s


def direct_send(subj, body, kind="IDEA", in_reply_to="-", to="hermes", sender="workbuddy",
                priority="normal", ack_required=False, dedupe=True, dedupe_window=1800, force=False):
    """直投一条总线消息到 to 的收件箱。成功返回 True，失败返回 False/错误串。

    落盘路径：
      E:/AgentCommons/bus/inbox/<to>/<yyyyMMdd-HHmmss>__<sender>__<slug>__<r4>.json
    JSON 结构与 commons.ps1 post 完全对齐
      (id / ts / from / to / subject / body / priority / status / refs)。

    新增（铁律 R37 · 防淹没）：
      - priority: "normal" | "high" | "urgent" —— 关键信置 high/urgent 让 Hermes 优先查阅。
      - ack_required: True 时写 requires_ack 字段，供 SLA 追办强追。
      - dedupe/force: 同(发件人+收件人+主题)在 dedupe_window 秒内重复投递自动抑制（返回
        "SUPPRESSED_DUP:<last>"），force=True 强制直发（用于关键升级信）。
    """
    # 去重节流：避免我们自己的重复建议刷屏淹没关键信
    if dedupe and not force:
        skip, last = _dedupe_should_skip(sender, to, subj, dedupe_window, force)
        if skip:
            return "SUPPRESSED_DUP:" + (last or "")
    try:
        inbox = BUS_ROOT / to
        inbox.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return "ERR_MKDIR:" + str(e)
    diag = []
    for _i in range(3):
        try:
            mid = time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
            stamp = time.strftime("%Y%m%d-%H%M%S")
            # 宪章文件名格式：<yyyyMMdd-HHmmss>__<发件人>__<主题前24字>.json
            # 仅在同秒同发件人同主题（极罕见）时追加 -<r4> 去重后缀，保证主名合规。
            r4 = uuid.uuid4().hex[:4]
            fname = "%s__%s__%s.json" % (stamp, sender, _slug(subj))
            fpath = inbox / fname
            if fpath.exists():
                fname = "%s__%s__%s-%s.json" % (stamp, sender, _slug(subj), r4)
                fpath = inbox / fname
            msg = {
                "id": mid,
                "ts": datetime.now().isoformat(),
                "from": sender,
                "to": to,
                "subject": subj,
                "body": body,
                "priority": priority,
                "requires_ack": bool(ack_required),
                "status": "pending",
                "refs": [],
            }
            fpath.write_text(json.dumps(msg, ensure_ascii=False, indent=2), encoding="utf-8")
            if fpath.exists() and fpath.stat().st_size > 0:
                return True
            diag.append("att%d ZERO" % _i)
        except Exception as e:
            diag.append("att%d EXC=%r" % (_i, e))
        time.sleep(1)
    try:
        d = Path(r"E:/GoldstrategyEngine/data/continuous_evolution")
        d.mkdir(parents=True, exist_ok=True)
        with open(str(d / "evo_send_diag.log"), "a", encoding="utf-8") as f:
            f.write("[%s] SUBJ=%s -> FAIL\n%s\n\n" % (time.strftime("%H:%M:%S"), subj, "\n".join(diag)))
    except Exception:
        pass
    return False


def send_to_hermes(subj, body, kind="IDEA", in_reply_to="-"):
    """兼容别名：发往 Hermes。"""
    return direct_send(subj, body, kind=kind, in_reply_to=in_reply_to, to="hermes", sender="workbuddy")
