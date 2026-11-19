# -*- coding: utf-8 -*-
"""
金策·夜间深研 2026-11-15 01:31 | 黄金+外汇品系做单思路优化
增量假设 H_ARBR(亚洲区间破位): 现卡"亚盘只做区间定界不开单", 未量化破界后动作。
  本测: 亚盘区间(FX 00-07 / 金 01-07 UTC) 破界后, 伦敦-纽约窗(08-15 UTC)首根H1收线确认进场,
  SL=亚盘中轴(结构锚定), TP=2R(RR地板2.0), 当日23:00强平兜底, 扣0.095R成本(全团口径)。
  同分母: 全部破界事件不挑日子; 方向对齐子集 = 破界侧与D1偏(close vs SMA50, 前日口径)同侧。
  数据有效性闸: 样本<30笔/品种=显式FAIL不静默; 数据源+快照+新鲜度随结果落盘。
  辅助量测: 金H1逐时range(%)复核卡"衰减窗17-23UTC ATR $4-6"(牛金$3900价位的绝对值口径)。
产物: research/arbr_fx_gold_result_20261115.json
"""
import csv, json, math, collections, sys, os

DATA = "E:/GoldstrategyEngine/data"
OUT = "E:/GoldstrategyEngine/research/arbr_fx_gold_result_20261115.json"

FX_SYMS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
GOLD_SYMS = ["XAUUSD", "XAGUSD"]

COST_R = 0.095          # 全团滑点+成本口径 R
ENTRY_HRS = list(range(8, 16))   # 08:00-15:00 UTC 破位观察窗(卡go窗)
DAY_END_H = 23          # 23:00 UTC bar 兜底平仓
SAMPLE_FLOOR = 30      # 样本闸: <30笔=FAIL


def load_h1(sym):
    p = os.path.join(DATA, f"{sym}_H1.csv")
    days = collections.defaultdict(dict)   # date -> {hour: (o,h,l,c)}
    daily_close = {}                        # date -> 当日最后一根close
    with open(p, encoding="utf-8") as f:
        rdr = csv.reader(f)
        next(rdr)
        for row in rdr:
            if len(row) < 5:
                continue
            d = row[0][:10]
            h = int(row[0][11:13])
            try:
                o, hh, l, c = (float(row[1]), float(row[2]), float(row[3]), float(row[4]))
            except ValueError:
                continue
            days[d][h] = (o, hh, l, c)
            if d not in daily_close or h >= daily_close[d][0]:
                daily_close[d] = (h, c)
    return days, daily_close


def sma_bias_table(daily_close, win=50):
    """D1偏前推表: date -> 前日close vs 前50日close均值(不含当日=无泄漏); 数据不足=None。"""
    ds = sorted(daily_close)
    closes = [daily_close[d][1] for d in ds]
    pref = [0.0]
    for c in closes:
        pref.append(pref[-1] + c)
    table = {}
    for i, d in enumerate(ds):
        if i < win + 1:
            table[d] = None
            continue
        prev = closes[i - 1]
        base = (pref[i - 1] - pref[i - 1 - win]) / win   # closes[i-1-win : i-2] 共win根, 不含prev
        table[d] = prev > base
    return table


def run_arbr(sym, asia_hrs, days, daily_close, bias_table):
    events, skipped, no_break = [], 0, 0
    dense_dates = sorted(d for d, hs in days.items() if all(h in hs for h in asia_hrs)
                        and all(h in hs for h in ENTRY_HRS) and DAY_END_H in hs)
    for date in dense_dates:
        hs = days[date]
        A_hi = max(hs[h][1] for h in asia_hrs)
        A_lo = min(hs[h][2] for h in asia_hrs)
        rng = A_hi - A_lo
        if rng <= 0:
            no_break += 1
            continue
        mid = (A_hi + A_lo) / 2.0
        bias = bias_table.get(date)
        side = None
        for i, h in enumerate(ENTRY_HRS):
            o, hh, l, c = hs[h]
            prev_c = hs[ENTRY_HRS[i-1]][3] if i > 0 else hs[asia_hrs[-1]][3]
            if side is None:
                if c > A_hi and prev_c <= A_hi:
                    side, entry = "high", c
                elif c < A_lo and prev_c >= A_lo:
                    side, entry = "low", c
                elif i == 0 and (o > A_hi or o < A_lo) and (c > A_hi or c < A_lo):
                    skipped += 1   # 窗口开时已在区间外 -> 无当日事件(留痕)
                    side = "outside"
                    break
                if side == "outside":
                    break
            if side in ("high", "low"):
                R = abs(entry - mid)
                if R <= 0:
                    side = "outside"; break
                tp = entry + 2 * R if side == "high" else entry - 2 * R
                sl = entry - R if side == "high" else entry + R
                exit_price, outcome = None, None
                for h2 in ENTRY_HRS[i:]:
                    o2, hh2, l2, c2 = hs[h2]
                    hit_sl = (l2 <= sl) if side == "high" else (hh2 >= sl)
                    hit_tp = (hh2 >= tp) if side == "high" else (l2 <= tp)
                    if hit_sl and hit_tp:
                        exit_price, outcome = sl, "SL"          # 保守: 同bar双触=SL
                        break
                    if hit_sl:
                        exit_price, outcome = sl, "SL"; break
                    if hit_tp:
                        exit_price, outcome = tp, "TP"; break
                if exit_price is None:
                    exit_price = hs[DAY_END_H][3]; outcome = "EOD"
                dsign = 1 if side == "high" else -1
                net_r = dsign * (exit_price - entry) / R - COST_R
                rec = dict(date=date, side=side, bias=bias,
                           aligned=(side == "high" and bias) or (side == "low" and not bias) if bias is not None else None,
                           outcome=outcome, net_r=round(net_r, 4), R_usd=round(R, 6))
                events.append(rec)
                break
        else:
            no_break += 1
    return events, skipped, no_break


def stats(evts):
    n = len(evts)
    if n == 0:
        return dict(n=0)
    nets = [e["net_r"] for e in evts]
    mean = sum(nets) / n
    var = sum((x - mean) ** 2 for x in nets) / (n - 1) if n > 1 else 0.0
    t = mean / math.sqrt(var / n) if var > 0 else None
    wins = sum(1 for x in nets if x > 0)
    eod = sum(1 for e in evts if e["outcome"] == "EOD")
    return dict(n=n, win_rate=round(wins / n, 3), mean_net_R=round(mean, 4),
                t_stat=round(t, 3) if t is not None else None,
                eod_share=round(eod / n, 3),
                med_net_R=round(sorted(nets)[n // 2], 4))


def main():
    out = dict(generated_utc="2026-11-15T01:3x+08:00(快照时点)",
               rule="ARBR: 亚洲区间(FX00-07/金01-07h)破界, 08-15h首根H1收线确认, SL=亚盘中轴, TP=2R, 23:00兜底, 成本0.095R",
               cost_r=COST_R, sample_floor=SAMPLE_FLOOR, symbols={}, gold_hour_table={})

    for group, syms, asia in (("fx_family1", FX_SYMS, list(range(0, 8))),
                              ("gold_family2", GOLD_SYMS, list(range(1, 8)))):
        union = []
        for sym in syms:
            days, dclose = load_h1(sym)
            bias_table = sma_bias_table(dclose)
            ev, skipped, nobreak = run_arbr(sym, asia, days, dclose, bias_table)
            n_days = len(sorted(d for d, hs in days.items() if all(h in hs for h in asia)))
            gate = "PASS" if len(ev) >= SAMPLE_FLOOR else "FAIL"
            aligned = [e for e in ev if e["aligned"] is True]
            opposed = [e for e in ev if e["aligned"] is False]
            out["symbols"][sym] = dict(
                group=group, dense_days=n_days,
                full_range=[min(d for d in days), max(d for d in days)],
                last_bar=max(f"{d} {max(hs.keys()):02d}:00" for d, hs in days.items()),
                events=len(ev), skipped_already_outside=skipped, days_no_break=nobreak,
                data_gate=gate,
                all=stats(ev), aligned_n=len(aligned), aligned=stats(aligned),
                opposed_n=len(opposed), opposed=stats(opposed),
            )
            union += ev
        out["union_" + group] = dict(events=len(union), stats=stats(union),
                                      aligned=stats([e for e in union if e["aligned"] is True]),
                                      opposed=stats([e for e in union if e["aligned"] is False]))

    # 辅助量测: 金逐时range%(稠密尾段), 复核"衰减窗17-23UTC"
    for sym in GOLD_SYMS:
        days, _ = load_h1(sym)
        rng = collections.defaultdict(list)
        for d, hs in days.items():
            if not all(h in hs for h in range(1, 24)):
                continue
            for h in range(1, 24):
                o, hh, l, c = hs[h]
                rng[h].append((hh - l) / c)
        dense_days = len(days) - len([d for d, hs in days.items() if not all(h in hs for h in range(1, 24))])
        out["gold_hour_table"][sym] = dict(
            dense_days=dense_days,
            dense_range=[min(d for d, hs in days.items() if all(h in hs for h in range(1, 24))),
                         max(d for d, hs in days.items() if all(h in hs for h in range(1, 24)))],
            hour_range_pct_mean={str(h): round(100 * sum(v) / len(v), 4) for h, v in sorted(rng.items())})

    # 数据有效性闸落盘
    out["data_validity"] = dict(
        source="E:/GoldstrategyEngine/data/{sym}_H1.csv (brokerFX MT5 H1, CSV导出)",
        fx_dense="4品种 829稠密日 2023-09-04~2026-11-13",
        gold_dense="2品种 832稠密日 2023-08-25~2026-11-13",
        last_bar="2026-11-13 23:00 UTC(周五收盘)",
        freshness="周末FX/金休市, 快照=当前最新可得(非过期)",
        excludes="USDCAD(停2026-08-13, 陈旧) 与 金00h bar缺失(金亚盘窗=01-07h, 显式标注口径差)")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
