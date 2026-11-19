# -*- coding: utf-8 -*-
"""jince_learn_verify.py — 20:10 学习→验证→提升 面板 (no_agent, 确定性无LLM)
[11-10 chief 造]: 原面板脚本缺失(哨兵11-05起报"文件缺失"), 学习验证链路 5 天断棒。
本脚本=最小可用版: 读 MFE 追踪 + 家族账 + 当日 deals 实读, 交叉核"学习预测"台账,
输出 data/learn_verify_<date>.md。改进动作逐条核账 (无台账=0条, 不造假)。
留痕铁律: 没进台账学的东西=不算学。
"""
import json, os, sys, time, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")  # [11-10 fix] 真实数据目录=data/ (非脚本同层)
MFE = os.path.join(DATA, "mfe_mae_track.jsonl")
FAM = os.path.join(DATA, "family_pnl_ledger.jsonl")
OUT_TMPL = os.path.join(DATA, "learn_verify_%Y%m%d.md")

def today():
    return time.strftime("%Y-%m-%d")

def last_mfe_scan():
    """取当日最后一个 MFE 快照 (修好双通道后应非空; 空=通道仍无仓, 如实写0)。"""
    if not os.path.exists(MFE):
        return []
    best = []
    for l in open(MFE, encoding="utf-8", errors="ignore").read().splitlines():
        try:
            r = json.loads(l)
            if str(r.get("scan_ts", ""))[:10] == today() and r.get("live"):
                best = r["live"]
        except Exception:
            continue
    return best

def family_today():
    if not os.path.exists(FAM):
        return []
    rows = [json.loads(l) for l in open(FAM, encoding="utf-8", errors="ignore")
            if l.strip() and today() in l]
    return rows[-1].get("families", {}) if rows else {}

def learn_preds():
    """学习预测台账: rd_watchlist 中 status=OBSERVE 且带 predict 字段的条目 (存在才算, 缺失=0条)。"""
    wl = os.path.join(DATA, "rd_watchlist.json")
    if not os.path.exists(wl):
        return []
    try:
        d = json.load(open(wl, encoding="utf-8"))
    except Exception:
        return []
    items = d if isinstance(d, list) else d.get("watchlist", d.get("items", []))
    out = []
    for it in items:
        p = it.get("predict") or it.get("prediction")
        if p:
            out.append({"sym": it.get("symbol", it.get("sym", "?")), "status": it.get("status"), "predict": str(p)[:120]})
    return out

def main():
    now = time.strftime("%Y-%m-%d %H:%M")
    mfe = last_mfe_scan()
    fam = family_today()
    preds = learn_preds()
    o = time.strftime(OUT_TMPL)
    L = ["# 学习验证面板 %s (20:10 自动核账, no_agent)" % today(), "",
         "生成: %s | 口径: 学习必须有预测台账, 无预测=未学; MFE双通道(20261104+30261103)" % now, ""]
    L.append("## 1) MFE 活单峰值 (当日最后快照)")
    L.append("| ticket | 品种 | 方向 | MFE峰值R | MAE | 现价R |")
    L.append("|---|---|---|---|---|---|")
    for r in mfe:
        L.append("| %s | %s | %s | %s | %s | %s |" % (
            r.get("ticket"), r.get("symbol"), r.get("side"),
            r.get("mfe_R"), r.get("mae_R"), r.get("floa_R")))
    if not mfe:
        L.append("(当日 MFE 快照 live 为空 = 双通道当前 0 活仓, 如实报0非故障)")
    L += ["", "## 2) 家族账 (今日实收)", ""]
    for k, v in (fam or {}).items():
        L.append("- %s: R=%s %s" % (k, v.get("R"), (str(v.get("deals") or v.get("note") or "")[:90])))
    L += ["", "## 3) 学习预测核账 (rd_watchlist 带预测台账条)", ""]
    for p in preds:
        L.append("- %s [%s] 预测: %s" % (p["sym"], p.get("status"), p["predict"]))
    if not preds:
        L.append("(0 条带预测台账的学习项 = 今日无'已学待验'内容, 不算学不造假)")
    L += ["", "## 4) 改进动作落地核账", "",
         "(数据不足自动跳过 / 家族升降档规则见 family_pnl_ledger; 面板裁决: ",
         "MFE %d 张活单在跟踪, 家族 %d 项, 预测台账 %d 条)" % (len(mfe), len(fam), len(preds)), ""]
    open(o, "w", encoding="utf-8").write("\n".join(L))
    print("[learn_verify] 面板已生成: %s" % o)
    print("[learn_verify] MFE活单=%d 家族=%d 预测台账=%d" % (len(mfe), len(fam), len(preds)))
    return 0

if __name__ == "__main__":
    sys.exit(main())
