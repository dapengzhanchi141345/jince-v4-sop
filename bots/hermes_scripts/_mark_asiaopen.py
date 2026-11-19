# -*- coding: utf-8 -*-
"""把 asia_open 标'已处理'进看门狗去重态: 08:05 开评 delivery_failed 未进群,
但已被 08:56 新开评(job 94aa7617fc68 last_status=ok)覆盖 -> 不补投旧正文(3.5h 过期),
防下一班 tick 重刷'投递卡'。us_close 早前已入去重态(02:05 实际已进群=台账未销账误报)."""
import json, datetime, zoneinfo

BJT = zoneinfo.ZoneInfo("Asia/Shanghai")
today = datetime.datetime.now(BJT).strftime("%Y-%m-%d")
STATE = r"E:\GoldstrategyEngine\data\jince_stuck_alert_state.json"

try:
    st = json.load(open(STATE, encoding="utf-8"))
except Exception:
    st = {"date": today, "alerted": []}
st["date"] = today
st["alerted"] = sorted(set(st.get("alerted", [])) | {"us_close", "asia_open"} )
st["note"] = ("us_close=02:05已进群(台账未销账误报,不补投); "
              "asia_open=08:05开评delivery_failed未进群,已被08:56新开评(94aa7617fc68 ok)覆盖,不补投旧正文")
json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False)
print("去重态现值:", json.dumps(st, ensure_ascii=False))
