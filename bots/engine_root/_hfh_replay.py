# -*- coding: utf-8 -*-
"""⑬ 黄飞日内节奏 三项同分母回放 (总调度令"深度研发加快出徒").
事件基: 黄飞 224 笔 XAUUSD (trades_剔除后.json). 四桶同分母对拍:
  ORIG   黄飞原始 224 笔净利 (基线, 真实发生)
  A_FAST ⑬-a 错单 5min 市价快砍 (浮亏单重算, 盈利单走原路径)
  B_HARD ⑬-b 盈利单 60min 强制平 (对比"赢单拿>1h")
  C_BE   ⑬-c 浮盈 0.5R 移 SL 到保本 (浮盈不回吐成净亏)
每桶扣 2×point 滑点 (SLIP/笔), 同分母公平. 价源=TMGM XAUUSD M1 (同源金, 近似 TradeMax).
选择效应复核: >1h 桶 top 笔贡献占比 + 剔除 top5 稳健性.
运行: C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe E:/GoldstrategyEngine/_hfh_replay.py
"""
import sys, os, json, datetime, bisect

ROOT = "E:/GoldstrategyEngine"
TRADES = r"E:\workbuddy\内容中心\交付\2026-10_黄飞账户15014338_深度解析\trades_剔除后.json"
M1 = os.path.join(ROOT, "data", "_hfh_xau_m1_cache.json")
OUT = os.path.join(ROOT, "data", "rd_verify_batch_hfh_intraday.json")
SLIP = 0.02   # 2 x point @ 0.01 手 XAUUSD (引擎惯用点差近似)
FAST_MIN = 5.0
HARD_MIN = 60.0
BE_R = 0.5

def load_m1():
    d = json.load(open(M1, "r", encoding="utf-8"))
    rows = d["rows"]
    times = [r[0] for r in rows]
    return rows, times, d["meta"]

def path_outcome(rows, times, t_open, direction, entry, sl, tp, R, cap_min):
    """在 [t_open, t_open+cap_min] 内逐 M1 回放, 返回 (outcome, px, minutes_held).
    outcome: 'SL'/'TP'/'0.5R'/'close'. 按价路径先后触发判定 (先到的算)."""
    i0 = bisect.bisect_left(times, t_open)
    t_cap = t_open + int(cap_min * 60)
    be_hit = False   # 先到 0.5R 置位 (C 桶用)
    out, px, held = "close", None, cap_min
    for j in range(i0, min(i0 + int(cap_min * 2), len(rows))):
        t, o, h, l, c, tv = rows[j]
        if t > t_cap:
            break
        held = (t - t_open) / 60.0
        if direction == "BUY":
            if sl and l <= sl:
                out, px = "SL", sl; break
            if tp and h >= tp:
                out, px = "TP", tp; break
            if not be_hit and R and c >= entry + BE_R * R:
                be_hit = True
        else:  # SELL
            if sl and h >= sl:
                out, px = "SL", sl; break
            if tp and l <= tp:
                out, px = "TP", tp; break
            if not be_hit and R and c <= entry - BE_R * R:
                be_hit = True
    if out == "close":
        # 取 cap 内最后一个 close
        last_c = None
        for j in range(i0, min(i0 + int(cap_min * 2), len(rows))):
            if rows[j][0] <= t_cap:
                last_c = rows[j][4]
        px = last_c if last_c is not None else entry
    return out, px, be_hit, held

def pnl(direction, entry, px):
    return (px - entry) if direction == "BUY" else (entry - px)

def main():
    m1cache = load_m1()
    rows, times, meta = m1cache
    trades = json.load(open(TRADES, "r", encoding="utf-8"))
    for t in trades:
        t["otime_dt"] = datetime.datetime.fromisoformat(t["otime_dt"])
        t["ctime_dt"] = datetime.datetime.fromisoformat(t["ctime_dt"])

    CAP_MIN = 75.0   # 回放窗口上限 (覆盖 >1h 桶)
    # 每笔预计算 4 桶
    per = []
    for t in trades:
        direction = t["type"].upper()
        entry = t["open"]
        sl = t["sl"] if t["sl"] else None
        tp = t["tp"] if t["tp"] else None
        R = abs(sl - entry) if sl else abs(tp - entry) if tp else None
        t_open = int(t["otime_dt"].timestamp())
        orig = t["profit"] - SLIP
        # A: 5min 快砍
        out, px, be, held = path_outcome(rows, times, t_open, direction, entry, sl, tp, R, FAST_MIN)
        if out == "SL":
            a_pnl = pnl(direction, entry, px) - SLIP
        else:
            # 5min 时点: 浮亏则砍在 5min 价, 否则走原路径 (用 ORIG 近似, 因 5min 后黄飞自己路径)
            c5 = px if out in ("TP", "close") else px
            # 简化: 若 5min 前已到 TP -> TP 盈亏; 否则若在 5min 价浮亏 -> 砍在 5min 价; 否则保持原 orig
            if out == "TP":
                a_pnl = pnl(direction, entry, px) - SLIP
            else:
                px5 = pnl(direction, entry, px)
                a_pnl = px5 - SLIP if px5 < 0 else (orig)  # 浮亏砍, 浮盈走原路径
        # B: 60min 硬砍盈利单
        out, px, be, held = path_outcome(rows, times, t_open, direction, entry, sl, tp, R, HARD_MIN)
        if out == "TP":
            b_pnl = pnl(direction, entry, px) - SLIP
        else:
            # 60min 时点强制平
            b_pnl = pnl(direction, entry, px) - SLIP
        # C: 0.5R 移保本
        out, px, be, held = path_outcome(rows, times, t_open, direction, entry, sl, tp, R, CAP_MIN)
        if be:
            # 到了 0.5R -> SL 移保本: 之后打保本=0, 打 TP=TP 盈亏
            if out == "TP":
                c_pnl = pnl(direction, entry, px) - SLIP
            else:
                c_pnl = 0.0 - SLIP   # 打保本收 0 (扣往返)
        else:
            # 没到 0.5R: 打原 SL = SL 盈亏, 打 TP / close 走原路径
            if out == "SL":
                c_pnl = pnl(direction, entry, px) - SLIP
            else:
                c_pnl = pnl(direction, entry, px) - SLIP
        per.append({
            "ticket": t["ticket"], "type": direction, "otime": t["otime_dt"].isoformat(),
            "dur_min": round(t["dur_min"], 1), "R_pts": R,
            "orig": round(orig, 2), "A": round(a_pnl, 2), "B": round(b_pnl, 2), "C": round(c_pnl, 2),
            "tail": t["dur_min"] >= 60, "win": t["profit"] > 0,
        })

    def bucket_stats(key):
        vals = [p[key] for p in per]
        n = len(vals); wins = sum(1 for v in vals if v > 0)
        gw = sum(v for v in vals if v > 0); gl = sum(v for v in vals if v < 0)
        # 最大回撤 (逐笔累加)
        run = 0; peak = 0; mdd = 0
        for v in vals:
            run += v
            peak = max(peak, run)
            mdd = max(mdd, peak - run)
        return {"n": n, "wins": wins, "wr": round(wins / n, 3),
                "net": round(sum(vals), 2), "pf": round(gw / abs(gl), 3) if gl else None,
                "mdd": round(mdd, 2)}

    stats = {k: bucket_stats(k) for k in ("orig", "A", "B", "C")}

    # 选择效应复核: >1h 桶
    tail = [p for p in per if p["tail"]]
    tail_net = sum(p["orig"] for p in tail)
    top5 = sorted(tail, key=lambda p: -p["orig"])[:5]
    top10 = sorted(tail, key=lambda p: -p["orig"])[:10]
    sel = {
        "tail_n": len(tail), "tail_net": round(tail_net, 2),
        "tail_share_of_total": round(tail_net / stats["orig"]["net"], 3),
        "top5_share_of_tail": round(sum(p["orig"] for p in top5) / tail_net, 3) if tail_net else None,
        "top10_share_of_tail": round(sum(p["orig"] for p in top10) / tail_net, 3) if tail_net else None,
        "top5_sells": sum(1 for p in top5 if p["type"] == "SELL"),
        "top5": [{"ticket": p["ticket"], "type": p["type"], "dur": p["dur_min"], "pnl": p["orig"]} for p in top5],
        # 剔除 top5 后的稳健性: B 桶是否仍贡献
        "tail_ex_top5_net": round(sum(p["orig"] for p in tail if p not in top5), 2),
    }

    out = {
        "generated": datetime.datetime.now().isoformat(),
        "by": "总调度 (黄飞15014338 ⑬日内节奏 同分母回放, 出徒加速)",
        "source_trades": "trades_剔除后.json (224笔, 已剔09-11两笔人工无止损单)",
        "price_source": "TMGM XAUUSD M1 " + str(meta.get("bars")) + " bars (同源金近似 TradeMax)",
        "slip_per_trade": SLIP,
        "params": {"fast_min": FAST_MIN, "hard_min": HARD_MIN, "be_r": BE_R},
        "buckets": stats,
        "selection_effect": sel,
        "per_trade": per,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("=== ⑬ 四桶同分母回放 (224笔, 扣2xpoint) ===")
    for k, label in [("orig", "ORIG原始"), ("A", "A 5min快砍"), ("B", "B 60min硬砍"), ("C", "C 0.5R移保本")]:
        s = stats[k]
        print(f"{label:12} 净利{s['net']:8.2f} 胜率{s['wr']*100:5.1f}% PF{s['pf']} MDD{s['mdd']}")
    print("=== 选择效应 (>1h桶) ===")
    print(f"  >1h桶 {sel['tail_n']}笔 净利{sel['tail_net']} 占全期{sel['tail_share_of_total']*100:.0f}%")
    print(f"  前5笔占该桶{sel['top5_share_of_tail']*100:.0f}% 前10占{sel['top10_share_of_tail']*100:.0f}% top5里{sel['top5_sells']}笔SELL")
    print(f"  剔除top5后 >1h桶余 {sel['tail_ex_top5_net']}")
    print("SAVED", OUT)
    return 0

if __name__ == "__main__":
    sys.exit(main())
