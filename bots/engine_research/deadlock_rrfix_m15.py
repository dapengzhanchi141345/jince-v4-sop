# -*- coding: utf-8 -*-
"""
死锁修复候选五验 · 高流动性品种 M15/H1 同分母回测 (纯研究 · 不改 live)
========================================================================
背景(2026-11-12): 黄金"很久没交易"根因 = DEMO 分支 _struct_sl_tp 结构 SL 取"更靠外"(60根摆动),
黄金 60 根 M15 支撑常 >6×ATR -> 2R 地板在 12ATR 封顶下不可达 -> R:R 质量闸(1.95)必拒
(live24_trades.csv: 11-10 起 SKIP_RR_QUALITY 1900+ 连拒, XAUUSD 22:45 仍在拒)。

候选:
  BASE  = 现役 DEMO 行为(结构加宽 + 12ATR 封顶 + 2R 地板), 闸拒 setup 记 0 成交
  FIX_B = 保 R:R 优先地板: 当 2×dSL > 12ATR (即 dSL > 6ATR) 时, SL 收窄到 6ATR,
          TP = 12ATR, 保持 R:R = 2.0 (workbuddy 黄金解锁议案候选 B)
  另 ×  ADX 上限 ∈ {None=现役, 40}  两档(实盘 ADX≥40 簇 100% 亏, 反事实净R翻正)

口径(同分母铁律):
  * 进场种群 = gate_replica.gen_entries_gated (实盘 6 闸逐行复刻, 自检 PASS, 常量对平 PASS)
    + 引擎 SKIP_H1 复刻(M15 品种: H1 MA5/MA20 方向不符则跳)
  * 每品种用其 native entry TF (XAU/BTC M15, EUR/GBP/ETH H1, 数据 = 11-12 已换入的 UTC 口径新 CSV)
  * 出场 = 48 根 MAXHOLD (同引擎), SL 优先于 TP 同根保守, 滑点 0.095R/笔
  * 五验: ①净R ②胜率 ③5折时间切分全段同向(≥4/5 为正 vs BASE) ④OOS 70/30 ⑤成本 0.05/0.10 压力

输出: research/deadlock_rrfix_m15_result.json + 本报告 stdout
绝不改 jince_live24.py / 参数 / 账户。
"""
import csv, json, os, sys, datetime

ROOT = "E:/GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
STAGE = "E:/workbuddy/workbuddygongzuoqu/2026-11-12-18-43-15/深度优化_v2/01_WFO种群一致性T0门禁"
sys.path.insert(0, STAGE)
from gate_replica import gen_entries_gated, ADX_MIN  # noqa: E402

# 品种 -> (数据文件 TF, 是否 M15 需 H1 方向闸)
SYMS = {
    "XAUUSD": ("M15", True), "BTCUSD": ("M15", True),
    "EURUSD": ("H1", False), "GBPUSD": ("H1", False), "ETHUSD": ("H1", False),
    "XAGUSD": ("H1", False),
}
MAX_BARS = 48          # 引擎 MAXHOLD
COST_R = 0.095         # 滑点 0.095R/笔 (五验族统一口径)
ADX_MAX_LIST = [None, 40.0]
VARIANTS = ["BASE", "FIX_B", "FIX_D"]


def load_sym(sym):
    tf, need_h1 = SYMS[sym]
    times, bars = [], []
    with open(os.path.join(DATA, "%s_%s.csv" % (sym, tf)), encoding="utf-8") as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            if len(row) < 5:
                continue
            try:
                times.append(row[0])
                bars.append([float(row[1]), float(row[2]), float(row[3]), float(row[4])])
            except Exception:
                times.pop()
                bars.pop()
    h1 = None
    if need_h1:
        rows1 = []
        with open(os.path.join(DATA, "%s_H1.csv" % sym), encoding="utf-8") as f:
            r = csv.reader(f)
            next(r, None)
            for row in r:
                if len(row) < 5:
                    continue
                try:
                    rows1.append([row[0], float(row[1]), float(row[2]), float(row[3]), float(row[4])])
                except Exception:
                    continue
        h1 = rows1  # [time,o,h,l,c]
    return times, bars, h1


def dx_arr(bars):
    """复刻 entry_quality_wfo.dx_arr (简化 DI 差(14)), bars[i]=[o,h,l,c] —— 与引擎 mismatch=0 已验。"""
    n = len(bars)
    dx = [0.0] * n
    for i in range(14, n):
        plus = minus = 0.0
        for j in range(i - 13, i + 1):
            up = bars[j][1] - bars[j - 1][1]
            dn = bars[j - 1][2] - bars[j][2]
            if up > dn and up > 0:
                plus += up
            elif dn > up and dn > 0:
                minus += dn
        d = plus + minus
        dx[i] = abs(plus - minus) / d * 100.0 if d > 0 else 0.0
    return dx


def atr_at(bars, i):
    n = 14
    if i < n:
        return 0.0
    trs = []
    for j in range(i - n + 1, i + 1):
        pc = bars[j - 1][3]
        trs.append(max(bars[j][1] - bars[j][2], abs(bars[j][1] - pc), abs(bars[j][2] - pc)))
    return sum(trs) / n


def struct_sl_tp(sym, entry, sig, h, l, a, ps, variant):
    """逐行复刻 jince_live24._struct_sl_tp(DEMO 分支) + _sl_tp_finish, 带变体开关。"""
    sgn = 1 if sig > 0 else -1
    sl_mult = ps.get("sl_mult", 3.5)
    tp_mult = ps.get("tp_mult", 8.0)
    atr_sl = entry - sgn * min(sl_mult, 1.2) * a          # 候选A封顶(已进引擎)
    atr_tp = entry + sgn * tp_mult * a
    sh = max(h[-60:])
    sl_ = min(l[-60:])
    buf = a * 0.3
    if variant != "FIX_D":
        if sig > 0:
            new_sl = min(atr_sl, sl_ - buf)
            new_tp = max(atr_tp, sh + buf)
        else:
            new_sl = max(atr_sl, sh + buf)
            new_tp = min(atr_tp, sl_ - buf)
    else:
        # FIX_D: ATR 基准点位(REAL 分支逻辑, 金银族候选) —— 不做结构加宽,
        # SL=min(sl_mult,1.2)a, TP=tp_mult a (随后统一走 2R 地板/12ATR 封顶)
        new_sl = atr_sl
        new_tp = atr_tp
    tp_cap = entry + sgn * 12.0 * a
    new_tp = min(new_tp, tp_cap) if sig > 0 else max(new_tp, tp_cap)
    # _sl_tp_finish: R:R 地板(12ATR 封顶)
    dSL = abs(entry - new_sl)
    dTP = abs(entry - new_tp)
    need = min(2.0 * dSL, 12.0 * a) if a > 0 else dSL
    if a > 0 and dTP < need:
        new_tp = entry + sgn * need
    if variant == "FIX_B" and a > 0:
        # 保 R:R 优先: SL 太宽(>6ATR)时收窄到 6ATR, TP=12ATR, RR 恒 2.0
        if dSL > 6.0 * a:
            new_sl = entry - sgn * 6.0 * a
            new_tp = entry + sgn * 12.0 * a
    return new_sl, new_tp


def h1_dir_at(sym, h1, t_iso, need_h1, sig):
    """引擎 SKIP_H1 复刻: M15 品种上 H1 MA5/MA20 方向非 0 且与信号反向 -> 跳。
    近似: 取 t_iso 时刻前已收线的 H1 bar(不含正在收的那根), 用其 closes 算 MA。"""
    if not need_h1 or h1 is None:
        return 0
    # H1 bar time = 该小时起点; M15 bar time t 所属小时 = t[:13]; 已收线 = < 当前小时
    cur_h = t_iso[:13]
    closes = [b[4] for b in h1 if b[0][:13] < cur_h]
    if len(closes) < 20:
        return 0
    m5, m20 = sum(closes[-5:]) / 5.0, sum(closes[-20:]) / 20.0
    d = 1 if m5 > m20 else (-1 if m5 < m20 else 0)
    return -1 if (d != 0 and sig != d) else 0


def simulate(bars, i, sig, sl, tp, cost=COST_R):
    """从 i+1 起走 MAX_BARS 根; SL 优先; 返回 R(净, 扣滑点) 与 exit_kind。bars[i]=[o,h,l,c]。"""
    dSL = abs(bars[i][3] - sl)
    if dSL <= 0:
        return 0.0, "badsl"
    entry = bars[i][3]
    for j in range(i + 1, min(i + 1 + MAX_BARS, len(bars))):
        lo, hi = bars[j][2], bars[j][1]
        if sig > 0:
            if lo <= sl:
                return (sl - entry) / dSL - cost, "sl"
            if hi >= tp:
                return (tp - entry) / dSL - cost, "tp"
        else:
            if hi >= sl:
                return (entry - sl) / dSL - cost, "sl"
            if lo <= tp:
                return (entry - tp) / dSL - cost, "tp"
    # MAXHOLD 市价平(收线)
    ex = bars[min(i + MAX_BARS, len(bars) - 1)][3]
    r = (ex - entry) / dSL if sig > 0 else (entry - ex) / dSL
    return r - cost, "maxhold"


def run_sym(sym, ps):
    times, bars, h1 = load_sym(sym)
    dx = dx_arr(bars)
    res = {"sym": sym, "n_bars": len(bars), "tf": SYMS[sym][0], "per_adx": {}}
    fold_k = 5
    for adx_max in ADX_MAX_LIST:
        ents = gen_entries_gated(bars, dx, adx_min=ADX_MIN, adx_max=adx_max,
                                 max_bars=MAX_BARS, demo=True)
        # 引擎 SKIP_H1 复刻过滤(M15 品种)
        ents = [(i, s) for (i, s) in ents if h1_dir_at(sym, h1, times[i], SYMS[sym][1], s) == 0]
        key = "adx_max=%s" % ("None" if adx_max is None else int(adx_max))
        out = {"n_entries": len(ents), "variants": {}}
        for v in VARIANTS:
            rs, kinds = [], []
            for (i, s) in ents:
                a = atr_at(bars, i)
                if a <= 0:
                    continue
                entry = bars[i][3]
                w0 = max(0, i - 59)
                hh = [b[1] for b in bars[w0:i + 1]]
                ll = [b[2] for b in bars[w0:i + 1]]
                sl, tp = struct_sl_tp(sym, entry, s, hh, ll, a, ps, v)
                if v == "BASE":
                    rr = abs(tp - entry) / abs(sl - entry) if abs(sl - entry) > 0 else 0.0
                    if rr < 1.95:
                        rs.append(0.0)
                        kinds.append("gate_reject")
                        continue
                r, k = simulate(bars, i, s, sl, tp)
                rs.append(r)
                kinds.append(k)
            m = len(rs)
            pos_folds = 0
            fold_res = []
            for f_ in range(fold_k):
                seg = rs[f_ * m // fold_k:(f_ + 1) * m // fold_k] if m else []
                ssum = sum(seg)
                fold_res.append(round(ssum, 2))
                if ssum > 0:
                    pos_folds += 1
            oos_cut = int(m * 0.7)
            net = sum(rs)
            out["variants"][v] = {
                "n": m,
                "n_gated_reject": kinds.count("gate_reject"),
                "n_tp": kinds.count("tp"), "n_sl": kinds.count("sl"),
                "n_maxhold": kinds.count("maxhold"),
                "net_R": round(net, 2),
                "mean_R": round(net / m, 4) if m else 0.0,
                "win_rate": round(100.0 * sum(1 for x in rs if x > 0) / m, 1) if m else 0.0,
                "oos70_net_R": round(sum(rs[oos_cut:]), 2),
                "oos70_mean_R": round(sum(rs[oos_cut:]) / max(1, m - oos_cut), 4) if m > oos_cut else 0.0,
                "folds": fold_res, "folds_pos": pos_folds,
            }
        res["per_adx"][key] = out
    return res


def main():
    ps_all = json.load(open(os.path.join(DATA, "fresh", "practice_params_all_symbols.json"), encoding="utf-8"))
    allres = []
    for sym in SYMS:
        allres.append(run_sym(sym, ps_all.get(sym, {})))
    rep = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "cost_R": COST_R, "max_bars": MAX_BARS,
        "note": "同分母: 同 entry 种群(gate_replica 6 闸+SKIP_H1 复刻) × 两变体; BASE 闸拒记 0 成交; 滑点 0.095R; 数据=11-12 UTC 口径新 CSV",
        "results": allres,
    }
    out = os.path.join(ROOT, "research", "deadlock_rrfix_m15_result.json")
    json.dump(rep, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("== 死锁修复五验 · 结果摘要 ==")
    for r in allres:
        for k, v in r["per_adx"].items():
            for vn, x in v["variants"].items():
                print("%-7s %-12s %-7s n=%-5d 拒%d | 净R=%+8.2f 均R=%+7.4f 胜率=%5.1f%% OOS70=%+8.2f 5折=%s(%d/5正)" % (
                    r["sym"], k, vn, x["n"], x["n_gated_reject"], x["net_R"], x["mean_R"],
                    x["win_rate"], x["oos70_net_R"], str(x["folds"]), x["folds_pos"]))
    print("已落盘:", out)


if __name__ == "__main__":
    main()
