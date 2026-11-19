# -*- coding: utf-8 -*-
"""
WFV 终报生成器 — 消费 walk_forward_validator.run_wfv 产出的 JSON，
筛出样本外正 edge 的策略×品种组合，汇总每策略稳健度，输出 Markdown 终报。

用法:
    python gen_wfv_report.py [wfv_json] [out_md]
默认: data/wfv_batch1.json -> data/WFV_REPORT.md

判定标准(可调):
    POS_EDGE_PF   = 1.10   样本外 wfo_pf 阈值(>1 才赚钱)
    MIN_OOS_FOLDS = 3       5折中至少3折样本外正(防单折运气)
    OVERFIT_WARN  = 20      训练折中位pf / 样本外pf 之比 > 此值 -> 标注过拟合嫌疑
"""
import json
import os
import sys
import datetime

POS_EDGE_PF = 1.10
MIN_OOS_FOLDS = 3
OVERFIT_WARN = 20.0


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build(data):
    per = data.get("per_symbol", {})
    rows = []          # 每个 (品种,策略) 正edge命中
    strategy_hits = {} # 策略 -> [品种列表]
    for sym, blk in per.items():
        note = blk.get("note", "")
        summ = blk.get("summary", {})
        if not summ:
            continue
        for st, d in summ.items():
            wfo = float(d.get("wfo_pf", 0) or 0)
            oos = int(d.get("oos_folds", 0) or 0)
            n = int(d.get("n", 0) or 0)
            wr = float(d.get("wr", 0) or 0)
            train_med = float(d.get("train_pf_med", 0) or 0)
            ratio = (train_med / wfo) if wfo > 0 else 0
            overfit = ratio > OVERFIT_WARN
            is_pos = (wfo >= POS_EDGE_PF) and (oos >= MIN_OOS_FOLDS) and (n >= 20)
            rows.append({
                "sym": sym, "st": st, "wfo": wfo, "oos": oos, "n": n,
                "wr": wr, "train_med": train_med, "ratio": ratio,
                "overfit": overfit, "pos": is_pos, "note": note,
            })
            if is_pos:
                strategy_hits.setdefault(st, []).append(sym)

    pos_rows = [r for r in rows if r["pos"]]
    pos_rows.sort(key=lambda r: -r["wfo"])

    # 策略稳健度排名
    strat_rank = sorted(
        [(st, syms) for st, syms in strategy_hits.items()],
        key=lambda kv: (-len(kv[1]), -max(rows_for(rows, kv[0])) if rows_for(rows, kv[0]) else 0),
    )
    return rows, pos_rows, strat_rank, strategy_hits


def rows_for(rows, st):
    return [r["wfo"] for r in rows if r["st"] == st and r["pos"]]


def fmt_md(data, rows, pos_rows, strat_rank, strategy_hits, src):
    gen = data.get("generated", "")
    folds = data.get("folds", 5)
    nt = data.get("symbols_tested", 0)
    elap = data.get("elapsed_s", 0)
    lines = []
    lines.append("# WFV 样本外正 Edge 终报")
    lines.append("")
    lines.append(f"- 生成时间: {gen}")
    lines.append(f"- 数据源: `{src}`")
    lines.append(f"- 方法: Walk-Forward 样本外验证 (K={folds} 折时间序, 训练窗网格搜参, 只报测试折样本外 pf)")
    lines.append(f"- 测试品种数: {nt} | 耗时: {elap}s")
    lines.append(f"- 判定阈值: wfo_pf≥{POS_EDGE_PF} 且 样本外折≥{MIN_OOS_FOLDS}/{folds} 且 样本≥20")
    lines.append("")

    lines.append("## 一、结论速览")
    lines.append("")
    if not pos_rows:
        lines.append("**未找到任何样本外正 edge 组合。** 7 策略在当前市况 + WFV 严谨验证下均无可靠 edge，需转向新策略研究（非调参）。")
    else:
        n_sym = len(set(r["sym"] for r in pos_rows))
        n_st = len(strat_rank)
        lines.append(f"**找到 {len(pos_rows)} 个样本外正 edge 组合**，覆盖 {n_sym} 个品种 / {n_st} 个策略。")
        lines.append("")
        lines.append("### 策略稳健度排名（在多少品种上验证出正 edge）")
        lines.append("")
        lines.append("| 策略 | 正edge品种数 | 代表品种 | 最高wfo_pf |")
        lines.append("|:--|:--|:--|:--|")
        for st, syms in strat_rank:
            wfos = [r["wfo"] for r in pos_rows if r["st"] == st]
            best = max(wfos) if wfos else 0
            rep = ", ".join(syms[:4])
            lines.append(f"| {st} | {len(syms)} | {rep} | {best:.2f} |")
    lines.append("")

    lines.append("## 二、正 Edge 候选清单（按 wfo_pf 降序）")
    lines.append("")
    if pos_rows:
        lines.append("| 品种 | 策略 | wfo_pf | 胜率 | 样本 | OOS折 | 训练中位pf | 过拟合嫌疑 |")
        lines.append("|:--|:--|:--|:--|:--|:--|:--|:--|")
        for r in pos_rows:
            flag = "⚠️" if r["overfit"] else ""
            lines.append(
                f"| {r['sym']} | {r['st']} | {r['wfo']:.2f} | {r['wr']:.2f} | {r['n']} | {r['oos']}/{folds} | {r['train_med']:.1f} | {flag} |"
            )
    else:
        lines.append("（无）")
    lines.append("")

    lines.append("## 三、全部策略×品种扫描明细")
    lines.append("")
    lines.append("| 品种 | 策略 | wfo_pf | 胜率 | 样本 | OOS折 | 训练中位pf | 判定 |")
    lines.append("|:--|:--|:--|:--|:--|:--|:--|:--|")
    for r in sorted(rows, key=lambda x: (x["sym"], -x["wfo"])):
        judge = "✅正edge" if r["pos"] else ("过拟合嫌疑" if r["overfit"] else "负/不稳")
        lines.append(
            f"| {r['sym']} | {r['st']} | {r['wfo']:.2f} | {r['wr']:.2f} | {r['n']} | {r['oos']}/{folds} | {r['train_med']:.1f} | {judge} |"
        )
    lines.append("")

    lines.append("## 四、接入 live 门控建议")
    lines.append("")
    if pos_rows:
        lines.append("将上表 ✅ 组合写入 `edge_tracker` 的 WFV 白名单（替换当前 `get_backtest_pf` 回测兜底），")
        lines.append("使 `is_symbol_allowed` 在实盘样本不足时，优先放行 WFV 验证过的 (品种,策略) 组合，而非被朴素回测误导。")
        lines.append("")
        lines.append("优先级：先接稳健度排名前 2 的策略（跨品种正 edge 最多者），灰度验证 1-2 周实盘样本后再全量。")
    else:
        lines.append("无正 edge 可接。建议冻结当前 7 策略开仓，转入新信号研究（突破/动量/波动率/订单流等）。")
    lines.append("")
    lines.append(f"> 报告由 gen_wfv_report.py 自动生成 @ {datetime.datetime.now().isoformat()}")
    return "\n".join(lines)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "data/wfv_batch1.json"
    out = sys.argv[2] if len(sys.argv) > 2 else "data/WFV_REPORT.md"
    if not os.path.exists(src):
        print(f"[gen_wfv_report] 源文件不存在: {src}（WFV 批量是否跑完？）")
        return 1
    data = load(src)
    rows, pos_rows, strat_rank, strategy_hits = build(data)
    md = fmt_md(data, rows, pos_rows, strat_rank, strategy_hits, src)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[gen_wfv_report] 已生成: {out}")
    print(f"  正edge组合: {len(pos_rows)} | 覆盖品种: {len(set(r['sym'] for r in pos_rows))} | 策略: {len(strat_rank)}")
    for st, syms in strat_rank:
        print(f"  {st}: {len(syms)} 品种 -> {', '.join(syms[:6])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
