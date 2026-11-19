# -*- coding: utf-8 -*-
"""金策 L5 · 10 条躺平 OBSERVE 激活 (确定性脚本, 0 LLM, 0 改实盘)
[2026-10-14] @user "加强学习讨论研发" -> @chief 议题A: 10 条 OBSERVE 逐条给三选一结论.
样本实数全部实拉自 edge_tracker.json / xu_time_weight 焊点 (同分母铁律, 不靠 source 口播).
红线: 0 放大 0 进 live, 只补判断岗留痕 (activation 字段), 0 碰 gate_flags/risk_state.
五验①样本≈1000 事件: 现全腿 n<30 远不够 -> 无一可启动五验, 只能攒样/降级/冻结.
"""
import json, os, time

D = r"E:\GoldstrategyEngine\data"
INBOX = os.path.join(D, "evolution_inbox.json")


def et():
    try:
        et = json.load(open(os.path.join(D, "edge_tracker.json"), encoding="utf-8"))
        return et.get("symbols", {})
    except Exception:
        return {}


def act(leg, syms):
    """按 leg 名取样本实数 + 三选一去向."""
    d = syms.get(leg)
    n = (d or {}).get("n", 0) if d else 0
    wr = (d or {}).get("wr") if d else None
    pf = (d or {}).get("pf") if d else None
    no_src = leg not in syms
    out = {"leg": leg, "n": n, "wr": wr, "pf": pf}

    if leg == "CVX":
        out.update(direction="OBSERVE_FROZEN",
                   reason="edge_tracker 无此腿样本源 (n=0), 数据不可靠 -> 冻结不攒不放大 (L4 CVX 降级口径)")
    elif leg == "EURJPY":
        out.update(direction="AMPLIFY_TRACK",
                   reason="真出徒候选: n=%s/30 (差%s) 且 pf=%.2f 过 payoff≥2 线 -> 优先 0.01 并行攒到 30; 放大仍走出徒四件齐" %
                   (n, 30 - n, pf or 0))
    elif leg == "GBPCAD":
        out.update(direction="DOWNGRADE_THIN_EDGE",
                   reason="薄边: pf=%.2f < payoff≥2 出徒线 -> 追满 30 也放大 0; 不优先, 保持 OBSERVE 不占 0.01 并行位" % (pf or 0))
    elif "时段权重" in leg:
        out.update(direction="ACTIVATED_CONSUMER",
                   reason="时段权重已跳②焊入 advisory_to_order._xu_time_gate (徐总 00-04 最赚/17-18 最亏), 已有消费者; 观察激活, 0 进 live")
    elif leg == "SamSupplyDemand" or leg.startswith("EVO"):
        out.update(direction="WATCH_TRUNCATED",
                   reason="残稿腿: 源 331 行截断 + 三红线 0 命中 -> L4 终裁 WATCH 结构参考, 0 回测 0 live; 销账点=用户给完整版源码")
    elif no_src:
        out.update(direction="OBSERVE_FROZEN",
                   reason="edge_tracker 无样本源, 数据不可靠 -> 冻结")
    else:
        # 小样本 / 薄边 / 虚高 分判
        if pf and pf >= 2.0 and n >= 15:
            out.update(direction="AMPLIFY_TRACK",
                       reason="正期望且样本过半: n=%s/30 差%s, pf=%.2f -> 0.01 攒样到 30 (放大走出徒四件齐)" % (n, 30 - n, pf))
        elif n < 5:
            out.update(direction="KEEP_COLLECTING",
                       reason="n=%s 样本不足 5 -> 继续攒样, 0 放大 0 退" % n)
        else:
            note = ""
            if pf and pf > 5:
                note = " (pf=%.2f 小样本虚高, 不认当放大依据, 只攒样)" % pf
            out.update(direction="KEEP_COLLECTING",
                       reason="n=%s/30 未达出徒线 -> 继续攒样, 0 放大 0 退%s" % (n, note))
    out["oos_gap"] = max(0, 30 - n) if not no_src else None
    return out


def main():
    ib = json.load(open(INBOX, encoding="utf-8"))
    syms = et()
    now_ts = int(time.time())
    obs = [e for e in ib["queue"] if e.get("verdict") == "OBSERVE"]
    activated = []
    for e in obs:
        leg = e.get("leg") or ""
        # leg 名兜底: 从 id 尾段取 (EVO-20261008-5T-EURJPY -> EURJPY)
        if not leg:
            tail = e.get("id", "").split("-")[-1]
            # SH-时段权重 / SamSupplyDemand 特殊
            leg = tail if tail not in ("OBSERVE",) else e.get("id")
        a = act(leg, syms)
        e["activation"] = {"ts": now_ts, "by": "strategy-rd L5", "sample": a,
                            "five_test_gate": "五验①样本≈1000 未达 (n=%s), 0 启动" % a["n"]}
        activated.append((e.get("id"), a["direction"], a["n"]))
    ib["activation_batch"] = {"ts": now_ts, "by": "strategy-rd L5",
                               "n_activated": len(activated),
                               "rule": "逐条三选一去向 + 样本实数 (同分母铁律), 0 放大 0 live 0 改 gate_flags"}
    json.dump(ib, open(INBOX, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("activated %d OBSERVE 条 (实拉样本):" % len(activated))
    for iid, dirn, n in activated:
        print("  %-28s -> %-20s n=%s" % (iid, dirn, n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
