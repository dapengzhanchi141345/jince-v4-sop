# -*- coding: utf-8 -*-
r"""金策·Monte Carlo + 日 VaR 风控量化哨 (确定性 0LLM, 每日 07:45 cron)
源: data/jince_family_pnl_ledger.jsonl (交易级行: date/family/symbol/profit[R]).
口径(全网顶配标准, 全部 R 分母):
  日 VaR95 = 1.65 * std(按日聚合净R) —— >2.0R/日 = 红
  Monte Carlo 1000: 交易盈亏序 bootstrap 重采样 -> 权益路径(R), MaxDD 分布, 报 95 分位
  样本 <30 笔 = 红色"样本不足"(数据有效性闸, 不静默)
全绿=stdout 空(不投递); 异常=一行红报。结果落 data/mc_var_last.json。
"""
import json
import os
import re
import statistics

DATA = r"E:\GoldstrategyEngine\data"
LEDGER = os.path.join(DATA, "jince_family_pnl_ledger.jsonl")
OUT = os.path.join(DATA, "mc_var_last.json")
VVAR_Z = 1.65
VVAR_RED_R = 2.0      # 日 VaR95 > 2.0R = 红
MC_N = 1000
MC_SEED = 20261114
MIN_TRADES = 30


def trades():
    out = []
    for line in open(LEDGER, encoding="utf-8", errors="replace"):
        m = re.search(r"\{.*\}", line)
        if not m:
            continue
        try:
            r = json.loads(m.group(0))
        except Exception:
            continue
        if r.get("profit") is None or not r.get("date"):
            continue
        try:
            out.append((r["date"], float(r["profit"])))
        except Exception:
            continue
    return out


def main():
    import datetime
    import random
    ts_list = trades()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if len(ts_list) < MIN_TRADES:
        print("⚠️ [MC/VaR] 交易级样本仅 %d 笔(<%d), 不可算=数据不足红色(交易台账是否在写?), 不静默" % (len(ts_list), MIN_TRADES))
        json.dump({"ts": now, "n": len(ts_list), "ok": False, "reason": "样本不足"}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return 0
    pnls = [p for _, p in ts_list]
    daily = {}
    for d, p in ts_list:
        daily[d] = daily.get(d, 0.0) + p
    dvals = list(daily.values())
    mu = statistics.fmean(dvals)
    sd = statistics.pstdev(dvals) if len(dvals) > 1 else 0.0
    var95_R = VVAR_Z * sd
    random.seed(MC_SEED)
    maxdds = []
    for _ in range(MC_N):
        eq, peak, mdd = 0.0, 0.0, 0.0
        for _ in range(30):
            eq += random.choice(pnls)
            peak = max(peak, eq)
            mdd = max(mdd, peak - eq)
        maxdds.append(mdd)
    maxdds.sort()
    mdd95 = maxdds[int(0.95 * (MC_N - 1))]
    res = {"ts": now, "n_trades": len(ts_list), "n_days": len(dvals),
           "daily_mean_R": round(mu, 3), "daily_std_R": round(sd, 3),
           "var95_daily_R": round(var95_R, 3), "mdd95_30trades_R": round(mdd95, 3),
           "mc_runs": MC_N, "date_range": [min(daily), max(daily)], "ok": True}
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    red = []
    if var95_R > VVAR_RED_R:
        red.append("日VaR95=%.2fR>%sR红线" % (var95_R, VVAR_RED_R))
    if mdd95 > 8.0:
        red.append("30笔MonteCarlo MaxDD 95分位=%.2fR>8R容忍线" % mdd95)
    if red:
        print("⚠️ [MC/VaR] %s | %s 至 %s 共%d笔: 日VaR95=%.2fR MaxDD95=%.2fR" % (
            "; ".join(red), res["date_range"][0], res["date_range"][1], len(ts_list), var95_R, mdd95))
    return 0


if __name__ == "__main__":
    main()
