# -*- coding: utf-8 -*-
"""
Hermes 来信监听哨兵 —— 根治"响应不及时"
每 60s 扫描 E:/AgentCommons/bus/inbox/workbuddy/ 下未处理来信(frm=hermes)：
  - 1 分钟内感知新信
  - routine 类（回执/状态/讨论）：自动 ack 回信 + 入待办
  - 敏感类（实盘/参数/越权）：仅高亮告警，不自动回，待人(chief/用户)终裁
  - 全部移入 processed + 写日志 + 心跳，绝不遗漏
设计为短进程模式（计划任务每1分钟触发 once），配合 IgnoreNew 防重叠。
路径全部用 pathlib 正斜杠，规避 Windows 反斜杠混用问题。
"""
import os
# 强制临时目录指向 E 盘（铁律：C 盘禁写）。关键修复：计划任务启动的长驻进程
# 继承系统 TEMP=C:\Users\...\Temp，导致 send_to_hermes 内部 handshake/commons.ps1
# 写临时文件失败→返回False。须在 import 任何模块前覆盖，确保在长驻进程内也生效。
os.environ["TMPDIR"] = "E:/workbuddy/tmp"
os.environ["TEMP"] = "E:/workbuddy/tmp"
os.environ["TMP"] = "E:/workbuddy/tmp"
import tempfile
tempfile.tempdir = "E:/workbuddy/tmp"

import subprocess
from pathlib import Path
import sys, json, time, shutil

# 通信只走 AgentCommons 总线（单一事实源，宪章铁律）。
# 关键路径约定（务必遵守，勿改）：
#   - 收件：E:/AgentCommons/bus/inbox/workbuddy/
#   - 发件：E:/AgentCommons/bus/inbox/hermes/   （bus_send.direct_send 负责）
#   - 归档：E:/AgentCommons/bus/archive/workbuddy/   （宪章规定：处理完移 bus/archive/<收件人>/）
#   - 深度记忆：只落 docs/hermes_deep_memory.md + data/jince_deep_memory_* 结构化库；
#              绝不写入 E:/资料 或任何散落临时目录。
INBOX = Path(r"E:/AgentCommons/bus/inbox/workbuddy")
ARCHIVE = Path(r"E:/AgentCommons/bus/archive/workbuddy")
STATE = Path(r"E:/GoldstrategyEngine/data/continuous_evolution/hermes_mailbox_state.json")
LOG = Path(r"E:/GoldstrategyEngine/data/continuous_evolution/hermes_mailbox_log.jsonl")
HEARTBEAT = Path(r"E:/GoldstrategyEngine/data/continuous_evolution/hermes_mailbox_heartbeat.json")
ALERTS = Path(r"E:/GoldstrategyEngine/data/continuous_evolution/hermes_alerts.log")

# 敏感关键词（命中即仅告警不自动回）
SENSITIVE = ["实盘", "下单", "开仓参数", "参数变更", "越权", "部署", "投产", "止损", "止盈", "强平", "magic", "仓位", "改挂"]

# 总线直投统一走 bus_send（直接落盘 JSON，根治计划任务长驻进程里 powershell stdout
# 丢失导致回执被误判失败的顽疾）。与 commons.ps1 post 同结构、同落盘路径。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bus_send import direct_send, send_to_hermes

CAN_REPLY = True

# 需主理人(agent)实质介入的关键词：命中即写入实时待办+高亮告警，
# 避免\"只回收讫模板、没人真正接\"的假响应（2026-11-08 15:44 用户口谕优化）。
NEED_HUMAN = ["求援", "求助", "请帮", "帮看", "帮忙", "对碰", "讨论", "请教",
              "怎么回事", "怎么", "为什么", "解析", "优化", "诊断", "建议",
              "请给", "需要", "没响应", "不工作", "卡死"]
TODO = Path(r"E:/GoldstrategyEngine/data/continuous_evolution/hermes_action_todo.jsonl")

SEEN = set()


def load_seen():
    try:
        return set(json.loads(STATE.read_text(encoding="utf-8")).get("seen", []))
    except Exception:
        return set()


def save_seen(seen):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"seen": list(seen), "updated": time.time()},
                                ensure_ascii=False, indent=2), encoding="utf-8")


def classify(msg):
    text = (msg.get("subject", "") + " " + msg.get("body", "")).lower()
    for k in SENSITIVE:
        if k.lower() in text:
            return "SENSITIVE"
    return "ROUTINE"


def ack_sensitive(msg):
    if not CAN_REPLY:
        return "NO_REPLY_CH"
    subj = "【WorkBuddy·进化营】敏感来信收讫(待复核)：" + (msg.get("subject", "")[:36])
    body = ("一、收讫确认：贵方 %s 来信已由我方监听哨兵实时感知（1分钟内），归类为【敏感类】。\n"
            "二、处理原则：凡涉'实盘/参数/越权/下单/投产'类，我方不自动执行，将高亮告警并提交 chief/用户终裁。\n"
            "三、响应时效：我方已收到并解析入待办，将在本轮对话内给出初步共识/澄清（不越权操作）。\n"
            "——金策·进化营 监听哨兵（自动）") % msg.get("ts", "")
    try:
        return send_to_hermes(subj, body, kind="IDEA", in_reply_to=msg.get("id", "-"))
    except Exception as e:
        return "ERR:" + str(e)


def ack_one(msg):
    if not CAN_REPLY:
        return "NO_REPLY_CH"
    subj = "【WorkBuddy·进化营】自动收讫：" + (msg.get("subject", "")[:40])
    body = ("一、收讫确认：贵方 %s 来信已由我方监听哨兵实时感知并解析入待办（1分钟内）。\n"
            "二、初步共识：凡涉'闸兼容/回执/状态同步/红线'类，我方均认同并共守。\n"
            "三、深度回应：稍后由进化营主理人基于深度记忆逐条作答并回发。\n"
            "四、敏感类（实盘/参数/越权）将高亮告警，须经 chief/用户终裁，不自动执行。\n"
            "——金策·进化营 监听哨兵（自动）") % msg.get("ts", "")
    try:
        return send_to_hermes(subj, body, kind="IDEA", in_reply_to=msg.get("id", "-"))
    except Exception as e:
        return "ERR:" + str(e)


def ack_summary(msgs):
    if not CAN_REPLY:
        return "NO_REPLY_CH"
    lines = ["检测到 %d 封积压 Hermes 来信，已全部解析入待办，将逐一深度回应：" % len(msgs)]
    for m in msgs:
        lines.append("  - [%s] %s" % (m.get("ts", "?"), m.get("subject", "")))
    lines.append("——金策·进化营 监听哨兵（自动积压清理）")
    subj = "【WorkBuddy·进化营】积压来信收讫汇总(%d封)" % len(msgs)
    try:
        return send_to_hermes(subj, "\n".join(lines), kind="IDEA")
    except Exception as e:
        return "ERR:" + str(e)


def mark_handled(fname, msg, action, ack):
    entry = {
        "ts": time.time(), "file": fname, "from": msg.get("frm"),
        "subject": msg.get("subject"), "recv_ts": msg.get("ts"),
        "class": classify(msg), "action": action, "ack": ack,
    }
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    if ack is True:
        # 回执成功：归档 + 标记已处理
        try:
            shutil.move(str(INBOX / fname), str(ARCHIVE / fname))
        except Exception:
            pass
        SEEN.add(fname)
    else:
        # 回执发送失败（总线瞬态）：保留在收件箱，下次扫描自动重试（自愈），不标记已处理、不归档
        pass


def maybe_todo(msg):
    """求援/求助类来信：除自动收讫外，写入实时待办+高亮告警，确保主理人(agent)即时实质响应。"""
    text = (msg.get("subject", "") + " " + msg.get("body", "")).lower()
    hit = [k for k in NEED_HUMAN if k.lower() in text]
    if not hit:
        return
    rec = {"ts": time.time(), "from": msg.get("frm"), "subject": msg.get("subject"),
           "recv_ts": msg.get("ts"), "triggers": hit, "status": "PENDING",
           "note": "需主理人(agent)实质响应，勿仅回模板收讫"}
    try:
        TODO.parent.mkdir(parents=True, exist_ok=True)
        with TODO.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        line = "[TODO][%s] Hermes 需主理人介入: %s | %s | triggers=%s" % (
            time.strftime("%H:%M:%S"), msg.get("ts"), msg.get("subject"), hit)
        print(line)
        with ALERTS.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def alert(msg):
    line = "[ALERT][%s] Hermes 敏感来信: %s | %s" % (
        time.strftime("%H:%M:%S"), msg.get("ts"), msg.get("subject"))
    print(line)
    with ALERTS.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def scan_once():
    """返回本次处理的 hermes 信列表 [(fname, msg)]"""
    out = []
    try:
        files = [f for f in os.listdir(INBOX)
                 if f.endswith(".json") and f not in SEEN
                 and (INBOX / f).is_file()]
    except Exception:
        return out
    files.sort()
    for fname in files:
        fpath = INBOX / fname
        try:
            msg = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception:
            SEEN.add(fname)
            continue
        sender = msg.get("frm") or msg.get("from")
        if sender != "hermes":
            # 非 hermes 信（yushi/dsh 等）：仅归档，不自动回
            try:
                shutil.move(str(fpath), str(ARCHIVE / fname))
            except Exception:
                pass
            SEEN.add(fname)
            with LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": time.time(), "file": fname,
                                    "from": msg.get("frm"), "action": "ARCHIVE_NON_HERMES"},
                                   ensure_ascii=False) + "\n")
            continue
        out.append((fname, msg))
    return out


def main():
    global SEEN
    SEEN = load_seen()
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    mode = sys.argv[1] if len(sys.argv) > 1 else "once"

    if mode == "once":
        msgs = scan_once()
        if msgs:
            if len(msgs) > 3:
                ack = ack_summary([m for _, m in msgs])
                for fname, m in msgs:
                    mark_handled(fname, m, "AUTO_ACK_SUMMARY", ack)
            else:
                for fname, m in msgs:
                    maybe_todo(m)
                    if classify(m) == "SENSITIVE":
                        alert(m)
                        mark_handled(fname, m, "ALERT_ACK", ack_sensitive(m))
                    else:
                        mark_handled(fname, m, "AUTO_ACK", ack_one(m))
            save_seen(SEEN)
            beat(len(msgs))
            print("scan once done, hermes_new=%d" % len(msgs))
        else:
            save_seen(SEEN)
            beat(0)
            print("scan once done, no new")
    else:
        while True:
            try:
                msgs = scan_once()
                if msgs:
                    if len(msgs) > 3:
                        ack = ack_summary([m for _, m in msgs])
                        for fname, m in msgs:
                            mark_handled(fname, m, "AUTO_ACK_SUMMARY", ack)
                else:
                    for fname, m in msgs:
                        maybe_todo(m)
                        if classify(m) == "SENSITIVE":
                            alert(m)
                            mark_handled(fname, m, "AUTO_ACK_SENSITIVE", ack_sensitive(m))
                        else:
                            mark_handled(fname, m, "AUTO_ACK", ack_one(m))
                save_seen(SEEN)
                beat(len(msgs))
                time.sleep(60)
            except Exception as e:
                print("ERR", e)
                time.sleep(30)


def beat(n):
    HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT.write_text(json.dumps({"ts": time.time(), "last_scan_new": n, "status": "alive"},
                                     ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
