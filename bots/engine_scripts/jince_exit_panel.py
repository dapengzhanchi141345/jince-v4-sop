# -*- coding: utf-8 -*-
"""金策离场面板 (L3 确定性, 0 LLM)
输入: data/mfe_mae_track.jsonl (30min 扫描, 持仓 mfe_R/mae_R/floa_R)
输出: data/exit_panel.json (逐族 MFE/MAE/离场效率 + 自动裁定)
裁定: 族样本>=30 且 中位效率<60% → 离场修复课题(只否决/降档, 不放大)
数据口径: 首版用开仓窗扫描; 异常R值(|R|>50)标记剔除并计数; rd 接入 MT5 历史deals导出后切全量
用法: 30min 巡检循环跑一次, 面板即真源
"""
import json, os, statistics, datetime

ROOT = r"E:\GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
ANOMALY_CAP = 50.0  # |R|>50 视为数据异常, 剔除

CRYPTO = {"BTCUSD", "ETHUSD", "SOLUSD", "DOGEUSD", "LTCUSD", "XLMUSD", "XRPUSD", "ADAUSD", "AVAXUSD", "DOTUSD", "LINKUSD"}
GOLD = {"XAUUSD", "XPTUSD", "XAGUSD"}
INDEX = {"US30", "US20", "US200", "US2000", "US500", "NDX", "SPX", "CHCUSD", "NASDAQ", "DAX", "FTSE", "N225", "HK50", "A50"}

def family(sym):
    s = (sym or "").upper()
    if s in CRYPTO:
        return "币系族"
    if s.endswith("JPY"):
        return "JPY族"
    if s in GOLD:
        return "金银族"
    if s in INDEX or ".HK" in s or s[:2].isdigit():
        return "股指股类族"
    return "外汇货币对族"

tickets = {}
n_scans = 0
anom = 0
src = os.path.join(DATA, "mfe_mae_track.jsonl")
if os.path.exists(src):
    for line in open(src, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        n_scans += 1
        for t in rec.get("live", []):
            tk = t.get("ticket")
            if tk is None:
                continue
            mfe = t.get("mfe_R", 0.0) or 0.0
            mae = t.get("mae_R", 0.0) or 0.0
            fl = t.get("floa_R", 0.0) or 0.0
            if abs(mfe) > ANOMALY_CAP or abs(mae) > ANOMALY_CAP or abs(fl) > ANOMALY_CAP:
                anom += 1
                mfe = 0.0 if abs(mfe) > ANOMALY_CAP else mfe
                mae = 0.0 if abs(mae) > ANOMALY_CAP else mae
                fl = 0.0 if abs(fl) > ANOMALY_CAP else fl
            d = tickets.get(tk)
            if d is None:
                tickets[tk] = {"symbol": t.get("symbol"), "side": t.get("side"),
                                "mfe": mfe, "mae": mae, "floa": fl, "n": 1,
                                "first": rec.get("scan_ts"), "last": rec.get("scan_ts")}
            else:
                d["mfe"] = max(d["mfe"], mfe)
                d["mae"] = min(d["mae"], mae)
                d["floa"] = fl
                d["n"] += 1
                d["last"] = rec.get("scan_ts")

fam = {}
for tk, d in tickets.items():
    fam.setdefault(family(d["symbol"]), []).append(d)

out = {"ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
       "n_scans": n_scans, "n_tickets": len(tickets), "n_anomaly_samples": anom,
       "data_note": "首版=开仓窗扫描(mfe_mae_track.jsonl), 异常R(>50)已剔除; 全量需rd接MT5历史deals导出后切换",
       "families": {}, "verdicts": []}
for f, arr in sorted(fam.items()):
    mfe_s = [x["mfe"] for x in arr if x["mfe"] > 0]
    mae_s = [x["mae"] for x in arr]
    effs = [min(1.0, x["floa"] / x["mfe"]) for x in arr if x["mfe"] >= 0.5 and x["floa"] > 0]
    p90abs, minmae = None, None
    if mae_s:
        abss = sorted(abs(m) for m in mae_s)
        p90abs = abss[min(len(abss) - 1, int(len(abss) * 0.9))]
        minmae = min(mae_s)
    rec = {"n_tickets": len(arr),
           "symbols": sorted({x["symbol"] for x in arr}),
           "n_mfe_pos": len(mfe_s),
           "median_mfe_R": round(statistics.median(mfe_s), 2) if mfe_s else None,
           "p90_abs_mae_R": round(p90abs, 2) if p90abs is not None else None,
           "min_mae_R": round(minmae, 2) if minmae is not None else None,
           "n_eff_samples": len(effs),
           "median_eff": round(statistics.median(effs), 2) if effs else None}
    out["families"][f] = rec
    if len(effs) >= 30 and effs and statistics.median(effs) < 0.60:
        out["verdicts"].append({"family": f,
                                "reason": "中位离场效率 %.0f%%<60%%, 样本%d" % (statistics.median(effs) * 100, len(effs)),
                                "action": "离场修复课题: 该族SL/TP锚调整(只否决/降档, 不放大)",
                                "rd_item": "exit_repair_%s_%s" % (f, datetime.date.today().isoformat())})

dst = os.path.join(DATA, "exit_panel.json")
json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("面板已验活: %s" % dst)
print("扫描%d / 票%d / 族%d / 异常样本%d" % (n_scans, len(tickets), len(fam), anom))
for f, r in out["families"].items():
    print("  %-8s n=%-3d medMFE=%s p90|MAE|=%s minMAE=%s eff=%s(n=%d)" % (
        f, r["n_tickets"], r["median_mfe_R"], r["p90_abs_mae_R"], r["min_mae_R"], r["median_eff"], r["n_eff_samples"]))
for v in out["verdicts"]:
    print("  裁定:", v["family"], v["reason"])
if not out["verdicts"]:
    print("  裁定: 无(样本不足或效率达标, 前向积累, 面板每30min自动刷新)")
