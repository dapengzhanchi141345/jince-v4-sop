# -*- coding: utf-8 -*-
"""跑 asia_open 去重标记 + 验下一班 tick 不再报它"""
import subprocess, sys, importlib.util, datetime, zoneinfo, json

print("[1] 跑标记脚本:")
r = subprocess.run([sys.executable, "_mark_asiaopen.py"], capture_output=True, text=True)
print(r.stdout.strip() if r.stdout else r.stderr[:200])

spec = importlib.util.spec_from_file_location("wd", r"E:\workbuddy\国外模型\hermes\scripts\jince_watchdog.py")
wd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wd)
today = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
print("[2] check_delivery_stuck(today) =", wd.check_delivery_stuck(today), "(应为空=不再刷 asia_open)")
st = json.load(open(r"E:\GoldstrategyEngine\data\jince_stuck_alert_state.json", encoding="utf-8"))
print("[3] 去重态:", json.dumps(st, ensure_ascii=False)[:160])
