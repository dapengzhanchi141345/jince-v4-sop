# -*- coding: utf-8 -*-
"""
monthly_review.py — 金策宗师团 月度复盘 (2026-09 起, 计划任务 10-25 自动跑)
================================================================
汇总一个月的 LIVE 训练数据 → 生成月度复盘报告(存 内容中心\\交付)。
数据源:
  data/training_log/equity_curve.csv     净值曲线 (每30分钟采样)
  data/training_log/daily_report_*.md    每日绩效
  data/pending_orders_state.json         挂单/持仓状态机 history (成交流水)
  data/auto_cycle.log                    全链运行日志 (故障率统计)
复盘指标: 收益/最大回撤/胜率/盈亏比/单笔R/边际损耗/故障轮次
结论: 是否具备切 $100 实盘条件 (标准: 正期望 + 回撤<5% + 无风控违规)
"""
import os, json, time, datetime, statistics

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
TLOG = os.path.join(DATA, "training_log")
DELIVER = r"E:\workbuddy\内容中心\交付\2026-09_金策宗师团"


def _pct(x):
    return f"{x:.2f}%"


def main():
    os.makedirs(DELIVER, exist_ok=True)
    today = datetime.datetime.now()
    start = today.replace(month=today.month - 1, day=today.day)
    period = f"{start.strftime('%Y-%m')} 至 {today.strftime('%Y-%m-%d')}"

    # 1. 净值曲线
    eq_path = os.path.join(TLOG, "equity_curve.csv")
    rows = []
    if os.path.exists(eq_path):
        for l in open(eq_path, encoding="utf-8").read().splitlines()[1:]:
            parts = l.split(",")
            try:
                rows.append({"ts": parts[0], "equity": float(parts[1]), "n_pos": int(parts[3]),
                             "consec": int(parts[5])})
            except Exception:
                pass
    eqs = [r["equity"] for r in rows]
    # 最大回撤
    peak, mdd = -1e9, 0.0
    for e in eqs:
        peak = max(peak, e)
        mdd = max(mdd, (peak - e) / peak if peak > 0 else 0)
    total_pnl = (eqs[-1] - eqs[0]) if len(eqs) > 1 else 0.0
    total_ret = total_pnl / eqs[0] if eqs and eqs[0] > 0 else 0.0
    # 日收益 (按天聚合)
    daily_eq = {}
    for r in rows:
        day = r["ts"][:10]
        daily_eq[day] = r["equity"]   # 当日最后一次采样
    daily_rets = []
    days = sorted(daily_eq.keys())
    for i in range(1, len(days)):
        prev, cur = daily_eq[days[i - 1]], daily_eq[days[i]]
        if prev > 0:
            daily_rets.append((cur - prev) / prev)
    best_day = max(daily_rets) if daily_rets else 0
    worst_day = min(daily_rets) if daily_rets else 0
    neg_days = sum(1 for x in daily_rets if x < 0)

    # 2. 成交流水 (状态机 history)
    st = {}
    sp = os.path.join(DATA, "pending_orders_state.json")
    if os.path.exists(sp):
        try:
            st = json.load(open(sp, encoding="utf-8"))
        except Exception:
            pass
    hist = st.get("history", [])
    placed = sum(1 for h in hist if "挂单" in h.get("evt", "") and "DRY" not in h.get("evt", ""))
    filled_n = sum(1 for h in hist if h.get("evt") == "挂单成交")
    wins = [h for h in hist if h.get("evt") == "L5止盈/离场"]
    losses = [h for h in hist if h.get("evt") == "L1止损/反转认亏"]
    win_pnls = [h.get("pnl", 0) for h in wins if h.get("pnl") is not None]
    loss_pnls = [h.get("pnl", 0) for h in losses if h.get("pnl") is not None]
    wr = len(wins) / (len(wins) + len(losses)) if (wins or losses) else float("nan")
    avg_win = statistics.mean(win_pnls) if win_pnls else 0
    avg_loss = abs(statistics.mean(loss_pnls)) if loss_pnls else 0
    pf = (sum(win_pnls) / abs(sum(loss_pnls))) if (loss_pnls and sum(loss_pnls) != 0) else float("nan")

    # 3. 故障统计 (auto_cycle.log)
    fault_lines = 0
    total_cycles = 0
    logp = os.path.join(DATA, "auto_cycle.log")
    if os.path.exists(logp):
        for l in open(logp, encoding="utf-8", errors="ignore"):
            if "[全链自动运行] " in l:
                total_cycles += 1
            if "异常" in l or "报错" in l or "失败" in l or "Traceback" in l:
                fault_lines += 1

    # 4. 结论
    checks = {
        "正期望 (期末>期初)": total_pnl > 0,
        "最大回撤 < 5%": mdd < 0.05,
        "日亏未破 3% 熔断": worst_day > -0.031,
        "风控违规次数 = 0": not any("违规" in str(h.get("why", "")) for h in hist),
        "全链故障率 < 5%": (fault_lines / total_cycles if total_cycles else 0) < 0.05,
    }
    pass_n = sum(checks.values())
    ready = pass_n >= 4 and checks["正期望 (期末>期初)"] and checks["最大回撤 < 5%"]

    rpt = os.path.join(DELIVER, f"月度复盘_{today.strftime('%Y-%m').replace('-','')}.md")
    with open(rpt, "w", encoding="utf-8") as f:
        f.write(f"# 金策宗师团 · 月度 LIVE 训练复盘\n\n")
        f.write(f"- 周期: {period} | demo 60137964 ($1000 起始)\n")
        f.write(f"- 生成时间: {today.isoformat(timespec='minutes')}\n\n")
        f.write("## 绩效总览\n\n")
        f.write(f"| 指标 | 数值 |\n|---|---|\n")
        f.write(f"| 期末净值 | ${eqs[-1]:.2f} (净值曲线 {len(rows)} 采样) |\n" if eqs else "| 期末净值 | 无数据 |\n")
        f.write(f"| 总盈亏 | {total_pnl:+.2f} ({_pct(total_ret*100) if eqs else '-'}) |\n")
        f.write(f"| 最大回撤 | {_pct(mdd*100)} |\n")
        f.write(f"| 最好日/最差日 | {_pct(best_day*100)} / {_pct(worst_day*100)} |\n")
        f.write(f"| 亏损日 | {neg_days}/{len(daily_rets)} 天 |\n" if daily_rets else "| 亏损日 | - |\n")
        f.write(f"| 挂单数 | {placed} | 成交 {filled_n} | 止盈 {len(wins)} 认亏 {len(losses)} |\n")
        f.write(f"| 胜率 | {_pct(wr*100)} | 盈亏比(PF) | {pf:.2f} |\n" if not (wr != wr) else "| 胜率 | 无成交 |\n")
        f.write(f"| 全链轮次 | {total_cycles} | 故障行 | {fault_lines} |\n\n")
        f.write("## 切实盘条件核验 (≥4项通过 且 前两项必须通过)\n\n")
        for k, v in checks.items():
            f.write(f"  - {'✓' if v else '✗'} {k}\n")
        concl = "具备切 $100 实盘条件 (建议仓位 1% 风险)" if ready else "不建议切换: 继续训练/策略需优化"
        f.write(f"\n**结论: {concl}**\n\n")
        f.write("## 逐日绩效\n\n")
        for d in days:
            f.write(f"  {d}: 期末净值 ${daily_eq[d]:.2f}\n")
        f.write("\n---\n**模拟账号实盘训练 | 历史表现≠未来收益 | 本复盘不承诺未来回报**\n")
    print(f"月度复盘已生成: {rpt}")
    print(f"通过 {pass_n}/{len(checks)} 项 | 切实盘建议: {'可以切' if ready else '继续训练'}")


if __name__ == "__main__":
    main()
