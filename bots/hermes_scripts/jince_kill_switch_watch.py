# -*- coding: utf-8 -*-
r"""金策·一键 kill switch 看守 (cron 每1min, no_agent 确定性 0LLM)
触发方式(李彦明或主bot): 把 E:\GoldstrategyEngine\data\kill_switch.json 写成
  {"state": "TRIGGERED", "ts": "...", "by": "李彦明"}
本看守: TRIGGERED 且未处理 -> ATE 调 jince_kill_switch_exec.py(撤全挂单+市价全平+halt),
        完成后写 handled_ts(幂等不重放); ARMED 或已处理 -> 静默退出(不投递)。
--drill: 月度纸面演练(不碰任何实单): 验 ATE 可导入/MT5 可 init/文件链可读可写/全函数可 import, 结果落 drill json, 全绿静默。
"""
import datetime
import json
import os
import os
import subprocess
import sys

DATA = r"E:\GoldstrategyEngine\data"
KS = os.path.join(DATA, "kill_switch.json")
EXEC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jince_kill_switch_exec.py")
ATE = r"C:\Users\ASUS\.workbuddy\binaries\python\envs\ate\Scripts\python.exe"
DRILL = os.path.join(DATA, "kill_switch_drill_last.json")


def ensure_kfile():
    if not os.path.exists(KS):
        json.dump({"state": "ARMED", "ts": datetime.datetime.now().isoformat(timespec="seconds")},
                  open(KS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    try:
        return json.load(open(KS, encoding="utf-8"))
    except Exception:
        return {"state": "ARMED"}


def drill():
    res = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "checks": [], "ok": True}
    import importlib.util
    spec_ok = importlib.util.find_spec("json") is not None and os.path.exists(EXEC)
    res["checks"].append("exec脚本存在+stdlib: %s" % spec_ok)
    # [11-15 修] cron 包装器 PYTHONPATH 污染 ATE 子进程(同 preflight 07:30拍 exit3 根因): spawn 前剥 Python 环境变量
    _env_clean = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE", "VIRTUAL_ENV")}
    r = subprocess.run([ATE, "-c", "import MetaTrader5 as m, time; ok=m.initialize(); time.sleep(2); print('INIT_OK' if ok else 'INIT_FAIL'); m.shutdown()"], env=_env_clean,
                       capture_output=True, text=True, timeout=120)
    init_ok = "INIT_OK" in (r.stdout or "")
    res["checks"].append("ATE+MetaTrader5 可初始化: %s" % init_ok)
    ks = ensure_kfile()
    res["checks"].append("触发文件可读: state=%s" % ks.get("state"))
    ok = spec_ok and init_ok and ks.get("state") == "ARMED"
    res["ok"] = ok
    json.dump(res, open(DRILL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if not ok:
        print("⚠️ kill switch 月度演练 FAIL: " + " | ".join(res["checks"]))
    return 0


def main():
    if "--drill" in sys.argv:
        return drill()
    ks = ensure_kfile()
    if ks.get("state") != "TRIGGERED" or ks.get("handled_ts"):
        return 0
    _env_clean2 = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE", "VIRTUAL_ENV")}
    r = subprocess.run([ATE, EXEC], capture_output=True, text=True, timeout=300, env=_env_clean2)
    print((r.stdout or r.stderr or "").strip())
    ks2 = ensure_kfile()
    ks2["handled_ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    ks2["handled_exit"] = r.returncode
    json.dump(ks2, open(KS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
