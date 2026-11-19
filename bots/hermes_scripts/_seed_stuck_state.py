# -*- coding: utf-8 -*-
"""种今日去重态 + 验 check_delivery_stuck 修复: us_close 不再重报, 未告警的真卡节点保留一次"""
import json, datetime, zoneinfo, importlib.util

BJT = zoneinfo.ZoneInfo("Asia/Shanghai")
today = datetime.datetime.now(BJT).strftime("%Y-%m-%d")
STATE = r"E:\GoldstrategyEngine\data\jince_stuck_alert_state.json"
json.dump({"date": today, "alerted": ["us_close"]}, open(STATE, "w", encoding="utf-8"), ensure_ascii=False)
print("[1] 去重态已种:", json.dumps({"date": today, "alerted": ["us_close"]}, ensure_ascii=False))

spec = importlib.util.spec_from_file_location("wd", r"E:\workbuddy\国外模型\hermes\scripts\jince_watchdog.py")
wd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wd)
r1 = wd.check_delivery_stuck(today)
print("[2] 首跑(应剩真实卡点, us_close 被去重吃掉):", r1)
r2 = wd.check_delivery_stuck(today)
print("[3] 再跑(全部被去重吃掉, 应空):", r2)
print("[4] 去重态现值:", json.dumps(json.load(open(STATE, encoding="utf-8")), ensure_ascii=False))
