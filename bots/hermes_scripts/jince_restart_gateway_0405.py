# -*- coding: utf-8 -*-
"""JinceRestartGateway 04:05 one-shot: 复查空闲 -> gateway stop/start (pywin32 生效) + 记台账。no_agent 纯 Python, 0 LLM."""
import subprocess, time, sys, os, glob, json

HERMES_DIR = r"E:\workbuddy\国外模型\hermes"
H = os.path.join(HERMES_DIR, "bin", "hermes.exe")
LEDGER = r"E:\GoldstrategyEngine\data\learning_ledger_20261105.md"
log = []

def sh(args):
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=HERMES_DIR, timeout=180)
    return (r.stdout or "").strip(), (r.stderr or "").strip(), r.returncode

try:
    # 1. 复查: 试 stop (有 live session 会被 gateway 自己拒 -> 安全机制, 不硬来)
    out, err, rc = sh([H, "gateway", "stop"])
    if "Refusing" in out or "would be interrupted" in out or rc != 0:
        log.append("SKIP: gateway 拒停(live sessions 在途): " + (out + err)[:300])
        print("\n".join(log)); sys.exit(0)
    time.sleep(8)
    # 2. 启动 (pywin32 已装 -> log lock 不再降级)
    out2, err2, rc2 = sh([H, "gateway", "start"])
    log.append("START: " + (out2 + err2)[:300])
    time.sleep(15)
    # 3. 验证: status
    out3, err3, rc3 = sh([H, "gateway", "status"])
    log.append("STATUS: " + (out3 + err3)[:300])
    print("\n".join(log))
except subprocess.TimeoutExpired:
    print("TIMEOUT: gateway 命令超时(积压严重) — 顺延 04:30 重试")
except Exception as e:
    print("ERR: %r" % e)

# 台账留痕
try:
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write("\n## 十六、04:05 网关重启(一次性任务) 留痕\n时间: %s\n%s\n" % (time.strftime("%m-%d %H:%M %Z"), "\n".join(log) or "NO_LOG"))
except Exception:
    pass
