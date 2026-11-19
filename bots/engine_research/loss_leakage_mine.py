# -*- coding: utf-8 -*-
"""
亏损单深度泄漏挖掘 (2026-11-12) —— 第一波 PROFIT_SECURE 损失驱动优化 · 第 0 步
=============================================================================
用户口谕: "务必根据交易数据 把亏损单子的策略参数深度优化"
本脚本用**真实 11 月交易数据**量化六参数(及回撤地板)的"利润泄漏":

  - live24_trades.csv : 真实开/平/硬平/斩亏事件 + 成交价 + pnl + adx
  - mfe_mae_track.jsonl : 引擎逐笔 MFE/MAE/浮动 R(同一 price-R 单位, 仅含曾处于 live 的仓)

通用 price-R 口径(与引擎 r_mult 同基底, 跨品种一致, 不需合约表):
  dist    = |entry - sl|                       (引擎 SL = entry ∓ 2ATR => dist=2ATR)
  realized_R = (exit - entry) * dir / dist      (dir: +1 多 / -1 空)
  => 主分析只依赖 csv(全量亏损单); jsonl 仅做 MFE 富集(样本有限)。

泄漏定义(用户最痛 "做对方向冲高后吐回"): 仅在 jsonl 富集子集里用
  mfe_R>=1.0 且 realized_R<0.5*mfe_R 判定; csv 主分析用 realized_R 分层刻画亏损形态。

红线: 纯研究, 不改引擎/不连 MT5/不开实单; 产物落 E 盘。
"""
import csv, json, os
from collections import defaultdict

ROOT = "E:/GoldstrategyEngine"
CSV = os.path.join(ROOT, "data", "live24_trades.csv")
JSONL = os.path.join(ROOT, "data", "mfe_mae_track.jsonl")
OUT_MD = os.path.join(ROOT, "research", "loss_leakage_report.md")
OUT_JSON = os.path.join(ROOT, "research", "loss_leakage_data.json")

EXIT_EVENTS = {"CLOSE", "MAXHOLD硬平", "B0_EXIT", "LOSECUT斩亏", "SLTP_OPT",
               "MAGIC_DUP_EXIT", "MANUAL_SL_PATCH"}

def f(x):
    try:
        return float(x)
    except Exception:
        return None

def load_csv():
    opens, exits = {}, {}
    with open(CSV, encoding="utf-8") as fh:
        r = csv.reader(fh)
        next(r, None)
        for row in r:
            if len(row) < 9:
                continue
            ts, ev = row[0], row[1]
            sym, dstr, tkt = row[2], row[3], row[4]
            try:
                d = int(float(dstr))
            except Exception:
                d = 0
            if ev == "OPEN":
                opens[tkt] = dict(ts=ts, sym=sym, dir=d,
                                   entry=f(row[5]), sl=f(row[6]))
            elif ev in EXIT_EVENTS:
                exit_px = f(row[8]) if len(row) > 8 else None
                pnl = f(row[9]) if len(row) > 9 else None
                adx = f(row[10]) if len(row) > 10 else None
                cur = exits.get(tkt)
                # 取首个有成交价的退出事件(优先真实成交价)
                if cur is None or (exit_px is not None and cur.get("exit") is None):
                    exits[tkt] = dict(ts=ts, ev=ev, sym=sym, dir=d,
                                       entry=f(row[5]), sl=f(row[6]),
                                       exit=exit_px, pnl=pnl, adx=adx)
    return opens, exits

def load_jsonl():
    last = {}
    with open(JSONL, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            for rec in obj.get("live", []):
                t = rec.get("ticket")
                if t is None:
                    continue
                last[str(t)] = rec
    return last

def rr_band(x):
    if x < -0.8:  return "A.重亏(<-0.8R 接近打满SL)"
    if x < -0.2:  return "B.中亏(-0.8~-0.2R)"
    if x < 0:     return "C.微亏(-0.2~0R 疑似吐回)"
    if x < 0.5:   return "D.微利(0~0.5R)"
    return "E.中利(>=0.5R)"

def main():
    opens, exits = load_csv()
    mfe = load_jsonl()

    # ---- 主分析: 全量 csv 亏损单 ----
    rows = []
    by_sym = defaultdict(list)
    by_event = defaultdict(list)
    by_band = defaultdict(list)
    by_adx = defaultdict(list)
    n = n_win = n_loss = 0
    loss_r_total = 0.0
    # 持仓时长(开→平 小时)
    hold_hours = []

    for tkt, ex in exits.items():
        op = opens.get(tkt)
        entry = ex.get("entry") or (op["entry"] if op else None)
        sl = ex.get("sl") or (op["sl"] if op else None)
        d = ex.get("dir") or (op["dir"] if op else 0)
        exit_px = ex.get("exit")
        if entry is None or sl is None or exit_px is None or d == 0:
            continue
        dist = abs(entry - sl)
        if dist <= 1e-9:
            continue
        realized_R = (exit_px - entry) * d / dist
        adx = ex.get("adx")
        # 持仓时长
        hh = None
        if op:
            try:
                from datetime import datetime
                t0 = datetime.strptime(op["ts"], "%Y-%m-%d %H:%M:%S")
                t1 = datetime.strptime(ex["ts"], "%Y-%m-%d %H:%M:%S")
                hh = (t1 - t0).total_seconds() / 3600.0
                hold_hours.append(hh)
            except Exception:
                pass
        rec = dict(ticket=tkt, sym=ex["sym"], dir=d, ev=ex["ev"],
                   realized_R=round(realized_R, 4), adx=(round(adx, 1) if adx is not None else None),
                   band=rr_band(realized_R), hold_h=round(hh, 2) if hh is not None else None,
                   mfe_R=None, leakage_R=None, giveback_fail=False)
        rows.append(rec)
        by_sym[ex["sym"]].append(rec)
        by_event[ex["ev"]].append(rec)
        by_band[rec["band"]].append(rec)
        if adx is not None:
            ab = ("ADX<25" if adx < 25 else "25-35" if adx < 35 else ">=35")
            by_adx[ab].append(rec)
        n += 1
        if realized_R > 0:
            n_win += 1
        else:
            n_loss += 1
            loss_r_total += realized_R

    # ---- 富集: jsonl MFE(仅样本) ----
    gb_fail = []
    for rec in rows:
        j = mfe.get(str(rec["ticket"]))
        if not j:
            continue
        mr = f(j.get("mfe_R"))
        if mr is None:
            continue
        rec["mfe_R"] = round(mr, 4)
        if mr > 0:
            rec["leakage_R"] = round(mr - rec["realized_R"], 4)
        if mr >= 1.0 and rec["realized_R"] < 0.5 * mr:
            rec["giveback_fail"] = True
            gb_fail.append(rec)

    # ---- 报告 ----
    L = []
    L.append("# 亏损单利润泄漏挖掘报告 (2026-11-12)\n")
    L.append("> 数据源: `live24_trades.csv`(真实 11 月全量成交) + `mfe_mae_track.jsonl`(引擎逐笔 MFE, 富集样本)\n")
    L.append("> 口径: price-R 跨品种一致; `realized_R=(exit-entry)*dir/|entry-sl|`; 主分析纯 csv, 不依赖 jsonl。\n")
    L.append("\n## 1. 全量亏损单总览(csv 主分析)\n")
    L.append("| 指标 | 值 |")
    L.append("|---|---|")
    L.append("| 可结算逐笔 | %d |" % n)
    L.append("| 盈利 / 亏损 | %d / %d |" % (n_win, n_loss))
    L.append("| 胜率 | %.1f%% |" % (100.0 * n_win / n if n else 0))
    L.append("| 亏损单累计实现 R | %.2f R |" % loss_r_total)
    L.append("| 平均亏损单 R | %.3f R |" % (loss_r_total / n_loss if n_loss else 0))
    if hold_hours:
        L.append("| 平均持仓时长 | %.1f h |" % (sum(hold_hours) / len(hold_hours)))
    L.append("| jsonl 富集到有 MFE 的逐笔 | %d (其中吐回失败 %d) |" % (
        sum(1 for r in rows if r["mfe_R"] is not None), len(gb_fail)))

    L.append("\n## 2. 实现 R 分层(亏损形态)\n")
    L.append("| 分层 | 笔数 | 占比 |")
    L.append("|---|---|---|")
    for b in ["A.重亏(<-0.8R 接近打满SL)", "B.中亏(-0.8~-0.2R)",
              "C.微亏(-0.2~0R 疑似吐回)", "D.微利(0~0.5R)", "E.中利(>=0.5R)"]:
        if b not in by_band:
            continue
        lst = by_band[b]
        L.append("| %s | %d | %d%% |" % (b, len(lst), round(100 * len(lst) / n)))

    L.append("\n## 3. 按退出事件分布\n")
    L.append("| 事件 | 笔数 | 盈利 | 亏损 | 平均实现R |")
    L.append("|---|---|---|---|---|")
    for ev, lst in sorted(by_event.items(), key=lambda kv: -len(kv[1])):
        cnt = len(lst)
        w = sum(1 for r in lst if r["realized_R"] > 0)
        ar = sum(r["realized_R"] for r in lst) / cnt
        L.append("| %s | %d | %d | %d | %.3f |" % (ev, cnt, w, cnt - w, ar))

    L.append("\n## 4. 按品种分布(优先优化对象)\n")
    L.append("| 品种 | 笔数 | 盈利 | 亏损 | 平均实现R | 微亏/微利占比 |")
    L.append("|---|---|---|---|---|---|")
    for sym, lst in sorted(by_sym.items(), key=lambda kv: -len(kv[1])):
        cnt = len(lst)
        w = sum(1 for r in lst if r["realized_R"] > 0)
        ar = sum(r["realized_R"] for r in lst) / cnt
        cdf = sum(1 for r in lst if r["band"].startswith(("C", "D")))
        L.append("| %s | %d | %d | %d | %.3f | %d%% |" % (sym, cnt, w, cnt - w, ar, round(100 * cdf / cnt)))

    if by_adx:
        L.append("\n## 5. 按 ADX 分布(弱趋势更易吐回?)\n")
        L.append("| ADX 区间 | 笔数 | 平均实现R |")
        L.append("|---|---|---|")
        for ab in ["ADX<25", "25-35", ">=35"]:
            if ab not in by_adx:
                continue
            lst = by_adx[ab]
            L.append("| %s | %d | %.3f |" % (ab, len(lst), sum(r["realized_R"] for r in lst) / len(lst)))

    if gb_fail:
        L.append("\n## 6. 富集子集: 做对却吐回>50%% 的亏损单(jsonl MFE)\n")
        L.append("| ticket | 品种 | MFE | 实现R | 吐回R | 出场 |")
        L.append("|---|---|---|---|---|---|")
        for r in sorted(gb_fail, key=lambda x: -(x["leakage_R"] or 0))[:40]:
            L.append("| %s | %s | %.2f | %.2f | %.2f | %s |" % (
                r["ticket"], r["sym"], r["mfe_R"], r["realized_R"], r["leakage_R"], r["ev"]))

    L.append("\n## 7. 结论与优化靶心\n")
    L.append("- 全量 %d 笔结算, 胜率 %.1f%%, 亏损单累计 %.2f R。" % (n, 100.0*n_win/n if n else 0, loss_r_total))
    L.append("- 亏损形态分层 + 品种/事件分布已定位『最该优化的亏损单』, 直接喂给 `profit_secure_deep_v2.py` 五验做损失驱动寻优。")
    L.append("- 优化杠杆(均须先过五验 + chief R11 翻闸, 不在本脚本落码):")
    L.append("  ① 回撤地板带宽 GIVEBACK_BAND_R 0.6→更紧(0.4/0.5): 兜住『冲高后反转』吐回;")
    L.append("  ② 锁半利地板 PS_LOCK_HALF_R 1.2→更早(1.0) / 保本缓冲 PS_BE_BUF_R 0.2→更宽: 抗 0.5R 回踩、保住反转前利润;")
    L.append("  ③ 入场侧信号枯竭已另有 WFO 在跑(信号闸松弛), 本脚本只管出场侧六参数 + 回撤地板。")
    L.append("- **数据治理建议(写入规章制度)**: 当前 jsonl 仅记录 live 仓 MFE, 关闭即丢; 应在 CLOSE/硬平事件落盘时**持久化该笔 mfe_R**, 否则无法对历史亏损单做逐笔吐回审计。此为下一轮损失驱动 WFO 的必备前提。")

    md = "\n".join(L)
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write(md)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(dict(n=n, n_win=n_win, n_loss=n_loss,
                       loss_r_total=round(loss_r_total, 3),
                       rows=rows), fh, ensure_ascii=False, indent=1)

    print("=== 亏损单泄漏挖掘完成 (csv 主分析) ===")
    print("可结算逐笔: %d | 盈利 %d / 亏损 %d | 胜率 %.1f%%" % (
        n, n_win, n_loss, 100.0 * n_win / n if n else 0))
    print("亏损单累计实现 R: %.2f R | 平均亏损 %.3f R" % (
        loss_r_total, loss_r_total / n_loss if n_loss else 0))
    print("jsonl 富集 MFE 逐笔: %d (吐回失败 %d)" % (
        sum(1 for r in rows if r["mfe_R"] is not None), len(gb_fail)))
    print("报告 -> %s" % OUT_MD)

if __name__ == "__main__":
    main()
