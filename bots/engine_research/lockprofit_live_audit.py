# -*- coding: utf-8 -*-
"""
第一波锁利·现场只读审计 (不改引擎 / 不改参数 / 零生产变更)
回答用户: 现在能不能锁住大浮盈? 再有单子有大利润, 这次能不能防止利润回吐?

数据源(全部为现役运行实例真实产物):
  data/live24_trades.csv   事件流 OPEN / SL_TRAIL / 终态出场
  data/mfe_mae_track.jsonl MT5 实读持仓快照, 含真实 mfe_R (最大有利偏移, R口径)

方法要点(修正旧复盘脚本 yesterday_profit_leak_analysis.py 的缺陷):
  1. 浮盈峰值取 mfe_mae_track 的 mfe_R (MT5实读), 不再用"落袋值当峰值"的自证代理;
  2. dist(1R) 一律取 OPEN 行的初始 SL, 不用 SL_TRAIL 行的目标SL / 终态行的SL;
  3. SL_TRAIL 的 rc 逐条统计, 识别券商拒单(10016)导致的锁利推进未落地;
  4. 以 10:39:51 (现役实例 PID 55768 启动, 已加载修复版) 为修复上线分界。
"""
import csv, json, os, re, collections, datetime as dt

ROOT = "E:/GoldstrategyEngine"
CSV = os.path.join(ROOT, "data", "live24_trades.csv")
MFE = os.path.join(ROOT, "data", "mfe_mae_track.jsonl")
OUT = os.path.join(ROOT, "research", "lockprofit_live_audit.csv")
CUT = "2026-11-11 10:39:51"
DAYS = ("2026-11-10", "2026-11-11")

TERMINAL = {"CLOSE", "B0_EXIT", "LOSECUT斩亏", "IDX_BLEED斩亏", "MAXHOLD硬平",
            "PINBAR_TOP", "PINBAR_BOTTOM", "MAGIC_DUP_EXIT"}


def num(x):
    try:
        return float(x)
    except Exception:
        return None


def cell(row, i):
    return row[i] if len(row) > i else ""


def parse_float_r(note):
    m = re.search(r"浮(盈|亏)([-+]?\d+\.?\d*)R", note or "")
    if not m:
        return None
    v = float(m.group(2))
    return v if m.group(1) == "盈" else -v


# ---------- 1. MT5 实读 MFE 峰值 ----------
mfe_peak = {}
mfe_last = {}
mfe_first_ts = {}
mfe_max_floa = {}
with open(MFE, encoding="utf-8") as f:
    for ln in f:
        ln = ln.strip()
        if not ln:
            continue
        try:
            j = json.loads(ln)
        except Exception:
            continue
        ts = j.get("scan_ts", "")
        if not ts.startswith(DAYS):
            continue
        for v in j.get("live", []):
            tk = str(v.get("ticket"))
            m = v.get("mfe_R")
            if isinstance(m, (int, float)):
                if tk not in mfe_peak or m > mfe_peak[tk]:
                    mfe_peak[tk] = m
                mfe_first_ts.setdefault(tk, ts)
            fl = v.get("floa_R")
            if isinstance(fl, (int, float)):
                if tk not in mfe_max_floa or fl > mfe_max_floa[tk]:
                    mfe_max_floa[tk] = fl
            mfe_last[tk] = (ts, fl, m)

# ---------- 2. 事件流按 ticket 聚合 ----------
by = collections.defaultdict(list)
with open(CSV, encoding="utf-8") as f:
    for row in csv.reader(f):
        if not row or not row[0].startswith(DAYS):
            continue
        tk = cell(row, 4).strip()
        if not tk.isdigit():
            continue
        by[tk].append(row)

recs = []
for tk, evs in by.items():
    evs.sort(key=lambda r: r[0])
    opens = [r for r in evs if r[1] == "OPEN"]
    terms = [r for r in evs if r[1] in TERMINAL]
    trails = [r for r in evs if r[1] == "SL_TRAIL"]
    if not opens:
        continue
    o = opens[0]
    entry = num(cell(o, 5))
    init_sl = num(cell(o, 6))
    try:
        direction = int(cell(o, 3))
    except Exception:
        continue
    if entry is None or init_sl is None or direction == 0:
        continue
    dist = abs(entry - init_sl)
    if dist <= 0:
        continue

    # 终态落袋 R (用 OPEN 的初始 SL 定义 1R)
    realized = None
    exit_type, exit_ts = "", ""
    if terms:
        t = terms[-1]
        exit_type, exit_ts = t[1], t[0]
        ex = num(cell(t, 8))
        if ex is not None:
            realized = ((ex - entry) / dist) if direction > 0 else ((entry - ex) / dist)

    # SL_TRAIL 轨迹: 目标SL换算成 R, 记录 rc
    tr_seq = []
    for r in trails:
        ns = num(cell(r, 6))
        note = cell(r, 11)
        rc = ""
        m = re.search(r"rc=(\d+)", note)
        if m:
            rc = m.group(1)
        tr_seq.append({
            "ts": r[0],
            "sl_R": ((ns - entry) / dist) if direction > 0 else ((entry - ns) / dist) if ns is not None else None,
            "float_R": parse_float_r(note),
            "tag": (note.split(" 浮盈")[0] if " 浮盈" in note else note)[:22],
            "rc": rc,
        })
    # 事件流中出现的最大浮盈 (含 SL_TRAIL note)
    ev_peak = max([x["float_R"] for x in tr_seq if x["float_R"] is not None] or [-9e9])
    mt5_peak = mfe_peak.get(tk)
    cands = [x for x in (mt5_peak, ev_peak if ev_peak > -8e8 else None, realized) if x is not None]
    peak = max(cands) if cands else None

    oks = [x for x in tr_seq if x["rc"] == "10009"]
    rejs = [x for x in tr_seq if x["rc"] == "10016"]
    best_ok = max([x["sl_R"] for x in oks if x["sl_R"] is not None] or [-9e9])

    recs.append({
        "ticket": tk, "sym": cell(o, 2), "dir": direction,
        "open_ts": o[0], "entry": entry, "init_sl": init_sl, "dist": dist,
        "exit_type": exit_type, "exit_ts": exit_ts, "realized": realized,
        "peak": peak, "mt5_peak": mt5_peak, "ev_peak": ev_peak if ev_peak > -8e8 else None,
        "n_trail": len(tr_seq), "n_ok": len(oks), "n_rej": len(rejs),
        "best_ok_sl_R": best_ok if best_ok > -8e8 else None,
        "last_floa": mfe_last.get(tk, (None, None, None))[1],
        "last_scan": mfe_last.get(tk, (None, None, None))[0],
        "tr_seq": tr_seq,
        "post_fix": o[0] >= CUT,
    })

# ---------- 3. 输出 ----------
print("=" * 92)
print("  第一波锁利 · 现场只读审计  |  数据 11-10 ~ 11-11  |  修复上线分界 %s" % CUT)
print("=" * 92)
print("  聚合到 OPEN 的单子: %d 笔   其中修复后开仓: %d 笔" %
      (len(recs), sum(1 for x in recs if x["post_fix"])))

big = [x for x in recs if x["peak"] is not None and x["peak"] >= 1.5]
print("\n【大浮盈单 (峰值 >= 1.5R)】共 %d 笔" % len(big))
print("  %-11s %-8s %-3s %-8s %-8s %-8s %-8s %-7s %-6s %s" %
      ("ticket", "品种", "向", "开仓", "峰值R", "落袋R", "回吐R", "锁利SL", "拒单", "出场"))
for x in sorted(big, key=lambda v: -v["peak"]):
    leak = (x["peak"] - x["realized"]) if x["realized"] is not None else None
    print("  %-11s %-8s %-3s %-8s %8.2f %8s %8s %8s %6d %s" %
          (x["ticket"], x["sym"], "多" if x["dir"] > 0 else "空", x["open_ts"][11:16],
           x["peak"],
           "%.2f" % x["realized"] if x["realized"] is not None else "持仓中",
           "%.2f" % leak if leak is not None else "-",
           "%.2fR" % x["best_ok_sl_R"] if x["best_ok_sl_R"] is not None else "无",
           x["n_rej"], x["exit_type"] or "未平"))

# 分修复前后
print("\n【修复前 vs 修复后】(仅统计已有峰值估计的单子)")
for label, grp in (("修复前(11-10及11-11 10:39前)", [x for x in recs if not x["post_fix"]]),
                   ("修复后(10:39:51起)", [x for x in recs if x["post_fix"]])):
    g = [x for x in grp if x["peak"] is not None]
    b = [x for x in g if x["peak"] >= 1.5]
    done = [x for x in b if x["realized"] is not None]
    print("  %-34s 单数=%3d 大浮盈=%2d 已平=%2d 峰值合计=%6.2fR 落袋合计=%6.2fR" %
          (label, len(g), len(b), len(done),
           sum(x["peak"] for x in done), sum(x["realized"] for x in done)))

# rc 统计
alltr = [t for x in recs for t in x["tr_seq"]]
print("\n【SL 推进 · 券商回执】共 %d 次" % len(alltr))
for rc, n in collections.Counter(t["rc"] or "无回执" for t in alltr).most_common():
    print("    rc=%-8s %3d 次" % (rc, n))
print("  10016 明细(券商拒单 = 该次锁利推进未落地):")
for t in alltr:
    if t["rc"] == "10016":
        print("    %s  浮盈%.2fR  tag=%-22s 目标SL=%.2fR" %
              (t["ts"], t["float_R"] or 0, t["tag"], t["sl_R"] if t["sl_R"] is not None else -9))

# 修复后大浮盈单的 SL 轨迹全展开
print("\n【修复后大浮盈单 · SL 逐次推进轨迹】")
for x in sorted([y for y in big if y["post_fix"]], key=lambda v: -v["peak"]):
    print("  ticket=%s %s %s 开仓%s dist=%.4f 峰值=%.2fR 落袋=%s" %
          (x["ticket"], x["sym"], "多" if x["dir"] > 0 else "空", x["open_ts"],
           x["dist"], x["peak"],
           "%.2fR" % x["realized"] if x["realized"] is not None else "持仓中"))
    for t in x["tr_seq"]:
        print("     %s  浮盈%6.2fR  -> SL %7.2fR  rc=%-6s %s" %
              (t["ts"], t["float_R"] if t["float_R"] is not None else -9,
               t["sl_R"] if t["sl_R"] is not None else -9, t["rc"] or "-", t["tag"]))
    if x["last_scan"]:
        print("     最后实读 %s  mfe=%.3fR  当前浮盈指标=%s" %
              (x["last_scan"], x["mt5_peak"] or 0, x["last_floa"]))

# CSV 明细
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["ticket", "symbol", "dir", "open_ts", "post_fix", "peak_R", "mt5_mfe_R",
                "realized_R", "leak_R", "exit_type", "n_trail", "n_rej", "best_ok_sl_R", "last_floa"])
    for x in sorted(recs, key=lambda v: -(v["peak"] or -9)):
        w.writerow([x["ticket"], x["sym"], x["dir"], x["open_ts"], x["post_fix"],
                    round(x["peak"], 3) if x["peak"] is not None else "",
                    x["mt5_peak"] if x["mt5_peak"] is not None else "",
                    round(x["realized"], 3) if x["realized"] is not None else "",
                    round(x["peak"] - x["realized"], 3) if (x["peak"] is not None and x["realized"] is not None) else "",
                    x["exit_type"], x["n_trail"], x["n_rej"],
                    round(x["best_ok_sl_R"], 3) if x["best_ok_sl_R"] is not None else "",
                    x["last_floa"]])
print("\n  明细已存: %s" % OUT)
print("  审计完毕 (只读, 未修改任何生产文件)")
