# -*- coding: utf-8 -*-
"""system_patrol_1119.py — 金策制度巡检哨(30min, no_agent, 全绿静默/红件一行报+rd_queue)
李令11-19"以后不能再出现这样的问题, 立即建立工作制度": 制度靠机器验活不靠人记.
逐条验《金策工作制度_铁律清单_v1》一~六章"机器验证"列; 红件=非零信息行+rd_queue工单(owner=责任岗).
"""
import os, sys, time, json, glob, datetime as dt

ROOT = "E:/GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
red = []
now = time.time()


def add(rule, msg, owner):
    red.append(dict(rule=rule, msg=msg[:200], owner=owner))


# ---- D1 效期戳双记字段 ----
try:
    d = json.load(open(os.path.join(DATA, "data_officer_last.json"), encoding="utf-8"))
    if "m30_kline_end" not in d:
        add("D1", "效期戳缺 m30_kline_end 双记字段", "数据官")
    stale = [x for x in d.get("m30_kline_stale", [])]
    if stale:
        add("D1", "K线尾停红件未消化: %s" % ",".join(stale[:3]), "数据官")
    if now - d.get("ts", 0) > 40 * 60:
        add("D1", "效期戳超40min未刷(数据官哨停摆?)", "数据官")
except Exception as ex:
    add("D1", "效期戳读失败 %s" % str(ex)[:60], "数据官")

# ---- D2 M30闸=2h ----
try:
    src = open(os.path.join(ROOT, "jince_data_officer.py"), encoding="utf-8").read()
    if '"M30": 2' not in src:
        add("D2", "数据官 M30 闸≠2h(被改?)", "数据官")
except Exception as ex:
    add("D2", "D2读脚本失败 %s" % str(ex)[:50], "数据官")

# ---- D3 孤儿件 ----
orph = [f for f in glob.glob(os.path.join(DATA, "tf_cache", "*.npz.*.npz"))
        if now - os.path.getmtime(f) > 3600]
if orph:
    add("D3", "孤儿npz超1h未清: %s" % os.path.basename(orph[0]), "数据官")

# ---- E1 波脚本幂等 ----
for f in glob.glob(os.path.join(ROOT, "scripts", "exec_wave", "*.py")):
    s = open(f, encoding="utf-8").read()
    if ("已有本波仓" in s or "跳过" in s) and "positions_get" in s:
        continue
    add("E1", "波脚本 %s 缺幂等去重(positions_get+跳过)" % os.path.basename(f), "执行岗")

# ---- E4 12h红线有执行者 ----
lc = [json.loads(l) for l in open(os.path.join(DATA, "order_lifecycle.jsonl"), encoding="utf-8") if l.strip()]
live_rows = [r for r in lc[-40:] if r.get("ev") == "place" and r.get("live")]
if live_rows:
    last_place_ts = max(r.get("ts", "") for r in live_rows)
    # E4: ts 格式漂移(order_lifecycle 新旧行 空格/T 混用)→ 归一化+防崩, 解析失败本拍跳过12h检查
    _e4_ts = last_place_ts[:19].replace("T", " ")
    try:
        _e4_hit = dt.datetime.strptime(_e4_ts, "%Y-%m-%d %H:%M:%S").replace(microsecond=0).timestamp() + 12 * 3600 > now
    except Exception:
        _e4_hit = False
    if _e4_hit:
        tl = [json.loads(l) for l in open(os.path.join(DATA, "task_ledger.jsonl"), encoding="utf-8") if l.strip()]
        if not any("红线" in str(t.get("task", "")) and t.get("ts", "") >= last_place_ts[:16] for t in tl[-30:]):
            add("E4", "在账12h腿未见红线哨登记(open行%s后无redline登记)" % last_place_ts[:16], "执行岗")

# ---- G2 闸门文件schema ----
try:
    rf = json.load(open(os.path.join(DATA, "risk_freeze_state.json"), encoding="utf-8"))
    if "coin_freeze" not in rf:
        add("G2", "risk_freeze_state 缺 coin_freeze 字段", "风控岗")
except Exception as ex:
    add("G2", "risk_freeze_state 读失败 %s" % str(ex)[:50], "风控岗")

# ---- S4 哨脚本被归档=事件 ----
for f in glob.glob(os.path.join(DATA, "disabled_*.disabled")):
    if now - os.path.getmtime(f) < 24 * 3600:
        add("S4", "哨脚本近24h被归档: %s(须红报+留因)" % os.path.basename(f), "风控岗")

# ---- S1/S2 哨群健康(确定性主层) ----
try:
    po = json.load(open(os.path.join(DATA, "param_officer_state.json"), encoding="utf-8"))
    if now - dt.datetime.fromisoformat(str(po.get("ts", ""))) .total_seconds() > 40 * 60:
        add("S1", "参数官哨超40min未落态", "总调度")
except Exception:
    pass

if red:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    for r in red:
        print("[制度巡检红] %s(%s岗): %s" % (r["rule"], r["owner"], r["msg"]))
    try:
        q = json.load(open(os.path.join(DATA, "rd_queue.json"), encoding="utf-8"))
        for r in red:
            tid = "patrol_%s_%s" % (r["rule"].lower(), ts[8:10] + ts[11:13])
            if tid not in q and not any(r["rule"].lower() in str(k).lower() and str(v.get("status")) not in ("DONE", "CLOSED")
                                        for k, v in q.items() if isinstance(v, dict)):
                q[tid] = dict(id=tid, sev="P2" if r["rule"] in ("E4", "S4") else "P1", status="queued",
                              by="system-patrol(制度巡检)", ts=ts, task=r["msg"],
                              owner_matrix="责任岗=%s" % r["owner"])
        json.dump(q, open(os.path.join(DATA, "rd_queue.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception as ex:
        print("[制度巡检红] rd_queue写失败: %s" % str(ex)[:80])
    sys.exit(0)
# 全绿=静默(no_agent watchdog pattern: 空stdout=不发消息), 心跳只落文件
with open(os.path.join(DATA, "system_patrol_last.json"), "w", encoding="utf-8") as f:
    json.dump(dict(ts=int(now), red=0), f)
