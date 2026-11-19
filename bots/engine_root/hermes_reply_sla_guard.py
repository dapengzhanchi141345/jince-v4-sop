# -*- coding: utf-8 -*-
"""
Hermes 回执 SLA 追办哨兵 —— 根治"Hermes 不及时回我"
目标：双向及时。我方监听哨兵已保证 1 分钟内给 Hermes 回执；本哨兵保证
      Hermes 在 SLA 内回应我方（否则自动催办 + 告警），避免我方发信石沉大海。

机制（基于总线落盘文件，零侵入，不修改任何发送脚本）：
  - outbox：扫描 E:/AgentCommons/bus/inbox/hermes/ 下我方(__workbuddy__)发信，
            解析 id / ts / subject；主题含"回执|回复|讨论|请教|对碰|请|确认|反馈|问"
            的记为 expect_reply（明确期待回执）。
  - hermes_in：扫描 E:/AgentCommons/bus/inbox/workbuddy/（含 archive）下 frm=hermes 来信。
  - 匹配：因 Hermes 回信不带 in_reply_to，用"时间窗口 + 主题2-gram 软匹配"。
            对每封 expect_reply 的 outbox 信 O，若其后 SLA 窗口内存在主题相关
            的 Hermes 来信 → 已回；否则超时未回。
  - 全局静默检测：若我方最近发信距今 > SLA，且之后 Hermes 完全无来信 → 整体催办。
  - 催办限频：同一封 outbox 至少间隔 6h 才再催；本地告警 + 落盘状态防重复。

红线：本哨兵只发"催办/健康询问"类中性信，绝不替 chief/用户做决策或越权操作。
"""
import os
import subprocess
# 强制临时目录指向 E 盘（铁律：C 盘禁写）。修复：计划任务长驻进程继承系统 C 盘 TEMP，
# 导致 send_to_hermes 内部 handshake/commons.ps1 写临时文件失败→返回False。须在 import 前覆盖。
os.environ["TMPDIR"] = "E:/workbuddy/tmp"
os.environ["TEMP"] = "E:/workbuddy/tmp"
os.environ["TMP"] = "E:/workbuddy/tmp"
import tempfile
tempfile.tempdir = "E:/workbuddy/tmp"

from pathlib import Path
import sys, json, time, re

# 通信只走 AgentCommons 总线（单一事实源，宪章铁律）。
# 关键路径约定：收件 inbox/workbuddy、发件 inbox/hermes、归档 bus/archive/workbuddy
# （宪章规定：处理完移 bus/archive/<收件人>/）。深度记忆只落 docs/hermes_deep_memory.md
# + data/jince_deep_memory_* 结构化库；绝不写入 E:/资料 或散落临时目录。
HERMES_INBOX = Path(r"E:/AgentCommons/bus/inbox/workbuddy")
ARCHIVE = Path(r"E:/AgentCommons/bus/archive/workbuddy")
OUTBOX_DIR = Path(r"E:/AgentCommons/bus/inbox/hermes")
STATE = Path(r"E:/GoldstrategyEngine/data/continuous_evolution/evo_sla_state.json")
ALERTS = Path(r"E:/GoldstrategyEngine/data/continuous_evolution/evo_sla_alerts.log")

SLA_MIN = 60            # 期待回执的 SLA（分钟）
CHASE_GAP_MIN = 360     # 同一封信两次催办最小间隔（分钟）
EXPECT_KW = ["回执", "回复", "讨论", "请教", "对碰", "请", "确认", "反馈", "问", "建议"]

# 总线直投统一走 bus_send（直接落盘 JSON，根治长驻进程 powershell stdout 丢失问题）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bus_send import direct_send, send_to_hermes

CAN_REPLY = True


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"last_chase": {}, "hermes_last_active": 0}


def save_state(st):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_ts_from_filename(fname):
    """从 '20261108-122519__workbuddy__主题__id.json' 解析时间"""
    m = re.match(r"(\d{8})-(\d{6})__", fname)
    if m:
        try:
            return time.mktime(time.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S"))
        except Exception:
            return None
    return None


def bigrams(s):
    s = re.sub(r"[\s\-_【】()（）\[\]【】,.，。:：!！?？]", "", s)
    return set(s[i:i + 2] for i in range(len(s) - 1))


def get_outbox():
    """我方已发信（期待回执的）"""
    out = []
    if not OUTBOX_DIR.exists():
        return out
    for f in os.listdir(OUTBOX_DIR):
        if not f.endswith(".json") or "__workbuddy__" not in f:
            continue
        ts = parse_ts_from_filename(f)
        if ts is None:
            continue
        try:
            d = json.loads((OUTBOX_DIR / f).read_text(encoding="utf-8"))
        except Exception:
            continue
        subj = d.get("subject", "")
        mid = d.get("id") or f[:-5].split("__")[-1]
        expect = any(k in subj for k in EXPECT_KW)
        out.append({"id": mid, "ts": ts, "subject": subj, "expect": expect, "file": f})
    out.sort(key=lambda x: x["ts"])
    return out


def get_hermes_in():
    """Hermes 来信（含 archive）"""
    res = []
    for base in (HERMES_INBOX, ARCHIVE):
        if not base.exists():
            continue
        for f in os.listdir(base):
            if not f.endswith(".json") or "__hermes__" not in f:
                continue
            try:
                d = json.loads((base / f).read_text(encoding="utf-8"))
            except Exception:
                continue
            if (d.get("frm") or d.get("from")) != "hermes":
                continue
            ts = None
            if d.get("ts"):
                try:
                    ts = time.mktime(time.strptime(str(d["ts"]).replace("T", "")[:14], "%Y%m%d%H%M%S"))
                except Exception:
                    ts = parse_ts_from_filename(f)
            if ts is None:
                ts = parse_ts_from_filename(f)
            res.append({"ts": ts, "subject": d.get("subject", ""), "id": d.get("id", "")})
    res.sort(key=lambda x: (x["ts"] or 0))
    return res


def matched(ob, hermes_in, sla_ts):
    """O 发出后 SLA 窗口内是否有主题相关的 Hermes 来信"""
    for h in hermes_in:
        if h["ts"] is None or h["ts"] < ob["ts"]:
            continue
        if h["ts"] > sla_ts:
            break
        if bigrams(ob["subject"]) & bigrams(h["subject"]):
            return h
    return None


def alert(msg):
    line = "[SLA-ALERT][%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line)
    with ALERTS.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def chase(ob, reason, st):
    """对同一封超时信限频催办"""
    now = time.time()
    last = st.get("last_chase", {}).get(ob["id"], 0)
    if now - last < CHASE_GAP_MIN * 60:
        return "SKIPPED_RATELIMIT"
    if not CAN_REPLY:
        return "NO_REPLY_CH"
    subj = "【WorkBuddy·进化营】催办回执：" + ob["subject"][:36]
    body = ("一、我方于 %s 已发送《%s》并期待回执，距发信已超 %d 分钟未收到贵方回应。\n"
            "二、请贵方在收到本催办后尽快回执/讨论；若已回请忽略。\n"
            "三、本催办由回执 SLA 追办哨兵自动发出（限频，不重复刷屏）。\n"
            "——金策·进化营 回执 SLA 追办哨兵（自动）") % (
        time.strftime("%Y-%m-%d %H:%M", time.localtime(ob["ts"])), ob["subject"],
        int((now - ob["ts"]) / 60))
    try:
        r = direct_send(subj, body, kind="IDEA", in_reply_to=ob["id"])
        st.setdefault("last_chase", {})[ob["id"]] = now
        return r
    except Exception as e:
        return "ERR:" + str(e)


def main():
    st = load_state()
    outbox = get_outbox()
    hermes_in = get_hermes_in()
    now = time.time()

    # 更新 Hermes 最后活跃时间
    h_times = [h["ts"] for h in hermes_in if h["ts"]]
    if h_times:
        st["hermes_last_active"] = max(st["hermes_last_active"], max(h_times))

    chased = []
    for ob in outbox:
        if not ob["expect"]:
            continue
        if now - ob["ts"] > 24 * 3600:   # 仅追近 24h 超时信，避免骚扰历史旧账
            continue
        sla_ts = ob["ts"] + SLA_MIN * 60
        if now < sla_ts:
            continue  # 还在 SLA 窗口内，不催
        if matched(ob, hermes_in, sla_ts):
            continue  # 已回
        r = chase(ob, "timeout", st)
        chased.append((ob["subject"], r))

    # 全局静默检测：最近发信后 Hermes 再无来信
    if outbox:
        last_out = max(o["ts"] for o in outbox)
        if now - last_out > SLA_MIN * 60 and (st.get("hermes_last_active", 0) < last_out):
            last = st.get("last_chase", {}).get("__global__", 0)
            if now - last >= CHASE_GAP_MIN * 60 and CAN_REPLY:
                subj = "【WorkBuddy·进化营】通信健康询问"
                body = ("一、我方最近一次发信为 %s，此后未收到贵方任何来信，已超过 %d 分钟。\n"
                        "二、如通信链路正常，请回执任意内容以确认活跃；如我方监听有误请指正。\n"
                        "——金策·进化营 回执 SLA 追办哨兵（自动）") % (
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(last_out)), SLA_MIN)
                try:
                    direct_send(subj, body, kind="IDEA")
                    st.setdefault("last_chase", {})["__global__"] = now
                    chased.append(("__global__", "OK"))
                except Exception as e:
                    chased.append(("__global__", "ERR:" + str(e)))

    # 集成 Hermes 待办聚合路由（铁律 R37）：每轮顺带刷新高优先级聚合信，
    # 让 Hermes 只盯一处即可及时查阅，关键信不再被巡逻噪音淹没。
    try:
        import importlib.util as _ilu
        _rspec = _ilu.spec_from_file_location(
            "hermes_alert_router",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "hermes_alert_router.py"))
        _rmod = _ilu.module_from_spec(_rspec)
        _rspec.loader.exec_module(_rmod)
        _rmod.main()
    except Exception as e:
        alert("alert_router 集成异常: %s" % e)

    save_state(st)
    print("SLA scan done. outbox=%d hermes_in=%d chased=%d" % (len(outbox), len(hermes_in), len(chased)))
    for s, r in chased:
        print("  chase:", s[:40], "->", r)


if __name__ == "__main__":
    main()
