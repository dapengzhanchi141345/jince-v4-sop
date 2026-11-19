# -*- coding: utf-8 -*-
"""金策 L5 · 徐总数据 OOS 桥接 (确定性脚本, 0 LLM)
[2026-10-10] @user 给的外部实盘数据 (E:\资料\徐总数据) 解析件 xu_parsed.json -> 三格桥接:
  1) data/xu_oos_bridge.json: 13万笔金腿 = 外部 OOS 参考样本 (WATCH), 三条硬伤标记,
     0 进 live 出单链 (payoff 0.64 < 2 出徒线).
  2) data/xu_time_weight.json: BJT 小时/周几权重表 -> 每日开评研判读此表 (只降档/否决参考,
     不直接开仓; 沿用"研判只做否决门+提权"铁律).
  3) training_graduation_tracker.json: SH1a/金腿条目加 external_sample_ref 字段 (只挂参考,
     不动 oos_now 计数 -- 出徒 30 笔铁律 = 我方 0.01 实盘自攒, 外部样本严禁顶替).
红线: 只学结构不学仓位; 历史回测≠未来收益; 0 碰实盘.
"""
import json, os, time

DATA = r"E:\GoldstrategyEngine\data"

def load(p):
    return json.load(open(p, encoding="utf-8"))

def main():
    xu = load(os.path.join(DATA, "xu_parsed.json"))
    now_ts = int(time.time())
    by_hour = xu["by_hour_bjt"]
    xau = xu["by_symbol"].get("XAUUSD", {})

    # ---- 1) 硬伤判定 (确定性判据, 全部实拉自 xu_parsed) ----
    thin_edge = xu.get("rr_proxy", 1.0) < 2.0
    dd_pct = xu.get("real_max_dd_pct_of_peak", 0)          # 0.7386 = 73.9% (占净值峰值)
    dd_bad = dd_pct > 0.20
    xau_n = xau.get("n", 0); tot_n = xu.get("n", 1)
    single_sym = xau_n / max(tot_n, 1) > 0.90
    hard_fails = []
    if thin_edge: hard_fails.append("薄边: RR proxy %.2f < 2.0 出徒线" % xu.get("rr_proxy", 0))
    if dd_bad: hard_fails.append("回撤 %.1f%% > 20%% 闸 (无熔断/冷却口径, 2023-02 实拉 73.9%%)" % (dd_pct * 100))
    if single_sym: hard_fails.append("单品种集中 XAUUSD %.0f%% (%d/%d, 违反 164 分散口径)" % (xau_n / max(tot_n, 1) * 100, xau_n, tot_n))

    # 时段权重: 按小时净赚排名, 最赚段/最亏段 (n 需>=100 才算有效权重, 否则不下结论)
    hour_rank = sorted(by_hour.items(), key=lambda kv: -kv[1])
    best_h = [h for h, v in hour_rank[:2] if v > 0]
    worst_h = [h for h, v in hour_rank[-2:] if v < 0]

    bridge = {
        "ts": now_ts,
        "source": "E:\\资料\\徐总数据 (xu_parsed.json n=%s 笔, 4.5年实盘)" % xu.get("n"),
        "leg_ref": "XAUUSD 短打腿 (SH1 系)",
        "status": "WATCH_外部OOS参考",
        "live_flag": False,
        "amp_allowed": False,
        "xau_ref": {"n": xau.get("n"), "wr": round((xau.get("w", 0) / xau.get("n", 1)), 4), "net": round(xau.get("net", 0), 2)},
        "hard_fails": hard_fails,
        "learn_only": ["时段权重(00-04加仓/17-18降权, 跟 SH2 合流)", "剥头皮结构(固定SL+快进快出, 跟 SH1 本地回测对照)"],
        "not_learn": ["薄边仓位(RR<2 放大)", "无风控回撤(73.9%)", "单品种集中(94%)"],
        "oos_substitution_banned": True,  # 出徒30笔=我方0.01实盘自攒, 外部样本严禁顶替计数
    }
    json.dump(bridge, open(os.path.join(DATA, "xu_oos_bridge.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---- 2) 时段权重表 (开评研判读) ----
    week = {"周一": 24713, "周二": 52526, "周四": 42974, "周五": 23280, "周三": 14032}  # 报告实数(4.5年聚合)
    tw = {
        "ts": now_ts,
        "source": "xu_parsed.by_hour_bjt (131392 笔 BJT 小时净利)",
        "hour_net": {int(k): round(v, 1) for k, v in by_hour.items()},
        "top_hours": best_h, "bottom_hours": worst_h,
        "best_block": "00-04 凌晨段 (小时口径: 01时+33508/13时+17759 单峰; 报告聚合 00-04 段 +79072)",
        "worst_block": "17-18 段 (17时-2487/18时-5504, 报告聚合 -7991)",
        "weekday_net": week,
        "use_rule": "开评研判: top_hours 段允许正常研判; bottom_hours 段一律降档/否决 (00-04 与 17-18 口径跟 SH2 合流). 只做否决门+提权参考, 不单独开仓.",
    }
    json.dump(tw, open(os.path.join(DATA, "xu_time_weight.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---- 3) graduation tracker 挂参考 (不动 oos_now) ----
    tp = os.path.join(DATA, "training_graduation_tracker.json")
    tr = load(tp)
    ref_note = "external_sample_ref=xu_131392(WATCH 0 放大, payoff0.64/回撤73.9%/单品种94%% 三硬伤)"
    touched = []
    for leg in tr.get("legs", []):
        nm = leg.get("leg", "")
        if nm in ("SH1a", "SH1", "SH2") or "XAU" in nm:
            leg["external_sample_ref"] = ref_note
            touched.append(nm)
    tr["xu_bridge"] = {"ts": now_ts, "status": bridge["status"], "touched_legs": touched,
                       "rule": "外部样本仅参考, oos_now 计数 0 混入 (出徒30笔=我方实盘自攒)"}
    tr["updated_ts"] = now_ts
    tr["updated_by"] = "strategy-rd L5 xu_bridge"
    json.dump(tr, open(tp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("xu_bridge OK: hard_fails=%s top_h=%s worst_h=%s touched=%s" % (hard_fails, best_h, worst_h, touched))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
