# -*- coding: utf-8 -*-
"""order_xp_1119.py — 订单经验值(XP)聚合层: 每单必沉淀学习经验, 为进化升级提供参考(李令11-19)
零侵入: 从 order_lifecycle.jsonl place/close 行配对计算, 不新增写入点.
XP规则: 基础10; 盈利侧出场(TP/锁盈)=+20(会赢); 亏损侧出场=+5"学到"(李令制度: 亏损=学习≠斩除, 必附原因+修正方向), -10罚; 未平仓=0.
格级聚合(sym×params_ver): n/胜率/净利/累计XP → 状态机:
  n>=30 且 净利>=0 且 胜率>=55% = "⑥线30样本满, 建议翻闸" → 自动rd_queue工单(参数官裁)
  n>=10 且 净利<0 = "降级建议(换宽档/REJECT审)" → rd_queue
  其余 = "WATCH攒样 n/30"
--daily 模式(20:15哨): 当日XP+格状态+建议 → stdout报回微信; 常规=静默.
"""
import json, os, sys, datetime as dt

ROOT = "E:/GoldstrategyEngine"
BASE = os.path.join(ROOT, "data")
XP_SNAP = os.path.join(BASE, "order_xp.json")
XP_DAILY = os.path.join(BASE, "order_xp_daily.jsonl")
RDQ = os.path.join(BASE, "rd_queue.json")


def normalize_cell(sym, pv):
    """格子键规范化: 从params_ver抠 SL/TP 倍数 → 抠不出查格表该品种官方倍数 → 仍无=原值。防同逻辑格因标签差异被切碎"""
    import re
    pv = str(pv)
    m = re.search(r"(?:SL|sl|损)[\s=:]?([\d.]+)\D*(?:TP|tp|盈)[\s=:]?([\d.]+)", pv)
    if not m:
        m = re.search(r"SL([\d.]+).{0,12}(?:TP|盈)([\d.]+)", pv)
    if m:
        return f"{sym}@{m.group(1)}/{m.group(2)}"
    try:
        cells = json.load(open(os.path.join(BASE, "auto_soul_params.json"), encoding="utf-8")).get("cells", {})
        c = cells.get(sym)
        if c:
            return f"{sym}@{c['sl_mult']}/{c['tp_mult']}"
    except Exception:
        pass
    return f"{sym}@{pv}"


def pair_orders():
    opens, closes = {}, {}
    p = os.path.join(BASE, "order_lifecycle.jsonl")
    if not os.path.exists(p):
        return [], {}
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        tk = str(r.get("ticket"))
        if r.get("ev") == "place" and tk not in opens:
            opens[tk] = r
        elif r.get("ev") == "close" and tk not in closes:
            closes[tk] = r
    orders = []
    for tk, o in opens.items():
        c = closes.get(tk)
        row = {"ticket": tk, "sym": o.get("sym"), "side": o.get("side"), "cell": normalize_cell(o.get("sym"), o.get("params_ver", "default")),
               "open_ts": o.get("ts"), "close_ts": c.get("ts") if c else None,
               "pnl": c.get("pnl") if c else None, "cause": c.get("cause") if c else None, "open": c is None}
        if c:
            if row["pnl"] is None:
                row["xp"] = 0
                row["learn"] = "close记录缺失, 不计XP"
            else:
                profit_side = row["pnl"] > 0
                xp = 10 + (20 if profit_side else -10 + 5)  # 亏损: -10罚+5学到
                row["xp"] = xp
                row["learn"] = ("会赢:" + str(row["cause"])) if profit_side else ("学到:止损位结构失效, 修正方向=该格换宽档或换格审(验尸哨02:30出因果)")
        else:
            row["xp"] = 0
            row["learn"] = "在仓未结"
        orders.append(row)
    return orders


def cell_stats(orders):
    st = {}
    for o in orders:
        if o.get("open") or o.get("pnl") is None:
            continue  # 在仓 或 close记录缺失(不计XP) 不入格统计
        k = o["cell"]
        e = st.setdefault(k, {"n": 0, "wins": 0, "pnl": 0.0, "xp": 0})
        e["n"] += 1
        e["pnl"] = round(e["pnl"] + (o["pnl"] or 0), 4)
        e["xp"] += o.get("xp", 0)
        if (o["pnl"] or 0) > 0:
            e["wins"] += 1
    for k, e in st.items():
        wr = e["wins"] / e["n"] if e["n"] else 0
        if e["n"] >= 30 and e["pnl"] >= 0 and wr >= 0.55:
            e["state"] = "⑥线30样本满, 建议翻闸(参数官裁)"
        elif e["n"] >= 10 and e["pnl"] < 0:
            e["state"] = "降级建议: 该格30d负, 换宽档/REJECT审(参数官)"
        else:
            e["state"] = f"WATCH攒样 {e['n']}/30"
        e["wr"] = round(wr, 3)
    return st


def file_rdq_tickets(st):
    """rd_queue.json=平铺dict(key=工单ID), 兼容写错过的tickets列表(有则删)"""
    try:
        q = json.load(open(RDQ, encoding="utf-8"))
    except Exception:
        q = {}
    if isinstance(q, dict) and "tickets" in q and isinstance(q["tickets"], list):
        q.pop("tickets")
        q_dirty = True
    else:
        q_dirty = False
    added = 0
    nows = dt.datetime.now().isoformat()
    for k, e in st.items():
        sym, cell = (k.split("@", 1) + [""])[:2]
        if "⑥线" in e["state"]:
            tid = f"xp6_{sym}_{cell}"
            if tid not in q:
                q[tid] = {"id": tid, "sev": "P1", "status": "OPEN", "by": "XP聚合层(主bot)", "ts": nows,
                          "task": f"{sym} {cell}: 前向OOS {e['n']}样本 净利{e['pnl']} 胜率{e['wr']} = ⑥线满, 建议翻闸",
                          "owner_matrix": "参数官", "note": "李令: 每单经验值为进化参考; 自动立单"}
                added += 1
        elif "降级" in e["state"]:
            tid = f"xdn_{sym}_{cell}"
            if tid not in q:
                q[tid] = {"id": tid, "sev": "P2", "status": "OPEN", "by": "XP聚合层(主bot)", "ts": nows,
                          "task": f"{sym} {cell}: {e['n']}样本 净利{e['pnl']}<0, 降级/换宽档审",
                          "owner_matrix": "参数官", "note": "XP聚合层自动立单"}
                added += 1
    if added or q_dirty:
        q["ts"] = int(dt.datetime.now().timestamp())
        json.dump(q, open(RDQ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return added


def sync_close_rows():
    """close行自愈: 已开但缺close行且已不在账的单 → 从服务器成交(deals, 服务器时间=本地+2h)合成close行补录
    (治: 早期出场漏留痕=XP/验尸数据不完整; 11-19 首两笔EUR即此case)"""
    import MetaTrader5 as mt5
    try:
        mt5.initialize()
    except Exception:
        return 0
    now = dt.datetime.now()
    cur = {str(p.ticket) for p in (mt5.positions_get() or ())}
    missing, have_close, allopens = [], set(), {}
    p = os.path.join(BASE, "order_lifecycle.jsonl")
    for line in open(p, encoding="utf-8") if os.path.exists(p) else []:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("ev") == "place":
            allopens[str(r.get("ticket"))] = r
        elif r.get("ev") == "close":
            have_close.add(str(r.get("ticket")))
    missing = [tk for tk, o in allopens.items() if tk not in have_close and tk not in cur]
    n = 0
    if missing:
        deals = mt5.history_deals_get(now - dt.timedelta(hours=24), now + dt.timedelta(hours=2, minutes=5)) or ()
        outs = {}
        for d in deals:
            if d.entry == mt5.DEAL_ENTRY_OUT:
                outs.setdefault(str(d.position_id), []).append(d)
        with open(p, "a", encoding="utf-8") as f:
            for tk in missing:
                ds = outs.get(tk, [])
                if ds:
                    pnl = round(sum(d.profit + d.commission for d in ds), 3)
                    price = ds[-1].price
                    cause = "R10自动补录: close行缺失, 从服务器成交合成"
                else:
                    pnl, price, cause = None, None, "成交窗内无close记录(超24h窗口或他magic), 不计XP"
                f.write(json.dumps({"ev": "close", "ts": dt.datetime.now().isoformat(), "sym": allopens[tk].get("sym"),
                    "ticket": tk, "close_price": price, "pnl": pnl, "cause": cause, "magic": 20261104,
                    "actor": "XP聚合层close行自愈(数据完整性)"}, ensure_ascii=False) + "\n")
                n += 1
    mt5.shutdown()
    return n


def main():
    daily = "--daily" in sys.argv
    if daily:
        n_sync = sync_close_rows()  # close行自愈先行(数据完整才谈XP)
    orders = pair_orders()
    st = cell_stats(orders)
    today = dt.datetime.now().strftime("%Y-%m-%d")
    todays = [o for o in orders if (o.get("open_ts") or "")[:10] == today]  # 当日口径=当日开的单(不含补录close的旧单)
    snap = {"ts": dt.datetime.now().isoformat(), "cells": st,
            "today": todays, "total_orders": len(orders),
            "total_pnl": round(sum((o["pnl"] or 0) for o in orders if not o.get("open")), 4),
            "total_xp": sum(o.get("xp", 0) for o in orders)}
    json.dump(snap, open(XP_SNAP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if daily:
        with open(XP_DAILY, "a", encoding="utf-8") as f:
            f.write(json.dumps({"day": today, "ts": snap["ts"], "cells": st,
                                "n_orders_today": len(todays), "xp_today": sum(o.get("xp", 0) for o in todays),
                                "pnl_today": round(sum((o["pnl"] or 0) for o in todays if o.get("close_ts")), 4)}, ensure_ascii=False) + "\n")
        file_rdq_tickets(st)
        lines = [f"[每日XP] {today}: 当日单{len(todays)}笔 当日XP{sum(o.get('xp', 0) for o in todays)} 累计单{snap['total_orders']} 累计净{snap['total_pnl']} 累计XP{snap['total_xp']}"
                 + (f" [close自愈补录{n_sync}行]" if n_sync else "")]
        for k, e in sorted(st.items(), key=lambda kv: -kv[1]["xp"]):
            lines.append(f"  {k}: {e['n']}笔 胜率{e['wr']:.0%} 净利{e['pnl']} XP{e['xp']} = {e['state']}")
        print("\n".join(lines))
        return
    # 常规(哨跑): 仅当有⑥线/降级新工单时出声
    try:
        q = json.load(open(RDQ, encoding="utf-8"))
    except Exception:
        q = {}
    added = file_rdq_tickets(st)
    if added:
        nonwatch = [k for k, e in st.items() if e["state"].startswith(("⑥线", "降级"))]
        print(f"[XP] 新增{added}张格级进化工单(参数官rd_queue待裁): {nonwatch}")


if __name__ == "__main__":
    main()
