# -*- coding: utf-8 -*-
"""
交易全生命周期深度分析引擎 · trade_lifecycle_analyzer
====================================================
用户口谕(2026-11-12 14:32): "每一个单子从开单到关闭都要全程深度分析... 让专人负责... 全面深度优化进场出场点位, 全面提升赚钱能力"。

数据源(自包含, 不依赖H1回放):
  E:/GoldstrategyEngine/data/live24_trades.csv
    列: ts,event,symbol,dir,ticket,entry,sl,tp,exit,pnl,adx,note
    OPEN        -> 进场上下文(entry/sl/tp/adx/信号备注)
    SL_TRAIL    -> 止损拖拽路径; 每行 note 含 "浮盈X.XXR" = 当时浮盈R(峰值即MFE代理)
    CLOSE/MAXHOLD硬平/B0_EXIT/LOSECUT斩亏/MAGIC_DUP_EXIT/USD_TAKE -> 出场(出场价/pnl/原因/持仓时长)
    SKIP_*      -> 进场质量漏斗(各闸拦截计数)

核心指标(每单):
  R          = (exit-entry)*dir / |entry-sl|            # 已实现R倍数
  MFE_R      = max(SL_TRAIL note浮盈R)                  # 峰值有利偏移(代理); 无trail则=MFE未知
  MAE_R      = 从note浮亏推断(如B0_EXIT浮亏-0.67R)       # 峰值不利偏移(代理)
  GIVEBACK_R = MFE_R - R                                # 回吐利润(留给市场的钱)
  EXIT_EFF   = R / MFE_R                                # 出场效率(1.0=卖在山顶)
  HOLD_H     = 持仓时长(小时, 取自note持仓Xh/min 或 ts差)
  EXIT_TYPE  = 出场类型(B0假突破/MAXHOLD触顶/斩亏/USD落袋/强制平/其他)
  ENTRY_ADX  = 进场ADX(趋势强度)
  SIGNAL     = 从OPEN/SKIP note提取的信号族(若可辨)

输出: research/trade_deep_analysis/runs/<RUN>/ 下
  00_SUMMARY.md          顶层KPI + 进场漏斗 + 分群表 + 优化假说
  01_per_trade_table.csv 全量匹配单明细
  02_per_trade_deep.md   逐单深度剖析(开→平)
  metrics.json           机器可读
纯研究/只读, 不改引擎、不连MT5。
"""
import csv, os, re, json, sys, time as _t
from collections import defaultdict, Counter
from datetime import datetime

ROOT = "E:/GoldstrategyEngine"
TRADE_CSV = os.path.join(ROOT, "data", "live24_trades.csv")
OUT_BASE = os.path.join(ROOT, "research", "trade_deep_analysis", "runs")

EXIT_EVENTS = {"CLOSE", "MAXHOLD硬平", "B0_EXIT", "LOSECUT斩亏",
               "MAGIC_DUP_EXIT", "USD_TAKE", "PINBAR_EXIT", "OPEN_REJECTED"}
# 注: SLTP_OPT 是 SL/TP 优化事件(rc=10016, 非真实平仓), 不计入出场。
SKIP_EVENTS = {"SKIP_RR_QUALITY", "SKIP_H1", "SKIP_SPREAD", "SKIP_PORTFOLIO",
               "SKIP_HALT", "SKIP_RETIRE_FREEZE", "SKIP_SESSION", "SKIP_CONC",
               "SKIP_SESSION_GAP", "SKIP_GATE1", "SKIP_CHASE", "SKIP_CLOSEONLY",
               "SKIP_IDX_SESSION", "SKIP_SCA_SESSION", "SKIP_SL_SPREAD", "SKIP_VOLCLASS",
               "SKIP_EVENT_TIMING", "SKIP_STOP_CAP", "SKIP_RR_QUALITY", "SKIP_SPREAD2",
               "SKIP_DAYLOSS", "SKIP_SCA_SESSION"}
FALSE_OPEN_MARK = ("假阳性", "实盘无此仓", "OPEN_REJECTED", "断线被拒", "no network")


def pfloat(x):
    try:
        return float(x)
    except Exception:
        return None


def pdt(s):
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def fR(note):
    """提取 note 中 '浮盈X.XXR' 或 '浮亏-X.XXR' 的R值(取最大正向=峰值有利)。"""
    if not note:
        return None
    vals = [float(v) for v in re.findall(r"浮盈([-\d.]+)R", note)]
    neg = [float(v) for v in re.findall(r"浮亏(-?[\d.]+)R", note)]
    allv = vals + neg
    return max(allv) if allv else None


def hold_h(note, ts_open, ts_exit):
    h = None
    if note:
        m = re.search(r"持仓([\d.]+)h", note)
        if m:
            h = float(m.group(1))
        else:
            m = re.search(r"持仓(\d+)分钟", note)
            if m:
                h = float(m.group(1)) / 60.0
            else:
                m = re.search(r"持仓(\d+)min", note)
                if m:
                    h = float(m.group(1)) / 60.0
    if h is None and ts_open and ts_exit:
        d = (ts_exit - ts_open).total_seconds() / 3600.0
        if d >= 0:
            h = d
    return h


def parse():
    opens, trails, exits, skips = {}, defaultdict(list), {}, Counter()
    with open(TRADE_CSV, encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            ev = (row.get("event") or "").strip()
            if ev == "OPEN":
                tk = row.get("ticket", "")
                if tk in ("", "0") or any(k in (row.get("note") or "") for k in FALSE_OPEN_MARK):
                    continue
                if tk in opens:
                    continue
                opens[tk] = row
            elif ev == "SL_TRAIL":
                trails[row.get("ticket", "")].append(row)
            elif ev in EXIT_EVENTS:
                tk = row.get("ticket", "")
                if tk and tk not in exits:
                    exits[tk] = row
            elif ev in SKIP_EVENTS:
                skips[ev] += 1
    return opens, trails, exits, skips


def get_dist(o, trs, dirn, entry):
    """重建 1R 距离: 优先 OPEN 的 sl; 缺失则用首条 SL_TRAIL 的锁利标签反推
    (如 '强化锁0.2R 浮盈0.50R' -> sl=entry+0.2*dist -> dist=(sl-entry)*dir/0.2)。"""
    sl0 = pfloat(o.get("sl"))
    if sl0 is not None and abs(sl0 - entry) > 1e-9:
        return abs(sl0 - entry)
    for t in trs:
        tag = t.get("note", "")
        slv = pfloat(t.get("sl"))
        if slv is None or entry is None:
            continue
        lr = 0.2 if "保本" in tag else None
        if lr is None:
            m = re.search(r"锁([\d.]+)R", tag)
            if m:
                lr = float(m.group(1))
        if lr and lr > 0:
            d = (slv - entry) * dirn / lr
            if d > 0:
                return d
    # 兜底: 纯ATR轨道首条(r已知), sl≈entry+(r-0.4)R 反推 (dist=2ATR)
    for t in trs:
        slv = pfloat(t.get("sl"))
        r = fR(t.get("note"))
        if slv is None or r is None or abs(r - 0.4) < 1e-6:
            continue
        d = (slv - entry) * dirn / (r - 0.4)
        if d > 0:
            return d
    return None


def build_trades(opens, trails, exits):
    trades = []
    for tk, o in opens.items():
        entry = pfloat(o.get("entry"))
        if entry is None:
            continue
        dirn = 1 if (o.get("dir") or "").strip() in ("1", "BUY") else -1
        trs = trails.get(tk, [])
        dist = get_dist(o, trs, dirn, entry)
        if dist is None or dist <= 0:
            continue
        ex = exits.get(tk)
        # MFE 代理: SL_TRAIL note 浮盈R 峰值
        mfe = None
        for t in trs:
            v = fR(t.get("note"))
            if v is not None:
                mfe = v if mfe is None else max(mfe, v)
        rec = dict(ticket=tk, sym=o.get("symbol", ""), dirn=dirn,
                   entry=entry, sl=entry - dirn * dist, tp=pfloat(o.get("tp")),
                   adx=pfloat(o.get("adx")), note_open=o.get("note", ""),
                   ts_open=pdt(o.get("ts")), trails=len(trs), mfe=mfe)
        if ex:
            exit_px = pfloat(ex.get("exit")) or pfloat(ex.get("sl"))
            pnl = pfloat(ex.get("pnl"))
            rec.update(exit_px=exit_px, pnl=pnl, note_exit=ex.get("note", ""),
                       ts_exit=pdt(ex.get("ts")), exit_event=ex.get("event", ""))
            if exit_px is not None:
                R = (exit_px - entry) * dirn / dist
                rec["R"] = R
                rec["exit_eff"] = (R / mfe) if (mfe and mfe > 0) else None
                rec["giveback"] = (mfe - R) if mfe is not None else None
            rec["hold_h"] = hold_h(ex.get("note", ""), rec["ts_open"], rec["ts_exit"])
            rec["exit_type"] = classify_exit(ex.get("event", ""), ex.get("note", ""))
        else:
            rec["exit_type"] = "OPEN_ONLY(未匹配出场)"
        trades.append(rec)
    return trades


def classify_exit(ev, note):
    if ev == "B0_EXIT":
        return "B0假突破失效"
    if ev == "MAXHOLD硬平":
        return "MAXHOLD触顶强平"
    if ev == "LOSECUT斩亏":
        return "LOSECUT斩亏"
    if ev == "USD_TAKE":
        return "USD落袋"
    if ev == "MAGIC_DUP_EXIT":
        return "MAGIC重复退出"
    if ev == "CLOSE":
        if "L4_C1_CLOSE" in (note or "") or "RECONCILE" in (note or ""):
            return "强制/对账平"
        return "主动平"
    if ev == "PINBAR_EXIT":
        return "PINBAR插针平"
    return ev or "其他"


def cohort(trades, key):
    g = defaultdict(list)
    for t in trades:
        if "R" not in t:
            continue
        g[key(t)].append(t)
    rows = []
    for k, ts in g.items():
        n = len(ts)
        net = sum(t["R"] for t in ts)
        win = sum(1 for t in ts if t["R"] > 0)
        loss = sum(1 for t in ts if t["R"] < -1e-6)
        avg_mfe = sum((t.get("mfe") or 0) for t in ts) / n
        avg_gb = sum((t.get("giveback") or 0) for t in ts) / n
        rows.append((k, n, net, net / n, win / n * 100, loss / n * 100, avg_mfe, avg_gb))
    rows.sort(key=lambda r: -r[2])
    return rows


def main():
    t0 = _t.time()
    opens, trails, exits, skips = parse()
    trades = build_trades(opens, trails, exits)
    closed = [t for t in trades if "R" in t]
    print("解析完成: OPEN=%d 匹配出场=%d 总记录=%d | SKIP事件=%d类" %
          (len(opens), len(closed), len(trades), len(skips)))
    if not closed:
        print("无匹配出场单, 退出")
        return

    netR = sum(t["R"] for t in closed)
    win = sum(1 for t in closed if t["R"] > 0)
    loss = sum(1 for t in closed if t["R"] < -1e-6)
    n = len(closed)
    avg_mfe = sum((t.get("mfe") or 0) for t in closed) / n
    avg_gb = sum((t.get("giveback") or 0) for t in closed) / n
    with_mfe = [t for t in closed if t.get("mfe") is not None]
    avg_eff = (sum(t["exit_eff"] for t in with_mfe if t.get("exit_eff") is not None and t["R"] > 0) /
               max(1, len([t for t in with_mfe if t.get("exit_eff") is not None and t["R"] > 0])))

    run = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = os.path.join(OUT_BASE, run)
    os.makedirs(outdir, exist_ok=True)

    # ---- 00_SUMMARY.md ----
    L = []
    L.append("# 交易全生命周期深度分析 · %s\n" % run)
    L.append("## 顶层KPI (匹配出场单 n=%d)" % n)
    L.append("- 净R = **%.4f**  |  均值R = %.4f" % (netR, netR / n))
    L.append("- 胜率 = %.1f%%  |  亏损率 = %.1f%%" % (win / n * 100, loss / n * 100))
    L.append("- 平均MFE(峰值有利R) = %.3f  |  平均回吐GIVEBACK = %.3f R" % (avg_mfe, avg_gb))
    L.append("- 平均出场效率 = %.1f%% (1.0=卖在山顶; 越低=回吐越多)" % (avg_eff * 100))
    L.append("")
    L.append("## 进场质量漏斗 (SKIP_* 拦截计数 → 哪里漏单/过严)")
    tot_skip = sum(skips.values())
    L.append("- 总拦截 = %d 次候选信号被闸拒" % tot_skip)
    for k, v in skips.most_common():
        L.append("  - %s : %d" % (k, v))
    L.append("")
    L.append("## 分群: 按品种 (净R排序)")
    L.append("| 品种 | n | 净R | 均值R | 胜率 | 亏损率 | 平均MFE | 平均回吐 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for k, nn, nr, ar, wr, lr, am, ag in cohort(closed, lambda t: t["sym"]):
        L.append("| %s | %d | %.3f | %.4f | %.1f%% | %.1f%% | %.3f | %.3f |" %
                 (k, nn, nr, ar, wr, lr, am, ag))
    L.append("")
    L.append("## 分群: 按出场类型")
    L.append("| 出场类型 | n | 净R | 均值R | 胜率 | 亏损率 | 平均MFE | 平均回吐 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for k, nn, nr, ar, wr, lr, am, ag in cohort(closed, lambda t: t["exit_type"]):
        L.append("| %s | %d | %.3f | %.4f | %.1f%% | %.1f%% | %.3f | %.3f |" %
                 (k, nn, nr, ar, wr, lr, am, ag))
    L.append("")
    L.append("## 分群: 按进场ADX区间 (进场质量)")
    def adx_bucket(t):
        a = t.get("adx") or 0
        if a < 25: return "ADX<25(弱趋势)"
        if a < 40: return "ADX 25-40(中趋势)"
        return "ADX>=40(强趋势)"
    L.append("| ADX区间 | n | 净R | 均值R | 胜率 | 亏损率 | 平均MFE | 平均回吐 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for k, nn, nr, ar, wr, lr, am, ag in cohort(closed, adx_bucket):
        L.append("| %s | %d | %.3f | %.4f | %.1f%% | %.1f%% | %.3f | %.3f |" %
                 (k, nn, nr, ar, wr, lr, am, ag))
    L.append("")
    L.append("## 优化假说 (自动生成 · 供WFO验证)")
    hyps = gen_hypotheses(closed, skips)
    for h in hyps:
        L.append("- " + h)
    L.append("")
    with open(os.path.join(outdir, "00_SUMMARY.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    # ---- 01_per_trade_table.csv ----
    with open(os.path.join(outdir, "01_per_trade_table.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ticket", "sym", "dir", "entry", "sl", "exit", "R", "MFE_R",
                    "giveback_R", "exit_eff", "hold_h", "adx", "exit_type", "note"])
        for t in sorted(closed, key=lambda x: x.get("R", 0)):
            w.writerow([t["ticket"], t["sym"], t["dirn"], "%.5f" % t["entry"],
                        "%.5f" % t["sl"], "%.5f" % t.get("exit_px", 0), "%.4f" % t["R"],
                        "%.3f" % (t.get("mfe") or 0), "%.3f" % (t.get("giveback") or 0),
                        "%.3f" % (t.get("exit_eff") or 0), "%.2f" % (t.get("hold_h") or 0),
                        "%.1f" % (t.get("adx") or 0), t["exit_type"],
                        (t.get("note_exit") or "")[:80]])

    # ---- 02_per_trade_deep.md ----
    D = ["# 逐单深度剖析 (开→平)\n"]
    for t in sorted(closed, key=lambda x: x.get("R", 0)):
        D.append("## #%s %s %s @ %.5f" % (t["ticket"], t["sym"],
                     "BUY" if t["dirn"] > 0 else "SELL", t["entry"]))
        D.append("- 进场: ADX=%.1f | SL=%.5f (1R=%.5f) | TP=%s" %
                 (t.get("adx") or 0, t["sl"], abs(t["entry"] - t["sl"]),
                  "%.5f" % t["tp"] if t.get("tp") else "—"))
        D.append("- 出场: %s | 价=%.5f | PnL=%s | 持仓=%.2fh" %
                 (t["exit_type"], t.get("exit_px", 0), t.get("pnl"), t.get("hold_h") or 0))
        D.append("- **R=%.4f** | MFE(峰值)=%.3fR | 回吐=%.3fR | 出场效率=%.1f%%" %
                 (t["R"], t.get("mfe") or 0, t.get("giveback") or 0,
                  (t.get("exit_eff") or 0) * 100))
        D.append("- SL拖拽次数=%d | 备注(开):%s" % (t["trails"], (t.get("note_open") or "")[:90]))
        D.append("- 备注(平):%s" % ((t.get("note_exit") or "")[:120]))
        D.append("")
    with open(os.path.join(outdir, "02_per_trade_deep.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(D))

    # ---- 结构化分群 (供自动化watcher直接读取, 无需解析markdown) ----
    def cohort_rows(getter):
        rows = []
        for k, nn, nr, ar, wr, lr, am, ag in cohort(closed, getter):
            rows.append(dict(bucket=k, n=nn, netR=round(nr, 4), avgR=round(ar, 4),
                             win_rate=round(wr / 100, 3), loss_rate=round(lr / 100, 3),
                             avg_mfe=round(am, 3), avg_giveback=round(ag, 3)))
        return rows
    adx_rows = cohort_rows(adx_bucket)
    exit_rows = cohort_rows(lambda t: t["exit_type"])
    sym_rows = cohort_rows(lambda t: t["sym"])

    # ---- metrics.json ----
    metrics = dict(run=run, n_closed=n, netR=round(netR, 4), avgR=round(netR / n, 4),
                  win_rate=round(win / n, 3), loss_rate=round(loss / n, 3),
                  avg_mfe=round(avg_mfe, 3), avg_giveback=round(avg_gb, 3),
                  avg_exit_eff=round(avg_eff, 3), skips=dict(skips),
                  hypotheses=hyps,
                  adx_cohorts=adx_rows, exit_cohorts=exit_rows, sym_cohorts=sym_rows)
    with open(os.path.join(outdir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    print("输出目录: %s" % outdir)
    print("净R=%.4f 胜率=%.1f%% 均值R=%.4f 平均MFE=%.3f 平均回吐=%.3f 出场效率=%.1f%%" %
          (netR, win / n * 100, netR / n, avg_mfe, avg_gb, avg_eff * 100))
    print("用时 %.1fs" % (_t.time() - t0))


def gen_hypotheses(closed, skips):
    H = []
    by_type = defaultdict(list)
    for t in closed:
        by_type[t["exit_type"]].append(t)
    # 回吐最大的出场类型
    for et, ts in by_type.items():
        if len(ts) < 5:
            continue
        ag = sum((t.get("giveback") or 0) for t in ts) / len(ts)
        if ag > 0.5:
            H.append("【回吐】%s 类(n=%d)平均回吐 %.2fR —— 建议收紧该类别止盈/轨道, 或核查其SL拖拽是否过松" %
                     (et, len(ts), ag))
    # MAXHOLD 触顶: 是否砍赢单
    mh = by_type.get("MAXHOLD触顶强平", [])
    if mh:
        avg_mfe = sum((t.get("mfe") or 0) for t in mh) / len(mh)
        avg_R = sum(t["R"] for t in mh) / len(mh)
        H.append("【MAXHOLD】触顶强平 n=%d: 平均MFE=%.2fR 但均值R=%.2fR (回吐%.2fR/单) —— 18h触顶可能过早截断趋势单, 建议评估延长持仓上限或仅对低ADX生效" %
                 (len(mh), avg_mfe, avg_R, avg_mfe - avg_R))
    # ADX 弱趋势亏损
    weak = [t for t in closed if (t.get("adx") or 0) < 25 and t["R"] < 0]
    if weak:
        H.append("【进场质量】ADX<25 亏损单 n=%d, 均值R=%.3f —— 弱趋势环境下亏损集中, 建议进场质量闸对低ADX加严(已SKIP类拦截%d次, 但仍有漏网)" %
                 (len(weak), sum(t["R"] for t in weak) / len(weak), skips.get("SKIP_RR_QUALITY", 0)))
    # 拦截最多的闸
    if skips:
        top = skips.most_common(1)[0]
        H.append("【进场漏斗】拦截最多=%s(%d次) —— 若该闸候选事后回测多为赢单, 则闸过严, 需WFO松弛(参考11-12 signal_gate_wfo结论)" %
                 (top[0], top[1]))
    # B0 亏损
    b0 = by_type.get("B0假突破失效", [])
    if b0:
        lr = sum(1 for t in b0 if t["R"] < 0) / len(b0)
        H.append("【B0假突破】n=%d 亏损率=%.0f%% —— 假突破截断模块的亏损主源, 建议复盘其结构失效判定阈值(持仓时长/双确认)是否可降误杀" %
                 (len(b0), lr * 100))
    if not H:
        H.append("当前各分群回吐/亏损分布均衡, 无明显单一优化靶点; 建议聚焦逐单MFE→R缺口最大的前N单做案例复盘。")
    return H


if __name__ == "__main__":
    main()
