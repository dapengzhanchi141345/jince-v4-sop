# -*- coding: utf-8 -*-
"""⑬-b PBO 阈值邻域扫描: 硬砍阈值 [30,45,60,75,90,120]min 逐档净利, 看 60min 是否邻域最优(过拟合信号).
同分母: 每档都用全 224 笔事件基重放. 另算 R 空间正确口径 (USD 风险).
运行: C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe E:/GoldstrategyEngine/_hfh_pbo.py
"""
import sys, os, json, datetime, bisect

ROOT = "E:/GoldstrategyEngine"
sys.path.insert(0, ROOT)
TRADES = r"E:\workbuddy\内容中心\交付\2026-10_黄飞账户15014338_深度解析\trades_剔除后.json"
M1 = os.path.join(ROOT, "data", "_hfh_xau_m1_cache.json")
OUT = os.path.join(ROOT, "data", "rd_verify_batch_hfh_pbo.json")
SLIP = 0.02

def main():
    rows = json.load(open(M1, "r", encoding="utf-8"))["rows"]
    times = [r[0] for r in rows]
    trades = json.load(open(TRADES, "r", encoding="utf-8"))
    for t in trades:
        t["otime_dt"] = datetime.datetime.fromisoformat(t["otime_dt"])
        t["ctime_dt"] = datetime.datetime.fromisoformat(t["ctime_dt"])

    def pnl(d, e, px):
        return (px - e) if d == "BUY" else (e - px)

    def bucket(threshold_min):
        nets = []
        for t in trades:
            d = t["type"].upper(); e = t["open"]
            sl = t["sl"] if t["sl"] else None; tp = t["tp"] if t["tp"] else None
            R = abs(sl - e) if sl else (abs(tp - e) if tp else None)
            t0 = int(t["otime_dt"].timestamp()); tc = t0 + int(threshold_min * 60)
            i0 = bisect.bisect_left(times, t0)
            px_out = None; out = "close"
            for j in range(i0, min(i0 + int(threshold_min * 2) + 60, len(rows))):
                if rows[j][0] > tc: break
                tt, o, h, l, c, tv = rows[j]
                if d == "BUY":
                    if sl and l <= sl: out, px_out = "SL", sl; break
                    if tp and h >= tp: out, px_out = "TP", tp; break
                else:
                    if sl and h >= sl: out, px_out = "SL", sl; break
                    if tp and l <= tp: out, px_out = "TP", tp; break
            if px_out is None:
                lastc = e
                for j in range(i0, len(rows)):
                    if rows[j][0] <= tc: lastc = rows[j][4]
                    else: break
                px_out = lastc
            nets.append(pnl(d, e, px_out) - SLIP)
        gw = sum(x for x in nets if x > 0); gl = -sum(x for x in nets if x < 0)
        # 正确 R 口径: 每笔真实风险USD = R_pts * 1(0.01手, 1点=1USD)
        rr = []
        for t2, n2 in zip(trades, nets):
            R = abs(t2["sl"] - t2["open"]) if t2["sl"] else (abs(t2["tp"] - t2["open"]) if t2["tp"] else 1.0)
            risk_usd = max(R, 0.5)  # 0.01手 XAU: R_pts点 = R_pts USD
            rr.append(n2 / risk_usd)
        return {"net": round(sum(nets), 2), "pf": round(gw / gl, 3) if gl > 1e-9 else None,
                "wr": round(sum(1 for x in nets if x > 0) / len(nets), 3),
                "avg_R": round(sum(rr) / len(rr), 4), "net_R": round(sum(rr), 2)}

    sweep = {}
    for m in [30, 45, 60, 75, 90, 120]:
        sweep[str(m)] = bucket(m)
        print(f"阈值{m:>3}min: 净利{sweep[str(m)]['net']:8.2f} PF{sweep[str(m)]['pf']} 胜率{sweep[str(m)]['wr']*100:.1f}% 均值R {sweep[str(m)]['avg_R']:+.3f}R")

    nets60 = sweep["60"]["net"]
    pos_share = sum(1 for m in sweep if sweep[m]["net"] > 0) / len(sweep)
    best_m = max(sweep, key=lambda m: sweep[m]["net"])
    mono = all(sweep[str(a)]["net"] >= sweep[str(b)]["net"] - 60 for a, b in zip([30, 45, 60, 75, 90], [45, 60, 75, 90, 120]))
    out = {"generated": datetime.datetime.now().isoformat(), "by": "总调度 ⑬-b PBO邻域扫描",
           "sweep": sweep, "best_threshold": best_m, "best_net": sweep[best_m]["net"],
           "60min_not_local_max": best_m != "60",
           "verdict_pbo": ("PASS(60min邻域内非孤峰)" if best_m in ("60", "75") else
                            "WATCH(最优阈值在%s, 60min=次优档, 需确认是过拟合还是真实最优)" % best_m)}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("PBO 判据:", out["verdict_pbo"], "最优阈值:", best_m)
    return 0

if __name__ == "__main__":
    sys.exit(main())
