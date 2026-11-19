# -*- coding: utf-8 -*-
"""销账 us_close + asia_open: 确认实际进群事实, 置 delivered 停止即时重投刷屏
- us_close: 02:05 正文本会话已收进群(12:45 补发=刷第二遍, 判误刷), 销账
- asia_open: 08:05 原报未进群, 但 12:45 即时重投的已是最新重新生成版(12:45 tick 数据),
  内容不丢, 本轮后停刷, 销账"""
import sys, importlib.util, datetime, zoneinfo, json
spec = importlib.util.spec_from_file_location("wd", "jince_watchdog.py")
wd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wd)
today = datetime.datetime.now(wd.BJT).strftime("%Y-%m-%d")
wd.mark_delivered("us_close", today, "02:05 正文实际已进群(本会话 02:0x 已收+摘要), 12:45 补发=误刷第二遍, 销账停刷")
wd.mark_delivered("asia_open", today, "08:05 原报漏进, 12:45 即时重投版(最新tick)已进群, 内容不丢, 销账停刷")
print("销账完成:")
for k in ("us_close", "asia_open"):
    d = json.load(open(wd.QUEUE, encoding="utf-8"))
    for it in d.get("items", []):
        if it.get("key") == k and it.get("status") == "delivered":
            print(" ", k, "->", it.get("note", "")[:60])
# 验: 下一班 check_delivery_stuck 后 stuck 是否被 delivered_nodes 摘掉
stuck = wd.check_delivery_stuck(today)
done = wd.delivered_nodes(today)
print("stuck(原始):", [(s[0], s[2]) for s in stuck])
print("done(已销账):", sorted(done))
print("过滤后仍会即时重投的:", [s[0] for s in stuck if s[0] not in done])
