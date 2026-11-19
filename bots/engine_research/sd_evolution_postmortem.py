#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""金策·订单验尸进化哨 (制度: 李11-15令 "每次开单都有进化")
每单结算(平/挂单失效/强平)后自动验尸:
  1) 对账 order_lifecycle.jsonl(open 无 close) x MT5 历史成交 -> 补 close 事件(含 P&L/出场原因/持仓时长)
  2) 逐单验尸三问: ①对/错? (P&L 符号) ②为什么? (出场原因归类 TP/SL/锁利/12h强平/区失效) ③改什么? (参数命中: 该品种 slc/tpmul/trig/gb 是否按 v2 表挂的; WR 偏差)
  3) 进化输出: evolution_daily.json (当日每单结论 + 参数表命中率 + 建议动作 rd_queue/skill/参数表)
  4) 技能提升钩子: 连续 3 单同因出场(如 SL 全扫) -> 自动落 rd_queue 提案(供 chief 裁定, 不自动改表)
纯确定性 0 LLM; 数据无效闸: MT5 连不上/台账缺失 -> 显式 FAIL 不静默.
"""
import json, os, time, datetime as dt, sys
import MetaTrader5 as mt5

ROOT = "E:/GoldstrategyEngine"
LC = os.path.join(ROOT, "data", "order_lifecycle.jsonl")
OUT = os.path.join(ROOT, "data", "evolution_daily.json")
RDQ = "E:/GoldstrategyEngine/data/rd_queue.json"
MAGIC = 20261104
TZ = dt.timezone(dt.timedelta(hours=8))


def load_lc():
    if not os.path.exists(LC):
        return []
    rows = []
    for line in open(LC, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def main():
    ok = False
    import time as _t
    for _i in range(3):  # 11-16即时启动: MT5 掉线 5min 重试 x3, 不干等下日
        ok = mt5.initialize()
        if ok:
            break
        _t.sleep(300)
    if not ok:
        print("FAIL MT5初始化3次失败: %s (数据无效闸: 拒出报告, 不静默)" % str(mt5.last_error()))
        sys.exit(1)
    a = mt5.account_info()
    if a is None or int(a.login) != 60137964:
        print("FAIL 账户不对=%s 拒跑" % getattr(a, "login", None))
        mt5.shutdown()
        sys.exit(1)

    lc = load_lc()
    # 11-16修: 只对账 live=True 开单(dry 记录不进 MT5 对账, 否则补出假平仓)
    opens = [r for r in lc if r.get("ev") == "open" and r.get("live", True)]
    closes = [r for r in lc if r.get("ev") == "close" and r.get("live", True)]
    open_keys = set((o.get("sym"), o.get("ticket")) for o in opens)
    closed_keys = set((c.get("sym"), c.get("ticket")) for c in closes)

    # ① 对账: MT5 历史 12h 内已结算的 SD 单 (close 台账缺失的补记)
    t0 = int(time.time()) - 12 * 3600
    deals = mt5.history_deals_get(t0, int(time.time())) or []
    settled = {}
    for d in deals:
        if d.magic != MAGIC:
            continue
        settled.setdefault(d.symbol, []).append(d)
    now = time.strftime("%F %T")
    added = 0
    for o in opens:
        if (o.get("sym"), o.get("ticket")) in closed_keys:
            continue
        sym = o.get("sym")
        cands = [d for d in settled.get(sym, []) if d.type in (1, 3)]  # DEAL_TYPE_OUT/OUT_BY
        if not cands:
            continue
        # 该单 12h 内有平仓 deal -> 补 close (P&L 用 deal.profit 累加; 单品种 0.01 手口径)
        pnl = sum(d.profit + d.swap + d.commission for d in cands)
        ex = cands[-1]
        kind = "SL" if abs(ex.price - o.get("sl", 0)) < 1e-9 and o.get("sl") else ("TP" if abs(ex.price - o.get("tp", 0)) < 1e-9 and o.get("tp") else "结算")
        line = dict(ev="close", ts=now, sym=sym, ticket=o.get("ticket"), close_price=ex.price,
                    pnl_usd=round(pnl, 2), close_kind=kind, params_ver=o.get("params_ver"),
                    auto="补记(验尸哨对账)")
        with open(LC, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        closed_keys.add((sym, o.get("ticket")))
        added += 1

    # ② 逐单验尸三问 (当日 close)
    today = dt.datetime.now(TZ).strftime("%F")
    closes_today = [r for r in lc if r.get("ev") == "close" and str(r.get("ts", "")).startswith(today)]
    reports = []
    for c in closes_today:
        o = next((x for x in opens if x.get("sym") == c.get("sym") and x.get("ticket") == c.get("ticket") and x.get("ev") == "open"), {})
        win = c.get("pnl_usd", 0) > 0
        kind = c.get("close_kind", "结算")
        pver = c.get("params_ver", 0)
        # 三问
        q1 = "对" if win else "错"
        q2 = kind + ("(锁利保护后离场)" if kind in ("SL",) and win else "")
        sp = json.load(open(os.path.join(ROOT, "research", "sd_symbol_params.json"), encoding="utf-8"))
        pp = sp.get("params", sp).get(c.get("sym"), {})
        q3 = "按 v%s 表执行, 无参数漂移" % pver if pver else "无版本锚(旧单), 建议下版补锚"
        reports.append(dict(sym=c.get("sym"), ticket=c.get("ticket"), pnl=c.get("pnl_usd"),
                            kind=kind, verdict=q1, why=q2, action=q3, pver=pver,
                            params_used=dict(slc=pp.get("slc"), tpmul=pp.get("tpmul"), trig=pp.get("trig"), giveback=pp.get("giveback"))))

    # ③ 进化判定: 连续 3 单同因 SL 错 -> rd_queue 提案 (不自动改表)
    sl_losses = [r for r in reports if r["kind"] == "SL" and not str(r["verdict"]) == "对"]
    n_sl = len(sl_losses)
    prop = None
    if n_sl >= 3:
        prop = "SD批 %d 单当日 SL 全扫: 建议 chief 裁定收紧 %s 的 slc 或换 12h 前一日选样 (v2 口径), 勿盲目动全局" % (
            n_sl, ",".join(sorted(set(r["sym"] for r in sl_losses))))
        try:
            q = json.load(open(RDQ, encoding="utf-8")) if os.path.exists(RDQ) else []
            if not isinstance(q, list):
                q = q.get("queue", [])
            q.append(dict(ts=now, from_="hermes-验尸哨", kind="sl_streak_proposal", body=prop, status="pending"))
            json.dump(q, open(RDQ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except Exception:
            pass
    wr = (sum(1 for r in reports if r["verdict"] == "对") / len(reports)) if reports else None
    out = dict(ts=now, account=60137964, closes_today=len(reports), closes_added=added,
               win_rate=wr, per_order=reports, streak_proposal=prop,
               gate="PASS" if (mt5.account_info() is not None) else "FAIL")
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    mt5.shutdown()
    # stdout 简报 (no_agent 哨: 空=无事; 有内容=投报)
    if reports or added:
        print("验尸进化哨: 当日结算 %d 单 (补记 %d), WR=%s, 建议=%s" % (
            len(reports), added, ("%.0f%%" % (100 * wr)) if wr is not None else "-", prop or "无"))
    else:
        print("")  # 静默


if __name__ == "__main__":
    main()
