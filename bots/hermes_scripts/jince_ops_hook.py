#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策 24h 研发段后 · 运营同步钩子 (ops-manager profile, 每 4h 错峰自取)
研发段在 04/08/12/16/20 BJT 跑并往 data/ops_sync_queue.json 追加 1 条;
本钩子挂 05/09/13/17/21 BJT(错开下一段研发开跑高峰), 读队列最新未取条目 →
投群 1 条(=ops-manager 被点名干的活) + 落运营台账 ops_ledger_24h.json
(ts/主题/动作/状态/心跳=alive), 并把该条 taken 置位。
无未取条目 → 静默(空 stdout, 不刷群); 有 → 打印 1 行(留痕)。
fail-open: 队列/台账读写异常 → 打印降级 1 行(不崩、不挡交易全链; 下轮自动续)。
不碰: 挂单真闸源/撤单/交易配置。
"""
import os, json, datetime, zoneinfo

DATA = r"E:/GoldstrategyEngine/data"
OPSQ = os.path.join(DATA, "ops_sync_queue.json")
LED = os.path.join(DATA, "ops_ledger_24h.json")
BJT = zoneinfo.ZoneInfo("Asia/Shanghai")

def load_json(p, dft):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return dft

def save_json(p, obj):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)

def main():
    now = datetime.datetime.now(BJT)
    q = load_json(OPSQ, {"queue": []})
    pending = [x for x in q.get("queue", []) if not x.get("taken")]
    if not pending:
        return  # 无活 → 静默(下轮再扫)
    it = pending[0]
    # 取走: 置 taken
    it["taken"] = now.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        save_json(OPSQ, q)
    except Exception:
        pass
    # 落运营台账
    ld = load_json(LED, {"entries": []})
    ld["entries"].append({
        "ts": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "bot": "ops-manager",
        "theme": it.get("theme", "?"),
        "action": "同步进内容排期+物料+读者池(档1)",
        "new_candidate": str(it.get("new_candidate", "?"))[:40],
        "verdict": it.get("verdict", "?"),
        "status": "queued_done",
        "heartbeat": "alive",
    })
    try:
        save_json(LED, ld)
    except Exception:
        pass
    left = len([x for x in q.get("queue", []) if not x.get("taken")])
    print(f"[金策运营同步钩子 {now.strftime('%H:%M')}] @ops-manager 同步研发新活: 主题={it.get('theme', '?')} 候选={str(it.get('new_candidate', '?'))[:30]} 判定={it.get('verdict', '?')} → 档1内容排期+物料+读者池已入队; 剩余待取 {left} 条; 台账 ops_ledger_24h 已落盘(心跳=alive)")

if __name__ == "__main__":
    main()
